#!/usr/bin/env python3
"""
Downloader for PCIJ contractor documents.

The page at https://pcij.org/2025/08/30/flood-control-records/ lists Articles of
Incorporation and General Information Sheets for dozens of DPWH flood-control
contractors. This script scrapes that index and downloads each document into a
structured on-disk cache for offline analysis.

Usage:
    python scripts/download_pcij_contractor_documents.py \
        --output-dir data/pcij/flood-control-records

Key behaviours:
  * Groups downloads per contractor (one directory per contractor slug).
  * Supports dry-run mode to preview work without fetching files.
  * Skips files that already exist unless --overwrite is provided.
  * Emits a JSONL manifest listing every attempted download.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, NavigableString, Tag


DEFAULT_PAGE_URL = "https://pcij.org/2025/08/30/flood-control-records/"
DEFAULT_OUTPUT_DIR = Path("data/pcij/flood-control-records")
MANIFEST_FILENAME = "manifest.jsonl"

DOC_LABEL_MAP: Dict[str, str] = {
    "articles of incorporation": "articles-of-incorporation",
    "general information sheet": "general-information-sheet",
}

CONTRACTOR_TEXT_EXCLUSIONS: Sequence[str] = (
    "articles of incorporation",
    "general information sheet",
    "click to share",
    "share this",
    "linked in",
    "facebook",
    "twitter",
    "instagram",
    "refresh this page",
    "document:",
    "records of flood-control contractors",
)


@dataclass(frozen=True)
class DocumentLink:
    contractor_name: str
    contractor_slug: str
    document_type: str
    label: str
    url: str


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def slugify(value: str) -> str:
    lowered = value.lower()
    cleaned = re.sub(r"[^a-z0-9]+", "-", lowered)
    slug = cleaned.strip("-")
    return slug or "unknown"


def looks_like_contractor(raw_text: str) -> bool:
    text = " ".join(raw_text.strip().split())
    if not text:
        return False

    lowered = text.lower()
    if any(exclusion in lowered for exclusion in CONTRACTOR_TEXT_EXCLUSIONS):
        return False
    if ":" in text:
        return False

    alpha_chars = sum(1 for char in text if char.isalpha())
    if alpha_chars == 0:
        return False
    uppercase_chars = sum(1 for char in text if char.isalpha() and char.isupper())
    if uppercase_chars / alpha_chars < 0.6:
        return False

    allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,&'()/-")
    if not all(char.upper() in allowed for char in text):
        return False

    # Names on the PCIJ page are all-caps and typically include Inc./Corp./Contractor.
    if len(text) < 4 or len(text.split()) > 12:
        return False

    return True


def iter_document_links(page_html: str, page_url: str) -> Iterable[DocumentLink]:
    soup = BeautifulSoup(page_html, "html.parser")
    current_contractor: Optional[str] = None
    seen_pairs: Set[Tuple[str, str]] = set()

    for node in soup.descendants:
        if isinstance(node, NavigableString):
            text = str(node).strip()
            if looks_like_contractor(text):
                current_contractor = text
            continue

        if not isinstance(node, Tag):
            continue

        if node.name != "a":
            continue

        label = node.get_text(strip=True)
        normalized_label = label.lower()
        if normalized_label not in DOC_LABEL_MAP:
            continue

        if not current_contractor:
            logging.warning("Encountered %s without a contractor heading", label)
            contractor_name = "UNKNOWN CONTRACTOR"
        else:
            contractor_name = current_contractor

        document_type = DOC_LABEL_MAP[normalized_label]
        normalized_url = node.get("href", "").strip()
        if not normalized_url or normalized_url == "#":
            logging.info("Skipping empty link for %s (%s)", contractor_name, label)
            continue

        absolute_url = urljoin(page_url, normalized_url)
        absolute_url = normalize_drive_url(absolute_url)
        contractor_slug = slugify(contractor_name)

        dedupe_key = (contractor_slug, document_type)
        if dedupe_key in seen_pairs:
            logging.debug(
                "Skipping duplicate %s for contractor %s", document_type, contractor_name
            )
            continue

        seen_pairs.add(dedupe_key)
        yield DocumentLink(
            contractor_name=contractor_name,
            contractor_slug=contractor_slug,
            document_type=document_type,
            label=label,
            url=absolute_url,
        )


def guess_filename(document: DocumentLink, response: requests.Response) -> str:
    disposition = response.headers.get("Content-Disposition")
    if disposition:
        match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', disposition)
        if match:
            filename = match.group(1).strip().strip('"')
            if filename:
                return filename

    parsed = urlparse(response.url or document.url)
    path_name = Path(parsed.path).name
    if "." in path_name:
        return path_name

    content_type = response.headers.get("Content-Type", "").lower()
    if "pdf" in content_type:
        extension = ".pdf"
    elif "msword" in content_type or "wordprocessingml" in content_type:
        extension = ".docx"
    elif "zip" in content_type:
        extension = ".zip"
    else:
        extension = ".bin"

    return f"{document.document_type}{extension}"


def normalize_drive_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc not in {"drive.google.com", "www.drive.google.com"}:
        return url

    if parsed.path.startswith("/file/d/"):
        parts = parsed.path.split("/")
        try:
            file_id = parts[3]
        except IndexError:
            return url
        return f"https://drive.google.com/uc?export=download&id={file_id}"

    if parsed.path == "/uc":
        query = parse_qs(parsed.query)
        file_id = query.get("id", [None])[0]
        if file_id:
            return f"https://drive.google.com/uc?export=download&id={file_id}"

    return url


def _flatten_query(values: Dict[str, Sequence[str]]) -> Dict[str, str]:
    return {key: value[-1] if isinstance(value, list) else value for key, value in values.items()}


def _extract_drive_confirm_token(content: str) -> Optional[str]:
    match = re.search(r'confirm=([0-9A-Za-z_]+)', content)
    if match:
        return match.group(1)
    return None


def _needs_drive_confirmation(response: requests.Response) -> bool:
    content_type = response.headers.get("Content-Type", "").lower()
    if "text/html" not in content_type:
        return False
    parsed = urlparse(response.url or "")
    return parsed.netloc in {"drive.google.com", "www.drive.google.com"} and parsed.path.startswith("/uc")


def fetch_with_drive_support(session: requests.Session, url: str, timeout: int = 60) -> requests.Response:
    response = session.get(url, timeout=timeout, stream=True)
    if not _needs_drive_confirmation(response):
        return response

    for key, value in session.cookies.items():
        if key.startswith("download_warning"):
            response.close()
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            query["confirm"] = [value]
            params = _flatten_query(query)
            return session.get(url, params=params, timeout=timeout, stream=True)

    # Fallback: parse token from HTML body
    try:
        content = response.text
    except Exception:  # pragma: no cover - requests only
        content = ""
    token = _extract_drive_confirm_token(content)
    if not token:
        return response

    response.close()
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    query["confirm"] = [token]
    params = _flatten_query(query)
    return session.get(url, params=params, timeout=timeout, stream=True)


def download_document(
    session: requests.Session,
    document: DocumentLink,
    output_root: Path,
    overwrite: bool,
    dry_run: bool,
) -> Optional[Path]:
    contractor_dir = output_root / document.contractor_slug
    contractor_dir.mkdir(parents=True, exist_ok=True)

    if dry_run:
        logging.info("[dry-run] Would download %s → %s", document.url, contractor_dir)
        return None

    response = fetch_with_drive_support(session, document.url)
    response.raise_for_status()

    filename = guess_filename(document, response)
    destination = contractor_dir / filename

    if destination.exists() and not overwrite:
        logging.info("Skipping existing file %s", destination)
        return destination

    logging.info(
        "Downloading %s (%s) for %s",
        document.label,
        document.document_type,
        document.contractor_name,
    )

    with destination.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                handle.write(chunk)

    return destination


def write_manifest(manifest_path: Path, records: Iterable[Dict[str, str]]) -> None:
    with manifest_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Download Articles of Incorporation and General Information Sheets from "
            "the PCIJ flood-control contractor records page."
        )
    )
    parser.add_argument(
        "--page-url",
        default=DEFAULT_PAGE_URL,
        help=f"Source page URL (default: {DEFAULT_PAGE_URL})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where documents will be stored",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-download files even if they already exist",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only list planned downloads without fetching files",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional path for a JSONL manifest (defaults to <output-dir>/manifest.jsonl)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_arguments(argv)
    configure_logging(args.verbose)

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    logging.info("Fetching index page %s", args.page_url)
    response = session.get(args.page_url, timeout=60)
    response.raise_for_status()

    manifest_records: List[Dict[str, str]] = []
    downloaded: List[Path] = []
    encountered_errors: List[str] = []

    for document in iter_document_links(response.text, args.page_url):
        try:
            destination = download_document(
                session=session,
                document=document,
                output_root=output_dir,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
            )
            if destination:
                downloaded.append(destination)

            manifest_records.append(
                {
                    "contractor_name": document.contractor_name,
                    "contractor_slug": document.contractor_slug,
                    "document_type": document.document_type,
                    "label": document.label,
                    "url": document.url,
                    "destination": str(destination) if destination else "",
                }
            )
        except requests.HTTPError as exc:
            logging.error(
                "Failed to download %s for %s: %s",
                document.document_type,
                document.contractor_name,
                exc,
            )
            encountered_errors.append(document.url)
        except Exception as exc:  # pylint: disable=broad-except
            logging.exception(
                "Unexpected error downloading %s for %s",
                document.document_type,
                document.contractor_name,
            )
            encountered_errors.append(document.url)

    manifest_path = args.manifest or output_dir / MANIFEST_FILENAME
    write_manifest(manifest_path, manifest_records)
    logging.info("Wrote manifest with %d entries to %s", len(manifest_records), manifest_path)

    if encountered_errors:
        logging.warning("Encountered %d errors during download", len(encountered_errors))
        return 1

    if args.dry_run:
        logging.info("Dry run completed successfully")
    else:
        logging.info("Downloaded %d documents", len(downloaded))

    return 0


if __name__ == "__main__":
    sys.exit(main())



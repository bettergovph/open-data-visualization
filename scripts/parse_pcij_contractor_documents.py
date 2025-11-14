#!/usr/bin/env python3
"""
Parse downloaded PCIJ contractor documents to extract incorporators and officers.

Inputs:
    - A directory containing contractor subfolders populated by
      `download_pcij_contractor_documents.py`.

Outputs:
    - One JSON file per contractor containing extracted incorporators/officers.

Example:
    python scripts/parse_pcij_contractor_documents.py \
        --input-dir /home/joebert/open-data-visualization/database/pcij \
        --output-dir /home/joebert/open-data-visualization/database/pcij_parsed
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pdfplumber
import pytesseract
from PIL import Image
from pytesseract import Output

DEFAULT_INPUT_DIR = Path("database/pcij")
DEFAULT_OUTPUT_DIR = Path("database/pcij_parsed")
PCIJ_SOURCE_URL = "https://pcij.org/2025/08/30/flood-control-records/"

NATIONALITY_TOKENS = {
    "FILIPINO",
    "AMERICAN",
    "BRITISH",
    "CANADIAN",
    "CHINESE",
    "JAPANESE",
    "KOREAN",
    "SINGAPOREAN",
    "MALAYSIAN",
    "INDIAN",
    "GERMAN",
    "FRENCH",
    "AUSTRALIAN",
    "SPANISH",
    "ITALIAN",
}

OFFICER_KEYWORDS = [
    "Chairman",
    "President",
    "Vice Chairman",
    "Vice-Chairman",
    "Vice President",
    "Executive Vice President",
    "EVP",
    "SVP",
    "AVP",
    "General Manager",
    "Treasurer",
    "Assistant Treasurer",
    "Corporate Secretary",
    "Secretary",
    "Assistant Secretary",
    "Compliance Officer",
    "Comptroller",
    "Chief Operating Officer",
    "Chief Financial Officer",
    "COO",
    "CFO",
]


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def normalize_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name).strip(" ,;")
    if not cleaned:
        return ""
    # Preserve uppercase abbreviations but title-case the rest.
    parts = []
    for token in cleaned.split(" "):
        if token.isupper() and len(token) <= 3:
            parts.append(token)
        else:
            parts.append(token.capitalize())
    return " ".join(parts)


def extract_pdf_lines(pdf_path: Path) -> List[str]:
    """Extract text lines from a PDF using embedded text or OCR."""
    lines: List[str] = []
    if not pdf_path.exists():
        logging.debug("PDF %s does not exist", pdf_path)
        return lines

    with pdfplumber.open(pdf_path) as pdf:
        for index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text(x_tolerance=2, y_tolerance=2)
            if not text:
                image = page.to_image(resolution=300).original.convert("L")
                thresholded = image.point(lambda x: 0 if x < 160 else 255, "1")
                prepared = thresholded.convert("L")
                text = pytesseract.image_to_string(
                    prepared, config="--psm 6 --oem 3"
                )
            if not text:
                logging.debug("No text extracted from %s page %d", pdf_path, index)
                continue
            for raw_line in text.splitlines():
                stripped = raw_line.strip()
                if stripped:
                    lines.append(stripped)
    return lines


def parse_officers_from_gis(lines: Sequence[str]) -> List[Dict[str, Sequence[str]]]:
    collector: List[Dict[str, Sequence[str]]] = []
    in_section = False
    current: Optional[Dict[str, Sequence[str]]] = None
    name_pattern = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")

    for line in lines:
        upper_line = line.upper()
        if "DIRECTORS / OFFICERS" in upper_line:
            in_section = True
            logging.debug("Found directors/officers section header")
            continue
        if not in_section:
            continue
        if upper_line.startswith("INSTRUCTION"):
            break

        match = name_pattern.match(line)
        if match:
            name_raw = match.group(2).strip(" :;-")
            name = normalize_name(name_raw)
            if not name:
                continue
            current = {"name": name, "roles": []}
            collector.append(current)
            continue

        if not current:
            continue

        found_roles: List[str] = []
        for keyword in OFFICER_KEYWORDS:
            if re.search(rf"\b{re.escape(keyword)}\b", line, re.IGNORECASE):
                found_roles.append(keyword)

        if found_roles:
            unique_roles = list(dict.fromkeys(current["roles"])) if current["roles"] else []
            for role in found_roles:
                if role not in unique_roles:
                    unique_roles.append(role)
            current["roles"] = unique_roles

    # Deduplicate by name keeping the richest role set.
    dedup: Dict[str, Dict[str, Sequence[str]]] = {}
    for entry in collector:
        name = entry["name"]
        roles = list(entry.get("roles", []))
        if name not in dedup:
            dedup[name] = {"name": name, "roles": roles}
        else:
            existing_roles = list(dedup[name].get("roles", []))
            merged = list(dict.fromkeys(existing_roles + roles))
            dedup[name]["roles"] = merged
    return list(dedup.values())


def _token_contains_nationality(line: str) -> Optional[str]:
    upper = line.upper()
    for token in NATIONALITY_TOKENS:
        if token in upper:
            return token
    return None


def ocr_page_lines(page: "pdfplumber.page.Page") -> List[str]:
    image = page.to_image(resolution=300).original.convert("L")
    thresholded = image.point(lambda x: 0 if x < 160 else 255, "1").convert("L")
    data = pytesseract.image_to_data(
        thresholded, config="--psm 6 --oem 3", output_type=Output.DICT
    )
    lines: Dict[Tuple[int, int, int], List[str]] = defaultdict(list)
    for idx, text in enumerate(data["text"]):
        if text is None:
            continue
        text_clean = text.strip()
        if not text_clean:
            continue
        try:
            conf_value = float(data["conf"][idx])
        except (ValueError, TypeError):
            conf_value = -1.0
        if conf_value < 60:
            continue
        key = (
            data.get("block_num", [0])[idx],
            data.get("par_num", [0])[idx],
            data.get("line_num", [0])[idx],
        )
        lines[key].append(text_clean)
    ordered_keys = sorted(
        lines.keys(),
        key=lambda x: (x[0], x[1], x[2]),
    )
    return [" ".join(lines[key]) for key in ordered_keys]


def parse_incorporators_from_aoi_pdf(pdf_path: Path) -> List[str]:
    if not pdf_path.exists():
        return []

    candidates: List[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_lines = ocr_page_lines(page)
            previous_line = ""
            for line in page_lines:
                nationality = _token_contains_nationality(line)
                if nationality:
                    upper = line.upper()
                    index = upper.find(nationality)
                    name_fragment = line[:index].strip(" .,:;_-")
                    candidate = name_fragment or previous_line
                    if candidate:
                        candidates.append(candidate)
                    previous_line = ""
                else:
                    previous_line = line
    return clean_incorporator_names(candidates)


def clean_incorporator_names(candidates: Sequence[str]) -> List[str]:
    disallowed_tokens = {
        "ARTICLE",
        "AUTHORIZED",
        "CAPITAL",
        "STOCK",
        "TRANSFER",
        "OWNERSHIP",
        "PROVIDED",
        "NATIONALS",
        "PERCENTAGE",
        "SHAREHOLDINGS",
        "SHAREHOLDERS",
        "SHARES",
        "VOLUNTARILY",
        "ASSIGNMENT",
        "RIGHT",
        "PURCHASE",
        "MAY",
        "ELEVENTH",
        "NINTH",
        "EIGHTH",
        "SEVENTH",
        "SIXTH",
        "FIFTH",
        "FOURTH",
        "THIRD",
        "SECOND",
        "FIRST",
        "PHILIPPINE",
        "PHILIPPINES",
        "PROVIDED",
        "REDUCE",
        "INTEREST",
        "AMOUNT",
        "SUBSCRIBED",
        "PAID",
        "TRANSFER",
        "PUBLIC",
        "FOREIGN",
        "COMMON",
        "TOTAL",
        "TYPE",
        "NUMBER",
        "HOLDERS",
    }

    cleaned: List[str] = []
    for candidate in candidates:
        stripped = candidate.strip()
        if not stripped:
            continue
        if stripped.upper().startswith("ARTICLE"):
            continue
        normalized = re.sub(r"[^A-Za-z .,'-]+", " ", stripped)
        normalized = re.sub(r"\s+", " ", normalized).strip(" .,'-")
        if len(normalized) < 4:
            continue
        if len(normalized.split()) < 2:
            continue
        if any(char.isdigit() for char in normalized):
            continue
        upper_tokens = {token.upper() for token in normalized.split()}
        if upper_tokens & disallowed_tokens:
            continue
        cleaned.append(normalize_name(normalized))
    return list(dict.fromkeys(cleaned))


def parse_aoi_officer_mentions(lines: Sequence[str]) -> Dict[str, List[str]]:
    """
    Attempt to capture Treasurer/Secretary assignments from Articles text.
    The OCR quality is inconsistent, so this best-effort parser looks for patterns
    close to 'has been elected ... Treasurer' etc.
    """
    text_blob = " ".join(lines)
    officer_roles: Dict[str, List[str]] = defaultdict(list)
    patterns = {
        "Treasurer": re.compile(
            r"([A-Z][A-Za-z .,']+)\s+has\s+been\s+elected\s+by\s+the\s+subscribers\s+as\s+Treasurer",
            re.IGNORECASE,
        ),
        "Secretary": re.compile(
            r"([A-Z][A-Za-z .,']+)\s+has\s+been\s+elected\s+.*\bSecretary",
            re.IGNORECASE,
        ),
    }
    for role, pattern in patterns.items():
        for match in pattern.finditer(text_blob):
            name = normalize_name(match.group(1))
            if name:
                officer_roles[name].append(role)
    return officer_roles


def merge_officer_roles(
    officers: List[Dict[str, Sequence[str]]],
    extra_roles: Dict[str, List[str]],
) -> List[Dict[str, Sequence[str]]]:
    if not extra_roles:
        return officers
    merged: Dict[str, Dict[str, Sequence[str]]] = {
        officer["name"]: {"name": officer["name"], "roles": list(officer.get("roles", []))}
        for officer in officers
    }
    for name, roles in extra_roles.items():
        bucket = merged.setdefault(name, {"name": name, "roles": []})
        merged_roles = list(dict.fromkeys(list(bucket.get("roles", [])) + roles))
        bucket["roles"] = merged_roles
    return list(merged.values())


def detect_document_type(filename: str) -> Optional[str]:
    upper = filename.upper()
    if "GENERAL" in upper or "GIS" in upper:
        return "general_information_sheet"
    if "AOI" in upper or "ARTICLES" in upper:
        return "articles_of_incorporation"
    return None


def find_document_paths(contractor_dir: Path) -> Dict[str, Path]:
    mapping: Dict[str, Path] = {}
    for path in sorted(contractor_dir.glob("*.pdf")):
        doc_type = detect_document_type(path.name)
        if doc_type and doc_type not in mapping:
            mapping[doc_type] = path
    return mapping


def build_contractor_payload(contractor_dir: Path) -> Optional[Dict[str, object]]:
    document_paths = find_document_paths(contractor_dir)
    if not document_paths:
        logging.warning("No parsed PDF documents found in %s", contractor_dir)
        return None

    contractor_name = contractor_dir.name.replace("-", " ").title()

    officers: List[Dict[str, Sequence[str]]] = []
    incorporators: List[str] = []

    if "general_information_sheet" in document_paths:
        gis_lines = extract_pdf_lines(document_paths["general_information_sheet"])
        officers = parse_officers_from_gis(gis_lines)

    if "articles_of_incorporation" in document_paths:
        aoi_path = document_paths["articles_of_incorporation"]
        aoi_lines = extract_pdf_lines(aoi_path)
        incorporators = parse_incorporators_from_aoi_pdf(aoi_path)
        officer_roles = parse_aoi_officer_mentions(aoi_lines)
        officers = merge_officer_roles(officers, officer_roles)

    payload = {
        "contractor_slug": contractor_dir.name,
        "contractor_name_guess": contractor_name,
        "documents": {key: str(path) for key, path in document_paths.items()},
        "incorporators": sorted(dict.fromkeys(incorporators)),
        "officers": officers,
        "sources": [PCIJ_SOURCE_URL],
        "generated_at": datetime.utcnow().isoformat(),
    }
    return payload


def write_payload(output_dir: Path, payload: Dict[str, object], overwrite: bool) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{payload['contractor_slug']}.json"
    if destination.exists() and not overwrite:
        logging.info("Skipping existing parsed file %s", destination)
        return destination
    with destination.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    return destination


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract incorporators and officers from PCIJ contractor documents."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help="Directory containing contractor folders with downloaded PDFs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where parsed JSON files will be written.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing parsed JSON outputs.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on number of contractors to process.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_arguments(argv)
    configure_logging(args.verbose)

    input_dir = args.input_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if not input_dir.exists():
        logging.error("Input directory %s does not exist", input_dir)
        return 1

    contractor_dirs = sorted(
        [
            path
            for path in input_dir.iterdir()
            if path.is_dir()
        ]
    )
    if args.limit is not None:
        contractor_dirs = contractor_dirs[: args.limit]

    if not contractor_dirs:
        logging.warning("No contractor directories found in %s", input_dir)
        return 0

    written = 0
    for contractor_dir in contractor_dirs:
        payload = build_contractor_payload(contractor_dir)
        if not payload:
            continue
        destination = write_payload(output_dir, payload, overwrite=args.overwrite)
        logging.info("Wrote %s", destination)
        written += 1

    logging.info("Parsed %d contractors", written)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



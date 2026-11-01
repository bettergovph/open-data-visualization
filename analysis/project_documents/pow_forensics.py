"""Audit indexed FY2027 POW PDFs and expose conservative forensic signals."""
import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "static/nep-preview/dpwh-in-depth-data.json"
OUTPUT = ROOT / "static/nep-preview/pow-forensics-data.json"
DEFAULT_PDF_ROOT = Path("/Volumes/T5 EVO/bettergov-research/nep/data_sources/dpwh_project_documents/on_demand")


def pdf_string(path):
    return "(" + str(path).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


def image_profiles(raw):
    profiles = []
    marker = re.compile(rb"/Subtype\s*/Image\b")
    for match in marker.finditer(raw):
        start = raw.rfind(b"<<", 0, match.start())
        if start < 0:
            continue
        depth = 0
        i = start
        end = None
        while i < len(raw) - 1:
            pair = raw[i:i + 2]
            if pair == b"<<":
                depth += 1
                i += 2
            elif pair == b">>":
                depth -= 1
                i += 2
                if depth == 0:
                    end = i
                    break
            else:
                i += 1
        if end is None:
            continue
        d = raw[start:end]
        def field(name, pattern):
            found = re.search(pattern, d)
            return found.group(1).decode("latin1", "replace") if found else None
        profile = {
            "width": field("Width", rb"/Width\s+(\d+)(?=\s|/|>)"),
            "height": field("Height", rb"/Height\s+(\d+)(?=\s|/|>)"),
            "bitsPerComponent": field("BitsPerComponent", rb"/BitsPerComponent\s+(\d+)(?=\s|/|>)"),
            "colorSpace": field("ColorSpace", rb"/ColorSpace\s*(\[[^\]]*\]|/[A-Za-z0-9]+|\d+\s+\d+\s+R)"),
            "filter": field("Filter", rb"/Filter\s*(\[[^\]]*\]|/[A-Za-z0-9]+)"),
        }
        if profile["width"] or profile["height"]:
            profiles.append(profile)
        # Skip nested delimiters already consumed by this image dictionary.
        marker = re.compile(rb"/Subtype\s*/Image\b")
        if end > match.start():
            marker = re.compile(rb"/Subtype\s*/Image\b")
            # finditer has no mutable cursor; nested image-like payload tokens are unlikely.
    return profiles


def parse_gs_records(stdout):
    records = {}
    current = None
    for line in stdout.splitlines():
        if line.startswith("@@DOC@@"):
            current = line[len("@@DOC@@"):].strip()
            records[current] = {}
        elif current and line.startswith("@@") and "=" in line:
            key, value = line[2:].split("=", 1)
            if key == "PAGES":
                key = "pdfPageCount"
            value = value.strip()
            if value == "__NONE__":
                value = None
            else:
                try:
                    raw = bytes.fromhex(value)
                    if raw.startswith(b"\xfe\xff"):
                        value = raw[2:].decode("utf-16-be", "replace")
                    elif raw.startswith(b"\xff\xfe"):
                        value = raw[2:].decode("utf-16-le", "replace")
                    elif len(raw) > 2 and raw[1::2].count(0) > len(raw) // 5:
                        value = raw.decode("utf-16-be", "replace")
                    elif len(raw) > 2 and raw[::2].count(0) > len(raw) // 5:
                        value = raw.decode("utf-16-le", "replace")
                    else:
                        value = raw.decode("utf-8", "replace")
                except ValueError:
                    value = "[metadata decode error]"
            records[current][key.lower()] = value
        elif current and line == "@@ERROR@@":
            records[current]["error"] = True
    return records


def read_pdf_info(files):
    chunks = [
        "/printhex { (%stdout) (w) file exch writehexstring } bind def",
        "/printfield { /key exch def info key known { info key get dup type /stringtype eq { printhex } { 2000 string cvs printhex } ifelse } { (__NONE__) print } ifelse } bind def",
        "/nl (\n) def",
    ]
    for code, path in files:
        chunks.extend([
            "{",
            f"(@@DOC@@{code}\\n) print",
            f"{pdf_string(path)} (r) file runpdfbegin",
            "/info pdfdict /PDFInfo get def",
            "(@@CREATOR=) print /Creator printfield nl print",
            "(@@PRODUCER=) print /Producer printfield nl print",
            "(@@CREATIONDATE=) print /CreationDate printfield nl print",
            "(@@MODDATE=) print /ModDate printfield nl print",
            "(@@PAGES=) print /NumPages printfield nl print",
            "runpdfend",
            "} stopped { (@@ERROR@@\\n) print } if",
        ])
    with tempfile.NamedTemporaryFile("w", suffix=".ps", encoding="latin1", delete=False) as f:
        script_path = Path(f.name)
        f.write("\n".join(chunks) + "\n")
    try:
        result = subprocess.run(
            ["gs", "-q", "-dNOSAFER", "-dNODISPLAY", "-dBATCH", "-f", str(script_path), "-c", "quit"],
            check=False, capture_output=True, text=True, errors="replace", timeout=900,
        )
        return parse_gs_records(result.stdout), result.returncode, result.stderr[-3000:]
    finally:
        script_path.unlink(missing_ok=True)


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parser_signals(pow_document):
    pages = pow_document.get("pages") or []
    statuses = Counter(p.get("status") for p in pages if p.get("status"))
    methods = Counter(p.get("method") for p in pages if p.get("method"))
    return {
        "parserItemRowCount": len(pow_document.get("rows") or []),
        "parserCategorySummaryRowCount": len(pow_document.get("costCategoryBreakdown") or []),
        "parserCandidatePageCount": statuses.get("candidate_rows", 0),
        "parserManualReviewPageCount": statuses.get("needs_manual_review", 0),
        "parserNoBillRowsPageCount": statuses.get("no_bill_rows_recovered", 0),
        "parserNeedsOcrPageCount": statuses.get("needs_ocr", 0),
        "parserOcrPageCount": sum(n for method, n in methods.items() if "OCR" in method),
        "parserNativeTextPageCount": sum(n for method, n in methods.items() if "native PDF text" in method),
        "parserSignatoryStatus": pow_document.get("signatoryStatus"),
        "parserErrorType": pow_document.get("errorType"),
    }


def catalog_coverage(pdf_root):
    """Count POW URLs in cached project metadata without fetching PDFs."""
    metadata_files = sorted(pdf_root.glob("2027DPWH-Proposal-*/metadata.json"))
    pow_codes = set()
    pow_pdf_records = 0
    for path in metadata_files:
        try:
            project = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for doc in project.get("documents", []) or []:
            document_type = re.sub(r"[^a-z]+", " ", str(doc.get("documentType", "")).lower()).strip()
            if document_type != "pow" and "program of work" not in document_type:
                continue
            if urlsplit(str(doc.get("url", ""))).path.lower().endswith(".pdf"):
                pow_pdf_records += 1
                pow_codes.add(path.parent.name)
    cached_files = list(pdf_root.glob("2027DPWH-Proposal-*/assets/*/pow.pdf"))
    cached_codes = {path.parts[-4] for path in cached_files}
    return {
        "cachedProjectMetadataRecords": len(metadata_files),
        "metadataProjectsWithPowPdfUrl": len(pow_codes),
        "metadataPowPdfSourceRecords": pow_pdf_records,
        "cachedPowPdfProjects": len(cached_codes),
        "cachedPowPdfCopiesAcrossCatalog": len(cached_files),
        "metadataProjectsWithPowNotCached": len(pow_codes - cached_codes),
        "cachedCoverageOfMetadataPowProjectsPct": round(100 * len(pow_codes & cached_codes) / len(pow_codes), 2) if pow_codes else None,
        "metadataCatalogPdfUrlsVerifiedReachable": False,
        "downloadMode": "on-demand per project; no bulk-download mode",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf-root", type=Path, default=DEFAULT_PDF_ROOT)
    parser.add_argument("--refresh-metadata-only", action="store_true", help="refresh Ghostscript document properties in the existing report data")
    args = parser.parse_args()
    if args.refresh_metadata_only:
        existing = json.loads(OUTPUT.read_text(encoding="utf-8"))
        existing["summary"].update(catalog_coverage(args.pdf_root))
        source_projects = {p.get("code"): p for p in json.loads(SOURCE.read_text(encoding="utf-8")).get("projects", [])}
        files = []
        for record in existing.get("documents", []):
            candidates = sorted((args.pdf_root / record["code"]).glob("assets/*/pow.pdf"))
            if candidates:
                path = candidates[0]
                files.append((record["code"], path))
                record["hasExifMarker"] = bool(re.search(rb"\xff\xd8\xff\xe1[\s\S]{2}Exif\x00\x00", path.read_bytes()))
        gs_info, gs_exit_code, gs_stderr = read_pdf_info(files)
        for record in existing.get("documents", []):
            source_project = source_projects.get(record["code"], {})
            source_pow = next((d for d in source_project.get("documents", []) if str(d.get("kind", "")).casefold() == "pow"), {})
            record["pages"] = [
                {"page": p.get("page"), "rotation": p.get("nativePageRotation"), "orientation": p.get("pageRectOrientation"), "status": p.get("status"), "method": p.get("method")}
                for p in (source_pow.get("pages") or [])
            ]
            record.update(parser_signals(source_pow))
            info = gs_info.get(record["code"], {})
            record.update(info)
            record["pdfParserError"] = bool(info.get("error"))
        summary = existing["summary"]
        summary["knownProcessingCaveat"] = "User reports AI was used to cover signatures before these supplied PDFs were provided; metadata and image structure may describe post-processing rather than original scans."
        creators = Counter(d.get("creator") for d in existing["documents"] if d.get("creator"))
        producers = Counter(d.get("producer") for d in existing["documents"] if d.get("producer"))
        summary.update({
            "documentsWithCreator": sum(bool(d.get("creator")) for d in existing["documents"]),
            "documentsWithProducer": sum(bool(d.get("producer")) for d in existing["documents"]),
            "creatorValues": dict(creators),
            "producerValues": dict(producers),
            "documentsWithCreationDate": sum(bool(d.get("creationdate")) for d in existing["documents"]),
            "documentsWithModDate": sum(bool(d.get("moddate")) for d in existing["documents"]),
            "documentsWithExifMarker": sum(bool(d.get("hasExifMarker")) for d in existing["documents"]),
            "pdfMetadataParserErrors": sum(bool(d.get("pdfParserError")) for d in existing["documents"]),
            "pdfMetadataParserErrorCodes": [d["code"] for d in existing["documents"] if d.get("pdfParserError")],
            "ghostscriptExitCode": gs_exit_code,
            "ghostscriptErrors": gs_stderr,
        })
        OUTPUT.write_text(json.dumps(existing, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(json.dumps({k: summary[k] for k in ("documentsWithCreator", "documentsWithProducer", "creatorValues", "producerValues", "documentsWithCreationDate", "documentsWithModDate", "pdfMetadataParserErrors", "pdfMetadataParserErrorCodes", "ghostscriptExitCode")}, ensure_ascii=False, indent=2))
        return
    indexed = json.loads(SOURCE.read_text(encoding="utf-8"))
    projects = indexed.get("projects", [])
    by_code = {p.get("code"): p for p in projects}
    indexed_docs = {}
    for project in projects:
        for doc in project.get("documents", []):
            if str(doc.get("kind", "")).casefold() == "pow":
                indexed_docs[project.get("code")] = (project, doc)

    files = []
    documents = []
    copies_by_code = Counter()
    failures = []
    page_orientation_counts = Counter()
    page_rotation_counts = Counter()
    page_method_counts = Counter()
    page_status_counts = Counter()
    for code, (project, doc) in indexed_docs.items():
        candidates = sorted((args.pdf_root / code).glob("assets/*/pow.pdf"))
        if not candidates:
            failures.append({"code": code, "reason": "No local POW PDF found"})
            continue
        matched = []
        for path in candidates:
            sha = file_sha256(path)
            if sha == doc.get("sha256"):
                matched.append(path)
            else:
                failures.append({"code": code, "reason": "PDF SHA-256 differs from index", "path": str(path), "sha256": sha})
        if not matched:
            continue
        copies_by_code[code] = len(matched)
        path = matched[0]
        files.append((code, path))
        raw = path.read_bytes()
        profiles = image_profiles(raw)
        unique_profiles = {json.dumps(p, sort_keys=True) for p in profiles}
        pages = []
        for page in doc.get("pages") or []:
            item = {
                "page": page.get("page"),
                "rotation": page.get("nativePageRotation"),
                "orientation": page.get("pageRectOrientation"),
                "status": page.get("status"),
                "method": page.get("method"),
            }
            pages.append(item)
            if item["orientation"]:
                page_orientation_counts[item["orientation"]] += 1
            if item["rotation"] is not None:
                page_rotation_counts[str(item["rotation"])] += 1
            if item["method"]:
                page_method_counts[item["method"]] += 1
            if item["status"]:
                page_status_counts[item["status"]] += 1
        orientations = {p["orientation"] for p in pages if p["orientation"]}
        rotations = {p["rotation"] for p in pages if p["rotation"] is not None}
        methods = {p["method"] for p in pages if p["method"]}
        xmp = bool(re.search(rb"/Type\s*/Metadata|/Subtype\s*/XML|<?xpacket", raw, re.I))
        exif = bool(re.search(rb"\xff\xd8\xff\xe1[\s\S]{2}Exif\x00\x00", raw))
        record = {
            "code": code,
            "title": project.get("name"),
            "office": project.get("office"),
            "region": project.get("region"),
            "pdfUrl": doc.get("url"),
            "sha256": doc.get("sha256"),
            "pageCount": doc.get("pageCount"),
            "documentStatus": doc.get("status"),
            "localCopies": len(matched),
            "pageOrientations": sorted(orientations),
            "pageRotations": sorted(rotations),
            "extractionMethods": sorted(methods),
            "mixedOrientation": len(orientations) > 1,
            "mixedRotation": len(rotations) > 1,
            "mixedExtractionMethods": len(methods) > 1,
            "embeddedImageObjects": len(profiles),
            "imageProfiles": profiles,
            "distinctImageProfiles": len(unique_profiles),
            "multipleImageProfiles": len(unique_profiles) > 1,
            "hasXmpMetadataObject": xmp,
            "hasExifMarker": exif,
            "pages": pages,
        }
        record.update(parser_signals(doc))
        documents.append(record)
    gs_info, gs_exit_code, gs_stderr = read_pdf_info(files)
    for record in documents:
        record.update(gs_info.get(record["code"], {}))

    image_count = sum(d["embeddedImageObjects"] for d in documents)
    producer_counts = Counter(d.get("producer") for d in documents if d.get("producer"))
    creator_counts = Counter(d.get("creator") for d in documents if d.get("creator"))
    summary = {
        "source": "static/nep-preview/dpwh-in-depth-data.json plus local POW PDF originals",
        "scope": "FY2027 DPWH NEP projects in the indexed document snapshot with matching local POW PDFs; not all years or agencies.",
        "knownProcessingCaveat": "User reports AI was used to cover signatures before these supplied PDFs were provided; metadata and image structure may describe post-processing rather than original scans.",
        "generatedAtUtc": indexed.get("generatedAtUtc"),
        "indexedProjects": len(projects),
        "indexedPowDocuments": len(indexed_docs),
        "localProjectsMatched": len(documents),
        "localPdfCopies": sum(d["localCopies"] for d in documents),
        "allLocalFilesMatchIndexedSha256": not failures and len(documents) == len(indexed_docs),
        "duplicateLocalCopies": sum(max(0, n - 1) for n in copies_by_code.values()),
        "documentsWithCreator": sum(bool(d.get("creator")) for d in documents),
        "documentsWithProducer": sum(bool(d.get("producer")) for d in documents),
        "creatorValues": dict(creator_counts),
        "producerValues": dict(producer_counts),
        "documentsWithCreationDate": sum(bool(d.get("creationdate")) for d in documents),
        "documentsWithModDate": sum(bool(d.get("moddate")) for d in documents),
        "documentsWithImageObjects": sum(d["embeddedImageObjects"] > 0 for d in documents),
        "embeddedImageObjects": image_count,
        "documentsWithMultipleImageProfiles": sum(d["multipleImageProfiles"] for d in documents),
        "documentsWithXmpMetadataObject": sum(d["hasXmpMetadataObject"] for d in documents),
        "documentsWithExifMarker": sum(d["hasExifMarker"] for d in documents),
        "mixedPageOrientationDocuments": sum(d["mixedOrientation"] for d in documents),
        "mixedPageRotationDocuments": sum(d["mixedRotation"] for d in documents),
        "mixedExtractionMethodDocuments": sum(d["mixedExtractionMethods"] for d in documents),
        "documentsWithoutPageDetails": sum(not d["pages"] or not d.get("pageCount") for d in documents),
        "pageOrientations": dict(page_orientation_counts),
        "pageRotations": dict(page_rotation_counts),
        "pageExtractionMethods": dict(page_method_counts),
        "pageExtractionStatuses": dict(page_status_counts),
        "ghostscriptExitCode": gs_exit_code,
        "ghostscriptErrors": gs_stderr,
        "creatorProducerCapturedInOriginalPdf": True,
        "embeddedImageMetadataCaptured": True,
        "pageResolutionCaptured": False,
        "compressionSignaturesCaptured": True,
        "pixelNoiseDataCaptured": False,
        "indexFailures": failures,
    }
    summary.update(catalog_coverage(args.pdf_root))
    documents.sort(key=lambda d: (d.get("code") or "", d.get("title") or ""))
    OUTPUT.write_text(json.dumps({"summary": summary, "documents": documents}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {OUTPUT} ({len(documents)} matched POW PDFs)")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

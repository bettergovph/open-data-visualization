#!/usr/bin/env python3
"""Export the FY2019 GAA Volume IA OCR transcript as a separate web dataset."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/Users/joebertj/nep/data_sources/gaa_2019_volume_ia/pages.jsonl")
DEST = ROOT / "static/nep-preview/fy2019-gaa-volume-ia-lines.json"


def main():
    lines = []
    for raw in SOURCE.open(encoding="utf-8"):
        page = json.loads(raw)
        for line in page.get("lines", []):
            text = line.get("text", "").strip()
            if not text:
                continue
            lines.append({
                "page": page.get("page"),
                "line": line.get("line_no"),
                "type": line.get("row_type", "text"),
                "text": text,
                "amounts": line.get("amount_candidates", []),
            })
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(json.dumps({
        "title": "FY2019 GAA Volume I-A OCR lines",
        "source": "DBM FY2019 General Appropriations Act, Volume I-A",
        "scope": "Scanned-volume OCR transcript; not a complete GAA dataset or DPWH project list. Amount candidates and row labels are unverified OCR.",
        "pages": 1078,
        "lines": lines,
    }, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines):,} OCR lines to {DEST} ({DEST.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()

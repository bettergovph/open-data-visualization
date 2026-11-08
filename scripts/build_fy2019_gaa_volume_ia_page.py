#!/usr/bin/env python3
"""Build the FY2019 Volume I-A OCR page and its page-owned data asset."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
TEMPLATE = SCRIPTS / "page_templates/gaa-2019-volume-ia.html"
DEST = ROOT / "static/nep-preview/gaa-2019-volume-ia.html"


def build() -> None:
    sys.path.insert(0, str(SCRIPTS))
    from export_fy2019_gaa_volume_ia import main as export_page_data

    export_page_data()
    page = TEMPLATE.read_text(encoding="utf-8")
    if "fy2019-gaa-volume-ia-lines.json" not in page:
        raise ValueError("FY2019 Volume I-A page template does not reference its data asset")
    DEST.write_text(page, encoding="utf-8")
    print(f"Built {DEST}")


if __name__ == "__main__":
    build()

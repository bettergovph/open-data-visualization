#!/usr/bin/env python3
"""Build the FY2015 DPWH technical GAA page and its page-owned data asset."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
TEMPLATE = SCRIPTS / "page_templates/gaa-2015-dpwh-technical.html"
DEST = ROOT / "static/nep-preview/gaa-2015-dpwh-technical.html"


def build() -> None:
    # Keep dataset production behind this page entry point so a page refresh
    # cannot accidentally regenerate another report's output.
    sys.path.insert(0, str(SCRIPTS))
    from export_fy2015_dpwh_technical_gaa import main as export_page_data

    export_page_data()
    page = TEMPLATE.read_text(encoding="utf-8")
    if "fy2015-dpwh-technical-gaa-data.json" not in page:
        raise ValueError("FY2015 page template does not reference its data asset")
    DEST.write_text(page, encoding="utf-8")
    print(f"Built {DEST}")


if __name__ == "__main__":
    build()

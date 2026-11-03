#!/usr/bin/env python3
"""Copy the parsed DBM FY2019 DPWH technical GAA rows to static storage."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/Users/joebertj/nep/data_sources/gaa_2019_dpwh_technical/lines.json")
DEST = ROOT / "static/nep-preview/fy2019-dpwh-technical-gaa-data.json"


def main():
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    DEST.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Exported {len(payload['rows']):,} UACS rows to {DEST} ({DEST.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()

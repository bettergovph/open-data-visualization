#!/usr/bin/env python3
"""Export parsed FY2015 DBM DPWH GAA account groups as a separate JSON file."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('/Users/joebertj/nep/data_sources/gaa_2015_dpwh_technical/lines.json')
DEST = ROOT / 'static/nep-preview/fy2015-dpwh-technical-gaa-data.json'


def main():
    payload = json.loads(SOURCE.read_text(encoding='utf-8'))
    DEST.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print(f"Exported {len(payload['rows']):,} capital-outlay PAP groups to {DEST} ({DEST.stat().st_size:,} bytes)")


if __name__ == '__main__':
    main()

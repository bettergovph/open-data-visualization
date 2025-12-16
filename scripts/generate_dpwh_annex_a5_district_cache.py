#!/usr/bin/env python3
"""
Generate a cache that classifies 2026 DPWH Annex A-5 projects into congressional districts.

Heuristic:
- Use `scripts/location_enricher.py` (unified_locations.parquet) to extract province/municipality/district/cgressman
  by scanning project titles/descriptions for known location strings.

Output:
- static/data/dpwh_annex_a5_district_cache.json
  {
    "generated_at": "...",
    "total_projects": 17179,
    "matched": 12345,
    "unmatched": 4834,
    "by_id": {
      "<contract_id>": {"province": "...", "municipality": "...", "district": "...", "congressman": "..."}
    }
  }
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import sys

# Allow running as `python3 scripts/...py` without installing as a package
sys.path.insert(0, str(Path(__file__).resolve().parent))

from location_enricher import LocationEnricher  # noqa: E402


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_2026 = BASE_DIR / "static" / "data" / "budget_amendments_2026.json"
OUT_PATH = BASE_DIR / "static" / "data" / "dpwh_annex_a5_district_cache.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_annex_a5_items() -> List[Dict[str, Any]]:
    if not DATA_2026.exists():
        raise FileNotFoundError(f"Missing {DATA_2026}")
    payload = json.loads(DATA_2026.read_text(encoding="utf-8"))
    items = (payload.get("projects") or []) + (payload.get("line_items") or [])
    return [it for it in items if (it.get("source_sheet") == "Annex A-5")]


def main() -> None:
    items = _load_annex_a5_items()
    enricher = LocationEnricher(db_path=str(BASE_DIR / "static" / "data" / "unified_locations.parquet"))
    enricher.load_db()

    by_id: Dict[str, Dict[str, Any]] = {}
    matched = 0
    for it in items:
        pid = it.get("id")
        if pid is None:
            continue
        pid_str = str(pid)
        text_project = {
            "name": it.get("name") or it.get("display_name") or "",
            "description": it.get("description") or "",
            "location": json.dumps(it.get("location") or {}) + " " + json.dumps(it.get("hierarchy") or {}),
        }
        enricher.enrich_project(text_project)
        province = text_project.get("province")
        municipality = text_project.get("municipality")
        district = text_project.get("district")
        congressman = text_project.get("congressman")

        if district and district != "Unknown":
            matched += 1

        by_id[pid_str] = {
            "province": province,
            "municipality": municipality,
            "district": district,
            "congressman": congressman,
        }

    out = {
        "generated_at": _now_iso(),
        "total_projects": len(items),
        "matched": matched,
        "unmatched": max(0, len(items) - matched),
        "by_id": by_id,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Wrote {OUT_PATH} ({len(by_id)} ids), matched={matched}/{len(items)}")


if __name__ == "__main__":
    main()

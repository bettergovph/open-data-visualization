#!/usr/bin/env python3
"""
Quick sampling harness to sanity-check dynasty location classification against real project text.

It pulls N sample projects per topic from `data/parquet/integrated_projects.parquet`,
runs the same worker classification logic used by `scripts/generate_dynasty_projects_cache_duckdb.py`,
and prints a compact report for human review.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module_from_path(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to import {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


_dynasty_mod = _load_module_from_path(
    "generate_dynasty_projects_cache_duckdb",
    REPO_ROOT / "scripts" / "generate_dynasty_projects_cache_duckdb.py",
)

DynastyProjectsCacheGeneratorDuckDB = _dynasty_mod.DynastyProjectsCacheGeneratorDuckDB
find_best_location_match_worker = _dynasty_mod.find_best_location_match_worker
init_worker = _dynasty_mod.init_worker
process_unified_chunk_worker = _dynasty_mod.process_unified_chunk_worker


DEFAULT_TOPICS: List[Tuple[str, List[str]]] = [
    ("metro_manila", ["%METRO MANILA%", "%NATIONAL CAPITAL REGION%"]),
    ("manila", ["%MANILA%"]),
    ("manila_north_road", ["%MANILA NORTH ROAD%", "%MANILA NORTH%ROAD%"]),
    ("iloilo", ["%ILOILO%"]),
    ("leyte", ["%LEYTE%"]),
    ("samar", ["%SAMAR%"]),
    ("davao", ["%DAVAO%"]),
    ("bagumbayan", ["%BAGUMBAYAN%"]),
    ("san_pedro", ["%SAN PEDRO%"]),
    ("maasin", ["%MAASIN%"]),
    ("mindoro", ["%MINDORO%"]),
    ("las_pinas_enye", ["%LAS PIÑAS%", "%LAS PINAS%"]),
]


def _load_projects_for_topic(
    con: duckdb.DuckDBPyConnection,
    parquet_path: str,
    patterns: List[str],
    n: int,
) -> List[Dict[str, Any]]:
    escaped = parquet_path.replace("'", "''")
    con.execute(f"CREATE OR REPLACE VIEW ip AS SELECT * FROM read_parquet('{escaped}')")

    clauses = []
    params: List[Any] = []
    for pat in patterns:
        clauses.append("project_name ILIKE ?")
        clauses.append("location ILIKE ?")
        params.extend([pat, pat])
    where = " OR ".join(clauses) if clauses else "FALSE"

    query = f"""
        SELECT
            project_name,
            location,
            contractor,
            amount,
            source,
            year
        FROM ip
        WHERE project_name IS NOT NULL
          AND ({where})
        ORDER BY project_name
        LIMIT {int(n)}
    """
    rows = con.execute(query, params).fetchall()
    out: List[Dict[str, Any]] = []
    for project_name, location, contractor, amount, source, year in rows:
        out.append(
            {
                "project_name": (project_name or "").strip(),
                "location": (location or "").strip(),
                "contractor": (contractor or "").strip(),
                "amount": amount,
                "source": (source or "Unknown"),
                "year": year,
            }
        )
    return out


async def _prepare_worker_state() -> Dict[str, Any]:
    generator = DynastyProjectsCacheGeneratorDuckDB(force_reclassify=True)

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        config_data, districts_data = await generator.load_config()
        political_dynasties_available = Path("data/parquet/political_dynasties.parquet").exists()
        congressmen_data = await generator.get_congressmen_data(
            None,
            config_data,
            districts_data,
            political_dynasties_available,
        )

        generator.location_matcher.load()

        district_lookup_dict, contractor_lookup_dict, contractor_inverted_index = generator._build_lookup_dictionaries(
            congressmen_data, districts_data
        )
        generator.location_dicts = generator._build_location_dictionaries(
            congressmen_data, district_lookup_dict, districts_data
        )

        canonical_name_map = generator._build_name_normalization_map(congressmen_data)

    shared_data = {
        "congressmen_data": congressmen_data,
        "district_lookup": district_lookup_dict,
        "contractor_lookup": contractor_lookup_dict,
        "contractor_inverted_index": contractor_inverted_index,
        "location_entries": generator.location_matcher.location_entries,
        "location_token_map": dict(generator.location_matcher.token_map),
        "safe_single_district_municipalities": list(generator.location_matcher.safe_single_district_municipalities),
        "location_dictionaries": generator.location_dicts,
        "substring_provinces": generator.substring_provinces,
        "canonical_name_map": canonical_name_map,
        "project_code_mapping": generator.project_code_mapping,
    }
    return shared_data


def _short(s: str, limit: int = 220) -> str:
    s = (s or "").replace("\n", " ").strip()
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def _short_loc_match(loc_match: Any) -> str:
    if not loc_match:
        return "None"
    try:
        parts = [str(p or "") for p in loc_match]
    except Exception:
        return _short(str(loc_match), 120)
    return "(" + ", ".join(_short(p, 60) for p in parts) + ")"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=10, help="Samples per topic")
    parser.add_argument(
        "--parquet",
        default="data/parquet/integrated_projects.parquet",
        help="Integrated projects parquet path",
    )
    parser.add_argument(
        "--topics-json",
        default="",
        help="Optional JSON file: {\"topic\": [\"%PAT%\", ...], ...}",
    )
    parser.add_argument(
        "--only",
        default="",
        help="Comma-separated topic names to run (default: all)",
    )
    args = parser.parse_args()

    topics = DEFAULT_TOPICS
    if args.topics_json:
        payload = json.loads(Path(args.topics_json).read_text(encoding="utf-8"))
        topics = [(k, v) for k, v in payload.items()]
    if args.only:
        wanted = {t.strip() for t in args.only.split(",") if t.strip()}
        topics = [(k, v) for k, v in topics if k in wanted]

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        shared_data = await _prepare_worker_state()
        init_worker(shared_data)

    con = duckdb.connect()
    try:
        for topic, patterns in topics:
            projects = _load_projects_for_topic(con, args.parquet, patterns, args.n)
            print(f"\n=== {topic} ({len(projects)}/{args.n}) ===")
            if not projects:
                continue

            # Compute location match tuple for visibility (same function the worker uses).
            loc_matches = []
            loc_name_matches = []
            for p in projects:
                search_text = f"{p.get('project_name','')} {p.get('location','')}".strip()
                loc_matches.append(find_best_location_match_worker(search_text))
                loc_name_matches.append(find_best_location_match_worker(p.get("project_name", "")))

            processed, _stats = process_unified_chunk_worker(projects)

            for i, (proj, loc_match) in enumerate(zip(processed, loc_matches), start=1):
                assigned = proj.get("district_congressman") or proj.get("contractor_congressman") or "None"
                match_type = proj.get("match_type") or "unknown"
                name_match = loc_name_matches[i - 1]
                base = (
                    f"{i:02d}. assigned={assigned}  type={match_type}  "
                    f"loc_match={_short_loc_match(loc_match)}"
                )
                if name_match != loc_match:
                    base += f"  name_match={_short_loc_match(name_match)}"
                print(base)
                print(f"    name: {_short(proj.get('project_name',''))}")
                if proj.get("location"):
                    print(f"    loc:  {_short(proj.get('location',''), 160)}")
    finally:
        con.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

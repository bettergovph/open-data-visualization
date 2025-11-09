#!/usr/bin/env python3
"""Export dynasty JSON files (config and districts) from the dynasty database."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import asyncpg
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT_DIR / "dynasty-projects-config.json"
DEFAULT_DISTRICTS_PATH = ROOT_DIR / "districts.json"


async def _connect() -> asyncpg.Connection:
    load_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        user=os.getenv("POSTGRES_USER", "budget_admin"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        database=os.getenv("POSTGRES_DB_DYNASTY", "dynasty"),
    )
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    return conn


def _normalize_entries(rows: List[asyncpg.Record]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for row in rows:
        entry: Dict[str, Any] = {
            "id": row["id"],
            "first_name_pattern": row["first_name_pattern"],
            "last_name_pattern": row["last_name_pattern"],
            "display_name": row["display_name"],
            "province": row["province"],
            "district_number": row["district_number"],
            "is_city_district": row["is_city_district"],
            "terms": row["terms"] or [],
        }

        barangays_list = row["barangays"] or []
        if barangays_list or not row["is_city_district"] or row["barangays_file"] is None:
            entry["barangays"] = barangays_list

        if row["full_name"] is not None:
            entry["full_name"] = row["full_name"]
        if row["is_partylist"]:
            entry["is_partylist"] = True
        if row["family_connections"] is not None:
            entry["family_connections"] = row["family_connections"]
        if row["previous_positions"] is not None:
            entry["previous_positions"] = row["previous_positions"]
        if row["barangays_file"] is not None:
            entry["barangays_file"] = row["barangays_file"]

        normalized.append(entry)
    return normalized


def _export_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Export dynasty JSON data from the database")
    parser.add_argument(
        "--config-output",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Output path for dynasty-projects-config export (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--districts-output",
        type=Path,
        default=DEFAULT_DISTRICTS_PATH,
        help=f"Output path for districts export (default: {DEFAULT_DISTRICTS_PATH})",
    )
    args = parser.parse_args()

    conn = await _connect()
    try:
        config_rows = await conn.fetch(
            """
            SELECT id, first_name_pattern, last_name_pattern, display_name, full_name,
                   province, district_number, is_city_district, is_partylist,
                   barangays, terms, family_connections, previous_positions, barangays_file
            FROM dynasty_projects_congressmen_config
            ORDER BY id
            """
        )
        config_metadata_row = await conn.fetchrow(
            "SELECT metadata, verified_contractors FROM dynasty_projects_config_metadata WHERE id = 1"
        )

        district_rows = await conn.fetch(
            "SELECT name, entity_type, data FROM district_entries ORDER BY name"
        )
        district_metadata_row = await conn.fetchrow(
            "SELECT metadata, key_findings, validation, notes FROM district_dataset_metadata WHERE id = 1"
        )
    finally:
        await conn.close()

    config_payload = {
        "metadata": config_metadata_row["metadata"] if config_metadata_row else {},
        "target_congressmen": _normalize_entries(config_rows),
    }

    verified_contractors = (
        config_metadata_row["verified_contractors"] if config_metadata_row and config_metadata_row["verified_contractors"] is not None else {}
    )
    if verified_contractors:
        config_payload["verified_contractors"] = verified_contractors

    districts_payload: Dict[str, Any] = {
        "metadata": district_metadata_row["metadata"] if district_metadata_row else {},
        "districts": {},
        "key_findings": district_metadata_row["key_findings"] if district_metadata_row else {},
        "validation": district_metadata_row["validation"] if district_metadata_row else {},
        "notes": district_metadata_row["notes"] if district_metadata_row else {},
    }

    for row in district_rows:
        # row["data"] is already parsed by the JSON codec, so it's a dict
        data = row["data"]
        # Handle case where data might still be a string (for backward compatibility)
        if isinstance(data, str):
            data = json.loads(data)
        districts_payload["districts"][row["name"]] = data

    _export_json(args.config_output, config_payload)
    _export_json(args.districts_output, districts_payload)

    print(f"✅ Exported config to {args.config_output}")
    print(f"✅ Exported districts to {args.districts_output}")


if __name__ == "__main__":
    asyncio.run(main())



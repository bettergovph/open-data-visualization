#!/usr/bin/env python3
"""Verify that dynasty JSON configuration files match the dynasty database tables."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import asyncpg
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "dynasty-projects-config.json"
DISTRICTS_PATH = ROOT_DIR / "districts.json"


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


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _normalize_config_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for entry in entries:
        normalized.append(
            {
                "id": entry["id"],
                "first_name_pattern": entry["first_name_pattern"],
                "last_name_pattern": entry["last_name_pattern"],
                "display_name": entry["display_name"],
                "full_name": entry.get("full_name"),
                "province": entry.get("province"),
                "district_number": entry.get("district_number"),
                "is_city_district": entry.get("is_city_district", False),
                "is_partylist": entry.get("is_partylist", False),
                "barangays": entry.get("barangays", []),
                "terms": entry.get("terms", []),
                "family_connections": entry.get("family_connections"),
                "previous_positions": entry.get("previous_positions"),
                "barangays_file": entry.get("barangays_file"),
            }
        )
    normalized.sort(key=lambda item: item["id"])
    return normalized


def _normalize_district_entries(entries: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    normalized: Dict[str, Dict[str, Any]] = {}
    for name, data in entries.items():
        entity_type = "city" if "barangays" in data else "province"
        normalized[name] = {
            "entity_type": entity_type,
            "data": data,
        }
    return normalized


def _sorted_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


async def main() -> None:
    config_json = _load_json(CONFIG_PATH)
    districts_json = _load_json(DISTRICTS_PATH)

    expected_config = _normalize_config_entries(config_json.get("target_congressmen", []))
    expected_config_metadata = config_json.get("metadata", {})
    expected_config_verified = config_json.get("verified_contractors", {})
    expected_districts = _normalize_district_entries(districts_json.get("districts", {}))
    expected_metadata = {
        "metadata": districts_json.get("metadata", {}),
        "key_findings": districts_json.get("key_findings", {}),
        "validation": districts_json.get("validation", {}),
        "notes": districts_json.get("notes", {}),
    }

    conn = await _connect()
    try:
        db_config_rows = await conn.fetch(
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
        db_config_metadata = config_metadata_row["metadata"] if config_metadata_row else {}
        db_config_verified = (
            config_metadata_row["verified_contractors"] if config_metadata_row else {}
        )

        db_config = [
            {
                "id": row["id"],
                "first_name_pattern": row["first_name_pattern"],
                "last_name_pattern": row["last_name_pattern"],
                "display_name": row["display_name"],
                "full_name": row["full_name"],
                "province": row["province"],
                "district_number": row["district_number"],
                "is_city_district": row["is_city_district"],
                "is_partylist": row["is_partylist"],
                "barangays": row["barangays"] or [],
                "terms": row["terms"] or [],
                "family_connections": row["family_connections"],
                "previous_positions": row["previous_positions"],
                "barangays_file": row["barangays_file"],
            }
            for row in db_config_rows
        ]

        district_rows = await conn.fetch(
            "SELECT name, entity_type, data FROM district_entries"
        )
        db_districts = {row["name"]: {"entity_type": row["entity_type"], "data": row["data"]} for row in district_rows}

        metadata_row = await conn.fetchrow(
            "SELECT metadata, key_findings, validation, notes FROM district_dataset_metadata WHERE id = 1"
        )
        db_metadata = {
            "metadata": metadata_row["metadata"] if metadata_row else {},
            "key_findings": metadata_row["key_findings"] if metadata_row else {},
            "validation": metadata_row["validation"] if metadata_row else {},
            "notes": metadata_row["notes"] if metadata_row else {},
        }
    finally:
        await conn.close()

    ok = True

    if _sorted_json(db_config) != _sorted_json(expected_config):
        print("❌ dynasty_projects_congressmen_config differs from dynasty-projects-config.json", file=sys.stderr)
        ok = False

    if _sorted_json(db_config_metadata) != _sorted_json(expected_config_metadata):
        print("❌ dynasty_projects_config_metadata differs from dynasty-projects-config.json metadata", file=sys.stderr)
        ok = False

    if _sorted_json(db_config_verified) != _sorted_json(expected_config_verified):
        print("❌ dynasty_projects_config_metadata verified_contractors differs from dynasty-projects-config.json", file=sys.stderr)
        ok = False

    if _sorted_json(db_districts) != _sorted_json(expected_districts):
        print("❌ district_entries differs from districts.json", file=sys.stderr)
        ok = False

    if _sorted_json(db_metadata) != _sorted_json(expected_metadata):
        print("❌ district_dataset_metadata differs from districts.json metadata", file=sys.stderr)
        ok = False

    if ok:
        print("✅ dynasty JSON files match the dynasty database tables")
    else:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())



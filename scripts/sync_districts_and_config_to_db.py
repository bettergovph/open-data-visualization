#!/usr/bin/env python3
"""Sync dynasty-projects-config.json and districts.json into the dynasty database."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict

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


async def _ensure_tables(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dynasty_projects_congressmen_config (
            id INTEGER PRIMARY KEY,
            first_name_pattern TEXT NOT NULL,
            last_name_pattern TEXT NOT NULL,
            display_name TEXT NOT NULL,
            full_name TEXT,
            province TEXT,
            district_number TEXT,
            is_city_district BOOLEAN NOT NULL DEFAULT FALSE,
            is_partylist BOOLEAN NOT NULL DEFAULT FALSE,
            barangays JSONB NOT NULL DEFAULT '[]'::jsonb,
            terms JSONB NOT NULL,
            family_connections JSONB,
            previous_positions JSONB,
            barangays_file TEXT,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
        """
    )

    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dynasty_projects_config_metadata (
            id INTEGER PRIMARY KEY,
            metadata JSONB NOT NULL,
            verified_contractors JSONB,
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
        """
    )

    await conn.execute(
        "ALTER TABLE dynasty_projects_config_metadata ADD COLUMN IF NOT EXISTS verified_contractors JSONB"
    )

    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS district_entries (
            name TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            data JSONB NOT NULL,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
        """
    )

    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS district_dataset_metadata (
            id INTEGER PRIMARY KEY,
            metadata JSONB NOT NULL,
            key_findings JSONB,
            validation JSONB,
            notes JSONB,
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
        )
        """
    )


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


async def _sync_config(conn: asyncpg.Connection, config_data: Dict[str, Any]) -> None:
    entries = config_data.get("target_congressmen", [])
    metadata = config_data.get("metadata", {})
    verified_contractors = config_data.get("verified_contractors", {})
    if not entries:
        raise RuntimeError("dynasty-projects-config.json contains no target_congressmen entries")

    ids = [entry["id"] for entry in entries]

    await conn.execute(
        "DELETE FROM dynasty_projects_congressmen_config WHERE NOT (id = ANY($1::int[]))",
        ids,
    )

    for entry in entries:
        barangays = entry.get("barangays", []) or []
        terms = entry.get("terms", []) or []
        family_connections = entry.get("family_connections")
        previous_positions = entry.get("previous_positions")

        await conn.execute(
            """
            INSERT INTO dynasty_projects_congressmen_config (
                id,
                first_name_pattern,
                last_name_pattern,
                display_name,
                full_name,
                province,
                district_number,
                is_city_district,
                is_partylist,
                barangays,
                terms,
                family_connections,
                previous_positions,
                barangays_file,
                updated_at
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7,
                $8, $9,
                $10,
                $11,
                $12,
                $13,
                $14,
                NOW()
            )
            ON CONFLICT (id) DO UPDATE SET
                first_name_pattern = EXCLUDED.first_name_pattern,
                last_name_pattern = EXCLUDED.last_name_pattern,
                display_name = EXCLUDED.display_name,
                full_name = EXCLUDED.full_name,
                province = EXCLUDED.province,
                district_number = EXCLUDED.district_number,
                is_city_district = EXCLUDED.is_city_district,
                is_partylist = EXCLUDED.is_partylist,
                barangays = EXCLUDED.barangays,
                terms = EXCLUDED.terms,
                family_connections = EXCLUDED.family_connections,
                previous_positions = EXCLUDED.previous_positions,
                barangays_file = EXCLUDED.barangays_file,
                updated_at = NOW()
            """,
            entry["id"],
            entry["first_name_pattern"],
            entry["last_name_pattern"],
            entry["display_name"],
            entry.get("full_name"),
            entry.get("province"),
            entry.get("district_number"),
            entry.get("is_city_district", False),
            entry.get("is_partylist", False),
            barangays,
            terms,
            family_connections,
            previous_positions,
            entry.get("barangays_file"),
        )

    await conn.execute(
        """
        INSERT INTO dynasty_projects_config_metadata (id, metadata, verified_contractors, updated_at)
        VALUES ($1, $2, $3, NOW())
        ON CONFLICT (id) DO UPDATE SET
            metadata = EXCLUDED.metadata,
            verified_contractors = EXCLUDED.verified_contractors,
            updated_at = NOW()
        """,
        1,
        metadata,
        verified_contractors,
    )


async def _sync_districts(conn: asyncpg.Connection, districts_data: Dict[str, Any]) -> None:
    districts = districts_data.get("districts", {})
    if not districts:
        raise RuntimeError("districts.json contains no districts entries")

    names = list(districts.keys())

    await conn.execute(
        "DELETE FROM district_entries WHERE NOT (name = ANY($1::text[]))",
        names,
    )

    for name, detail in districts.items():
        entity_type = detail.get("entity_type")
        if not entity_type:
            entity_type = "city" if "barangays" in detail else "province"
        await conn.execute(
            """
            INSERT INTO district_entries (name, entity_type, data, updated_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (name) DO UPDATE SET
                entity_type = EXCLUDED.entity_type,
                data = EXCLUDED.data,
                updated_at = NOW()
            """,
            name,
            entity_type,
            detail,
        )

    await conn.execute(
        """
        INSERT INTO district_dataset_metadata (
            id, metadata, key_findings, validation, notes, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, NOW())
        ON CONFLICT (id) DO UPDATE SET
            metadata = EXCLUDED.metadata,
            key_findings = EXCLUDED.key_findings,
            validation = EXCLUDED.validation,
            notes = EXCLUDED.notes,
            updated_at = NOW()
        """,
        1,
        districts_data.get("metadata", {}),
        districts_data.get("key_findings", {}),
        districts_data.get("validation", {}),
        districts_data.get("notes", {}),
    )


async def main() -> None:
    config_data = _load_json(CONFIG_PATH)
    districts_data = _load_json(DISTRICTS_PATH)

    conn = await _connect()
    try:
        await _ensure_tables(conn)
        async with conn.transaction():
            await _sync_config(conn, config_data)
            await _sync_districts(conn, districts_data)
        print("✅ dynasty-projects-config.json and districts.json successfully synced to dynasty DB")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())



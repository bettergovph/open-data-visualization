#!/usr/bin/env python3
"""
Import PCIJ flood control investigative tables into the dynasty database.

This script pulls the public Flourish visualisations embedded in
"Five Reveals from the Flood-Control Data" (PCIJ, 31 Aug 2025) and
translates them into structured records for:

- politician ↔ contractor relationships (with source URLs and notes)
- contractor organisation metadata (project values, CPES flags, etc.)
- basic political_dynasties entries for newly referenced lawmakers

Run this script whenever PCIJ refreshes the underlying Flourish tables.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import asyncpg
import requests
from dotenv import load_dotenv

ARTICLE_URL = "https://pcij.org/2025/08/31/5-reveals-from-the-flood-control-data/"
TABLE_LAWMAKERS = "https://public.flourish.studio/visualisation/24883358/visualisation.json"
TABLE_CONTRACTORS = "https://public.flourish.studio/visualisation/24821782/visualisation.json"

SOURCE_LABEL = "PCIJ Flood-Control Data (2025-08-31)"


@dataclass
class PersonMeta:
    """Metadata used to locate or create a political_dynasties entry."""

    first_name: str
    last_name: str
    nickname: Optional[str] = None
    middle_name: Optional[str] = None
    suffix: Optional[str] = None
    position: Optional[str] = None
    party: Optional[str] = None
    district: Optional[str] = None
    province: Optional[str] = None
    region: Optional[str] = None
    government_branch: str = "Legislative"
    position_category: Optional[str] = None
    government_level: str = "national"
    year: Optional[int] = 2025
    mode: str = "ensure"  # ensure | update | lookup


PERSON_METADATA: Dict[str, PersonMeta] = {
    'Francis "Chiz" Escudero': PersonMeta(
        first_name="Francis Joseph",
        last_name="Escudero",
        nickname="Chiz",
        party="NPC",
        position="SENATOR",
        position_category="Elected Officials",
        year=2025,
        mode="ensure",
    ),
    "Joel Villanueva": PersonMeta(
        first_name="Joel",
        last_name="Villanueva",
        party="Independent",
        position="SENATOR",
        position_category="Elected Officials",
        year=2025,
        mode="ensure",
    ),
    'Christoper Lawrence "Bong" Go': PersonMeta(
        first_name="Christopher Lawrence",
        last_name="Go",
        nickname="Bong",
        party="PDP–Laban",
        position="SENATOR",
        position_category="Elected Officials",
        year=2025,
        mode="ensure",
    ),
    "Elizaldy Co": PersonMeta(
        first_name="Elizaldy",
        last_name="Co",
        party="Ako Bicol",
        district="Ako Bicol Party-list",
        position="Representative, Ako Bicol Party-list",
        position_category="Representative",
        year=2025,
        mode="update",
    ),
    "Ferdinand Beltran": PersonMeta(
        first_name="Ferdinand",
        last_name="Beltran",
        party="Magbubukid Party-list",
        district="Magbubukid Party-list",
        position="Representative, Magbubukid Party-list",
        position_category="Representative",
        year=2025,
        mode="update",
    ),
    "Edwin Gardiola": PersonMeta(
        first_name="Edwin",
        last_name="Gardiola",
        party="CWS Party-list",
        district="CWS Party-list",
        position="Representative, CWS Party-list",
        position_category="Representative",
        year=2025,
        mode="update",
    ),
    "Munir Arbison Jr.": PersonMeta(
        first_name="Munir",
        last_name="Arbison",
        suffix="Jr.",
        party="Kapuso PM Party-list",
        district="Kapuso PM Party-list",
        position="Representative, Kapuso PM Party-list",
        position_category="Representative",
        year=2025,
        mode="ensure",
    ),
    "Munir Arbison": PersonMeta(
        first_name="Munir",
        last_name="Arbison",
        party="Lakas–CMD",
        district="Sulu–2nd District",
        position="Member, House of Representatives (Sulu–2nd District)",
        position_category="Representative",
        year=2016,
        mode="lookup",
    ),
    'Ramon "Jolo" Revillla': PersonMeta(
        first_name="Ramon Joseph",
        last_name="Revilla",
        nickname="Jolo",
        party="Lakas–CMD",
        province="Cavite",
        district="Cavite–1st District",
        position="Member, House of Representatives (Cavite–1st District)",
        position_category="Representative",
        year=2025,
        mode="ensure",
    ),
    "Lani Mercado-Revilla": PersonMeta(
        first_name="Lani",
        last_name="Revilla",
        party="Lakas–CMD",
        province="Cavite",
        district="Cavite–2nd District",
        position="Member, House of Representatives (Cavite–2nd District)",
        position_category="Representative",
        year=2025,
        mode="ensure",
    ),
    "Bryan Revilla": PersonMeta(
        first_name="Bryan",
        last_name="Revilla",
        party="Agimat Party-list",
        district="Agimat Party-list",
        position="Representative, Agimat Party-list",
        position_category="Representative",
        year=2025,
        mode="ensure",
    ),
    "Ramon Rodrigo Gutierrez": PersonMeta(
        first_name="Ramon Rodrigo",
        last_name="Gutierrez",
        party="1-Rider Party-list",
        district="1-Rider Party-list",
        position="Representative, 1-Rider Party-list",
        position_category="Representative",
        year=2025,
        mode="update",
    ),
    "Jernie Jett Nisay": PersonMeta(
        first_name="Jernie Jett",
        last_name="Nisay",
        party="Pusong Pinoy Party-list",
        district="Pusong Pinoy Party-list",
        position="Representative, Pusong Pinoy Party-list",
        position_category="Representative",
        year=2025,
        mode="ensure",
    ),
    "Caroline Agyao": PersonMeta(
        first_name="Caroline",
        last_name="Agyao",
        province="Kalinga",
        district="Kalinga–Lone District",
        position="Member, House of Representatives (Kalinga–Lone District)",
        position_category="Representative",
        year=2025,
        mode="update",
    ),
    "Carlos Loria": PersonMeta(
        first_name="Carlos",
        last_name="Loria",
        province="Albay",
        district="Albay–2nd District",
        position="Member, House of Representatives (Albay–2nd District)",
        position_category="Representative",
        year=2025,
        mode="ensure",
    ),
    "Augustina Pancho": PersonMeta(
        first_name="Augustina",
        last_name="Pancho",
        province="Bulacan",
        district="Bulacan–2nd District",
        position="Member, House of Representatives (Bulacan–2nd District)",
        position_category="Representative",
        year=2025,
        mode="ensure",
    ),
    "Cristina Angeles": PersonMeta(
        first_name="Maria Cristina",
        last_name="Angeles",
        province="Tarlac",
        district="Tarlac–2nd District",
        position="Member, House of Representatives (Tarlac–2nd District)",
        position_category="Representative",
        year=2025,
        mode="ensure",
    ),
    "Michaela Gonzales": PersonMeta(
        first_name="Michaela",
        last_name="Gonzales",
        province="Pampanga",
        district="Pampanga–3rd District",
        position="Member, House of Representatives (Pampanga–3rd District)",
        position_category="Representative",
        year=2025,
        mode="ensure",
    ),
}


def parse_currency(value: str) -> Decimal:
    """Convert Peso strings with commas into Decimal."""
    clean = value.replace("₱", "").replace(",", "").strip()
    if not clean:
        return Decimal("0")
    return Decimal(clean)


def split_contractors(raw: str) -> List[str]:
    """Split contractor cells that contain semicolons or newlines."""
    parts = re.split(r";|\n", raw)
    return [p.strip().upper() for p in parts if p.strip()]


async def ensure_person(conn: asyncpg.Connection, label: str, meta: PersonMeta) -> int:
    """Ensure a political_dynasties entry exists (or is updated) for the person."""
    async def update_person(person_id: int) -> None:
        await conn.execute(
            """
            UPDATE political_dynasties
               SET nickname = $3,
                   middle_name = $4,
                   suffix = $5,
                   party = $6,
                   region = $7,
                   province = $8,
                   position = $9,
                   position_category = $10,
                   government_branch = $11,
                   government_level = $12,
                   district = $13,
                   year = $14,
                   last_updated = $15,
                   canonical_first_name = UPPER(TRIM($1)),
                   canonical_name = UPPER(TRIM($1) || ' ' || TRIM($2))
             WHERE id = $16
            """,
            meta.first_name,
            meta.last_name,
            meta.nickname,
            meta.middle_name,
            meta.suffix,
            meta.party,
            meta.region,
            meta.province,
            meta.position,
            meta.position_category,
            meta.government_branch,
            meta.government_level,
            meta.district,
            meta.year,
            datetime.utcnow(),
            person_id,
        )

    existing_specific = None
    if meta.position:
        existing_specific = await conn.fetchrow(
            """
            SELECT id, position, year
              FROM political_dynasties
             WHERE UPPER(TRIM(first_name)) = UPPER($1)
               AND UPPER(TRIM(last_name)) = UPPER($2)
               AND UPPER(COALESCE(position, '')) = UPPER($3)
             ORDER BY year DESC NULLS LAST, id DESC
             LIMIT 1
            """,
            meta.first_name,
            meta.last_name,
            meta.position,
        )

    if meta.mode == "lookup":
        if existing_specific:
            return existing_specific["id"]
        fallback = await conn.fetchrow(
            """
            SELECT id
              FROM political_dynasties
             WHERE UPPER(TRIM(first_name)) = UPPER($1)
               AND UPPER(TRIM(last_name)) = UPPER($2)
             ORDER BY year DESC NULLS LAST, id DESC
             LIMIT 1
            """,
            meta.first_name,
            meta.last_name,
        )
        if not fallback:
            raise RuntimeError(f"Could not locate political_dynasties entry for {label}")
        return fallback["id"]

    if meta.mode == "update":
        target = existing_specific
        if not target:
            target = await conn.fetchrow(
                """
                SELECT id
                  FROM political_dynasties
                 WHERE UPPER(TRIM(first_name)) = UPPER($1)
                   AND UPPER(TRIM(last_name)) = UPPER($2)
                 ORDER BY year DESC NULLS LAST, id DESC
                 LIMIT 1
                """,
                meta.first_name,
                meta.last_name,
            )
        if not target:
            raise RuntimeError(f"No existing political_dynasties row to update for {label}")
        await update_person(target["id"])
        return target["id"]

    # mode == ensure
    if existing_specific:
        await update_person(existing_specific["id"])
        return existing_specific["id"]

    person_id = await conn.fetchval(
        """
        INSERT INTO political_dynasties (
            first_name,
            last_name,
            nickname,
            middle_name,
            suffix,
            party,
            region,
            province,
            municipality_city,
            position,
            year,
            government_branch,
            position_category,
            appointment_type,
            government_level,
            department,
            organization,
            canonical_first_name,
            canonical_name,
            dynasty_family_id,
            birth_date,
            last_updated,
            district
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,NULL,
            $9,$10,$11,$12,'elected',$13,NULL,NULL,
            UPPER(TRIM($16)), UPPER(TRIM($16) || ' ' || TRIM($17)),
            NULL,NULL,$14,$15
        )
        RETURNING id
        """,
        meta.first_name,
        meta.last_name,
        meta.nickname,
        meta.middle_name,
        meta.suffix,
        meta.party,
        meta.region,
        meta.province,
        meta.position,
        meta.year,
        meta.government_branch,
        meta.position_category or ("Representative" if meta.position and "Representative" in meta.position else "Elected Officials"),
        meta.government_level,
        datetime.utcnow(),
        meta.district,
        meta.first_name,
        meta.last_name,
    )
    return person_id


async def upsert_company_affiliation(
    conn: asyncpg.Connection,
    company: str,
    person_label: str,
    role: str,
) -> None:
    """Upsert into company_affiliations with article source."""
    await conn.execute(
        """
        INSERT INTO company_affiliations (
            company_name,
            person_name,
            role,
            source_url,
            confidence_level
        ) VALUES ($1,$2,$3,$4,$5)
        ON CONFLICT (company_name, person_name, role)
        DO UPDATE SET
            source_url = EXCLUDED.source_url,
            confidence_level = EXCLUDED.confidence_level
        """,
        company,
        person_label,
        role,
        ARTICLE_URL,
        8,
    )


async def upsert_politician_contractor(
    conn: asyncpg.Connection,
    person_id: int,
    contractor: str,
    affiliation: str,
) -> None:
    """Upsert politician_contractors with notes and source label."""
    now = datetime.utcnow()
    await conn.execute(
        """
        INSERT INTO politician_contractors (
            politician_id,
            contractor_name,
            match_confidence,
            notes,
            source,
            created_at,
            updated_at
        ) VALUES ($1,$2,$3,$4,$5,$6,$6)
        ON CONFLICT (politician_id, contractor_name)
        DO UPDATE SET
            match_confidence = EXCLUDED.match_confidence,
            notes = EXCLUDED.notes,
            source = EXCLUDED.source,
            updated_at = EXCLUDED.updated_at
        """,
        person_id,
        contractor,
        Decimal("1.00"),
        affiliation,
        SOURCE_LABEL,
        now,
    )


async def upsert_contractor_organization(
    conn: asyncpg.Connection,
    row: Dict[str, str],
) -> None:
    """Insert or update contractors_organizations with risk metadata."""
    name = row["Contractor"].upper()
    no_projects = int(row["No. of projects"])
    value_total = parse_currency(row["Value of projects"])
    breakdown = {
        "Luzon": float(parse_currency(row["Luzon"])),
        "Visayas": float(parse_currency(row["Visayas"])),
        "Mindanao": float(parse_currency(row["Mindanao"])),
    }
    payload = {
        "projects": no_projects,
        "value_of_projects": float(value_total),
        "regional_breakdown": breakdown,
        "had_poor_or_unsatisfactory_cpes": row["Had poor/unsatisfactory CPES rating"].strip().lower() == "yes",
        "has_past_controversies": row["Has past controversies*"].strip().lower() == "yes",
        "owner_manager": row["Owner/Manager"].strip(),
    }
    founders_raw = [f.strip() for f in row["Founders"].split(";") if f.strip()]
    affiliations: List[str] = []
    if row["Owner/Manager"].strip():
        affiliations.append(row["Owner/Manager"].strip())
    affiliations.extend(founders_raw)

    existing = await conn.fetchrow(
        """
        SELECT id FROM contractors_organizations
         WHERE organization_name = $1
        """,
        name,
    )

    if existing:
        await conn.execute(
            """
            UPDATE contractors_organizations
               SET organization_type = $2,
                   business_scope = $3,
                   political_affiliations = $4,
                   total_contract_value = $5,
                   website = $6,
                   updated_at = NOW()
             WHERE id = $1
            """,
            existing["id"],
            "Construction Company",
            json.dumps(payload, ensure_ascii=False),
            affiliations or None,
            value_total,
            ARTICLE_URL,
        )
    else:
        await conn.execute(
            """
            INSERT INTO contractors_organizations (
                organization_name,
                organization_type,
                business_scope,
                political_affiliations,
                total_contract_value,
                website,
                created_at,
                updated_at
            ) VALUES ($1,$2,$3,$4,$5,$6,NOW(),NOW())
            """,
            name,
            "Construction Company",
            json.dumps(payload, ensure_ascii=False),
            affiliations or None,
            value_total,
            ARTICLE_URL,
        )


def normalise_affiliation(text: str) -> str:
    """Condense whitespace in affiliation notes."""
    return re.sub(r"\s+", " ", text.strip())


async def process(conn: asyncpg.Connection) -> None:
    """Main orchestration."""
    lawmaker_table = requests.get(TABLE_LAWMAKERS, timeout=30).json()
    contractor_table = requests.get(TABLE_CONTRACTORS, timeout=30).json()

    lawmaker_rows = lawmaker_table["data"]["rows"][1:]
    contractor_headers = contractor_table["data"]["rows"][0]
    contractor_rows = [
        dict(zip(contractor_headers, row))
        for row in contractor_table["data"]["rows"][1:]
    ]

    for count, lawmaker, position, contractors, affiliation in lawmaker_rows:
        meta = PERSON_METADATA.get(lawmaker)
        if not meta:
            raise KeyError(f"No metadata configured for lawmaker '{lawmaker}'")
        person_id = await ensure_person(conn, lawmaker, meta)

        affiliation_clean = normalise_affiliation(affiliation)
        for contractor in split_contractors(contractors):
            if not contractor:
                continue
            await upsert_company_affiliation(conn, contractor, lawmaker, affiliation_clean)
            await upsert_politician_contractor(conn, person_id, contractor, affiliation_clean)

    for row in contractor_rows:
        await upsert_contractor_organization(conn, row)


async def main() -> None:
    load_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "budget_admin"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
        database=os.getenv("POSTGRES_DB_DYNASTY", "dynasty"),
    )
    try:
        await process(conn)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())



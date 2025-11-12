#!/usr/bin/env python3
"""
Bulk-import contractor relationships from the Rappler Politicontractors tracker.

The spreadsheet lives at `database/POLITICONTRACTORS.xlsx` and contains the
columns the newsroom cares about: politician group labels, specific positions,
contractor names (sometimes with aliases), and notes about the relationship.

This script normalizes that data and upserts it into the
`contractor_dynasty_matches` table so the constellation network can render the
contractor nodes mentioned in the tracker (e.g., Hi-Tone, FS Co, Centerways,
Dragon Twelve, Ferdstar, Tonka, Alro, JVN Construction, BHM Construction,
Makapa Corporation, Megapolitan Builders, etc.).

Highlights:
    * Parses the spreadsheet with pandas.
    * Cleans company names (splits on "/", strips "(FORMERLY ...)" notes).
    * Maps each contractor row to one or more dynasty figures, with manual
      overrides where the spreadsheet only lists nicknames.
    * Aggregates all positions/relationship blurbs per (company, dynasty) pair.
    * Upserts into Postgres with ON CONFLICT (company_name, dynasty_full_name).

Usage:
    $ source .env
    $ python scripts/database/import_politicontractors.py
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import os

import asyncpg
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent.parent
SHEET_PATH = BASE_DIR / "database" / "POLITICONTRACTORS.xlsx"
SOURCE_LABEL = "POLITICONTRACTORS.xlsx"

# Manual name overrides so we match canonical names and family groups.
CUSTOM_NAME_OVERRIDES: Dict[str, List[str]] = {
    "Anna Bondoc & Jayson Sagum": ["Anna York Bondoc", "Jayson Sagum"],
    "Caroline Agyao & Allen Jesse Mangaoang": ["Caroline Agyao", "Allen Jesse Mangaoang"],
    "Chavit Singson & family": [
        "Luis Chavit Singson",
        "Randy Singson",
        "Jerry Singson",
        "Ryan Singson",
        "Ronald Singson",
    ],
    "Dong, Mica, & Brenz Gonzales": [
        "Aurelio Gonzales Jr.",
        "Mica Gonzales",
        "Aurelio Brenz Gonzales",
    ],
    "Eddison & Marilyn Veneracion": ["Eddison Veneracion", "Marilyn Veneracion"],
    "Matugas-Abejo family": ["Francisco Matugas", "Elizabeth Matugas"],
    "Revilla family": ["Jolo Revilla", "Lani Mercado Revilla", "Bryan Revilla"],
    "Romeo & Eleanor Momo": ["Romeo Momo", "Eleanor Momo"],
    "Ronnie C. Lagnada": ["Ronnie Vicente Lagnada"],
    "Villar Family": ["Mark Villar", "Camille Villar"],
    "Dette and Chiz Escudero": ["Francis Escudero", "Bernadette Escudero"],
}

# Keywords that mean the fragment we extracted from the "Position" column is not
# actually a name (e.g., "Former mayor", "Incumbent representative").
NON_NAME_KEYWORDS = {
    "former",
    "incumbent",
    "representative",
    "senator",
    "mayor",
    "governor",
    "vice",
    "district",
    "city",
    "family",
    "councilor",
    "party-list",
}

# Regexes reused for text cleanup.
SPLIT_PERSON_PATTERN = re.compile(r"\s*(?:&| and |,|/|\+|\\)\s*", re.IGNORECASE)
PAREN_CONTENT_PATTERN = re.compile(r"([^\(\)]+?)\s*\(")


def normalize_ascii(value: str | float | int | None) -> str:
    """Normalize text to ASCII (best effort) and strip surrounding whitespace."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value)
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    return " ".join(text.split())


def extract_company_names(contractor: str) -> List[str]:
    """Split composite contractor strings (e.g. 'A / B (FORMERLY ...)') into names."""
    clean = normalize_ascii(contractor)
    if not clean:
        return []

    # Break on "/" which usually separates joint venture partners / aliases.
    raw_parts = [part.strip() for part in clean.split("/") if part.strip()]
    results: List[str] = []
    for part in raw_parts or [clean]:
        # Drop trailing "(FORMERLY ...)" style notes.
        base = part.split("(")[0].strip(" .")
        base = " ".join(base.split())
        if base:
            results.append(base)
    # Deduplicate while preserving order.
    seen = set()
    unique = []
    for name in results:
        if name not in seen:
            unique.append(name)
            seen.add(name)
    return unique


def extract_names(label: str, position: str) -> List[str]:
    """Derive person names from the spreadsheet's Politician + Position columns."""
    original_label = (label or "").strip()
    if not original_label:
        return []

    if original_label in CUSTOM_NAME_OVERRIDES:
        return CUSTOM_NAME_OVERRIDES[original_label]

    normalized_label = normalize_ascii(original_label)
    position_text = normalize_ascii(position or "").replace("<br>", "\n")

    names: List[str] = []
    if position_text:
        for match in PAREN_CONTENT_PATTERN.findall(position_text):
            candidate = match.strip().strip(",")
            if not candidate:
                continue
            lowered = candidate.lower()
            if any(keyword in lowered for keyword in NON_NAME_KEYWORDS):
                continue
            cleaned = " ".join(candidate.replace('"', " ").split())
            if cleaned and cleaned not in names:
                names.append(cleaned)

    if not names:
        # Fall back to the Politician label itself (splitting on punctuation).
        segments = [
            segment.strip()
            for segment in SPLIT_PERSON_PATTERN.split(normalized_label)
            if segment.strip()
        ]
        last_names = [seg.split()[-1] for seg in segments if len(seg.split()) >= 2]
        default_last = last_names[-1] if last_names else (normalized_label.split()[-1] if normalized_label else "")
        for seg in segments:
            tokens = seg.split()
            if len(tokens) == 1 and default_last:
                names.append(f"{tokens[0]} {default_last}")
            else:
                names.append(seg)
    else:
        # Ensure single-token names (e.g., "Jolo") inherit a family name.
        label_without_family = re.sub(r"\bfamily\b", "", normalized_label, flags=re.IGNORECASE).strip()
        segments = [
            segment.strip()
            for segment in SPLIT_PERSON_PATTERN.split(label_without_family)
            if segment.strip()
        ]
        last_names = [seg.split()[-1] for seg in segments if len(seg.split()) >= 2]
        default_last = last_names[-1] if last_names else (label_without_family.split()[-1] if label_without_family else "")
        enriched: List[str] = []
        for name in names:
            tokens = name.split()
            if len(tokens) == 1 and default_last:
                enriched.append(f"{name} {default_last}")
            else:
                enriched.append(name)
        names = enriched

    cleaned_names = []
    for name in names:
        name = " ".join(name.split())
        if not name:
            continue
        lowered = name.lower()
        if lowered in ("former", "incumbent"):
            continue
        if name not in cleaned_names:
            cleaned_names.append(name)
    return cleaned_names


def split_first_last(full_name: str) -> Tuple[str, str]:
    """Split a full name into (first_name, last_name)."""
    parts = full_name.split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return " ".join(parts[:-1]), parts[-1]


async def load_dataframe() -> pd.DataFrame:
    if not SHEET_PATH.exists():
        raise FileNotFoundError(f"Missing spreadsheet: {SHEET_PATH}")
    return pd.read_excel(SHEET_PATH)


def aggregate_entries(df: pd.DataFrame) -> Tuple[Dict[Tuple[str, str], Dict[str, Iterable[str]]], List[str]]:
    """Turn the spreadsheet into a dict keyed by (company, dynasty_full_name)."""
    entries: Dict[Tuple[str, str], Dict[str, set]] = {}
    unresolved_labels: List[str] = []

    relation_col = "Politician's relation/connection to contractor"

    for _, row in df.iterrows():
        contractor_raw = normalize_ascii(row.get("Contractor"))
        politician_label = (row.get("Politician") or "").strip()

        if not contractor_raw or not politician_label:
            continue

        companies = extract_company_names(contractor_raw)
        if not companies:
            continue

        position_text = normalize_ascii(row.get("Position"))
        relation_text = normalize_ascii(row.get(relation_col))

        names = extract_names(politician_label, position_text)
        if not names:
            unresolved_labels.append(politician_label)
            continue

        for company in companies:
            key_company = company
            for full_name in names:
                full_name_norm = normalize_ascii(full_name)
                if not full_name_norm:
                    continue

                dynasty_first, dynasty_last = split_first_last(full_name_norm)
                key = (key_company, full_name_norm)
                entry = entries.setdefault(
                    key,
                    {
                        "positions": set(),
                        "connections": set(),
                        "dynasty_first_name": dynasty_first,
                        "dynasty_last_name": dynasty_last,
                        "person_name": full_name_norm,
                    },
                )
                if position_text:
                    entry["positions"].add(position_text)
                if relation_text:
                    entry["connections"].add(relation_text)

    return entries, unresolved_labels


async def lookup_person_id(cache: Dict[Tuple[str, str], int], conn: asyncpg.Connection, first: str, last: str) -> int | None:
    key = (first.upper().strip(), last.upper().strip())
    if key in cache:
        return cache[key]
    row = await conn.fetchrow(
        """
        SELECT id FROM political_dynasties
        WHERE UPPER(TRIM(first_name)) = $1
          AND UPPER(TRIM(last_name)) = $2
        LIMIT 1
        """,
        key[0],
        key[1],
    )
    if row:
        cache[key] = row["id"]
        return row["id"]
    return None


async def upsert_entries(conn: asyncpg.Connection, entries: Dict[Tuple[str, str], Dict[str, Iterable[str]]]) -> Tuple[int, int, int, int]:
    """Perform the database upsert and return (inserted, updated) counts."""
    sql = """
        INSERT INTO contractor_dynasty_matches (
            company_name,
            person_name,
            role,
            dynasty_full_name,
            dynasty_first_name,
            dynasty_last_name,
            matched_at,
            source_csv_file
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
        ON CONFLICT (company_name, dynasty_full_name)
        DO UPDATE SET
            person_name = EXCLUDED.person_name,
            role = EXCLUDED.role,
            dynasty_first_name = EXCLUDED.dynasty_first_name,
            dynasty_last_name = EXCLUDED.dynasty_last_name,
            matched_at = EXCLUDED.matched_at,
            source_csv_file = EXCLUDED.source_csv_file
        RETURNING xmax = 0 AS inserted
    """

    matches_inserted = 0
    matches_updated = 0
    polit_inserted = 0
    polit_updated = 0
    now = datetime.utcnow()
    lookup_cache: Dict[Tuple[str, str], int] = {}

    contractor_sql = """
        INSERT INTO politician_contractors (
            politician_id,
            contractor_name,
            match_confidence,
            notes,
            source,
            created_at,
            updated_at
        ) VALUES ($1,$2,$3,$4,$5,$6,$7)
        ON CONFLICT (politician_id, contractor_name)
        DO UPDATE SET
            match_confidence = EXCLUDED.match_confidence,
            notes = EXCLUDED.notes,
            source = EXCLUDED.source,
            updated_at = EXCLUDED.updated_at
        RETURNING xmax = 0 AS inserted
    """

    for (company, full_name), payload in entries.items():
        positions = sorted(payload["positions"])
        connections = sorted(payload["connections"])

        role_parts = []
        if positions:
            role_parts.append("Positions: " + "; ".join(positions))
        if connections:
            role_parts.append("Connections: " + "; ".join(connections))
        role = " | ".join(role_parts) if role_parts else "Listed in Rappler Politicontractors tracker"

        result = await conn.fetchrow(
            sql,
            company,
            payload["person_name"],
            role,
            full_name,
            payload["dynasty_first_name"],
            payload["dynasty_last_name"],
            now,
            SOURCE_LABEL,
        )
        if result and result["inserted"]:
            matches_inserted += 1
        else:
            matches_updated += 1

        person_id = await lookup_person_id(lookup_cache, conn, payload["dynasty_first_name"], payload["dynasty_last_name"])
        if person_id:
            notes = role
            result_pc = await conn.fetchrow(
                contractor_sql,
                person_id,
                company,
                1.00,
                notes,
                SOURCE_LABEL,
                now,
                now,
            )
            if result_pc and result_pc["inserted"]:
                polit_inserted += 1
            else:
                polit_updated += 1

    return matches_inserted, matches_updated, polit_inserted, polit_updated


async def main() -> None:
    db_kwargs = {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "user": os.getenv("POSTGRES_USER", "budget_admin"),
        "password": os.getenv("POSTGRES_PASSWORD", "wuQ5gBYCKkZiOGb61chLcByMu"),
        "database": os.getenv("POSTGRES_DB_DYNASTY", "dynasty"),
    }

    print("📥 Loading Politicontractors spreadsheet…")
    df = await load_dataframe()
    entries, unresolved = aggregate_entries(df)

    if unresolved:
        unique_unresolved = sorted(set(unresolved))
        print("\n⚠️  Could not infer specific names for the following labels:")
        for label in unique_unresolved:
            print(f"   - {label}")
        print("   (You can extend CUSTOM_NAME_OVERRIDES to handle these manually.)")

    print(f"\n🧮 Prepared {len(entries)} contractor ↔ dynasty pairs")

    conn = await asyncpg.connect(**db_kwargs)
    try:
        match_ins, match_upd, polit_ins, polit_upd = await upsert_entries(conn, entries)
    finally:
        await conn.close()

    print(
        "\n✅ Upsert complete!"
        f" contractor_dynasty_matches → inserted: {match_ins:,}, updated: {match_upd:,};"
        f" politician_contractors → inserted: {polit_ins:,}, updated: {polit_upd:,}."
    )


if __name__ == "__main__":
    asyncio.run(main())


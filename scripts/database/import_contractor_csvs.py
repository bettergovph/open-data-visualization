#!/usr/bin/env python3
"""
Import precise contractor data from CSV files into political_dynasties.

This script reads the CSV files in the database folder (e.g., AlphaOmega_Stockholders_Officers.csv)
and imports all names with their exact roles, positions, and shareholdings into the dynasty database.

Usage:
    $ source .env
    $ python scripts/database/import_contractor_csvs.py
"""

from __future__ import annotations

import asyncio
import csv
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import asyncpg
from dotenv import load_dotenv

load_dotenv()

SOURCE_LABEL = "PCIJ Flood-Control Records - CSV Data"
DATABASE_DIR = Path(__file__).resolve().parent.parent.parent / "database"

# Map CSV filename prefixes to contractor names
CONTRACTOR_NAME_MAP: Dict[str, str] = {
    "AD_Gonzales": "A.D. GONZALES JR. CONSTRUCTION & TRADING CO. INC.",
    "AlphaOmega": "ALPHA & OMEGA GEN. CONTRACTOR & DEVELOPMENT CORP.",
    "AmethystHorizon": "AMETHYST HORIZON BUILDERS AND GEN. CONTRACTOR AND DEVELOPMENT CORP.",
    "Centerways": "CENTERWAYS CONSTRUCTION AND DEVELOPMENT INC.",
    "Elite": "ELITE GENERAL CONTRACTOR AND DEVELOPMENT CORP.",
    "GreatPacific": "GREAT PACIFIC BUILDERS AND GEN. CONTRACTOR INC.",
    "HiTone": "HI-TONE CONSTRUCTION & DEVELOPMENT CORP.",
    "LR_Tiqui": "L.R. TIQUI BUILDERS, INC.",
    "Makapa": "MAKAPA CORPORATION",
    "MGSamidan": "MG SAMIDAN CONSTRUCTION",
    "RoyalCrownMonarch": "ROYAL CROWN MONARCH CONSTRUCTION & SUPPLIES CORP.",
    "StMatthew": "ST. MATTHEW GEN. CONTRACTOR & DEVELOPMENT CORP.",
    "StTimothy": "ST. TIMOTHY CONSTRUCTION CORPORATION",
    "TopnotchCatalyst": "TOPNOTCH CATALYST BUILDERS INC.",
    "Triple8": "TRIPLE 8 CONSTRUCTION & SUPPLY, INC.",
    "Wawao": "WAWAO BUILDERS",
    "WayMaker": "WAY MAKER GENERAL CONTRACTOR OPC",
}


def split_name(full_name: str) -> Tuple[str, str, Optional[str]]:
    """
    Split a full name into (first_name, last_name, middle_name).
    
    Handles patterns like:
    - "CEZARAH ROWENA C. DISCAYA" -> ("CEZARAH ROWENA", "DISCAYA", "C.")
    - "AURELIO BRENZ P. GONZALES" -> ("AURELIO BRENZ", "GONZALES", "P.")
    - "MA. REGINE S. BELICARIO" -> ("MA. REGINE", "BELICARIO", "S.")
    """
    full_name = full_name.strip()
    if not full_name:
        return "", "", None
    
    parts = full_name.split()
    if not parts:
        return "", "", None
    
    if len(parts) == 1:
        return "", parts[0], None
    
    # Check if last part is a suffix
    last_part = parts[-1].upper()
    suffix_pattern = re.compile(r'^(JR\.?|SR\.?|II|III|IV|V|VI|VII|VIII|IX|X)$')
    if suffix_pattern.match(last_part):
        if len(parts) >= 3:
            return " ".join(parts[:-2]), parts[-2], parts[-1]
        else:
            return parts[0], parts[-2] if len(parts) > 1 else "", parts[-1]
    
    # Standard case: last token is last name
    if len(parts) == 2:
        return parts[0], parts[1], None
    else:
        # Multiple parts: check if second-to-last is a middle initial
        # "CEZARAH ROWENA C. DISCAYA" -> first="CEZARAH ROWENA", middle="C.", last="DISCAYA"
        if len(parts) >= 3 and len(parts[-2]) <= 3 and parts[-2].endswith('.'):
            # Middle initial with period
            return " ".join(parts[:-2]), parts[-1], parts[-2]
        else:
            # All parts before last are first/middle name
            return parts[0], parts[-1], " ".join(parts[1:-1]) if len(parts) > 2 else None


def normalize_role(role: str) -> str:
    """Normalize role descriptions."""
    if not role:
        return ""
    # Clean up common variations
    role = role.replace("&", "and")
    role = re.sub(r'\s+', ' ', role.strip())
    return role


async def ensure_person(
    conn: asyncpg.Connection,
    full_name: str,
    nationality: Optional[str] = None,
    gender: Optional[str] = None,
    is_incorporator: bool = False,
) -> Optional[int]:
    """
    Ensure a person exists in political_dynasties, creating if necessary.
    
    Returns the person_id if successful, None if name couldn't be parsed.
    """
    first_name, last_name, middle_name = split_name(full_name)
    
    if not first_name or not last_name:
        print(f"⚠️  Skipping unparseable name: {full_name}")
        return None
    
    # Try to find existing person
    existing = await conn.fetchrow(
        """
        SELECT id, first_name, last_name, middle_name
        FROM political_dynasties
        WHERE UPPER(TRIM(first_name)) = UPPER(TRIM($1))
          AND UPPER(TRIM(last_name)) = UPPER(TRIM($2))
        ORDER BY year DESC NULLS LAST, id DESC
        LIMIT 1
        """,
        first_name,
        last_name,
    )
    
    if existing:
        person_id = existing["id"]
        # Update middle_name if we have new info and existing is empty
        if middle_name and not existing.get("middle_name"):
            await conn.execute(
                """
                UPDATE political_dynasties
                SET middle_name = $1,
                    last_updated = $2
                WHERE id = $3
                """,
                middle_name,
                datetime.utcnow(),
                person_id,
            )
        return person_id
    
    # Create new person
    canonical_first = first_name.upper().strip()
    canonical_full = f"{first_name} {last_name}".upper().strip()
    
    person_id = await conn.fetchval(
        """
        INSERT INTO political_dynasties (
            first_name,
            last_name,
            middle_name,
            canonical_first_name,
            canonical_name,
            last_updated,
            government_branch,
            government_level,
            position_category
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9
        )
        RETURNING id
        """,
        first_name,
        last_name,
        middle_name,
        canonical_first,
        canonical_full,
        datetime.utcnow(),
        'Private Sector',
        'national',
        'Contractor/Corporate Officer',
    )
    
    print(f"➕ Created: {full_name} (ID: {person_id})")
    return person_id


async def link_person_to_contractor(
    conn: asyncpg.Connection,
    person_id: int,
    contractor_name: str,
    role: str,
    is_incorporator: bool = False,
    shares: Optional[str] = None,
    ownership_pct: Optional[str] = None,
) -> None:
    """Link a person to a contractor in the politician_contractors table."""
    notes_parts = [f"Role: {role}"]
    if is_incorporator:
        notes_parts.append("Incorporator")
    if shares:
        notes_parts.append(f"Shares: {shares}")
    if ownership_pct:
        notes_parts.append(f"Ownership: {ownership_pct}")
    
    notes = " | ".join(notes_parts)
    
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
        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (politician_id, contractor_name)
        DO UPDATE SET
            notes = EXCLUDED.notes,
            source = EXCLUDED.source,
            updated_at = EXCLUDED.updated_at
        """,
        person_id,
        contractor_name,
        1.0,  # High confidence - from official SEC documents
        notes,
        SOURCE_LABEL,
        datetime.utcnow(),
        datetime.utcnow(),
    )


def get_contractor_name_from_filename(filename: str) -> Optional[str]:
    """Extract contractor name from CSV filename."""
    base = Path(filename).stem
    # Remove common suffixes
    base = base.replace("_Stockholders_Officers", "")
    base = base.replace("_Stockholders", "")
    
    # Try direct match first
    if base in CONTRACTOR_NAME_MAP:
        return CONTRACTOR_NAME_MAP[base]
    
    # Try partial matches
    for key, value in CONTRACTOR_NAME_MAP.items():
        if base.startswith(key) or key in base:
            return value
    
    return None


async def process_csv_file(conn: asyncpg.Connection, csv_path: Path) -> Tuple[int, int]:
    """Process a single CSV file and return (persons_created, persons_linked)."""
    contractor_name = get_contractor_name_from_filename(csv_path.name)
    if not contractor_name:
        print(f"⚠️  Could not map filename to contractor: {csv_path.name}")
        return 0, 0
    
    print(f"\n📄 Processing {csv_path.name} -> {contractor_name}")
    
    persons_created = 0
    persons_linked = 0
    seen_names: Set[str] = set()  # Track to avoid duplicates
    
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            # Handle different column name variations
            name = (row.get("Name") or "").strip()
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            
            # Handle different role column names
            role = normalize_role(
                row.get("Position/Role") or 
                row.get("Position") or 
                row.get("Role") or 
                ""
            )
            
            # If no role but there's a Type column, use that
            if not role and "Type" in row:
                type_val = row.get("Type", "").strip()
                if type_val:
                    role = type_val
            
            nationality = (row.get("Nationality") or "").strip()
            gender = (row.get("Gender") or "").strip()
            
            # Check if incorporator (column may or may not exist)
            is_incorporator = False
            if "Incorporator" in row:
                incorp_val = (row.get("Incorporator") or "").strip().upper()
                is_incorporator = incorp_val == "Y" or incorp_val == "YES"
            
            shares = (row.get("Shares Owned") or row.get("Number of Shares") or "").strip()
            ownership_pct = (row.get("% Ownership") or row.get("% Ownership") or "").strip()
            
            person_id = await ensure_person(
                conn,
                name,
                nationality if nationality else None,
                gender if gender else None,
                is_incorporator,
            )
            
            if person_id:
                persons_created += 1
                await link_person_to_contractor(
                    conn,
                    person_id,
                    contractor_name,
                    role,
                    is_incorporator,
                    shares if shares else None,
                    ownership_pct if ownership_pct else None,
                )
                persons_linked += 1
    
    return persons_created, persons_linked


async def main() -> None:
    """Main entry point."""
    if not DATABASE_DIR.exists():
        print(f"❌ Database directory not found: {DATABASE_DIR}")
        return
    
    csv_files = list(DATABASE_DIR.glob("*_Stockholders*.csv"))
    if not csv_files:
        print(f"❌ No CSV files found in {DATABASE_DIR}")
        return
    
    db_kwargs = {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "user": os.getenv("POSTGRES_USER", "budget_admin"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
        "database": os.getenv("POSTGRES_DB_DYNASTY", "dynasty"),
    }
    
    print(f"📥 Processing {len(csv_files)} CSV files...")
    
    conn = await asyncpg.connect(**db_kwargs)
    try:
        total_created = 0
        total_linked = 0
        
        for csv_path in sorted(csv_files):
            created, linked = await process_csv_file(conn, csv_path)
            total_created += created
            total_linked += linked
        
        print(f"\n✅ Complete!")
        print(f"   Persons created/updated: {total_created}")
        print(f"   Contractor links created: {total_linked}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())


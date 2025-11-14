#!/usr/bin/env python3
"""
Correct abbreviated and incorrect names in political_dynasties using precise CSV data.

This script reads the CSV files and updates existing database entries with correct
full names, roles, and other information from the official SEC documents.

Usage:
    $ source .env
    $ python scripts/database/correct_contractor_names_from_csvs.py
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

SOURCE_LABEL = "PCIJ Flood-Control Records - CSV Data (Corrected)"
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


def normalize_name_for_matching(name: str) -> str:
    """Normalize name for fuzzy matching."""
    # Remove common prefixes/suffixes
    name = re.sub(r'^(That|The|A|An)\s+', '', name, flags=re.IGNORECASE)
    # Remove punctuation and extra spaces
    name = re.sub(r'[^\w\s]', ' ', name)
    name = ' '.join(name.upper().split())
    return name


def names_match(name1: str, name2: str) -> bool:
    """Check if two names likely refer to the same person."""
    norm1 = normalize_name_for_matching(name1)
    norm2 = normalize_name_for_matching(name2)
    
    # Exact match
    if norm1 == norm2:
        return True
    
    # Check if one is a substring of the other (for abbreviated names)
    if norm1 in norm2 or norm2 in norm1:
        # Extract last names and check if they match
        parts1 = norm1.split()
        parts2 = norm2.split()
        if parts1 and parts2 and parts1[-1] == parts2[-1]:
            return True
    
    # Check if they share the same last name and first initial
    parts1 = norm1.split()
    parts2 = norm2.split()
    if len(parts1) >= 2 and len(parts2) >= 2:
        if parts1[-1] == parts2[-1]:  # Same last name
            if parts1[0][0] == parts2[0][0]:  # Same first initial
                return True
    
    return False


async def find_matching_person(
    conn: asyncpg.Connection,
    correct_name: str,
    contractor_name: str,
) -> Optional[int]:
    """Find existing person in database that matches the correct name."""
    first_name, last_name, middle_name = split_name(correct_name)
    if not first_name or not last_name:
        return None
    
    # Normalize correct name for comparison
    correct_norm = normalize_name_for_matching(correct_name)
    
    # Strategy 1: Exact match by first and last name
    exact = await conn.fetchrow(
        """
        SELECT id, first_name, last_name, middle_name
        FROM political_dynasties
        WHERE UPPER(TRIM(first_name)) = UPPER(TRIM($1))
          AND UPPER(TRIM(last_name)) = UPPER(TRIM($2))
        ORDER BY id DESC
        LIMIT 1
        """,
        first_name,
        last_name,
    )
    if exact:
        return exact["id"]
    
    # Strategy 2: Find by contractor link and check name similarity
    # This is more reliable since we know they're linked to the same contractor
    linked = await conn.fetch(
        """
        SELECT pd.id, pd.first_name, pd.last_name, pd.middle_name
        FROM political_dynasties pd
        JOIN politician_contractors pc ON pd.id = pc.politician_id
        WHERE UPPER(pc.contractor_name) = UPPER($1)
          AND UPPER(TRIM(pd.last_name)) = UPPER(TRIM($2))
        """,
        contractor_name,
        last_name,
    )
    
    # Check each linked person for name similarity
    best_match = None
    best_score = 0
    
    for row in linked:
        existing_full = f"{row['first_name']} {row['last_name']}".strip()
        existing_norm = normalize_name_for_matching(existing_full)
        
        # Calculate similarity score
        score = 0
        if existing_norm == correct_norm:
            score = 100  # Exact match
        elif correct_norm in existing_norm or existing_norm in correct_norm:
            # One is substring of the other - check if first names match
            existing_first = normalize_name_for_matching(row['first_name'])
            correct_first = normalize_name_for_matching(first_name)
            if existing_first == correct_first:
                score = 80
            elif existing_first in correct_first or correct_first in existing_first:
                score = 60
            else:
                score = 40
        elif existing_norm.split()[-1] == correct_norm.split()[-1]:  # Same last name
            # Check first name similarity
            existing_first = normalize_name_for_matching(row['first_name'])
            correct_first = normalize_name_for_matching(first_name)
            if existing_first == correct_first:
                score = 70
            elif existing_first in correct_first or correct_first in existing_first:
                score = 50
        
        if score > best_score and score >= 60:  # Only accept reasonably good matches
            best_score = score
            best_match = row["id"]
    
    if best_match:
        return best_match
    
    return None


async def update_person_name(
    conn: asyncpg.Connection,
    person_id: int,
    correct_name: str,
    middle_name: Optional[str] = None,
) -> None:
    """Update person's name in the database."""
    first_name, last_name, parsed_middle = split_name(correct_name)
    if not first_name or not last_name:
        return
    
    # Use provided middle_name or parsed one
    final_middle = middle_name or parsed_middle
    
    canonical_first = first_name.upper().strip()
    canonical_full = f"{first_name} {last_name}".upper().strip()
    
    await conn.execute(
        """
        UPDATE political_dynasties
        SET first_name = $1,
            last_name = $2,
            middle_name = $3,
            canonical_first_name = $4,
            canonical_name = $5,
            last_updated = $6
        WHERE id = $7
        """,
        first_name,
        last_name,
        final_middle,
        canonical_first,
        canonical_full,
        datetime.utcnow(),
        person_id,
    )


async def update_contractor_link(
    conn: asyncpg.Connection,
    person_id: int,
    contractor_name: str,
    role: str,
    is_incorporator: bool = False,
    shares: Optional[str] = None,
    ownership_pct: Optional[str] = None,
) -> None:
    """Update or create contractor link with correct information."""
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
        1.0,
        notes,
        SOURCE_LABEL,
        datetime.utcnow(),
        datetime.utcnow(),
    )


def get_contractor_name_from_filename(filename: str) -> Optional[str]:
    """Extract contractor name from CSV filename."""
    base = Path(filename).stem
    base = base.replace("_Stockholders_Officers", "")
    base = base.replace("_Stockholders", "")
    
    if base in CONTRACTOR_NAME_MAP:
        return CONTRACTOR_NAME_MAP[base]
    
    for key, value in CONTRACTOR_NAME_MAP.items():
        if base.startswith(key) or key in base:
            return value
    
    return None


async def process_csv_file(conn: asyncpg.Connection, csv_path: Path) -> Tuple[int, int]:
    """Process a CSV file and correct matching names. Returns (corrected, created)."""
    contractor_name = get_contractor_name_from_filename(csv_path.name)
    if not contractor_name:
        print(f"⚠️  Could not map filename to contractor: {csv_path.name}")
        return 0, 0
    
    print(f"\n📄 Processing {csv_path.name} -> {contractor_name}")
    
    corrected = 0
    created = 0
    
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            correct_name = (row.get("Name") or "").strip()
            if not correct_name:
                continue
            
            role = (row.get("Position/Role") or row.get("Position") or row.get("Role") or "").strip()
            if not role and "Type" in row:
                role = row.get("Type", "").strip()
            
            is_incorporator = False
            if "Incorporator" in row:
                incorp_val = (row.get("Incorporator") or "").strip().upper()
                is_incorporator = incorp_val == "Y" or incorp_val == "YES"
            
            shares = (row.get("Shares Owned") or row.get("Number of Shares") or "").strip()
            ownership_pct = (row.get("% Ownership") or "").strip()
            
            # Find matching person
            person_id = await find_matching_person(conn, correct_name, contractor_name)
            
            if person_id:
                # Update existing person with correct name
                await update_person_name(conn, person_id, correct_name)
                await update_contractor_link(
                    conn,
                    person_id,
                    contractor_name,
                    role,
                    is_incorporator,
                    shares if shares else None,
                    ownership_pct if ownership_pct else None,
                )
                print(f"  ✓ Corrected: {correct_name} (ID: {person_id})")
                corrected += 1
            else:
                # Create new person if no match found
                first_name, last_name, middle_name = split_name(correct_name)
                if first_name and last_name:
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
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
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
                    
                    await update_contractor_link(
                        conn,
                        person_id,
                        contractor_name,
                        role,
                        is_incorporator,
                        shares if shares else None,
                        ownership_pct if ownership_pct else None,
                    )
                    print(f"  ➕ Created: {correct_name} (ID: {person_id})")
                    created += 1
    
    return corrected, created


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
    
    print(f"📥 Processing {len(csv_files)} CSV files to correct names...")
    
    conn = await asyncpg.connect(**db_kwargs)
    try:
        total_corrected = 0
        total_created = 0
        
        for csv_path in sorted(csv_files):
            corrected, created = await process_csv_file(conn, csv_path)
            total_corrected += corrected
            total_created += created
        
        print(f"\n✅ Complete!")
        print(f"   Names corrected: {total_corrected}")
        print(f"   New entries created: {total_created}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())


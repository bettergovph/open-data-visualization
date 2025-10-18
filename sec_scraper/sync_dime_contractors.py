#!/usr/bin/env python3
"""
Sync contractors from DIME database to philgeps.contractors table
Extracts all unique contractors from DIME projects and inserts them into philgeps.contractors
Uses fuzzy matching to avoid duplicates
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from typing import List, Dict, Set
from difflib import SequenceMatcher
import re

load_dotenv()


def is_valid_contractor_name(name: str) -> bool:
    """Check if name is valid - not a generic single common word"""
    if not name:
        return False
    
    # Common generic words that are invalid as standalone contractor names
    COMMON_WORDS = {
        'SUPPLY', 'SUPPLIES', 'CONSTRUCTION', 'BUILDERS', 'BUILDER', 'TRADING', 
        'ENTERPRISE', 'ENTERPRISES', 'INC', 'CORP', 'CORPORATION', 'CO', 'COMPANY', 
        'LTD', 'LIMITED', 'THE', 'AND', 'FOR', 'OF', 'GENERAL', 'SERVICES', 
        'DEVELOPMENT', 'CONTRACTOR', 'CONTRACTORS', 'ENGINEERING', 'DESIGN', 
        'MAINTENANCE', 'BUILD', 'CONST', 'MERCHANDISE'
    }
    
    # If multi-word, it's valid
    words = name.split()
    if len(words) > 1:
        return True
    
    # Single word - check if it's a common word
    if name.upper() in COMMON_WORDS:
        return False
    
    # Single word but not common - could be proper name or acronym - keep it
    return True

def is_joint_venture(name: str) -> bool:
    """Check if contractor name represents a joint venture
    
    ONLY check for / (forward slash) as JV indicator
    Do NOT use & or AND as they are part of company names
    """
    if not name:
        return False
    
    # ONLY use / as JV indicator
    return '/' in name


def extract_former_names(name: str) -> Dict[str, any]:
    """
    Extract both current and former names from a contractor name
    
    Handles:
    - Complete: "NEW (FORMERLY: OLD)"
    - Incomplete: "NEW (FORMERLY" or "NEW (FORMERLY: OLD" (missing closing paren)
    - No parens: "NEW FORMERLY: OLD"
    
    Returns dict with current name and list of former names
    """
    result = {
        'current': None,
        'former': []
    }
    
    # Pattern 1: Check for FORMERLY/FORMER/FOR with or without complete parentheses
    # Matches: "NAME (FORMERLY..." or "NAME FORMERLY:" or "NAME FOR:" or "NAME FOR ..."
    formerly_match = re.search(r'^(.+?)\s*\(?\s*\b(FORMERLY|FORMER|FOR|PREVIOUSLY|PREV)\b[\s:]*(.*)$', name, re.IGNORECASE)
    
    if formerly_match:
        current = formerly_match.group(1).strip()
        old_name_part = formerly_match.group(3).strip()
        
        # Remove trailing/leading punctuation and closing paren if present
        old_name_part = re.sub(r'^\s*[:;,\s]+', '', old_name_part)
        old_name_part = re.sub(r'\)?\s*$', '', old_name_part).strip()
        
        result['current'] = current
        
        # Keep all valid old names (even truncated) - SEC will find full name
        if old_name_part and is_valid_contractor_name(old_name_part):
            result['former'].append(old_name_part)
        
        return result
    
    # Pattern 2: Normal parentheses (no FORMERLY keyword)
    parentheses_pattern = r'\((.*?)\)'
    matches = re.findall(parentheses_pattern, name)
    
    if matches:
        # Clean the main name (remove parentheses content)
        main_name = re.sub(parentheses_pattern, '', name).strip()
        result['current'] = main_name if main_name and len(main_name) > 3 else name.strip()
    else:
        result['current'] = name.strip()
    
    return result


def split_joint_venture(name: str) -> List[Dict[str, any]]:
    """
    Split a joint venture contractor name into individual contractors
    Also handles former names separately
    Returns list of dicts: [{"name": "Company A", "former_names": ["Old Name A"]}, ...]
    """
    if not name:
        return []
    
    # First, extract current and former names
    name_data = extract_former_names(name)
    current_name = name_data['current']
    former_names = name_data['former']
    
    # List to hold all individual contractors
    individual_contractors = []
    
    # Process current name
    if current_name and is_joint_venture(current_name):
        # Split JV into individual contractors (ONLY on /)
        parts = []
        
        # Only split by '/' (forward slash)
        if '/' in current_name:
            parts = current_name.split('/')
        
        # Clean up each part and add as individual contractor
        if parts:
            for part in parts:
                cleaned = part.strip()
                # Remove "JOINT VENTURE" text if present
                cleaned = re.sub(r'\b(?:JOINT\s+VENTURE|JV)\b', '', cleaned, flags=re.IGNORECASE).strip()
                # Remove any remaining parenthetical content
                cleaned = re.sub(r'\s*\([^)]*\)', '', cleaned).strip()
                
            # Keep all valid names (reject generic single words)
            if cleaned and is_valid_contractor_name(cleaned):
                individual_contractors.append({
                    'name': cleaned,
                    'former_names': []
                })
        else:
            individual_contractors.append({
                'name': current_name,
                'former_names': []
            })
    elif current_name:
        # Single contractor (not JV)
        individual_contractors.append({
            'name': current_name,
            'former_names': []
        })
    
    # Process former names as separate entries (with validation)
    for former_name in former_names:
        if is_valid_contractor_name(former_name):
            individual_contractors.append({
                'name': former_name,
                'former_names': []
            })
    
    # If we found FORMERLY or / but couldn't extract valid names, return empty (don't add unsplit)
    # Only return original if there were NO split indicators
    if individual_contractors:
        return individual_contractors
    elif '/' in name or re.search(r'\b(FORMERLY|FORMER|FOR|PREVIOUSLY|PREV)\b', name, re.IGNORECASE) or '(' in name:
        return []  # Had indicators but couldn't split - skip it
    else:
        return [{'name': name.strip(), 'former_names': []}]  # Clean name, add it


def normalize_contractor_name(name: str) -> str:
    """Normalize contractor name for fuzzy matching"""
    if not name:
        return ""
    
    # Convert to uppercase
    normalized = name.upper()
    
    # Remove common suffixes and prefixes
    suffixes = [
        'INC.', 'INC', 'CORP.', 'CORP', 'CO.', 'CO', 'LTD.', 'LTD',
        'CORPORATION', 'INCORPORATED', 'COMPANY', 'LIMITED',
        'CONSTRUCTION', 'TRADING', 'ENTERPRISES', 'DEVELOPMENT',
        'BUILDERS', 'CONTRACTOR', 'CONTRACTORS', 'SERVICES',
        'GEN.', 'GENERAL', 'AND', '&'
    ]
    
    for suffix in suffixes:
        normalized = normalized.replace(suffix, '')
    
    # Remove special characters and extra spaces
    normalized = re.sub(r'[^A-Z0-9\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized)
    normalized = normalized.strip()
    
    return normalized


def fuzzy_match(name1: str, name2: str, threshold: float = 0.85) -> bool:
    """
    Check if two contractor names are similar using fuzzy matching
    Returns True if similarity ratio is above threshold
    """
    if not name1 or not name2:
        return False
    
    # Exact match after normalization
    norm1 = normalize_contractor_name(name1)
    norm2 = normalize_contractor_name(name2)
    
    if norm1 == norm2:
        return True
    
    # Fuzzy match using SequenceMatcher
    ratio = SequenceMatcher(None, norm1, norm2).ratio()
    
    return ratio >= threshold

async def get_dime_contractors() -> Set[str]:
    """
    Extract all unique contractors from DIME database
    Splits JV contractors and extracts former names
    """
    print("📊 Connecting to DIME database...")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DIME', 'dime')
    )
    
    try:
        # Get all contractors from DIME projects
        # The contractors field is a text array
        rows = await conn.fetch(
            """
            SELECT DISTINCT unnest(contractors) as contractor_name
            FROM projects
            WHERE contractors IS NOT NULL 
                AND array_length(contractors, 1) > 0
            """
        )
        
        print(f"✅ Found {len(rows)} contractor entries in DIME database")
        
        # Split JVs and extract former names
        all_contractors = set()
        jv_count = 0
        former_name_count = 0
        
        for row in rows:
            contractor_name = row['contractor_name']
            if not contractor_name or not contractor_name.strip():
                continue
            
            # Check if it's a JV or has former names
            is_jv = is_joint_venture(contractor_name)
            has_former = '(' in contractor_name and ('formerly' in contractor_name.lower() or 'former' in contractor_name.lower())
            
            # Split into individual contractors
            individual_contractors = split_joint_venture(contractor_name)
            
            if is_jv:
                jv_count += 1
            if has_former:
                former_name_count += 1
            
            for contractor_data in individual_contractors:
                contractor = contractor_data['name']
                if contractor and contractor.strip():
                    all_contractors.add(contractor.strip())
        
        print(f"   - JV entries split: {jv_count}")
        print(f"   - Former names extracted: {former_name_count}")
        print(f"✅ Total unique individual contractors: {len(all_contractors)}")
        return all_contractors
        
    finally:
        await conn.close()


async def get_existing_contractors() -> List[str]:
    """Get all existing contractors from philgeps.contractors table"""
    print("📊 Connecting to PhilGEPS database...")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
    )
    
    try:
        rows = await conn.fetch(
            """
            SELECT DISTINCT contractor_name
            FROM contractors
            """
        )
        
        existing = [row['contractor_name'] for row in rows]
        
        print(f"✅ Found {len(existing)} existing contractors in philgeps.contractors table")
        return existing
        
    finally:
        await conn.close()


def find_duplicates_with_fuzzy_match(new_contractors: Set[str], existing_contractors: List[str]) -> tuple:
    """
    Find new contractors that are not duplicates of existing ones
    Uses fuzzy matching to detect similar names
    Returns (unique_contractors, duplicates_found)
    """
    print("🔍 Checking for duplicates using fuzzy matching...")
    
    unique_contractors = []
    duplicates = []
    
    total = len(new_contractors)
    processed = 0
    
    for new_contractor in sorted(new_contractors):
        processed += 1
        if processed % 100 == 0:
            print(f"   Progress: {processed}/{total} contractors checked...")
        
        # Check against existing contractors
        is_duplicate = False
        for existing_contractor in existing_contractors:
            if fuzzy_match(new_contractor, existing_contractor):
                duplicates.append((new_contractor, existing_contractor))
                is_duplicate = True
                break
        
        # Also check against already unique contractors in this batch
        if not is_duplicate:
            for unique_contractor in unique_contractors:
                if fuzzy_match(new_contractor, unique_contractor):
                    duplicates.append((new_contractor, unique_contractor))
                    is_duplicate = True
                    break
        
        if not is_duplicate:
            unique_contractors.append(new_contractor)
    
    print(f"✅ Found {len(unique_contractors)} unique contractors, {len(duplicates)} duplicates")
    
    return unique_contractors, duplicates


async def add_missing_columns():
    """Add missing columns to contractors table if they don't exist"""
    print("🔧 Checking contractors table schema...")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
    )
    
    try:
        # Check if former_id column exists
        former_id_exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'contractors' 
                AND column_name = 'former_id'
            )
            """
        )
        
        if not former_id_exists:
            await conn.execute(
                """
                ALTER TABLE contractors 
                ADD COLUMN former_id INTEGER REFERENCES contractors(id)
                """
            )
            print("✅ Added former_id column")
        else:
            print("✅ former_id column already exists")
        
        # Check if source column exists
        source_exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'contractors' 
                AND column_name = 'source'
            )
            """
        )
        
        if not source_exists:
            await conn.execute(
                """
                ALTER TABLE contractors 
                ADD COLUMN source TEXT DEFAULT 'unknown'
                """
            )
            print("✅ Added source column")
        else:
            print("✅ source column already exists")
            
    finally:
        await conn.close()


async def insert_new_contractors(new_contractors: List[str]):
    """Insert new contractors into philgeps.contractors table"""
    if not new_contractors:
        print("✅ No new contractors to insert")
        return
    
    print(f"📝 Inserting {len(new_contractors)} new contractors...")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
    )
    
    try:
        # Insert contractors in batch
        inserted = 0
        updated = 0
        errors = 0
        for contractor_name in new_contractors:
            try:
                # Try to insert, if already exists then update source
                existing_id = await conn.fetchval(
                    """
                    SELECT id FROM contractors WHERE contractor_name = $1
                    """,
                    contractor_name
                )
                
                if existing_id:
                    # Update source if not already present
                    await conn.execute(
                        """
                        UPDATE contractors
                        SET source = CASE 
                            WHEN source IS NULL OR source = 'unknown' THEN $2
                            WHEN source NOT LIKE '%' || $2 || '%' THEN source || ', ' || $2
                            ELSE source
                        END
                        WHERE id = $1
                        """,
                        existing_id,
                        'dime'
                    )
                    updated += 1
                else:
                    # Insert new contractor
                    await conn.execute(
                        """
                        INSERT INTO contractors (contractor_name, source)
                        VALUES ($1, $2)
                        """,
                        contractor_name,
                        'dime'
                    )
                    inserted += 1
                    
                if (inserted + updated) % 100 == 0:
                    print(f"   Progress: {inserted} inserted, {updated} updated, {inserted + updated}/{len(new_contractors)} processed...")
            except Exception as e:
                print(f"⚠️  Error processing '{contractor_name}': {e}")
                errors += 1
        
        print(f"✅ Successfully inserted {inserted} new contractors, updated {updated} existing")
        if errors > 0:
            print(f"⚠️  {errors} errors encountered")
        print(f"   Note: Source field updated to track 'dime' origin")
        
    finally:
        await conn.close()


async def main():
    print("🚀 Starting DIME contractors sync...")
    print("📌 Unified contractors database: philgeps.contractors")
    print("   - Data sources: DIME, PhilGEPS, Flood (MeiliSearch)")
    print("   - SEC is verification tool (not a source)")
    print("   - JV contractors split into individual companies")
    print("   - Former names tracked separately")
    print()
    
    # Add missing columns if they don't exist
    await add_missing_columns()
    print()
    
    # Get contractors from DIME
    dime_contractors = await get_dime_contractors()
    
    # Get existing contractors from philgeps
    existing_contractors = await get_existing_contractors()
    
    # Find contractors that are in DIME but not in philgeps (exact match)
    existing_set = set(existing_contractors)
    potential_new = dime_contractors - existing_set
    
    print()
    print(f"📊 Initial counts:")
    print(f"   DIME contractors: {len(dime_contractors)}")
    print(f"   Existing in philgeps: {len(existing_contractors)}")
    print(f"   Potential new (exact match): {len(potential_new)}")
    print()
    
    if potential_new:
        # Use fuzzy matching to find truly unique contractors
        unique_contractors, duplicates = find_duplicates_with_fuzzy_match(potential_new, existing_contractors)
        
        print()
        print(f"📊 After fuzzy matching:")
        print(f"   Unique contractors to insert: {len(unique_contractors)}")
        print(f"   Duplicates detected: {len(duplicates)}")
        print()
        
        # Show some duplicate examples
        if duplicates:
            print("📋 Duplicate examples (first 10):")
            for new_name, existing_name in duplicates[:10]:
                print(f"   ❌ '{new_name}' → matches existing '{existing_name}'")
            if len(duplicates) > 10:
                print(f"   ... and {len(duplicates) - 10} more duplicates")
            print()
        
        # Show unique contractors preview
        if unique_contractors:
            print("📋 Preview of unique contractors to insert (first 10):")
            for contractor in unique_contractors[:10]:
                print(f"   ✅ {contractor}")
            if len(unique_contractors) > 10:
                print(f"   ... and {len(unique_contractors) - 10} more")
            print()
            
            # Insert unique contractors
            await insert_new_contractors(unique_contractors)
    else:
        print("✅ No new contractors to insert (all already exist)")
    
    print()
    print("✅ Sync completed!")


if __name__ == "__main__":
    asyncio.run(main())


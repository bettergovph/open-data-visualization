#!/usr/bin/env python3
"""
Sync contractors from MeiliSearch (flood control data) to philgeps.contractors table
Extracts all unique contractors from flood projects and inserts them into philgeps.contractors
Uses fuzzy matching to avoid duplicates
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from typing import List, Dict, Set
from difflib import SequenceMatcher
import re
import requests

load_dotenv()


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
    E.g., "Company ABC (formerly Company XYZ)" -> {"current": "Company ABC", "former": ["Company XYZ"]}
    Returns dict with current name and list of former names
    """
    result = {
        'current': None,
        'former': []
    }
    
    # Extract content in parentheses (often contains former names)
    parentheses_pattern = r'\((.*?)\)'
    matches = re.findall(parentheses_pattern, name)
    
    # Clean the main name (remove parentheses content)
    main_name = re.sub(parentheses_pattern, '', name).strip()
    if main_name and len(main_name) > 3:
        result['current'] = main_name
    else:
        result['current'] = name.strip()
    
    # Process parentheses content for former names
    for match in matches:
        match_lower = match.lower()
        
        # Check if it contains "formerly" or similar indicators
        if 'formerly' in match_lower or 'former' in match_lower or 'now' in match_lower:
            # Remove "formerly", "former", "now", etc.
            cleaned = re.sub(r'\b(?:formerly|former|now|known\s+as)\b', '', match, flags=re.IGNORECASE).strip()
            
            # Clean up punctuation
            cleaned = re.sub(r'^[:\-,\s]+', '', cleaned).strip()
            
            if cleaned and len(cleaned) > 3:
                result['former'].append(cleaned)
    
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
        parts = current_name.split('/')
        
        # Clean up each part and add as individual contractor
        for part in parts:
            cleaned = part.strip()
            # Remove "JOINT VENTURE" text if present
            cleaned = re.sub(r'\b(?:JOINT\s+VENTURE|JV)\b', '', cleaned, flags=re.IGNORECASE).strip()
            # Remove any parenthetical content
            cleaned = re.sub(r'\s*\([^)]*\)', '', cleaned).strip()
            
            if cleaned and len(cleaned) > 10:  # Minimum 10 chars
                individual_contractors.append({
                    'name': cleaned,
                    'former_names': []
                })
    elif current_name:
        # Single contractor (not JV)
        individual_contractors.append({
            'name': current_name,
            'former_names': []
        })
    
    # Process former names as separate entries
    for former_name in former_names:
        individual_contractors.append({
            'name': former_name,
            'former_names': []
        })
    
    return individual_contractors if individual_contractors else [{'name': name.strip(), 'former_names': []}]


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

async def get_flood_contractors() -> Set[str]:
    """
    Extract all unique contractors from MeiliSearch flood control data
    Splits JV contractors and extracts former names
    """
    print("📊 Connecting to MeiliSearch flood control index...")
    
    # Parse MEILI_HTTP_ADDR (format: "127.0.0.1:7700")
    meili_addr = os.getenv('MEILI_HTTP_ADDR', 'localhost:7700')
    if ':' in meili_addr:
        meilisearch_host, meilisearch_port = meili_addr.split(':')
    else:
        meilisearch_host = 'localhost'
        meilisearch_port = '7700'
    
    meilisearch_key = os.getenv('MEILI_MASTER_KEY', '')
    
    try:
        # Fetch all documents from MeiliSearch
        url = f"http://{meilisearch_host}:{meilisearch_port}/indexes/bettergov_flood_control/documents"
        
        headers = {}
        if meilisearch_key:
            headers['Authorization'] = f'Bearer {meilisearch_key}'
        
        all_projects = []
        offset = 0
        limit = 1000
        
        while True:
            response = requests.get(f"{url}?offset={offset}&limit={limit}", headers=headers)
            if not response.ok:
                print(f"⚠️  MeiliSearch request failed: {response.status_code}")
                print(f"   Trying without authentication...")
                response = requests.get(f"{url}?offset={offset}&limit={limit}")
                if not response.ok:
                    print(f"❌ Failed: {response.status_code}")
                    break
            
            data = response.json()
            results = data.get('results', [])
            
            if not results:
                break
            
            all_projects.extend(results)
            offset += len(results)
            
            print(f"   Fetched {offset} projects...")
            
            # Stop if we've got all results
            if len(results) < limit:
                break
        
        print(f"✅ Found {len(all_projects)} flood control projects")
        
        # Extract contractors
        all_contractors = set()
        jv_count = 0
        former_name_count = 0
        
        for project in all_projects:
            contractor_name = project.get('Contractor')
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
        
    except Exception as e:
        print(f"❌ Error fetching from MeiliSearch: {e}")
        return set()


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
                        'flood'
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
                        'flood'
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
        print(f"   Note: Source field updated to track 'flood' origin")
        
    finally:
        await conn.close()


async def main():
    print("🚀 Starting Flood (MeiliSearch) contractors sync...")
    print("📌 Unified contractors database: philgeps.contractors")
    print("   - Data sources: DIME, PhilGEPS, Flood (MeiliSearch)")
    print("   - SEC is verification tool (not a source)")
    print("   - JV contractors split into individual companies")
    print("   - Former names tracked separately")
    print()
    
    # Add missing columns if they don't exist
    await add_missing_columns()
    print()
    
    # Get contractors from Flood (MeiliSearch)
    flood_contractors = await get_flood_contractors()
    
    # Get existing contractors from philgeps
    existing_contractors = await get_existing_contractors()
    
    # Find contractors that are in Flood but not in philgeps (exact match)
    existing_set = set(existing_contractors)
    potential_new = flood_contractors - existing_set
    
    print()
    print(f"📊 Initial counts:")
    print(f"   Flood contractors: {len(flood_contractors)}")
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


#!/usr/bin/env python3
"""
Populate missing SEC data in PhilGEPS merchant parquet from SEC database.
Matches contractors by name using fuzzy matching.
"""

import asyncio
import asyncpg
import pandas as pd
from pathlib import Path
from difflib import SequenceMatcher
import os
from typing import Optional, Tuple

# PostgreSQL connection config
PG_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'user': os.getenv('POSTGRES_USER', 'budget_admin'),
    'password': os.getenv('POSTGRES_PASSWORD', 'wuQ5gBYCKkZiOGb61chLcByMu'),
}


def normalize_name(name: str) -> str:
    """Normalize contractor name for matching"""
    if not name:
        return ""
    
    # Strip quotes and whitespace
    normalized = name.strip().strip('"').strip("'").strip()
    
    # Convert to uppercase
    normalized = normalized.upper()
    
    # Remove common punctuation
    normalized = normalized.replace('.', ' ')
    normalized = normalized.replace(',', ' ')
    normalized = normalized.replace('-', ' ')
    normalized = normalized.replace('&', 'AND')
    
    # Remove extra whitespace
    normalized = ' '.join(normalized.split())
    
    return normalized


def fuzzy_match(name1: str, name2: str, threshold: float = 0.85) -> Tuple[bool, float]:
    """Fuzzy match two names, return (match, score)"""
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)
    
    if not norm1 or not norm2:
        return False, 0.0
    
    # Use SequenceMatcher for similarity
    ratio = SequenceMatcher(None, norm1, norm2).ratio()
    return ratio >= threshold, ratio


async def get_sec_contractors() -> list:
    """Get all contractors with SEC data from SEC database"""
    conn = await asyncpg.connect(
        host=PG_CONFIG['host'],
        port=PG_CONFIG['port'],
        user=PG_CONFIG['user'],
        password=PG_CONFIG['password'],
        database='sec'
    )
    
    try:
        # Get contractors with SEC numbers
        rows = await conn.fetch('''
            SELECT DISTINCT
                contractor_name,
                sec_number,
                status,
                address
            FROM contractors
            WHERE sec_number IS NOT NULL
            AND sec_number != ''
            ORDER BY contractor_name
        ''')
        
        contractors = []
        for row in rows:
            contractors.append({
                'contractor_name': row['contractor_name'],
                'sec_number': row['sec_number'],
                'status': row['status'],
                'address': row['address']
            })
        
        return contractors
    finally:
        await conn.close()


def find_best_match(merchant_name: str, sec_contractors: list, threshold: float = 0.85) -> Optional[dict]:
    """Find best matching SEC contractor for merchant name"""
    best_match = None
    best_score = 0.0
    
    # Try matching against merchant name and normalized name
    names_to_match = [merchant_name]
    
    for sec_contractor in sec_contractors:
        sec_name = sec_contractor['contractor_name']
        
        # Try matching each name variant
        for name_to_match in names_to_match:
            is_match, score = fuzzy_match(name_to_match, sec_name, threshold)
            
            if is_match and score > best_score:
                best_score = score
                best_match = sec_contractor.copy()
                best_match['match_score'] = score
                best_match['matched_name'] = name_to_match
    
    return best_match if best_score >= threshold else None


async def main():
    parquet_file = Path('database/philgeps_merchant_info.parquet')
    
    if not parquet_file.exists():
        print(f"❌ Parquet file not found: {parquet_file}")
        return
    
    print(f"📖 Reading {parquet_file}...")
    df = pd.read_parquet(parquet_file)
    
    initial_with_sec = df['reg_sec'].notna().sum()
    initial_without_sec = df['reg_sec'].isna().sum()
    
    print(f"📊 Initial statistics:")
    print(f"   Total entries: {len(df)}")
    print(f"   With SEC (from JSON): {initial_with_sec}")
    print(f"   Without SEC: {initial_without_sec}")
    
    # Get entries without SEC (only process those missing SEC data)
    # Prioritize existing SEC data - never overwrite what's already there
    missing_sec = df[df['reg_sec'].isna() | (df['reg_sec'] == '')].copy()
    print(f"\n🔍 Processing {len(missing_sec)} entries without SEC data...")
    
    if len(missing_sec) == 0:
        print("✅ All entries already have SEC data. Nothing to do.")
        return
    
    # Load SEC contractors
    print("📥 Loading SEC contractors from database...")
    sec_contractors = await get_sec_contractors()
    print(f"   Found {len(sec_contractors)} contractors with SEC data")
    
    # Match and populate (only for entries missing SEC - prioritize existing data)
    matches_found = 0
    matches_by_name = {}
    
    print("\n🔗 Matching contractors (only populating missing SEC data, preserving existing)...")
    for idx, row in missing_sec.iterrows():
        # Double-check that SEC is actually missing (safety check - prioritize existing)
        current_sec = df.at[idx, 'reg_sec']
        if pd.notna(current_sec) and str(current_sec).strip():
            continue  # Skip if SEC already exists - prioritize what's in parquet
        
        # Try matching using 'name' field first, then 'contractor_name'
        name_to_match = row.get('name') or row.get('contractor_name', '')
        
        if not name_to_match or pd.isna(name_to_match):
            continue
        
        # Check if we already matched this name
        if name_to_match in matches_by_name:
            match = matches_by_name[name_to_match]
        else:
            match = find_best_match(name_to_match, sec_contractors, threshold=0.85)
            if match:
                matches_by_name[name_to_match] = match
        
        if match:
            # Only update if SEC is still missing (double-check - prioritize existing)
            if pd.isna(df.at[idx, 'reg_sec']) or not str(df.at[idx, 'reg_sec']).strip():
                df.at[idx, 'reg_sec'] = match['sec_number']
                matches_found += 1
                
                if matches_found % 100 == 0:
                    print(f"   Matched {matches_found} contractors...")
    
    print(f"\n✅ Found {matches_found} new matches out of {len(missing_sec)} entries without SEC")
    
    # Show updated stats
    final_with_sec = df['reg_sec'].notna().sum()
    final_without_sec = df['reg_sec'].isna().sum()
    
    print(f"\n📊 Final statistics:")
    print(f"   Total entries: {len(df)}")
    print(f"   With SEC: {final_with_sec} (was {initial_with_sec}, added {matches_found})")
    print(f"   Without SEC: {final_without_sec}")
    
    # Save updated parquet (same file - maintain only one)
    print(f"\n💾 Saving updated parquet to {parquet_file}...")
    df.to_parquet(parquet_file, index=False, engine='pyarrow', compression='snappy')
    
    file_size_mb = parquet_file.stat().st_size / (1024 * 1024)
    print(f"✅ Saved! File size: {file_size_mb:.2f} MB")
    
    # Show sample matches
    print(f"\n📋 Sample new matches:")
    sample_matches = df[df['reg_sec'].notna()].tail(5)
    for _, row in sample_matches.iterrows():
        name = row.get('name') or row.get('contractor_name', 'N/A')
        sec = row.get('reg_sec', 'N/A')
        if name and sec:
            print(f"   {str(name)[:50]:50} -> {sec}")


if __name__ == "__main__":
    asyncio.run(main())


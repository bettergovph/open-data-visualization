#!/usr/bin/env python3
"""
Match PhilGEPS contractors with existing sec.contractors using fuzzy matching
Only updates has_philgeps column (has_flood and has_dime already correct)
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from difflib import SequenceMatcher
import re

load_dotenv('.env')

def normalize_contractor_name(name):
    """Normalize contractor name for fuzzy matching"""
    if not name:
        return ""
    
    normalized = name.upper().strip()
    normalized = normalized.replace('.', ' ')
    normalized = normalized.replace(',', ' ')
    normalized = normalized.replace('-', ' ')
    normalized = normalized.replace('&', 'AND')
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    # Remove common suffixes
    suffixes_to_remove = [
        'CORPORATION', 'CORP', 'INC', 'INCORPORATED', 'CO', 'COMPANY',
        'LTD', 'LIMITED', 'ENTERPRISES', 'ENTERPRISE'
    ]
    
    words = normalized.split()
    filtered_words = [w for w in words if w not in suffixes_to_remove]
    
    return ' '.join(filtered_words) if filtered_words else normalized

def fuzzy_match(name1, name2, threshold=0.88):
    """Strict fuzzy matching with 88% similarity threshold"""
    if not name1 or not name2:
        return False
    
    if name1 == name2:
        return True
    
    norm1 = normalize_contractor_name(name1)
    norm2 = normalize_contractor_name(name2)
    
    if norm1 == norm2:
        return True
    
    ratio = SequenceMatcher(None, norm1, norm2).ratio()
    return ratio >= threshold

async def main():
    print("🚀 Matching PhilGEPS contractors with SEC database...\n")
    
    # Connect to philgeps to get awardee names
    philgeps_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database='philgeps'
    )
    
    # Get all unique awardee names from contracts
    print("📊 Fetching awardee names from PhilGEPS contracts...")
    philgeps_contractors = await philgeps_conn.fetch('''
        SELECT DISTINCT awardee_name
        FROM contracts
        WHERE awardee_name IS NOT NULL
    ''')
    
    philgeps_names = [row['awardee_name'] for row in philgeps_contractors]
    print(f"✅ Found {len(philgeps_names):,} unique PhilGEPS contractor names\n")
    
    await philgeps_conn.close()
    
    # Connect to SEC database
    sec_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database='sec'
    )
    
    # Get all contractors from SEC
    print("📊 Fetching contractors from SEC database...")
    sec_contractors = await sec_conn.fetch('SELECT id, contractor_name FROM contractors')
    print(f"✅ Found {len(sec_contractors):,} contractors in SEC database\n")
    
    print("🔍 Starting fuzzy matching (88% threshold)...")
    print("   This will take a while...\n")
    
    # Create a set of normalized philgeps names for faster lookup
    philgeps_normalized = {normalize_contractor_name(name): name for name in philgeps_names}
    
    updated = 0
    matched = 0
    
    for i, sec_contractor in enumerate(sec_contractors):
        contractor_id = sec_contractor['id']
        contractor_name = sec_contractor['contractor_name']
        
        # Check for match with any PhilGEPS contractor
        has_match = False
        
        # First try exact normalized match (fast)
        norm_sec = normalize_contractor_name(contractor_name)
        if norm_sec in philgeps_normalized:
            has_match = True
        else:
            # Then try fuzzy match (slower)
            for philgeps_name in philgeps_names:
                if fuzzy_match(contractor_name, philgeps_name):
                    has_match = True
                    break
        
        if has_match:
            # Update has_philgeps to true
            await sec_conn.execute('''
                UPDATE contractors 
                SET has_philgeps = true
                WHERE id = $1
            ''', contractor_id)
            matched += 1
        
        updated += 1
        
        if updated % 100 == 0:
            print(f"   Progress: {updated:,}/{len(sec_contractors):,} ({matched:,} matched, {(matched/updated*100):.1f}%)...")
    
    print(f"\n✅ Matching complete!")
    print(f"   Processed: {updated:,} contractors")
    print(f"   Matched with PhilGEPS: {matched:,}\n")
    
    # Get final statistics
    stats = await sec_conn.fetchrow('''
        SELECT 
            COUNT(*) FILTER (WHERE has_flood AND NOT has_dime AND NOT has_philgeps) as flood_only,
            COUNT(*) FILTER (WHERE has_dime AND NOT has_flood AND NOT has_philgeps) as dime_only,
            COUNT(*) FILTER (WHERE has_philgeps AND NOT has_flood AND NOT has_dime) as philgeps_only,
            COUNT(*) FILTER (WHERE has_flood AND has_dime AND NOT has_philgeps) as flood_dime,
            COUNT(*) FILTER (WHERE has_flood AND has_philgeps AND NOT has_dime) as flood_philgeps,
            COUNT(*) FILTER (WHERE has_dime AND has_philgeps AND NOT has_flood) as dime_philgeps,
            COUNT(*) FILTER (WHERE has_flood AND has_dime AND has_philgeps) as all_three,
            COUNT(*) FILTER (WHERE has_flood) as total_flood,
            COUNT(*) FILTER (WHERE has_dime) as total_dime,
            COUNT(*) FILTER (WHERE has_philgeps) as total_philgeps
        FROM contractors
    ''')
    
    print("📊 Final Venn Diagram Data:")
    print(f"   🔵 Flood only:        {stats['flood_only']:,}")
    print(f"   🟢 DIME only:         {stats['dime_only']:,}")
    print(f"   🟡 PhilGEPS only:     {stats['philgeps_only']:,}")
    print(f"   🔵🟢 Flood + DIME:     {stats['flood_dime']:,}")
    print(f"   🔵🟡 Flood + PhilGEPS: {stats['flood_philgeps']:,}")
    print(f"   🟢🟡 DIME + PhilGEPS:  {stats['dime_philgeps']:,}")
    print(f"   🔵🟢🟡 All three:       {stats['all_three']:,}")
    print()
    print(f"   Total per source:")
    print(f"   🔵 Flood:    {stats['total_flood']:,}")
    print(f"   🟢 DIME:     {stats['total_dime']:,}")
    print(f"   🟡 PhilGEPS: {stats['total_philgeps']:,}")
    
    await sec_conn.close()
    
    print("\n✅ Sync completed!")

if __name__ == '__main__':
    asyncio.run(main())


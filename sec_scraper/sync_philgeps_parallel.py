#!/usr/bin/env python3
"""
Match PhilGEPS contractors with SEC database using parallel processing
Uses 5 threads for faster execution
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from difflib import SequenceMatcher
import re
from concurrent.futures import ThreadPoolExecutor
import threading

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
    
    suffixes_to_remove = [
        'CORPORATION', 'CORP', 'INC', 'INCORPORATED', 'CO', 'COMPANY',
        'LTD', 'LIMITED', 'ENTERPRISES', 'ENTERPRISE'
    ]
    
    words = normalized.split()
    filtered_words = [w for w in words if w not in suffixes_to_remove]
    
    return ' '.join(filtered_words) if filtered_words else normalized

def fuzzy_match(name1, name2, threshold=0.88):
    """Strict fuzzy matching"""
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

def check_philgeps_match(sec_contractor, philgeps_names, philgeps_normalized):
    """Check if SEC contractor matches any PhilGEPS contractor (thread-safe)"""
    contractor_id = sec_contractor['id']
    contractor_name = sec_contractor['contractor_name']
    
    # First try exact normalized match
    norm_sec = normalize_contractor_name(contractor_name)
    if norm_sec in philgeps_normalized:
        return contractor_id, True
    
    # Then try fuzzy match
    for philgeps_name in philgeps_names:
        if fuzzy_match(contractor_name, philgeps_name):
            return contractor_id, True
    
    return contractor_id, False

async def main():
    print("🚀 Parallel PhilGEPS matching (5 threads)...\n")
    
    # Get PhilGEPS contractors
    philgeps_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database='philgeps'
    )
    
    print("📊 Fetching PhilGEPS awardee names...")
    philgeps_contractors = await philgeps_conn.fetch('''
        SELECT DISTINCT awardee_name
        FROM contracts
        WHERE awardee_name IS NOT NULL
    ''')
    
    philgeps_names = [row['awardee_name'] for row in philgeps_contractors]
    philgeps_normalized = {normalize_contractor_name(name): name for name in philgeps_names}
    print(f"✅ Found {len(philgeps_names):,} PhilGEPS contractors\n")
    
    await philgeps_conn.close()
    
    # Get SEC contractors
    sec_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database='sec'
    )
    
    print("📊 Fetching SEC contractors...")
    sec_contractors = await sec_conn.fetch('SELECT id, contractor_name FROM contractors')
    print(f"✅ Found {len(sec_contractors):,} SEC contractors\n")
    
    print("🔍 Starting parallel fuzzy matching (5 threads)...")
    print("   This will take a few minutes...\n")
    
    # Use ThreadPoolExecutor for parallel processing
    matches_to_update = []
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        # Submit all tasks
        futures = []
        for sec_contractor in sec_contractors:
            future = executor.submit(check_philgeps_match, sec_contractor, philgeps_names, philgeps_normalized)
            futures.append(future)
        
        # Process results as they complete
        completed = 0
        matched = 0
        
        for future in futures:
            contractor_id, has_match = future.result()
            
            if has_match:
                matches_to_update.append(contractor_id)
                matched += 1
            
            completed += 1
            if completed % 500 == 0:
                print(f"   Progress: {completed:,}/{len(sec_contractors):,} ({matched:,} matched, {(matched/completed*100):.1f}%)...")
    
    print(f"\n✅ Matching complete: {matched:,} contractors matched with PhilGEPS")
    print(f"📝 Updating database...\n")
    
    # Batch update
    batch_size = 1000
    for i in range(0, len(matches_to_update), batch_size):
        batch = matches_to_update[i:i+batch_size]
        await sec_conn.execute('''
            UPDATE contractors 
            SET has_philgeps = true
            WHERE id = ANY($1::int[])
        ''', batch)
        
        if (i + len(batch)) % 1000 == 0:
            print(f"   Updated: {i + len(batch):,}/{len(matches_to_update):,}...")
    
    print(f"✅ Database updated!\n")
    
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


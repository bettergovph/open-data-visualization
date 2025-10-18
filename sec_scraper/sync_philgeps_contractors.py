#!/usr/bin/env python3
"""
Sync contractors from contracts table (PhilGEPS data) to contractors table
Uses awardee_name from contracts table
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
import re
from sync_flood_contractors import is_valid_contractor_name, split_joint_venture, normalize_contractor_name, fuzzy_match

load_dotenv('.env')

async def main():
    print("🚀 Starting PhilGEPS contractors sync...")
    print("📌 Source: contracts table (awardee_name)")
    print("📌 Target: contractors table\n")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
    )
    
    # Get all unique awardee names from contracts
    raw_contractors = await conn.fetch('''
        SELECT DISTINCT awardee_name 
        FROM contracts
        WHERE awardee_name IS NOT NULL
        ORDER BY awardee_name
    ''')
    
    print(f"✅ Found {len(raw_contractors)} unique awardee names in contracts table")
    
    # Split into individual contractors
    all_individual_contractors = set()
    jv_count = 0
    former_count = 0
    
    for row in raw_contractors:
        contractor_name = row['awardee_name']
        
        # Split using same logic as flood/DIME sync
        individual_contractors = split_joint_venture(contractor_name)
        
        if len(individual_contractors) > 1:
            jv_count += 1
        
        if 'FORMERLY' in contractor_name.upper() or 'FORMER' in contractor_name.upper():
            former_count += 1
        
        for contractor_data in individual_contractors:
            contractor = contractor_data['name']
            if contractor and contractor.strip() and is_valid_contractor_name(contractor):
                all_individual_contractors.add(contractor.strip())
    
    print(f"   - JV entries split: {jv_count}")
    print(f"   - Former names extracted: {former_count}")
    print(f"✅ Total unique individual contractors after splitting: {len(all_individual_contractors)}\n")
    
    # Get existing contractors
    existing_contractors = await conn.fetch('SELECT contractor_name FROM contractors')
    existing_set = set(row['contractor_name'] for row in existing_contractors)
    
    print(f"✅ Found {len(existing_set)} existing contractors in contractors table\n")
    
    # Find truly new contractors (exact match)
    new_contractors = []
    for contractor in all_individual_contractors:
        if contractor not in existing_set:
            new_contractors.append(contractor)
    
    print(f"📊 Initial counts:")
    print(f"   PhilGEPS contracts: {len(all_individual_contractors)}")
    print(f"   Existing in contractors: {len(existing_set)}")
    print(f"   Potential new (exact match): {len(new_contractors)}\n")
    
    if not new_contractors:
        print("✅ No new contractors to add - all already exist!")
        await conn.close()
        return
    
    # Skip fuzzy matching - just insert new contractors (exact match already done)
    print(f"📊 Skipping fuzzy matching for performance")
    print(f"✅ Found {len(new_contractors)} new contractors to insert\n")
    
    # Insert new contractors
    if new_contractors:
        print(f"📝 Inserting {len(new_contractors)} new contractors...")
        
        inserted = 0
        for contractor_name in new_contractors:
            try:
                # Simple insert (no conflict check since we already filtered exact duplicates)
                await conn.execute('''
                    INSERT INTO contractors (contractor_name, source)
                    VALUES ($1, $2)
                ''', contractor_name, 'philgeps')
                inserted += 1
                
                if inserted % 100 == 0:
                    print(f"   Progress: {inserted}/{len(new_contractors)}...")
            except Exception as e:
                print(f"⚠️  Error inserting '{contractor_name}': {e}")
        
        print(f"✅ Successfully inserted {inserted} new contractors")
    
    await conn.close()
    print("\n✅ Sync completed!")

if __name__ == '__main__':
    asyncio.run(main())


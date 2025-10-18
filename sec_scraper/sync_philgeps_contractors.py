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
    
    # Check for fuzzy duplicates
    print(f"🔍 Checking for duplicates using fuzzy matching...")
    truly_new = []
    duplicates = []
    
    for i, new_contractor in enumerate(new_contractors):
        if (i + 1) % 100 == 0:
            print(f"   Progress: {i+1}/{len(new_contractors)} contractors checked...")
        
        # Check if fuzzy match exists
        is_duplicate = False
        for existing in existing_set:
            if fuzzy_match(new_contractor, existing):
                duplicates.append((new_contractor, existing))
                is_duplicate = True
                break
        
        if not is_duplicate:
            truly_new.append(new_contractor)
    
    print(f"✅ Found {len(truly_new)} unique contractors, {len(duplicates)} duplicates\n")
    
    if duplicates and len(duplicates) <= 20:
        print(f"📋 Duplicate examples:")
        for new, existing in duplicates:
            print(f"   ❌ '{new}' → matches existing '{existing}'")
        print()
    
    # Insert new contractors
    if truly_new:
        print(f"📝 Inserting {len(truly_new)} new contractors...")
        
        inserted = 0
        for contractor_name in truly_new:
            try:
                await conn.execute('''
                    INSERT INTO contractors (contractor_name, source)
                    VALUES ($1, $2)
                    ON CONFLICT (contractor_name) DO UPDATE
                    SET source = CASE 
                        WHEN contractors.source IS NULL OR contractors.source = 'unknown' THEN $2
                        WHEN contractors.source NOT LIKE '%' || $2 || '%' THEN contractors.source || ', ' || $2
                        ELSE contractors.source
                    END
                ''', contractor_name, 'philgeps')
                inserted += 1
                
                if inserted % 100 == 0:
                    print(f"   Progress: {inserted}/{len(truly_new)}...")
            except Exception as e:
                print(f"⚠️  Error inserting '{contractor_name}': {e}")
        
        print(f"✅ Successfully inserted {inserted} new contractors")
    
    await conn.close()
    print("\n✅ Sync completed!")

if __name__ == '__main__':
    asyncio.run(main())


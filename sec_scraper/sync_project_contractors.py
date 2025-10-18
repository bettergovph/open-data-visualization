#!/usr/bin/env python3
"""
Sync contractors from project_contractors table to contractors table
Uses the same split logic as flood and DIME sync
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
import re
# Import the split functions from sync_flood_contractors
import sys
sys.path.insert(0, os.path.dirname(__file__))

# Import split logic - we'll inline it here for simplicity
from sync_flood_contractors import is_valid_contractor_name, split_joint_venture, normalize_contractor_name, fuzzy_match

load_dotenv('.env')

async def main():
    print("🚀 Starting project_contractors sync...")
    print("📌 Source: project_contractors table (flood project linkages)")
    print("📌 Target: contractors table\n")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
    )
    
    # Get all unique contractor names from project_contractors
    raw_contractors = await conn.fetch('''
        SELECT DISTINCT contractor_name 
        FROM project_contractors
        WHERE contractor_name IS NOT NULL
        ORDER BY contractor_name
    ''')
    
    print(f"✅ Found {len(raw_contractors)} unique contractor names in project_contractors")
    
    # Split into individual contractors
    all_individual_contractors = set()
    for row in raw_contractors:
        contractor_name = row['contractor_name']
        
        # Split using same logic as flood/DIME sync
        individual_contractors = split_joint_venture(contractor_name)
        
        for contractor_data in individual_contractors:
            contractor = contractor_data['name']
            if contractor and contractor.strip() and is_valid_contractor_name(contractor):
                all_individual_contractors.add(contractor.strip())
    
    print(f"✅ Total unique individual contractors after splitting: {len(all_individual_contractors)}")
    
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
    print(f"   Project_contractors: {len(all_individual_contractors)}")
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
    
    if duplicates:
        print(f"📋 Duplicate examples (first 10):")
        for new, existing in duplicates[:10]:
            print(f"   ❌ '{new}' → matches existing '{existing}'")
        if len(duplicates) > 10:
            print(f"   ... and {len(duplicates) - 10} more duplicates\n")
    
    # Insert new contractors
    if truly_new:
        print(f"📝 Inserting {len(truly_new)} new contractors...")
        
        inserted = 0
        for contractor_name in truly_new:
            try:
                await conn.execute('''
                    INSERT INTO contractors (contractor_name, source)
                    VALUES ($1, $2)
                    ON CONFLICT (contractor_name) DO NOTHING
                ''', contractor_name, 'flood')
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


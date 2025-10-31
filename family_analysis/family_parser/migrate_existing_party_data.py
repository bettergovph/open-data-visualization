#!/usr/bin/env python3
"""
Migrate existing party data from political_dynasties.party to party_memberships table.

This script:
1. Reads party data from political_dynasties table
2. Inserts unique parties into political_parties table
3. Creates party_membership records based on year/party combinations
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from collections import defaultdict


async def migrate_party_data():
    """Migrate party data from political_dynasties to party_memberships"""
    load_dotenv()
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        print("🔄 Migrating party data from political_dynasties to party_memberships...")
        
        # 1. Get all records with party data
        records = await conn.fetch("""
            SELECT DISTINCT 
                id as person_id,
                CONCAT(first_name, ' ', last_name) as full_name,
                party,
                year
            FROM political_dynasties
            WHERE party IS NOT NULL AND party <> '' AND year IS NOT NULL
            ORDER BY id, year
        """)
        
        if not records:
            print("ℹ️  No party data found to migrate")
            return
        
        print(f"📊 Found {len(records)} person-year-party combinations")
        
        # 2. Group by person and create membership periods
        person_parties = defaultdict(list)
        for record in records:
            person_key = (record['person_id'], record['full_name'])
            person_parties[person_key].append({
                'party': record['party'].strip(),
                'year': record['year']
            })
        
        print(f"📋 Processing {len(person_parties)} unique persons")
        
        # 3. For each person, create party membership records
        total_inserted = 0
        skipped = 0
        
        for (person_id, full_name), party_years in person_parties.items():
            # Group party years to create membership periods
            party_periods = defaultdict(lambda: {'years': [], 'min_year': None, 'max_year': None})
            
            for py in party_years:
                party_name = py['party']
                year = py['year']
                if party_periods[party_name]['min_year'] is None or year < party_periods[party_name]['min_year']:
                    party_periods[party_name]['min_year'] = year
                if party_periods[party_name]['max_year'] is None or year > party_periods[party_name]['max_year']:
                    party_periods[party_name]['max_year'] = year
                party_periods[party_name]['years'].append(year)
            
            # Create membership record for each party period
            for party_name, period in party_periods.items():
                # Ensure party exists in political_parties
                party_id = await conn.fetchval("""
                    SELECT id FROM political_parties WHERE name = $1
                """, party_name)
                
                if not party_id:
                    party_id = await conn.fetchval("""
                        INSERT INTO political_parties (name)
                        VALUES ($1)
                        RETURNING id
                    """, party_name)
                
                # Check if membership already exists
                existing = await conn.fetchval("""
                    SELECT id FROM party_memberships
                    WHERE person_id = $1 AND party_id = $2
                    LIMIT 1
                """, person_id, party_id)
                
                if existing:
                    skipped += 1
                    continue
                
                # Insert membership
                # Use year as joined_date (set to January 1st of that year)
                joined_date = f"{period['min_year']}-01-01"
                
                # If max_year is recent and they're still senators, consider them current
                is_current = period['max_year'] >= 2020  # Adjust threshold as needed
                left_date = None if is_current else f"{period['max_year']}-12-31"
                
                try:
                    await conn.execute("""
                        INSERT INTO party_memberships (
                            person_id, party_id, joined_date, left_date, is_current
                        )
                        VALUES ($1, $2, $3::date, $4::date, $5)
                    """, person_id, party_id, joined_date, left_date, is_current)
                    total_inserted += 1
                except Exception as e:
                    print(f"⚠️  Error inserting membership for {full_name} / {party_name}: {e}")
                    skipped += 1
        
        print(f"\n✅ Migration complete!")
        print(f"   - Created {total_inserted} party membership records")
        print(f"   - Skipped {skipped} duplicate/invalid records")
        
        # 4. Show summary
        summary = await conn.fetch("""
            SELECT 
                COUNT(DISTINCT person_id) as unique_persons,
                COUNT(DISTINCT party_id) as unique_parties,
                COUNT(*) as total_memberships,
                COUNT(*) FILTER (WHERE is_current = TRUE) as current_memberships
            FROM party_memberships
        """)
        
        if summary:
            row = summary[0]
            print(f"\n📊 Party Memberships Summary:")
            print(f"   - Unique persons: {row['unique_persons']}")
            print(f"   - Unique parties: {row['unique_parties']}")
            print(f"   - Total memberships: {row['total_memberships']}")
            print(f"   - Current memberships: {row['current_memberships']}")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(migrate_party_data())


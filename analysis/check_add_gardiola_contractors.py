#!/usr/bin/env python3
"""
Check if Newington and S-Ang Construction are in the database
and add them to Gardiola if they exist
"""

import asyncio
import asyncpg
import os
from pathlib import Path

# Load environment variables
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path)

async def main():
    # Connect to SEC database
    sec_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database='sec'
    )
    
    # Connect to Dynasty database
    dynasty_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        # Search for Newington
        print("🔍 Searching for 'Newington'...")
        newington = await sec_conn.fetch('''
            SELECT id, contractor_name FROM contractors
            WHERE UPPER(contractor_name) LIKE '%NEWINGTON%'
            LIMIT 10
        ''')
        print(f"   Found {len(newington)} Newington contractors:")
        newington_names = []
        for row in newington:
            print(f"     - {row['contractor_name']}")
            newington_names.append(row['contractor_name'])
        
        # Search for S-Ang
        print("\n🔍 Searching for 'S-Ang' or 'S ANG' or 'SANG'...")
        sang = await sec_conn.fetch('''
            SELECT id, contractor_name FROM contractors
            WHERE UPPER(contractor_name) LIKE '%S-ANG%' 
               OR UPPER(contractor_name) LIKE '%S ANG%'
               OR UPPER(contractor_name) LIKE '%SANG CONSTRUCTION%'
            LIMIT 10
        ''')
        print(f"   Found {len(sang)} S-Ang contractors:")
        sang_names = []
        for row in sang:
            print(f"     - {row['contractor_name']}")
            sang_names.append(row['contractor_name'])
        
        # Find Gardiola
        print("\n🔍 Finding Gardiola in dynasty database...")
        gardiola = await dynasty_conn.fetchrow('''
            SELECT id, first_name, last_name FROM political_dynasties
            WHERE (UPPER(first_name) LIKE '%TIRSO%' OR UPPER(first_name) LIKE '%EDWIN%')
              AND UPPER(last_name) LIKE '%GARDIOLA%'
            LIMIT 1
        ''')
        
        if not gardiola:
            print("❌ Gardiola not found in dynasty database")
            return
        
        print(f"✅ Found: {gardiola['first_name']} {gardiola['last_name']} (ID: {gardiola['id']})")
        
        # Check current contractors
        current_contractors = await dynasty_conn.fetch('''
            SELECT company_name FROM contractor_dynasty_matches
            WHERE dynasty_first_name = $1 AND dynasty_last_name = $2
        ''', gardiola['first_name'], gardiola['last_name'])
        
        print(f"\n📋 Current contractors ({len(current_contractors)}):")
        existing_companies = set()
        for row in current_contractors:
            print(f"   - {row['company_name']}")
            existing_companies.add(row['company_name'].upper())
        
        # Add Newington contractors
        added_count = 0
        if newington_names:
            print(f"\n➕ Adding Newington contractors...")
            for contractor_name in newington_names:
                if contractor_name.upper() not in existing_companies:
                    try:
                        await dynasty_conn.execute('''
                            INSERT INTO contractor_dynasty_matches (
                                dynasty_full_name, dynasty_first_name, dynasty_last_name,
                                company_name, role, person_name
                            )
                            VALUES ($1, $2, $3, $4, $5, $6)
                        ''',
                        f"{gardiola['first_name']} {gardiola['last_name']}",
                        gardiola['first_name'],
                        gardiola['last_name'],
                        contractor_name,
                        'Contractor',
                        f"{gardiola['first_name']} {gardiola['last_name']}"
                        )
                        print(f"   ✅ Added: {contractor_name}")
                        added_count += 1
                    except Exception as e:
                        print(f"   ❌ Error adding {contractor_name}: {e}")
                else:
                    print(f"   ℹ️  Already exists: {contractor_name}")
        
        # Add S-Ang contractors
        if sang_names:
            print(f"\n➕ Adding S-Ang contractors...")
            for contractor_name in sang_names:
                if contractor_name.upper() not in existing_companies:
                    try:
                        await dynasty_conn.execute('''
                            INSERT INTO contractor_dynasty_matches (
                                dynasty_full_name, dynasty_first_name, dynasty_last_name,
                                company_name, role, person_name
                            )
                            VALUES ($1, $2, $3, $4, $5, $6)
                        ''',
                        f"{gardiola['first_name']} {gardiola['last_name']}",
                        gardiola['first_name'],
                        gardiola['last_name'],
                        contractor_name,
                        'Contractor',
                        f"{gardiola['first_name']} {gardiola['last_name']}"
                        )
                        print(f"   ✅ Added: {contractor_name}")
                        added_count += 1
                    except Exception as e:
                        print(f"   ❌ Error adding {contractor_name}: {e}")
                else:
                    print(f"   ℹ️  Already exists: {contractor_name}")
        
        if added_count > 0:
            print(f"\n✅ Successfully added {added_count} contractor(s) to Gardiola")
        else:
            print(f"\nℹ️  No new contractors added (either not found or already exist)")
        
    finally:
        await sec_conn.close()
        await dynasty_conn.close()

if __name__ == "__main__":
    asyncio.run(main())


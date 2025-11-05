#!/usr/bin/env python3
"""
Remove incorrect contractors from Gardiola:
- 3 S Angel Construction and Supplies, Inc.
- KAWAINESANG CONSTRUCTION AND SUPPLY
- LANSANG CONSTRUCTION
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
    # Connect to Dynasty database
    dynasty_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        # Find Gardiola
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
        
        # List of contractors to remove
        contractors_to_remove = [
            '3 S Angel Construction and Supplies, Inc.',
            'KAWAINESANG CONSTRUCTION AND SUPPLY',
            'LANSANG CONSTRUCTION'
        ]
        
        print(f"\n🗑️  Removing {len(contractors_to_remove)} incorrect contractors...")
        
        removed_count = 0
        for contractor_name in contractors_to_remove:
            result = await dynasty_conn.execute('''
                DELETE FROM contractor_dynasty_matches
                WHERE dynasty_first_name = $1 
                  AND dynasty_last_name = $2
                  AND UPPER(company_name) = UPPER($3)
            ''', gardiola['first_name'], gardiola['last_name'], contractor_name)
            
            if 'DELETE' in result:
                deleted = int(result.split()[-1])
                if deleted > 0:
                    print(f"   ✅ Removed: {contractor_name}")
                    removed_count += deleted
                else:
                    print(f"   ℹ️  Not found: {contractor_name}")
        
        print(f"\n✅ Successfully removed {removed_count} contractor(s)")
        
        # Show remaining contractors
        remaining = await dynasty_conn.fetch('''
            SELECT company_name FROM contractor_dynasty_matches
            WHERE dynasty_first_name = $1 AND dynasty_last_name = $2
            ORDER BY company_name
        ''', gardiola['first_name'], gardiola['last_name'])
        
        print(f"\n📋 Remaining contractors ({len(remaining)}):")
        for row in remaining:
            print(f"   - {row['company_name']}")
        
    finally:
        await dynasty_conn.close()

if __name__ == "__main__":
    asyncio.run(main())


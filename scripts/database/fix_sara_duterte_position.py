#!/usr/bin/env python3
"""Fix Sara Duterte's position from PRESIDENT to VICE PRESIDENT"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def fix_sara_duterte_position():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        # Check Sara Duterte records
        sara = await conn.fetch('''
            SELECT id, first_name, last_name, position, province
            FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%SARA%' 
              AND UPPER(last_name) LIKE '%DUTERTE%'
            ORDER BY id DESC
        ''')
        
        print(f"Found {len(sara)} Sara Duterte records:")
        for r in sara:
            print(f"  ID: {r['id']}, Name: {r['first_name']} {r['last_name']}, Position: {r['position']}, Province: {r['province']}")
        
        # Update the one that says PRESIDENT to VICE PRESIDENT
        updated = 0
        for r in sara:
            if r['position'] and 'PRESIDENT' in r['position'].upper() and 'VICE' not in r['position'].upper():
                await conn.execute('''
                    UPDATE political_dynasties
                    SET position = 'VICE PRESIDENT OF THE PHILIPPINES'
                    WHERE id = $1
                ''', r['id'])
                print(f"\n✅ Updated ID {r['id']} from '{r['position']}' to 'VICE PRESIDENT OF THE PHILIPPINES'")
                updated += 1
        
        if updated == 0:
            print("\n✅ No records needed updating (all already correct)")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_sara_duterte_position())














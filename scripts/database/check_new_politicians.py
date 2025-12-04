#!/usr/bin/env python3
"""Check new politicians from CSV for duplicates and normalization issues"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def check_duplicates():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        # Check James Ang entries
        james_ang = await conn.fetch('''
            SELECT id, first_name, last_name, normalized_name, position
            FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%JAMES%' AND UPPER(last_name) LIKE '%ANG%'
            ORDER BY id
        ''')
        
        print("James Ang entries:")
        for r in james_ang:
            print(f"  ID: {r['id']}, Name: {r['first_name']} {r['last_name']}, Normalized: {r['normalized_name']}, Position: {r['position']}")
        
        # Check Jernie Nisay
        jernie = await conn.fetch('''
            SELECT id, first_name, last_name, normalized_name, position
            FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%JERNIE%' AND UPPER(last_name) LIKE '%NISAY%'
            ORDER BY id
        ''')
        
        print("\nJernie Nisay entries:")
        for r in jernie:
            print(f"  ID: {r['id']}, Name: {r['first_name']} {r['last_name']}, Normalized: {r['normalized_name']}, Position: {r['position']}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_duplicates())














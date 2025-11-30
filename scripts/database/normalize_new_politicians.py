#!/usr/bin/env python3
"""Normalize new politicians from CSV to ensure consistent normalized names"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def normalize_new_politicians():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        # Both James Ang entries should use "JAMES ANG JR" as normalized name
        await conn.execute('''
            UPDATE political_dynasties
            SET normalized_name = 'JAMES ANG JR'
            WHERE id = 4145248
        ''')
        print("✅ Normalized James Ang (ID: 4145248) to 'JAMES ANG JR'")
        
        # Jernie Nisay - normalize to "JERNIE NISAY" (shorter, more common)
        await conn.execute('''
            UPDATE political_dynasties
            SET normalized_name = 'JERNIE NISAY'
            WHERE id = 4149402
        ''')
        print("✅ Normalized Jernie Nisay (ID: 4149402) to 'JERNIE NISAY'")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(normalize_new_politicians())



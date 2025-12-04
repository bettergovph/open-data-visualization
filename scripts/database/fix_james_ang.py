#!/usr/bin/env python3
"""Fix James Ang Jr. name in database"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def fix_james_ang():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        # Find the incorrectly created record
        james = await conn.fetchrow('''
            SELECT id, first_name, last_name FROM political_dynasties
            WHERE id = 4162649
        ''')
        
        if james:
            await conn.execute('''
                UPDATE political_dynasties
                SET first_name = $1, last_name = $2, normalized_name = $3
                WHERE id = $4
            ''', 'JAMES', 'ANG JR', 'JAMES ANG JR', 4162649)
            print(f"✅ Fixed James Ang Jr. (ID: {james['id']})")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_james_ang())














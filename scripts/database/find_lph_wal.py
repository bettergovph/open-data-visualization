#!/usr/bin/env python3
"""Find LPH WAL entry"""

import asyncio
import asyncpg

async def find_lph_wal():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # Search for LPH WAL
        results = await conn.fetch('''
            SELECT id, first_name, last_name, middle_name, position, year
            FROM political_dynasties
            WHERE (UPPER(first_name) LIKE '%LPH%' AND UPPER(last_name) LIKE '%WAL%')
               OR (UPPER(first_name) = 'LPH' AND UPPER(last_name) = 'WAL')
               OR (UPPER(first_name) LIKE '%LPH%' OR UPPER(last_name) LIKE '%WAL%')
            ORDER BY id
        ''')
        
        if results:
            print(f'Found {len(results)} entries:')
            for r in results:
                full_name = f'{r["first_name"]} {r["middle_name"] or ""} {r["last_name"]}'.strip()
                print(f'  ID {r["id"]}: {full_name} ({r["position"]}, {r["year"]})')
        else:
            print('No entries found with LPH or WAL')
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(find_lph_wal())






















#!/usr/bin/env python3
"""Find entries with single-letter surnames that need normalization"""

import asyncio
import asyncpg

async def find_single_letter_surnames():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # Find entries with single-letter last names: C, D, I, S
        bad_surnames = ['C', 'D', 'I', 'S']
        
        print('🔍 Searching for entries with single-letter surnames (C, D, I, S):')
        all_bad = []
        
        for surname in bad_surnames:
            results = await conn.fetch('''
                SELECT id, first_name, last_name, middle_name, position, year
                FROM political_dynasties
                WHERE UPPER(TRIM(last_name)) = $1
                ORDER BY id
            ''', surname)
            
            if results:
                print(f'\n  Found {len(results)} entries with last_name = "{surname}":')
                for r in results:
                    full_name = f'{r["first_name"]} {r["middle_name"] or ""} {r["last_name"]}'.strip()
                    print(f'    ID {r["id"]}: {full_name} ({r["position"]}, {r["year"]})')
                    all_bad.append(r)
        
        print(f'\n📊 Total problematic entries: {len(all_bad)}')
        return all_bad
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(find_single_letter_surnames())






















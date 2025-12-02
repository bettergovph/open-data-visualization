#!/usr/bin/env python3
"""Check for AY and IT surnames"""

import asyncio
import asyncpg

async def check_ay_it():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # Check for AY and IT
        for surname in ['AY', 'IT']:
            results = await conn.fetch('''
                SELECT id, first_name, last_name, middle_name, position, year
                FROM political_dynasties
                WHERE UPPER(TRIM(last_name)) = $1
                ORDER BY id
            ''', surname)
            
            if results:
                print(f'Found {len(results)} with last_name = {surname}:')
                for r in results:
                    print(f'  ID {r["id"]}: {r["first_name"]} {r["last_name"]} ({r["position"]}, {r["year"]})')
            else:
                print(f'No entries found with last_name = {surname}')
        
        # Also check if they might be in first_name with empty/invalid last_name
        print('\nChecking for entries where first_name contains AY or IT as last word:')
        for pattern in ['AY', 'IT']:
            results = await conn.fetch('''
                SELECT id, first_name, last_name, position, year
                FROM political_dynasties
                WHERE UPPER(first_name) LIKE $1
                AND (last_name IS NULL OR last_name = '' OR UPPER(TRIM(last_name)) IN ('AY', 'IT', 'AGE'))
                ORDER BY id
                LIMIT 10
            ''', f'%{pattern}')
            
            if results:
                print(f'\n  Found entries with "{pattern}" in first_name:')
                for r in results:
                    print(f'    ID {r["id"]}: {r["first_name"]} {r["last_name"]} ({r["position"]}, {r["year"]})')
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_ay_it())






















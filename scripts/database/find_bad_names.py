#!/usr/bin/env python3
"""Find problematic names that need normalization or removal"""

import asyncio
import asyncpg

async def find_bad_names():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        bad_names = [
            'karen d', 'pacifico f. discaya I', 'jazzie ann s', 'joebert c', 
            'fairybel b', 'cezarah rowena c', 'pacifico f', 'discaya it', 
            'sg ay', 'jocelyn r. natividad', 'regene ann t. miranda'
        ]
        
        print('🔍 Searching for problematic names:')
        all_results = []
        for name in bad_names:
            # Search in first_name or last_name
            results = await conn.fetch('''
                SELECT id, first_name, last_name, position, year
                FROM political_dynasties
                WHERE UPPER(first_name) LIKE $1 OR UPPER(last_name) LIKE $1
                ORDER BY year DESC
                LIMIT 5
            ''', f'%{name.upper()}%')
            
            if results:
                print(f'\n  Found "{name}":')
                for r in results:
                    print(f'    ID {r["id"]}: {r["first_name"]} {r["last_name"]} ({r["position"]}, {r["year"]})')
                    all_results.append(r)
        
        if all_results:
            print(f'\n📊 Total problematic entries found: {len(all_results)}')
            print('\n💡 These entries should be normalized or removed')
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(find_bad_names())


























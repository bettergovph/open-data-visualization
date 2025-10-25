#!/usr/bin/env python3
"""
Get full names from top 5 political dynasties
"""

import asyncio
import asyncpg

async def get_full_names():
    try:
        conn = await asyncpg.connect(
            host='localhost',
            port='5432',
            user='budget_admin',
            password='wuQ5gBYCKkZiOGb61chLcByMu',
            database='dynasty'
        )
        
        print('✅ Connected to dynasty database')
        
        # Get full names from top 5 dynasties
        top_dynasties = ['TULFO', 'TAN', 'MENDOZA', 'RODRIGUEZ', 'GO']
        
        all_names = []
        
        for dynasty in top_dynasties:
            print(f'\n📋 Getting names for {dynasty} dynasty...')
            
            query = """
                SELECT DISTINCT 
                    CONCAT(first_name, ' ', last_name) as full_name,
                    province,
                    position,
                    year
                FROM political_dynasties 
                WHERE last_name = $1
                ORDER BY year DESC, CONCAT(first_name, ' ', last_name)
                LIMIT 50
            """
            
            names = await conn.fetch(query, dynasty)
            
            print(f'   Found {len(names)} members')
            for name in names[:10]:  # Show first 10
                print(f'   - {name["full_name"]} ({name["province"]}, {name["year"]})')
            
            all_names.extend([name['full_name'] for name in names])
        
        print(f'\n📊 Total unique names collected: {len(set(all_names))}')
        
        # Save to file
        with open('top5_dynasty_names.txt', 'w') as f:
            for name in set(all_names):
                f.write(f'{name}\n')
        
        print('✅ Names saved to top5_dynasty_names.txt')
        
        await conn.close()
        
    except Exception as e:
        print(f'❌ Error: {e}')

if __name__ == "__main__":
    asyncio.run(get_full_names())

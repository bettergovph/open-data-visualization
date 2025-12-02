#!/usr/bin/env python3
"""Find all problematic names"""

import asyncio
import asyncpg

async def find_all_bad_names():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # Check for the specific bad names
        bad_names_list = [
            'SG AY', 'PACIFICO IT', 'DISCAYA IT', 'JAZZIE ANN S',
            'JOEBERT C', 'FAIRYBEL B', 'CEZARAH ROWENA C',
            'JOCELYN R. NATIVIDAD', 'REGENE ANN T. MIRANDA'
        ]
        
        print('🔍 Searching for problematic names in political_dynasties:')
        all_bad = []
        for name in bad_names_list:
            # Split name into parts
            parts = name.split()
            if len(parts) >= 2:
                first_part = parts[0]
                last_part = ' '.join(parts[1:])
                
                results = await conn.fetch('''
                    SELECT id, first_name, last_name, position, year
                    FROM political_dynasties
                    WHERE (UPPER(first_name) LIKE $1 OR UPPER(last_name) LIKE $1)
                    AND (UPPER(first_name) LIKE $2 OR UPPER(last_name) LIKE $2)
                    ORDER BY year DESC
                ''', f'%{first_part}%', f'%{last_part}%')
                
                if results:
                    print(f'\n  Found "{name}":')
                    for r in results:
                        print(f'    ID {r["id"]}: {r["first_name"]} {r["last_name"]} ({r["position"]}, {r["year"]})')
                        all_bad.append(r)
        
        # Also check contractor table
        print('\n🔍 Checking politician_contractors for bad names:')
        contractor_bad = await conn.fetch('''
            SELECT DISTINCT pc.politician_id, pc.contractor_name, pd.first_name, pd.last_name, pd.id
            FROM politician_contractors pc
            JOIN political_dynasties pd ON pc.politician_id = pd.id
            WHERE UPPER(pd.first_name || ' ' || pd.last_name) IN ('SG AY', 'PACIFICO IT', 'DISCAYA IT')
            OR (UPPER(pd.first_name) = 'SG' AND UPPER(pd.last_name) = 'AY')
            OR (UPPER(pd.first_name) LIKE '%PACIFICO%' AND UPPER(pd.last_name) = 'IT')
            OR (UPPER(pd.first_name) LIKE '%DISCAYA%' AND UPPER(pd.last_name) = 'IT')
        ''')
        if contractor_bad:
            print('  Found in contractor connections:')
            for c in contractor_bad:
                print(f'    ID {c["id"]}: {c["first_name"]} {c["last_name"]} -> {c["contractor_name"]}')
                all_bad.append(c)
        
        print(f'\n📊 Total problematic entries: {len(all_bad)}')
        return all_bad
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(find_all_bad_names())























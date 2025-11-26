#!/usr/bin/env python3
"""Check MBB connections to Bonoan and Bernardo"""

import asyncio
import asyncpg

async def check_mbb_connections():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # Find MBB entries (Manuel M. Bonoan)
        mbb_entries = await conn.fetch('''
            SELECT id, first_name, last_name, position, year
            FROM political_dynasties
            WHERE (UPPER(first_name) LIKE '%MANUEL%' AND UPPER(last_name) LIKE '%BONOAN%')
               OR (UPPER(first_name) LIKE '%MBB%')
            ORDER BY id
        ''')
        
        print('MBB/Bonoan entries:')
        for r in mbb_entries:
            print(f'  ID {r["id"]}: {r["first_name"]} {r["last_name"]} ({r["position"]}, {r["year"]})')
        
        # Find Bonoan entries
        bonoan_entries = await conn.fetch('''
            SELECT id, first_name, last_name, position, year
            FROM political_dynasties
            WHERE UPPER(last_name) LIKE '%BONOAN%'
            ORDER BY id
        ''')
        
        print('\nBonoan entries:')
        for r in bonoan_entries:
            print(f'  ID {r["id"]}: {r["first_name"]} {r["last_name"]} ({r["position"]}, {r["year"]})')
        
        # Find Bernardo entries
        bernardo_entries = await conn.fetch('''
            SELECT id, first_name, last_name, position, year
            FROM political_dynasties
            WHERE UPPER(last_name) LIKE '%BERNARDO%'
            ORDER BY id
        ''')
        
        print('\nBernardo entries:')
        for r in bernardo_entries:
            print(f'  ID {r["id"]}: {r["first_name"]} {r["last_name"]} ({r["position"]}, {r["year"]})')
        
        # Check relationships for MBB
        if mbb_entries:
            mbb_id = mbb_entries[0]['id']
            
            # Check all relationships for MBB
            all_rels = await conn.fetch('''
                SELECT r.*, 
                       p1.first_name as person1_first, p1.last_name as person1_last,
                       p2.first_name as person2_first, p2.last_name as person2_last,
                       ct.name as relationship_type_name
                FROM relationships r
                LEFT JOIN political_dynasties p1 ON r.person_id = p1.id
                LEFT JOIN political_dynasties p2 ON r.related_person_id = p2.id
                LEFT JOIN connection_types ct ON r.relationship_type = ct.id
                WHERE r.person_id = $1 OR r.related_person_id = $1
                ORDER BY r.id
            ''', mbb_id)
            
            print(f'\nAll relationships for MBB (ID {mbb_id}):')
            for r in all_rels:
                if r['person_id'] == mbb_id:
                    other = f'{r["person2_first"]} {r["person2_last"]}'
                else:
                    other = f'{r["person1_first"]} {r["person1_last"]}'
                print(f'  -> {other}: {r["relationship_description"]} ({r["relationship_type_name"]})')
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_mbb_connections())


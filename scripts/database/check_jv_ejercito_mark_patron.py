#!/usr/bin/env python3
"""Check why JV Ejercito is connected to Mark Patron"""

import asyncio
import asyncpg

async def check_jv_ejercito_mark_patron():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # Find JV Ejercito
        jv_ejercito = await conn.fetch('''
            SELECT id, first_name, last_name, position, year
            FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%JV%' AND UPPER(last_name) = 'EJERCITO'
            ORDER BY year DESC
        ''')
        
        print('📋 JV Ejercito entries:')
        for p in jv_ejercito:
            print(f'  ID {p["id"]}: {p["first_name"]} {p["last_name"]} ({p["position"]}, {p["year"]})')
        
        # Find Mark Patron
        mark_patron = await conn.fetch('''
            SELECT id, first_name, last_name, position, year
            FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%MARK%' AND UPPER(last_name) LIKE '%PATRON%'
            ORDER BY year DESC
        ''')
        
        print('\n📋 Mark Patron entries:')
        for p in mark_patron:
            print(f'  ID {p["id"]}: {p["first_name"]} {p["last_name"]} ({p["position"]}, {p["year"]})')
        
        # Check relationships between them
        if jv_ejercito and mark_patron:
            jv_ids = [p['id'] for p in jv_ejercito]
            patron_ids = [p['id'] for p in mark_patron]
            
            relationships = await conn.fetch('''
                SELECT r.id, r.person_id, r.related_person_id, r.relationship_description,
                       p1.first_name as p1_first, p1.last_name as p1_last,
                       p2.first_name as p2_first, p2.last_name as p2_last
                FROM relationships r
                JOIN political_dynasties p1 ON r.person_id = p1.id
                JOIN political_dynasties p2 ON r.related_person_id = p2.id
                WHERE (r.person_id = ANY($1) AND r.related_person_id = ANY($2))
                   OR (r.person_id = ANY($2) AND r.related_person_id = ANY($1))
            ''', jv_ids, patron_ids)
            
            if relationships:
                print('\n🔗 Relationships found:')
                for r in relationships:
                    print(f'  {r["p1_first"]} {r["p1_last"]} -> {r["p2_first"]} {r["p2_last"]}')
                    print(f'    Description: {r["relationship_description"]}')
            else:
                print('\n❌ No direct relationship found')
                print('\n🔍 Checking for indirect connections via party-list or contractors...')
                
                # Check party-list connections
                party_list_conn = await conn.fetch('''
                    SELECT DISTINCT pl1.person_id as p1_id, pl2.person_id as p2_id,
                           pl1.party_list_number as pl1_num, pl2.party_list_number as pl2_num,
                           pd1.first_name as p1_first, pd1.last_name as p1_last,
                           pd2.first_name as p2_first, pd2.last_name as p2_last
                    FROM party_list_members pl1
                    JOIN party_list_members pl2 ON pl1.party_list_number = pl2.party_list_number
                    JOIN political_dynasties pd1 ON pl1.person_id = pd1.id
                    JOIN political_dynasties pd2 ON pl2.person_id = pd2.id
                    WHERE pl1.person_id != pl2.person_id
                    AND (pl1.person_id = ANY($1) AND pl2.person_id = ANY($2))
                ''', jv_ids, patron_ids)
                
                if party_list_conn:
                    print('  Found party-list connection:')
                    for c in party_list_conn:
                        print(f'    {c["p1_first"]} {c["p1_last"]} and {c["p2_first"]} {c["p2_last"]} both in party-list #{c["pl1_num"]}')
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_jv_ejercito_mark_patron())






















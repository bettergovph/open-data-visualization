#!/usr/bin/env python3
"""Check how Legarda connects to St. Timothy"""

import asyncio
import asyncpg

async def check_legarda_st_timothy():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # Find all people connected to St. Timothy
        st_timothy_people = await conn.fetch('''
            SELECT DISTINCT pc.politician_id, pd.first_name, pd.last_name
            FROM politician_contractors pc
            JOIN political_dynasties pd ON pc.politician_id = pd.id
            WHERE UPPER(pc.contractor_name) LIKE '%ST%TIMOTHY%'
        ''')
        
        print(f'📋 People connected to St. Timothy ({len(st_timothy_people)} found):')
        for p in st_timothy_people[:10]:
            print(f'  {p["first_name"]} {p["last_name"]} (ID {p["politician_id"]})')
        
        # Check if any of these are connected to Legarda via relationships
        if st_timothy_people:
            st_timothy_ids = [p['politician_id'] for p in st_timothy_people]
            
            # Find Legarda
            legarda = await conn.fetchrow('''
                SELECT id, first_name, last_name
                FROM political_dynasties
                WHERE UPPER(last_name) = 'LEGARDA' AND UPPER(first_name) = 'LOREN'
                ORDER BY year DESC
                LIMIT 1
            ''')
            
            if legarda:
                legarda_id = legarda['id']
                print(f'\n📋 Loren Legarda (ID {legarda_id})')
                
                # Check if Legarda is connected to any St. Timothy people
                connections = await conn.fetch('''
                    SELECT DISTINCT 
                        CASE WHEN r.person_id = $1 THEN r.related_person_id ELSE r.person_id END as connected_id,
                        pd.first_name, pd.last_name,
                        r.relationship_description
                    FROM relationships r
                    JOIN political_dynasties pd ON (
                        CASE WHEN r.person_id = $1 THEN r.related_person_id ELSE r.person_id END = pd.id
                    )
                    WHERE (r.person_id = $1 OR r.related_person_id = $1)
                    AND (CASE WHEN r.person_id = $1 THEN r.related_person_id ELSE r.person_id END = ANY($2))
                ''', legarda_id, st_timothy_ids)
                
                if connections:
                    print(f'\n✅ Found {len(connections)} connection(s) from Legarda to St. Timothy people:')
                    for c in connections:
                        print(f'  Loren Legarda -> {c["first_name"]} {c["last_name"]} ({c["relationship_description"]}) -> St. Timothy')
                else:
                    print('\n❌ No direct relationship found between Legarda and St. Timothy people')
                    print('   The connection might be through multiple hops or via contractor relationships only')
                    print('\n💡 Note: The constellation cache shows no chains with Legarda or St. Timothy,')
                    print('   which suggests they may not be connected through the relationship graph.')
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_legarda_st_timothy())


























#!/usr/bin/env python3
"""Find relationship chain from Legarda to St. Timothy"""

import asyncio
import asyncpg

async def find_legarda_chain():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # Get Legarda ID
        legarda = await conn.fetchrow('''
            SELECT id, first_name, last_name
            FROM political_dynasties
            WHERE UPPER(last_name) = 'LEGARDA' AND UPPER(first_name) = 'LOREN'
            ORDER BY year DESC
            LIMIT 1
        ''')
        
        if not legarda:
            print('❌ Loren Legarda not found')
            return
        
        legarda_id = legarda['id']
        print(f'✅ Found Loren Legarda (ID {legarda_id})')
        
        # Find people connected to Legarda via relationships
        connected = await conn.fetch('''
            SELECT DISTINCT 
                CASE WHEN r.person_id = $1 THEN r.related_person_id ELSE r.person_id END as connected_id,
                pd.first_name, pd.last_name,
                r.relationship_description
            FROM relationships r
            JOIN political_dynasties pd ON (
                CASE WHEN r.person_id = $1 THEN r.related_person_id ELSE r.person_id END = pd.id
            )
            WHERE r.person_id = $1 OR r.related_person_id = $1
            LIMIT 20
        ''', legarda_id)
        
        print(f'\n📋 People connected to Loren Legarda ({len(connected)} found):')
        for c in connected[:10]:
            print(f'  {c["first_name"]} {c["last_name"]} (ID {c["connected_id"]}) - {c["relationship_description"]}')
        
        # Check if any of these connected people have St. Timothy connections
        if connected:
            connected_ids = [c['connected_id'] for c in connected]
            st_timothy_connected = await conn.fetch('''
                SELECT DISTINCT pc.politician_id, pc.contractor_name, pd.first_name, pd.last_name
                FROM politician_contractors pc
                JOIN political_dynasties pd ON pc.politician_id = pd.id
                WHERE pc.politician_id = ANY($1)
                AND UPPER(pc.contractor_name) LIKE '%ST%TIMOTHY%'
            ''', connected_ids)
            
            if st_timothy_connected:
                print('\n✅ Found Legarda -> St. Timothy connection path:')
                for c in st_timothy_connected:
                    print(f'  Loren Legarda -> (relationship) -> {c["first_name"]} {c["last_name"]} -> {c["contractor_name"]}')
            else:
                print('\n❌ No St. Timothy connection found through direct relationships')
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(find_legarda_chain())











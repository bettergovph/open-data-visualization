#!/usr/bin/env python3
"""Find how Legarda connects to St. Timothy"""

import asyncio
import asyncpg

async def find_legarda_st_timothy():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # Find Legarda
        legarda = await conn.fetch('''
            SELECT id, first_name, last_name, position
            FROM political_dynasties
            WHERE UPPER(last_name) LIKE '%LEGARDA%'
            ORDER BY year DESC
            LIMIT 5
        ''')
        print('📋 Legarda entries:')
        for p in legarda:
            print(f'  ID {p["id"]}: {p["first_name"]} {p["last_name"]} ({p["position"]})')
        
        # Find St. Timothy contractor connections
        st_timothy = await conn.fetch('''
            SELECT DISTINCT pc.politician_id, pc.contractor_name, pd.first_name, pd.last_name
            FROM politician_contractors pc
            JOIN political_dynasties pd ON pc.politician_id = pd.id
            WHERE UPPER(pc.contractor_name) LIKE '%ST%TIMOTHY%'
            LIMIT 10
        ''')
        print('\n📋 St. Timothy contractor connections:')
        for c in st_timothy:
            print(f'  {c["first_name"]} {c["last_name"]} (ID {c["politician_id"]}) -> {c["contractor_name"]}')
        
        # Check if any Legarda is connected to St. Timothy
        if legarda:
            legarda_ids = [p['id'] for p in legarda]
            connections = await conn.fetch('''
                SELECT DISTINCT pc.politician_id, pc.contractor_name, pd.first_name, pd.last_name
                FROM politician_contractors pc
                JOIN political_dynasties pd ON pc.politician_id = pd.id
                WHERE pc.politician_id = ANY($1)
                AND UPPER(pc.contractor_name) LIKE '%ST%TIMOTHY%'
            ''', legarda_ids)
            if connections:
                print('\n✅ Direct Legarda -> St. Timothy connections:')
                for c in connections:
                    print(f'  {c["first_name"]} {c["last_name"]} -> {c["contractor_name"]}')
            else:
                print('\n❌ No direct Legarda -> St. Timothy connection found')
                # Check indirect connections via relationships
                print('\n🔗 Checking indirect connections via relationships...')
                indirect = await conn.fetch('''
                    WITH legarda_connected AS (
                        SELECT DISTINCT r.related_person_id as person_id
                        FROM relationships r
                        WHERE r.person_id = ANY($1)
                        UNION
                        SELECT DISTINCT r.person_id
                        FROM relationships r
                        WHERE r.related_person_id = ANY($1)
                    )
                    SELECT DISTINCT pc.politician_id, pc.contractor_name, pd.first_name, pd.last_name
                    FROM politician_contractors pc
                    JOIN political_dynasties pd ON pc.politician_id = pd.id
                    JOIN legarda_connected lc ON pc.politician_id = lc.person_id
                    WHERE UPPER(pc.contractor_name) LIKE '%ST%TIMOTHY%'
                ''', legarda_ids)
                if indirect:
                    print('✅ Indirect Legarda -> St. Timothy connections:')
                    for c in indirect:
                        print(f'  {c["first_name"]} {c["last_name"]} (connected to Legarda) -> {c["contractor_name"]}')
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(find_legarda_st_timothy())











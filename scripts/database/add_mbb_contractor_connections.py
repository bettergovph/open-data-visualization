#!/usr/bin/env python3
"""Add MBB contractor connections: Manuel Bonoan -> MBB, Roberto Bernardo -> MBB"""

import asyncio
import asyncpg

async def add_mbb_contractor_connections():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # Find Manuel Bonoan
        mbb_person = await conn.fetchrow('''
            SELECT id, first_name, last_name, position
            FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%MANUEL%' 
              AND UPPER(last_name) LIKE '%BONOAN%'
              AND (UPPER(position) LIKE '%DPWH%' OR UPPER(position) LIKE '%SECRETARY%')
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not mbb_person:
            print("❌ Manuel Bonoan not found")
            return
        
        print(f"✅ Found Manuel Bonoan: ID {mbb_person['id']} - {mbb_person['first_name']} {mbb_person['last_name']}")
        
        # Find Roberto Bernardo
        bernardo = await conn.fetchrow('''
            SELECT id, first_name, last_name, position
            FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%ROBERTO%' 
              AND UPPER(last_name) LIKE '%BERNARDO%'
              AND (UPPER(position) LIKE '%DPWH%' OR UPPER(position) LIKE '%UNDERSECRETARY%')
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not bernardo:
            print("❌ Roberto Bernardo not found")
            return
        
        print(f"✅ Found Roberto Bernardo: ID {bernardo['id']} - {bernardo['first_name']} {bernardo['last_name']}")
        
        # Check if MBB contractor connections already exist
        mbb_contractor_name = "MBB"
        
        # Check for Manuel Bonoan -> MBB
        existing_bonoan = await conn.fetchrow('''
            SELECT id FROM politician_contractors
            WHERE politician_id = $1 AND contractor_name = $2
        ''', mbb_person['id'], mbb_contractor_name)
        
        if existing_bonoan:
            print(f"✅ Manuel Bonoan -> MBB connection already exists (ID {existing_bonoan['id']})")
        else:
            # Add Manuel Bonoan -> MBB
            source_url = "https://newsinfo.inquirer.net/2140264/former-dpwh-official-links-more-senators-to-kickbacks"
            conn_id = await conn.fetchval('''
                INSERT INTO politician_contractors (politician_id, contractor_name, match_confidence, notes, source)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            ''', mbb_person['id'], mbb_contractor_name, 9, 
                "Manuel Bonoan connected to MBB contractor", source_url)
            print(f"✅ Added Manuel Bonoan -> MBB connection (ID {conn_id})")
        
        # Check for Roberto Bernardo -> MBB
        existing_bernardo = await conn.fetchrow('''
            SELECT id FROM politician_contractors
            WHERE politician_id = $1 AND contractor_name = $2
        ''', bernardo['id'], mbb_contractor_name)
        
        if existing_bernardo:
            print(f"✅ Roberto Bernardo -> MBB connection already exists (ID {existing_bernardo['id']})")
        else:
            # Add Roberto Bernardo -> MBB
            source_url = "https://newsinfo.inquirer.net/2140264/former-dpwh-official-links-more-senators-to-kickbacks"
            conn_id = await conn.fetchval('''
                INSERT INTO politician_contractors (politician_id, contractor_name, match_confidence, notes, source)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            ''', bernardo['id'], mbb_contractor_name, 9,
                "Roberto Bernardo connected to MBB contractor", source_url)
            print(f"✅ Added Roberto Bernardo -> MBB connection (ID {conn_id})")
        
        # Remove the direct relationship if it exists (since they should only connect through MBB)
        direct_rel = await conn.fetchrow('''
            SELECT id FROM relationships
            WHERE person_id = $1 AND related_person_id = $2
        ''', mbb_person['id'], bernardo['id'])
        
        if direct_rel:
            await conn.execute('DELETE FROM relationships WHERE id = $1', direct_rel['id'])
            print(f"🗑️  Removed direct relationship (ID {direct_rel['id']}) - they should connect through MBB contractor")
        
        print("\n✅ Done! Manuel Bonoan and Roberto Bernardo are now connected through MBB contractor")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(add_mbb_contractor_connections())









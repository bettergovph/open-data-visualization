#!/usr/bin/env python3
"""Normalize eden lyrea.co entry"""

import asyncio
import asyncpg

async def normalize_eden_lyrea():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # Find eden lyrea.co
        entry = await conn.fetchrow('''
            SELECT id, first_name, last_name, middle_name, position, year
            FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%EDEN%'
               AND (UPPER(last_name) LIKE '%LYREA%' OR UPPER(last_name) LIKE '%.CO%')
            LIMIT 1
        ''')
        
        if not entry:
            print('❌ eden lyrea.co entry not found')
            return
        
        print(f'🔍 Found: ID {entry["id"]}: {entry["first_name"]} {entry["last_name"]} ({entry["position"]}, {entry["year"]})')
        
        # Check if there's an existing "Eden Lyrea" entry (without .co)
        existing = await conn.fetchrow('''
            SELECT id, first_name, last_name, position, year
            FROM political_dynasties
            WHERE UPPER(first_name) = 'EDEN'
              AND UPPER(last_name) = 'LYREA'
              AND id != $1
            LIMIT 1
        ''', entry['id'])
        
        if existing:
            print(f'  Found existing entry: ID {existing["id"]}: {existing["first_name"]} {existing["last_name"]}')
            print('  Merging...')
            
            # Delete duplicate contractor connections first
            await conn.execute('''
                DELETE FROM politician_contractors pc1
                WHERE pc1.politician_id = $1
                AND EXISTS (
                    SELECT 1 FROM politician_contractors pc2
                    WHERE pc2.politician_id = $2
                    AND pc2.contractor_name = pc1.contractor_name
                )
            ''', existing['id'], entry['id'])
            
            # Move relationships
            await conn.execute('''
                UPDATE relationships
                SET person_id = $1
                WHERE person_id = $2
            ''', existing['id'], entry['id'])
            
            await conn.execute('''
                UPDATE relationships
                SET related_person_id = $1
                WHERE related_person_id = $2
            ''', existing['id'], entry['id'])
            
            # Move contractor connections
            await conn.execute('''
                UPDATE politician_contractors
                SET politician_id = $1
                WHERE politician_id = $2
            ''', existing['id'], entry['id'])
            
            # Delete the duplicate
            await conn.execute('DELETE FROM political_dynasties WHERE id = $1', entry['id'])
            print(f'  ✅ Merged and removed duplicate')
        else:
            # Normalize by removing .co from last name
            new_last_name = entry['last_name'].replace('.co', '').replace('.CO', '').strip()
            if new_last_name:
                await conn.execute('''
                    UPDATE political_dynasties
                    SET last_name = $1
                    WHERE id = $2
                ''', new_last_name, entry['id'])
                print(f'  ✅ Normalized: "{entry["last_name"]}" -> "{new_last_name}"')
            else:
                print(f'  ⚠️  Cannot normalize - last name would be empty')
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(normalize_eden_lyrea())






















#!/usr/bin/env python3
"""Merge remaining Pacifico F. Discaya with Pacifico Discaya"""

import asyncio
import asyncpg

async def merge_remaining_pacifico():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # Find Pacifico F. Discaya (ID 4162534)
        pacifico_f = await conn.fetchrow('''
            SELECT id, first_name, last_name, position, year
            FROM political_dynasties
            WHERE id = 4162534
        ''')
        
        if not pacifico_f:
            print('❌ Pacifico F. Discaya (ID 4162534) not found')
            return
        
        print(f'🔍 Found: ID {pacifico_f["id"]}: {pacifico_f["first_name"]} {pacifico_f["last_name"]}')
        
        # Find Pacifico Discaya (ID 4162510)
        pacifico_discaya = await conn.fetchrow('''
            SELECT id, first_name, last_name, position, year
            FROM political_dynasties
            WHERE id = 4162510
        ''')
        
        if not pacifico_discaya:
            print('❌ Pacifico Discaya (ID 4162510) not found')
            return
        
        print(f'🔍 Found to merge with: ID {pacifico_discaya["id"]}: {pacifico_discaya["first_name"]} {pacifico_discaya["last_name"]}')
        
        # Delete duplicate contractor connections first
        await conn.execute('''
            DELETE FROM politician_contractors pc1
            WHERE pc1.politician_id = $1
            AND EXISTS (
                SELECT 1 FROM politician_contractors pc2
                WHERE pc2.politician_id = $2
                AND pc2.contractor_name = pc1.contractor_name
            )
        ''', pacifico_discaya['id'], pacifico_f['id'])
        
        # Move relationships
        await conn.execute('''
            UPDATE relationships
            SET person_id = $1
            WHERE person_id = $2
        ''', pacifico_discaya['id'], pacifico_f['id'])
        
        await conn.execute('''
            UPDATE relationships
            SET related_person_id = $1
            WHERE related_person_id = $2
        ''', pacifico_discaya['id'], pacifico_f['id'])
        
        # Move contractor connections
        await conn.execute('''
            UPDATE politician_contractors
            SET politician_id = $1
            WHERE politician_id = $2
        ''', pacifico_discaya['id'], pacifico_f['id'])
        
        # Delete the duplicate
        await conn.execute('DELETE FROM political_dynasties WHERE id = $1', pacifico_f['id'])
        print(f'  ✅ Merged and removed duplicate')
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(merge_remaining_pacifico())










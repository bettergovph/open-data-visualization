#!/usr/bin/env python3
"""Update MBB contractor name to MBB GLOBAL PROPERTIES and remove direct relationship"""

import asyncio
import asyncpg

async def update_mbb_contractor_name():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # Delete old MBB entries (MBB GLOBAL PROPERTIES already exists)
        result = await conn.execute('''
            DELETE FROM politician_contractors
            WHERE contractor_name = 'MBB'
        ''')
        print(f'✅ Deleted old MBB contractor connections (MBB GLOBAL PROPERTIES already exists)')
        
        # Remove direct relationship between Manuel Bonoan and Roberto Bernardo
        direct_rel = await conn.fetchrow('''
            SELECT id FROM relationships
            WHERE person_id = $1 AND related_person_id = $2
        ''', 4162630, 4162626)
        
        if direct_rel:
            await conn.execute('DELETE FROM relationships WHERE id = $1', direct_rel['id'])
            print(f'🗑️  Removed direct relationship (ID {direct_rel["id"]})')
        else:
            print('ℹ️  No direct relationship found to remove')
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(update_mbb_contractor_name())


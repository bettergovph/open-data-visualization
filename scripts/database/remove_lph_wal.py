#!/usr/bin/env python3
"""Remove LPH WAL entry"""

import asyncio
import asyncpg

async def remove_lph_wal():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # Find the LPH WAL entry
        entry = await conn.fetchrow('''
            SELECT id, first_name, last_name, position, year
            FROM political_dynasties
            WHERE id = 4162519
        ''')
        
        if not entry:
            print('❌ LPH WAL entry not found')
            return
        
        print(f'🔍 Found entry: ID {entry["id"]}: {entry["first_name"]} {entry["last_name"]} ({entry["position"]}, {entry["year"]})')
        
        # Check relationships
        rels = await conn.fetchrow('''
            SELECT COUNT(*) as count
            FROM relationships
            WHERE person_id = $1 OR related_person_id = $1
        ''', entry['id'])
        
        # Check contractor connections
        contractors = await conn.fetchrow('''
            SELECT COUNT(*) as count
            FROM politician_contractors
            WHERE politician_id = $1
        ''', entry['id'])
        
        print(f'  Has {rels["count"]} relationships, {contractors["count"]} contractor connections')
        
        # Delete relationships
        if rels['count'] > 0:
            await conn.execute('''
                DELETE FROM relationships
                WHERE person_id = $1 OR related_person_id = $1
            ''', entry['id'])
            print(f'  🗑️  Deleted {rels["count"]} relationships')
        
        # Delete contractor connections
        if contractors['count'] > 0:
            await conn.execute('''
                DELETE FROM politician_contractors
                WHERE politician_id = $1
            ''', entry['id'])
            print(f'  🗑️  Deleted {contractors["count"]} contractor connections')
        
        # Delete the person
        await conn.execute('''
            DELETE FROM political_dynasties
            WHERE id = $1
        ''', entry['id'])
        
        print(f'  ✅ Removed LPH WAL entry (ID {entry["id"]})')
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(remove_lph_wal())

























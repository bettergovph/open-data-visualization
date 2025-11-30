#!/usr/bin/env python3
"""Unify Manuel Bonoan entries"""

import asyncio
import asyncpg

async def unify_manuel_bonoan():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # Get all Manuel Bonoan entries
        entries = await conn.fetch('''
            SELECT id, first_name, last_name, position, unified_person_id, normalized_name
            FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%MANUEL%' 
              AND UPPER(last_name) LIKE '%BONOAN%'
            ORDER BY id
        ''')
        
        if len(entries) < 2:
            print("✅ Only one Manuel Bonoan entry found, no unification needed")
            return
        
        # Use the lowest ID as canonical
        canonical_id = entries[0]['id']
        print(f"📌 Using ID {canonical_id} as canonical: {entries[0]['first_name']} {entries[0]['last_name']}")
        
        # Update all other entries to point to canonical
        for entry in entries[1:]:
            print(f"🔗 Unifying ID {entry['id']} -> {canonical_id}")
            
            # Update relationships
            await conn.execute('''
                UPDATE relationships 
                SET person_id = $1 
                WHERE person_id = $2
            ''', canonical_id, entry['id'])
            
            await conn.execute('''
                UPDATE relationships 
                SET related_person_id = $1 
                WHERE related_person_id = $2
            ''', canonical_id, entry['id'])
            
            # Update politician_contractors
            await conn.execute('''
                UPDATE politician_contractors 
                SET politician_id = $1 
                WHERE politician_id = $2
            ''', canonical_id, entry['id'])
            
            # Update unified_person_id
            await conn.execute('''
                UPDATE political_dynasties 
                SET unified_person_id = $1 
                WHERE id = $2
            ''', canonical_id, entry['id'])
            
            # Normalize name to match canonical
            await conn.execute('''
                UPDATE political_dynasties 
                SET first_name = $1, last_name = $2, normalized_name = $3
                WHERE id = $4
            ''', entries[0]['first_name'], entries[0]['last_name'], 
                f"{entries[0]['first_name']} {entries[0]['last_name']}", entry['id'])
        
        # Set unified_person_id for canonical entry
        await conn.execute('''
            UPDATE political_dynasties 
            SET unified_person_id = $1 
            WHERE id = $1
        ''', canonical_id)
        
        print(f"\n✅ Unified {len(entries)} Manuel Bonoan entries to ID {canonical_id}")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(unify_manuel_bonoan())













#!/usr/bin/env python3
"""
Remove problematic names from political_dynasties and related tables
These are incomplete/malformed entries that should be removed.
"""

import asyncio
import asyncpg

async def remove_bad_names():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # IDs to remove (incomplete/malformed names)
        ids_to_remove = [
            4162556,  # SG Ay
            4162555,  # Pacifico It
            4162528,  # Fairybel B
        ]
        
        print('🧹 Removing problematic names...\n')
        
        # Show what will be deleted
        total_rels = 0
        total_contractors = 0
        for pid in ids_to_remove:
            person = await conn.fetchrow('''
                SELECT id, first_name, last_name, position, year
                FROM political_dynasties
                WHERE id = $1
            ''', pid)
            
            if person:
                print(f'  Removing: ID {person["id"]}: {person["first_name"]} {person["last_name"]} ({person["position"]}, {person["year"]})')
                
                # Count relationships
                rels = await conn.fetchrow('''
                    SELECT COUNT(*) as count
                    FROM relationships
                    WHERE person_id = $1 OR related_person_id = $1
                ''', pid)
                rel_count = rels['count'] if rels else 0
                total_rels += rel_count
                if rel_count > 0:
                    print(f'    - {rel_count} relationships will be deleted')
                
                # Count contractor connections
                contractors = await conn.fetchrow('''
                    SELECT COUNT(*) as count
                    FROM politician_contractors
                    WHERE politician_id = $1
                ''', pid)
                contractor_count = contractors['count'] if contractors else 0
                total_contractors += contractor_count
                if contractor_count > 0:
                    print(f'    - {contractor_count} contractor connections will be deleted')
        
        print(f'\n📊 Summary:')
        print(f'  - {len(ids_to_remove)} people to remove')
        print(f'  - {total_rels} relationships to remove')
        print(f'  - {total_contractors} contractor connections to remove')
        
        # Delete relationships first
        print('\n🗑️  Deleting relationships...')
        for pid in ids_to_remove:
            deleted = await conn.execute('''
                DELETE FROM relationships
                WHERE person_id = $1 OR related_person_id = $1
            ''', pid)
            print(f'  Deleted relationships for ID {pid}')
        
        # Delete contractor connections
        print('🗑️  Deleting contractor connections...')
        for pid in ids_to_remove:
            deleted = await conn.execute('''
                DELETE FROM politician_contractors
                WHERE politician_id = $1
            ''', pid)
            print(f'  Deleted contractor connections for ID {pid}')
        
        # Delete the people
        print('🗑️  Deleting people...')
        for pid in ids_to_remove:
            deleted = await conn.execute('''
                DELETE FROM political_dynasties
                WHERE id = $1
            ''', pid)
            print(f'  Deleted person ID {pid}')
        
        print(f'\n✅ Successfully removed {len(ids_to_remove)} problematic entries')
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(remove_bad_names())












#!/usr/bin/env python3
"""
Clean up problematic names in political_dynasties and politician_contractors
Names to remove/normalize:
- SG Ay (ID 4162556)
- Pacifico It (ID 4162555) - likely should be "Pacifico F. Discaya"
- Fairybel B (ID 4162528)
- Karen D (ID 4159757) - might be "Karen Dhaile Manera" which is OK
- Pacifico F. Discaya I (ID 4162511) - check if this is a duplicate
- Pacifico F. Discaya (ID 4162534) - check if this is a duplicate
"""

import asyncio
import asyncpg

async def clean_bad_names():
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
        
        print('🧹 Cleaning up problematic names...')
        
        # Check what will be deleted
        for pid in ids_to_remove:
            person = await conn.fetchrow('''
                SELECT id, first_name, last_name, position, year
                FROM political_dynasties
                WHERE id = $1
            ''', pid)
            
            if person:
                print(f'\n  Will remove: ID {person["id"]}: {person["first_name"]} {person["last_name"]} ({person["position"]}, {person["year"]})')
                
                # Check relationships
                rels = await conn.fetch('''
                    SELECT COUNT(*) as count
                    FROM relationships
                    WHERE person_id = $1 OR related_person_id = $1
                ''', pid)
                if rels[0]['count'] > 0:
                    print(f'    ⚠️  Has {rels[0]["count"]} relationships - will be deleted')
                
                # Check contractor connections
                contractors = await conn.fetch('''
                    SELECT COUNT(*) as count
                    FROM politician_contractors
                    WHERE politician_id = $1
                ''', pid)
                if contractors[0]['count'] > 0:
                    print(f'    ⚠️  Has {contractors[0]["count"]} contractor connections - will be deleted')
        
        # Ask for confirmation
        print('\n⚠️  This will permanently delete these entries and their relationships/contractor connections.')
        print('   Continue? (y/n): ', end='')
        
        # For now, just show what would be deleted
        # Uncomment below to actually delete:
        """
        response = input().strip().lower()
        if response != 'y':
            print('❌ Cancelled')
            return
        
        # Delete relationships first
        for pid in ids_to_remove:
            await conn.execute('''
                DELETE FROM relationships
                WHERE person_id = $1 OR related_person_id = $1
            ''', pid)
        
        # Delete contractor connections
        for pid in ids_to_remove:
            await conn.execute('''
                DELETE FROM politician_contractors
                WHERE politician_id = $1
            ''', pid)
        
        # Delete the people
        for pid in ids_to_remove:
            await conn.execute('''
                DELETE FROM political_dynasties
                WHERE id = $1
            ''', pid)
        
        print(f'✅ Deleted {len(ids_to_remove)} problematic entries')
        """
        
        # Check for Pacifico F. Discaya duplicates
        print('\n🔍 Checking for Pacifico F. Discaya duplicates:')
        discaya_entries = await conn.fetch('''
            SELECT id, first_name, last_name, position, year
            FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%PACIFICO%'
            AND UPPER(last_name) LIKE '%DISCAYA%'
            ORDER BY id
        ''')
        
        if discaya_entries:
            print(f'  Found {len(discaya_entries)} entries:')
            for e in discaya_entries:
                print(f'    ID {e["id"]}: {e["first_name"]} {e["last_name"]} ({e["position"]}, {e["year"]})')
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(clean_bad_names())











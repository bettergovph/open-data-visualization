#!/usr/bin/env python3
"""
Normalize or remove entries with invalid surnames (ay, it, age).
These are not valid surnames - they're likely fragments of incomplete names.
"""

import asyncio
import asyncpg
import re

async def normalize_bad_surnames():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        bad_surnames = ['AY', 'IT', 'AGE']
        
        print('🔍 Finding entries with invalid surnames...')
        all_bad = []
        
        for surname in bad_surnames:
            results = await conn.fetch('''
                SELECT id, first_name, last_name, middle_name, position, year
                FROM political_dynasties
                WHERE UPPER(last_name) = $1
                ORDER BY id
            ''', surname)
            
            if results:
                all_bad.extend(results)
        
        print(f'\n📊 Found {len(all_bad)} entries with invalid surnames')
        
        ids_to_remove = []
        ids_to_normalize = []
        
        for entry in all_bad:
            first_name = entry['first_name'] or ''
            middle_name = entry['middle_name'] or ''
            last_name = entry['last_name']
            
            # Check if first_name has multiple words that could be split
            first_words = first_name.strip().split()
            
            if len(first_words) > 1:
                # Can normalize: move last word of first_name to last_name
                new_first = ' '.join(first_words[:-1])
                new_last = first_words[-1]
                ids_to_normalize.append({
                    'id': entry['id'],
                    'old_first': first_name,
                    'old_last': last_name,
                    'new_first': new_first,
                    'new_last': new_last
                })
                print(f'\n  ID {entry["id"]}: Can normalize')
                print(f'    "{first_name} {last_name}" -> "{new_first} {new_last}"')
            else:
                # Cannot normalize - remove
                ids_to_remove.append(entry['id'])
                print(f'\n  ID {entry["id"]}: Cannot normalize - will remove')
                print(f'    "{first_name} {last_name}" ({entry["position"]}, {entry["year"]})')
        
        print(f'\n📊 Summary:')
        print(f'  - {len(ids_to_normalize)} entries to normalize')
        print(f'  - {len(ids_to_remove)} entries to remove')
        
        # Normalize entries
        if ids_to_normalize:
            print('\n🔧 Normalizing entries...')
            for entry in ids_to_normalize:
                await conn.execute('''
                    UPDATE political_dynasties
                    SET first_name = $1, last_name = $2
                    WHERE id = $3
                ''', entry['new_first'], entry['new_last'], entry['id'])
                print(f'  ✅ Normalized ID {entry["id"]}: "{entry["old_first"]} {entry["old_last"]}" -> "{entry["new_first"]} {entry["new_last"]}"')
        
        # Remove entries that can't be normalized
        if ids_to_remove:
            print('\n🗑️  Removing entries that cannot be normalized...')
            
            # Count what will be deleted
            for pid in ids_to_remove:
                rels = await conn.fetchrow('''
                    SELECT COUNT(*) as count
                    FROM relationships
                    WHERE person_id = $1 OR related_person_id = $1
                ''', pid)
                contractors = await conn.fetchrow('''
                    SELECT COUNT(*) as count
                    FROM politician_contractors
                    WHERE politician_id = $1
                ''', pid)
                
                if rels['count'] > 0 or contractors['count'] > 0:
                    print(f'  ID {pid}: Has {rels["count"]} relationships, {contractors["count"]} contractor connections')
            
            # Delete relationships
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
            
            print(f'  ✅ Removed {len(ids_to_remove)} entries')
        
        print(f'\n✅ Completed: {len(ids_to_normalize)} normalized, {len(ids_to_remove)} removed')
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(normalize_bad_surnames())










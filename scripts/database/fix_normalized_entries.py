#!/usr/bin/env python3
"""Fix incorrectly normalized entries by merging with existing entries or removing them"""

import asyncio
import asyncpg

async def fix_normalized_entries():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # 1. Fix "Cezarah Rowena" (ID 4162507) - should merge with "Cezarah Rowena Discaya"
        print('🔍 Checking Cezarah Rowena entry...')
        cezarah_rowena = await conn.fetchrow('''
            SELECT id, first_name, last_name, position, year
            FROM political_dynasties
            WHERE id = 4162507
        ''')
        
        if cezarah_rowena:
            print(f'  Found: ID {cezarah_rowena["id"]}: {cezarah_rowena["first_name"]} {cezarah_rowena["last_name"]}')
            
            # Check for Cezarah Rowena Discaya
            cezarah_discaya = await conn.fetchrow('''
                SELECT id, first_name, last_name, position, year
                FROM political_dynasties
                WHERE UPPER(first_name) LIKE '%CEZARAH%ROWENA%' 
                   OR (UPPER(first_name) LIKE '%CEZARAH%' AND UPPER(last_name) = 'DISCAYA')
                ORDER BY id
                LIMIT 1
            ''')
            
            if cezarah_discaya:
                print(f'  Found to merge with: ID {cezarah_discaya["id"]}: {cezarah_discaya["first_name"]} {cezarah_discaya["last_name"]}')
                
                # Move relationships and contractor connections to the target entry
                await conn.execute('''
                    UPDATE relationships
                    SET person_id = $1
                    WHERE person_id = $2
                ''', cezarah_discaya['id'], cezarah_rowena['id'])
                
                await conn.execute('''
                    UPDATE relationships
                    SET related_person_id = $1
                    WHERE related_person_id = $2
                ''', cezarah_discaya['id'], cezarah_rowena['id'])
                
                await conn.execute('''
                    UPDATE politician_contractors
                    SET politician_id = $1
                    WHERE politician_id = $2
                ''', cezarah_discaya['id'], cezarah_rowena['id'])
                
                # Delete the duplicate
                await conn.execute('DELETE FROM political_dynasties WHERE id = $1', cezarah_rowena['id'])
                print(f'  ✅ Merged and removed duplicate')
            else:
                # Update to Cezarah Rowena Discaya
                await conn.execute('''
                    UPDATE political_dynasties
                    SET first_name = 'Cezarah Rowena', last_name = 'Discaya'
                    WHERE id = $1
                ''', cezarah_rowena['id'])
                print(f'  ✅ Updated to Cezarah Rowena Discaya')
        
        # 2. Fix "Pacifico F. Discaya" (ID 4162511) - should merge with existing Pacifico Discaya
        print('\n🔍 Checking Pacifico F. Discaya entry...')
        pacifico_f = await conn.fetchrow('''
            SELECT id, first_name, last_name, position, year
            FROM political_dynasties
            WHERE id = 4162511
        ''')
        
        if pacifico_f:
            print(f'  Found: ID {pacifico_f["id"]}: {pacifico_f["first_name"]} {pacifico_f["last_name"]}')
            
            # Check for existing Pacifico Discaya (without F.)
            pacifico_discaya = await conn.fetchrow('''
                SELECT id, first_name, last_name, position, year
                FROM political_dynasties
                WHERE UPPER(first_name) LIKE '%PACIFICO%'
                  AND UPPER(last_name) = 'DISCAYA'
                  AND id != $1
                ORDER BY id
                LIMIT 1
            ''', pacifico_f['id'])
            
            if pacifico_discaya:
                print(f'  Found to merge with: ID {pacifico_discaya["id"]}: {pacifico_discaya["first_name"]} {pacifico_discaya["last_name"]}')
                
                # Move relationships and contractor connections
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
                
                # Delete duplicate contractor connections first, then move non-duplicates
                await conn.execute('''
                    DELETE FROM politician_contractors pc1
                    WHERE pc1.politician_id = $1
                    AND EXISTS (
                        SELECT 1 FROM politician_contractors pc2
                        WHERE pc2.politician_id = $2
                        AND pc2.contractor_name = pc1.contractor_name
                    )
                ''', pacifico_discaya['id'], pacifico_f['id'])
                
                await conn.execute('''
                    UPDATE politician_contractors
                    SET politician_id = $1
                    WHERE politician_id = $2
                ''', pacifico_discaya['id'], pacifico_f['id'])
                
                # Delete the duplicate
                await conn.execute('DELETE FROM political_dynasties WHERE id = $1', pacifico_f['id'])
                print(f'  ✅ Merged and removed duplicate')
            else:
                # Update to Pacifico Discaya (remove F.)
                await conn.execute('''
                    UPDATE political_dynasties
                    SET first_name = 'Pacifico', last_name = 'Discaya'
                    WHERE id = $1
                ''', pacifico_f['id'])
                print(f'  ✅ Updated to Pacifico Discaya')
        
        # 3. Fix "Jazzie ANN" (ID 4162529) - remove if no Jazzie Ann S* exists
        print('\n🔍 Checking Jazzie ANN entry...')
        jazzie_ann = await conn.fetchrow('''
            SELECT id, first_name, last_name, position, year
            FROM political_dynasties
            WHERE id = 4162529
        ''')
        
        if jazzie_ann:
            print(f'  Found: ID {jazzie_ann["id"]}: {jazzie_ann["first_name"]} {jazzie_ann["last_name"]}')
            
            # Check for Jazzie Ann S* (last name starting with S)
            jazzie_s = await conn.fetchrow('''
                SELECT id, first_name, last_name, position, year
                FROM political_dynasties
                WHERE UPPER(first_name) LIKE '%JAZZIE%'
                  AND UPPER(last_name) LIKE 'S%'
                  AND id != $1
                LIMIT 1
            ''', jazzie_ann['id'])
            
            if jazzie_s:
                print(f'  Found to merge with: ID {jazzie_s["id"]}: {jazzie_s["first_name"]} {jazzie_s["last_name"]}')
                # Move relationships and contractor connections
                await conn.execute('''
                    UPDATE relationships
                    SET person_id = $1
                    WHERE person_id = $2
                ''', jazzie_s['id'], jazzie_ann['id'])
                
                await conn.execute('''
                    UPDATE relationships
                    SET related_person_id = $1
                    WHERE related_person_id = $2
                ''', jazzie_s['id'], jazzie_ann['id'])
                
                await conn.execute('''
                    UPDATE politician_contractors
                    SET politician_id = $1
                    WHERE politician_id = $2
                ''', jazzie_s['id'], jazzie_ann['id'])
                
                # Delete the duplicate
                await conn.execute('DELETE FROM political_dynasties WHERE id = $1', jazzie_ann['id'])
                print(f'  ✅ Merged and removed duplicate')
            else:
                # Remove the entry
                await conn.execute('''
                    DELETE FROM relationships
                    WHERE person_id = $1 OR related_person_id = $1
                ''', jazzie_ann['id'])
                
                await conn.execute('''
                    DELETE FROM politician_contractors
                    WHERE politician_id = $1
                ''', jazzie_ann['id'])
                
                await conn.execute('DELETE FROM political_dynasties WHERE id = $1', jazzie_ann['id'])
                print(f'  ✅ Removed entry (no Jazzie Ann S* found)')
        
        print('\n✅ All entries fixed!')
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_normalized_entries())


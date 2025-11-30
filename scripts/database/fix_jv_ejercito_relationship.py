#!/usr/bin/env python3
"""Fix incorrect relationship between Mark Patron and JV Ejercito - should be JV dela Rosa"""

import asyncio
import asyncpg

async def fix_jv_relationship():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # Find the incorrect relationship
        incorrect_rel = await conn.fetchrow('''
            SELECT r.id, r.person_id, r.related_person_id, r.relationship_description,
                   p1.id as p1_id, p1.first_name as p1_first, p1.last_name as p1_last,
                   p2.id as p2_id, p2.first_name as p2_first, p2.last_name as p2_last
            FROM relationships r
            JOIN political_dynasties p1 ON r.person_id = p1.id
            JOIN political_dynasties p2 ON r.related_person_id = p2.id
            WHERE (p1.first_name LIKE '%MARK%' AND p1.last_name LIKE '%PATRON%'
                   AND p2.first_name LIKE '%JV%' AND p2.last_name = 'EJERCITO')
               OR (p1.first_name LIKE '%JV%' AND p1.last_name = 'EJERCITO'
                   AND p2.first_name LIKE '%MARK%' AND p2.last_name LIKE '%PATRON%')
        ''')
        
        if not incorrect_rel:
            print('❌ Incorrect relationship not found')
            return
        
        print(f'🔍 Found incorrect relationship (ID {incorrect_rel["id"]}):')
        print(f'  {incorrect_rel["p1_first"]} {incorrect_rel["p1_last"]} -> {incorrect_rel["p2_first"]} {incorrect_rel["p2_last"]}')
        
        # Find JV dela Rosa
        jv_dela_rosa = await conn.fetchrow('''
            SELECT id, first_name, last_name
            FROM political_dynasties
            WHERE (first_name ILIKE '%JV%' AND last_name ILIKE '%DELA ROSA%')
               OR (first_name ILIKE '%J%' AND last_name ILIKE '%DELA ROSA%')
            LIMIT 1
        ''')
        
        if not jv_dela_rosa:
            print('❌ JV dela Rosa not found')
            return
        
        print(f'\n✅ Found JV dela Rosa (ID {jv_dela_rosa["id"]})')
        
        # Determine which person is Mark Patron and which is JV Ejercito
        if incorrect_rel["p1_first"].upper().startswith("MARK") and incorrect_rel["p1_last"].upper().startswith("PATRON"):
            mark_patron_id = incorrect_rel["p1_id"]
            jv_ejercito_id = incorrect_rel["p2_id"]
        else:
            mark_patron_id = incorrect_rel["p2_id"]
            jv_ejercito_id = incorrect_rel["p1_id"]
        
        # Delete the incorrect relationship
        await conn.execute('''
            DELETE FROM relationships WHERE id = $1
        ''', incorrect_rel["id"])
        
        print(f'\n🗑️  Deleted incorrect relationship (ID {incorrect_rel["id"]})')
        
        # Check if correct relationship already exists
        existing = await conn.fetchrow('''
            SELECT id FROM relationships
            WHERE (person_id = $1 AND related_person_id = $2)
               OR (person_id = $2 AND related_person_id = $1)
        ''', mark_patron_id, jv_dela_rosa["id"])
        
        if existing:
            print(f'✅ Correct relationship already exists (ID {existing["id"]})')
        else:
            # Get business partner relationship type
            business_type = await conn.fetchrow('''
                SELECT id FROM connection_types
                WHERE description ILIKE '%business partner%'
                   OR description ILIKE '%contractor%'
                LIMIT 1
            ''')
            
            if business_type:
                # Create correct relationship
                await conn.execute('''
                    INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description, source_url)
                    VALUES ($1, $2, $3, $4, $5)
                ''', mark_patron_id, jv_dela_rosa["id"], business_type["id"],
                    'Patron relationship with contractor - V.R. PATRON BUILDERS & DEVELOPERS CORP.',
                    'https://kontradaya.org/2025-KD-report/')
                
                print(f'✅ Created correct relationship: Mark Patron -> JV dela Rosa')
        
        print('\n✅ Relationship fixed!')
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_jv_relationship())














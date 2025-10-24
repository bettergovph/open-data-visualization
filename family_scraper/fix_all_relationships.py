#!/usr/bin/env python3
"""
Fix all relationships to have exactly 6 entries for the 3 people
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def fix_all_relationships():
    """Create exactly 6 relationships for the 3 people"""
    
    # Database connection
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DYNASTY_SEC', 'dynasty')
    )
    
    try:
        print("🔧 Fixing all relationships to have exactly 6 entries...")
        
        # Get the correct relationship type IDs
        relationship_types = await conn.fetch("""
            SELECT id, code, description 
            FROM connection_types 
            ORDER BY id
        """)
        
        type_map = {ct['description']: ct['id'] for ct in relationship_types}
        
        # Find the 3 people IDs
        coefredo_uy = await conn.fetchrow("""
            SELECT id FROM political_dynasties 
            WHERE first_name = 'COEFREDO' AND last_name = 'UY'
            LIMIT 1
        """)
        
        stephany_tan = await conn.fetchrow("""
            SELECT id FROM political_dynasties 
            WHERE first_name = 'STEPHANY' AND last_name = 'TAN'
            LIMIT 1
        """)
        
        stephen_tan = await conn.fetchrow("""
            SELECT id FROM political_dynasties 
            WHERE first_name = 'STEPHEN JAMES' AND last_name = 'TAN'
            LIMIT 1
        """)
        
        if not all([coefredo_uy, stephany_tan, stephen_tan]):
            print("❌ Could not find all required people")
            return
        
        coefredo_id = coefredo_uy['id']
        stephany_id = stephany_tan['id']
        stephen_id = stephen_tan['id']
        
        print(f"Found IDs: Coefredo={coefredo_id}, Stephany={stephany_id}, Stephen={stephen_id}")
        
        # Delete ALL existing relationships for these 3 people
        await conn.execute("""
            DELETE FROM relationships 
            WHERE (person_id = ANY($1) OR related_person_id = ANY($1))
        """, [coefredo_id, stephany_id, stephen_id])
        
        print("✅ Deleted all existing relationships")
        
        # Create exactly 6 relationships
        relationships_to_add = [
            # 1. COEFREDO UY -> STEPHANY TAN (Father)
            (coefredo_id, stephany_id, type_map.get('Biological or adoptive father', 1), 'Father of Stephany Tan'),
            # 2. STEPHANY TAN -> COEFREDO UY (Daughter)
            (stephany_id, coefredo_id, type_map.get('Biological or adoptive daughter', 4), 'Daughter of Coefredo UY'),
            # 3. COEFREDO UY -> STEPHEN JAMES TAN (Father-in-law)
            (coefredo_id, stephen_id, type_map.get('Father-in-law', 17), 'Father-in-law of Stephen James Tan'),
            # 4. STEPHEN JAMES TAN -> COEFREDO UY (Son-in-law)
            (stephen_id, coefredo_id, type_map.get('Son-in-law', 18), 'Son-in-law of Coefredo UY'),
            # 5. STEPHEN JAMES TAN -> STEPHANY TAN (Husband)
            (stephen_id, stephany_id, type_map.get('Spouse (male)', 7), 'Husband of Stephany Tan'),
            # 6. STEPHANY TAN -> STEPHEN JAMES TAN (Wife)
            (stephany_id, stephen_id, type_map.get('Spouse (female)', 8), 'Wife of Stephen James Tan')
        ]
        
        for person_id, related_id, rel_type, description in relationships_to_add:
            await conn.execute("""
                INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (person_id, related_person_id, relationship_type) DO NOTHING
            """, person_id, related_id, rel_type, description)
        
        print("✅ Added exactly 6 relationships")
        
        # Verify the relationships
        print("\n📊 Final relationships:")
        final_relationships = await conn.fetch("""
            SELECT 
                p1.first_name || ' ' || p1.last_name as person,
                p2.first_name || ' ' || p2.last_name as related_person,
                ct.description as relationship,
                r.relationship_description
            FROM relationships r
            JOIN political_dynasties p1 ON r.person_id = p1.id
            JOIN political_dynasties p2 ON r.related_person_id = p2.id
            JOIN connection_types ct ON r.relationship_type = ct.id
            WHERE (p1.first_name IN ('COEFREDO', 'STEPHANY', 'STEPHEN JAMES'))
               OR (p2.first_name IN ('COEFREDO', 'STEPHANY', 'STEPHEN JAMES'))
            ORDER BY p1.first_name, p1.last_name
        """)
        
        print(f"Total relationships: {len(final_relationships)}")
        for rel in final_relationships:
            print(f"  {rel['person']} -> {rel['related_person']} ({rel['relationship']})")
        
        print(f"\n✅ Relationships fixed! Should have exactly 6 entries.")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_all_relationships())

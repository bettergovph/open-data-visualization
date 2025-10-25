#!/usr/bin/env python3
"""
Fix the relationship types and add missing relationships.
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def fix_relationship_types():
    """Fix relationship types and add missing relationships"""
    
    # Database connection
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DYNASTY_SEC', 'dynasty')
    )
    
    try:
        print("🔧 Fixing relationship types...")
        
        # Get the correct relationship type IDs
        relationship_types = await conn.fetch("""
            SELECT id, code, description 
            FROM connection_types 
            ORDER BY id
        """)
        
        type_map = {ct['description']: ct['id'] for ct in relationship_types}
        print("Available relationship types:")
        for ct in relationship_types:
            print(f"  {ct['id']}: {ct['code']} - {ct['description']}")
        
        # Find STEPHEN JAMES TAN and STEPHANY TAN IDs
        stephen_tan = await conn.fetchrow("""
            SELECT id FROM political_dynasties 
            WHERE first_name = 'STEPHEN JAMES' AND last_name = 'TAN'
            LIMIT 1
        """)
        
        stephany_tan = await conn.fetchrow("""
            SELECT id FROM political_dynasties 
            WHERE first_name = 'STEPHANY' AND last_name = 'TAN'
            LIMIT 1
        """)
        
        coefredo_uy = await conn.fetchrow("""
            SELECT id FROM political_dynasties 
            WHERE first_name = 'COEFREDO' AND last_name = 'UY'
            LIMIT 1
        """)
        
        if not all([stephen_tan, stephany_tan, coefredo_uy]):
            print("❌ Could not find all required people")
            return
        
        stephen_id = stephen_tan['id']
        stephany_id = stephany_tan['id']
        coefredo_id = coefredo_uy['id']
        
        print(f"Found IDs: Stephen={stephen_id}, Stephany={stephany_id}, Coefredo={coefredo_id}")
        
        # Delete existing incorrect relationships
        await conn.execute("""
            DELETE FROM relationships 
            WHERE (person_id = $1 AND related_person_id = $2)
               OR (person_id = $2 AND related_person_id = $1)
               OR (person_id = $1 AND related_person_id = $3)
               OR (person_id = $3 AND related_person_id = $1)
               OR (person_id = $2 AND related_person_id = $3)
               OR (person_id = $3 AND related_person_id = $2)
        """, stephen_id, stephany_id, coefredo_id)
        
        print("✅ Deleted incorrect relationships")
        
        # Add correct relationships
        relationships_to_add = [
            # Stephen James Tan -> Stephany Tan (Husband)
            (stephen_id, stephany_id, type_map.get('Spouse (male)', 5), 'Husband of Stephany Tan'),
            # Stephany Tan -> Stephen James Tan (Wife)  
            (stephany_id, stephen_id, type_map.get('Spouse (female)', 6), 'Wife of Stephen James Tan'),
            # Coefredo UY -> Stephany Tan (Father)
            (coefredo_id, stephany_id, type_map.get('Biological or adoptive father', 1), 'Father of Stephany Tan'),
            # Stephany Tan -> Coefredo UY (Daughter)
            (stephany_id, coefredo_id, type_map.get('Biological or adoptive daughter', 2), 'Daughter of Coefredo UY'),
            # Coefredo UY -> Stephen James Tan (Father-in-law)
            (coefredo_id, stephen_id, type_map.get('Father-in-law', 17), 'Father-in-law of Stephen James Tan'),
            # Stephen James Tan -> Coefredo UY (Son-in-law)
            (stephen_id, coefredo_id, type_map.get('Son-in-law', 18), 'Son-in-law of Coefredo UY')
        ]
        
        for person_id, related_id, rel_type, description in relationships_to_add:
            await conn.execute("""
                INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (person_id, related_person_id, relationship_type) DO NOTHING
            """, person_id, related_id, rel_type, description)
        
        print("✅ Added correct relationships")
        
        # Show the new relationships
        print("\n📊 New relationships:")
        new_relationships = await conn.fetch("""
            SELECT 
                p1.first_name || ' ' || p1.last_name as person,
                p2.first_name || ' ' || p2.last_name as related_person,
                ct.description as relationship,
                r.relationship_description
            FROM relationships r
            JOIN political_dynasties p1 ON r.person_id = p1.id
            JOIN political_dynasties p2 ON r.related_person_id = p2.id
            JOIN connection_types ct ON r.relationship_type = ct.id
            WHERE (p1.first_name IN ('STEPHEN JAMES', 'STEPHANY', 'COEFREDO'))
               OR (p2.first_name IN ('STEPHEN JAMES', 'STEPHANY', 'COEFREDO'))
            ORDER BY p1.first_name, p1.last_name
        """)
        
        for rel in new_relationships:
            print(f"  {rel['person']} -> {rel['related_person']} ({rel['relationship']})")
        
        print(f"\n✅ Relationship types fixed!")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_relationship_types())

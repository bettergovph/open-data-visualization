#!/usr/bin/env python3
"""
Clean up all relationships and create exactly 6 correct ones
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def fix_relationships_clean():
    """Clean up all relationships and create exactly 6 correct ones"""
    
    # Database connection
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DYNASTY_SEC', 'dynasty')
    )
    
    try:
        print("🧹 Cleaning up all relationships...")
        
        # Get the correct relationship type IDs
        relationship_types = await conn.fetch("""
            SELECT id, code, description 
            FROM connection_types 
            ORDER BY id
        """)
        
        type_map = {ct['description']: ct['id'] for ct in relationship_types}
        
        # Use the most recent COEFREDO UY record (ID 82107)
        coefredo_id = 82107
        stephany_id = 78160  # STEPHANY TAN
        stephen_id = 78075  # STEPHEN JAMES TAN
        
        print(f"Using IDs: Coefredo={coefredo_id}, Stephany={stephany_id}, Stephen={stephen_id}")
        
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
            WHERE (p1.id IN ($1, $2, $3) OR p2.id IN ($1, $2, $3))
            ORDER BY p1.first_name, p1.last_name
        """, coefredo_id, stephany_id, stephen_id)
        
        print(f"Total relationships: {len(final_relationships)}")
        for rel in final_relationships:
            print(f"  {rel['person']} -> {rel['related_person']} ({rel['relationship']})")
        
        if len(final_relationships) == 6:
            print(f"\n✅ Perfect! Exactly 6 relationships created.")
        else:
            print(f"\n❌ Expected 6 relationships, got {len(final_relationships)}")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_relationships_clean())

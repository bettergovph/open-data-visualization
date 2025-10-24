#!/usr/bin/env python3
"""
Create a proper relationships table to handle multiple relationships per politician.
This replaces the single connection_id/connection_type columns with a proper many-to-many relationship.
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def create_relationships_table():
    """Create the relationships table and migrate existing data"""
    
    # Database connection
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DYNASTY_SEC', 'dynasty')
    )
    
    try:
        print("🔧 Creating relationships table...")
        
        # Create relationships table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                id SERIAL PRIMARY KEY,
                person_id INTEGER NOT NULL REFERENCES political_dynasties(id) ON DELETE CASCADE,
                related_person_id INTEGER NOT NULL REFERENCES political_dynasties(id) ON DELETE CASCADE,
                relationship_type INTEGER NOT NULL REFERENCES connection_types(id),
                relationship_description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(person_id, related_person_id, relationship_type)
            );
        """)
        
        print("✅ Relationships table created")
        
        # Create index for better performance
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_relationships_person_id 
            ON relationships(person_id);
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_relationships_related_person_id 
            ON relationships(related_person_id);
        """)
        
        print("✅ Indexes created")
        
        # Migrate existing connection data to relationships table
        print("🔄 Migrating existing connection data...")
        
        # Get all people with existing connections
        existing_connections = await conn.fetch("""
            SELECT id, first_name, last_name, connection_id, connection_type, connection
            FROM political_dynasties 
            WHERE connection_id IS NOT NULL 
            AND connection_type IS NOT NULL
        """)
        
        migrated_count = 0
        for person in existing_connections:
            person_id = person['id']
            related_person_id = person['connection_id']
            relationship_type = person['connection_type']
            relationship_description = person['connection']
            
            # Insert into relationships table
            await conn.execute("""
                INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (person_id, related_person_id, relationship_type) DO NOTHING
            """, person_id, related_person_id, relationship_type, relationship_description)
            
            migrated_count += 1
        
        print(f"✅ Migrated {migrated_count} existing connections")
        
        # Create reverse relationships (bidirectional)
        print("🔄 Creating reverse relationships...")
        
        reverse_count = 0
        for person in existing_connections:
            person_id = person['id']
            related_person_id = person['connection_id']
            relationship_type = person['connection_type']
            relationship_description = person['connection']
            
            # Get reverse relationship type
            reverse_relationship_type = await get_reverse_relationship_type(conn, relationship_type)
            
            if reverse_relationship_type:
                # Create reverse relationship
                reverse_description = get_reverse_description(relationship_description, person['first_name'], person['last_name'])
                
                await conn.execute("""
                    INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (person_id, related_person_id, relationship_type) DO NOTHING
                """, related_person_id, person_id, reverse_relationship_type, reverse_description)
                
                reverse_count += 1
        
        print(f"✅ Created {reverse_count} reverse relationships")
        
        # Show sample data
        print("\n📊 Sample relationships:")
        sample_relationships = await conn.fetch("""
            SELECT 
                p1.first_name || ' ' || p1.last_name as person,
                p2.first_name || ' ' || p2.last_name as related_person,
                ct.description as relationship,
                r.relationship_description
            FROM relationships r
            JOIN political_dynasties p1 ON r.person_id = p1.id
            JOIN political_dynasties p2 ON r.related_person_id = p2.id
            JOIN connection_types ct ON r.relationship_type = ct.id
            LIMIT 10
        """)
        
        for rel in sample_relationships:
            print(f"  {rel['person']} -> {rel['related_person']} ({rel['relationship']})")
        
        print(f"\n✅ Relationships table setup complete!")
        print(f"📈 Total relationships: {len(await conn.fetch('SELECT COUNT(*) FROM relationships'))}")
        
    finally:
        await conn.close()

async def get_reverse_relationship_type(conn, relationship_type):
    """Get the reverse relationship type"""
    reverse_mapping = {
        1: 2,  # Father -> Son/Daughter
        2: 1,  # Son/Daughter -> Father
        3: 4,  # Mother -> Son/Daughter  
        4: 3,  # Son/Daughter -> Mother
        5: 6,  # Husband -> Wife
        6: 5,  # Wife -> Husband
        7: 8,  # Brother -> Brother/Sister
        8: 7,  # Sister -> Brother/Sister
        9: 10, # Uncle -> Nephew/Niece
        10: 9, # Nephew/Niece -> Uncle
        11: 12, # Aunt -> Nephew/Niece
        12: 11, # Nephew/Niece -> Aunt
        13: 14, # Grandfather -> Grandson/Granddaughter
        14: 13, # Grandson/Granddaughter -> Grandfather
        15: 16, # Grandmother -> Grandson/Granddaughter
        16: 15, # Grandson/Granddaughter -> Grandmother
        17: 18, # Father-in-law -> Son-in-law/Daughter-in-law
        18: 17, # Son-in-law/Daughter-in-law -> Father-in-law
        19: 20, # Mother-in-law -> Son-in-law/Daughter-in-law
        20: 19  # Son-in-law/Daughter-in-law -> Mother-in-law
    }
    
    return reverse_mapping.get(relationship_type)

def get_reverse_description(original_description, first_name, last_name):
    """Generate reverse relationship description"""
    if "Husband of" in original_description:
        return f"Wife of {first_name} {last_name}"
    elif "Wife of" in original_description:
        return f"Husband of {first_name} {last_name}"
    elif "Father of" in original_description:
        return f"Son/Daughter of {first_name} {last_name}"
    elif "Mother of" in original_description:
        return f"Son/Daughter of {first_name} {last_name}"
    else:
        return f"Related to {first_name} {last_name}"

if __name__ == "__main__":
    asyncio.run(create_relationships_table())

#!/usr/bin/env python3
"""
Fix political_dynasties table schema to support all required fields.
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def fix_table():
    """Add missing columns to political_dynasties table."""
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        print("🔧 Fixing political_dynasties table schema...")
        
        # List of columns to add if they don't exist
        columns_to_add = [
            ("aliases", "TEXT[]", "Array of alternative names"),
            ("dynasty_family_id", "VARCHAR(255)", "Dynasty family identifier"),
            ("birth_date", "DATE", "Date of birth"),
            ("maiden_name", "VARCHAR(255)", "Maiden name (for married individuals)"),
            ("last_updated", "TIMESTAMP", "Last update timestamp"),
            ("district", "VARCHAR(100)", "Congressional district"),
        ]
        
        for col_name, col_type, description in columns_to_add:
            # Check if column exists
            exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'political_dynasties' 
                    AND column_name = $1
                )
            """, col_name)
            
            if not exists:
                print(f"  ➕ Adding column: {col_name} ({col_type}) - {description}")
                await conn.execute(f"""
                    ALTER TABLE political_dynasties 
                    ADD COLUMN {col_name} {col_type}
                """)
            else:
                print(f"  ✓ Column exists: {col_name}")
        
        # Create family_relationships table if it doesn't exist
        print("\n🔧 Checking family_relationships table...")
        
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'family_relationships'
            )
        """)
        
        if not table_exists:
            print("  ➕ Creating family_relationships table...")
            await conn.execute("""
                CREATE TABLE family_relationships (
                    id SERIAL PRIMARY KEY,
                    person_id INTEGER NOT NULL,
                    related_person_id INTEGER NOT NULL,
                    relationship_type VARCHAR(100) NOT NULL,
                    notes TEXT,
                    source VARCHAR(255),
                    confidence_level VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (person_id) REFERENCES political_dynasties(id) ON DELETE CASCADE,
                    FOREIGN KEY (related_person_id) REFERENCES political_dynasties(id) ON DELETE CASCADE,
                    UNIQUE(person_id, related_person_id, relationship_type)
                )
            """)
            
            # Create indexes
            await conn.execute("""
                CREATE INDEX idx_family_relationships_person 
                ON family_relationships(person_id)
            """)
            await conn.execute("""
                CREATE INDEX idx_family_relationships_related 
                ON family_relationships(related_person_id)
            """)
            await conn.execute("""
                CREATE INDEX idx_family_relationships_type 
                ON family_relationships(relationship_type)
            """)
            
            print("  ✅ family_relationships table created with indexes")
        else:
            print("  ✓ family_relationships table exists")
        
        # Create politician_contractors table if it doesn't exist
        print("\n🔧 Checking politician_contractors table...")
        
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'politician_contractors'
            )
        """)
        
        if not table_exists:
            print("  ➕ Creating politician_contractors table...")
            await conn.execute("""
                CREATE TABLE politician_contractors (
                    id SERIAL PRIMARY KEY,
                    politician_id INTEGER NOT NULL,
                    contractor_name VARCHAR(500) NOT NULL,
                    match_confidence DECIMAL(5,2),
                    notes TEXT,
                    source VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (politician_id) REFERENCES political_dynasties(id) ON DELETE CASCADE,
                    UNIQUE(politician_id, contractor_name)
                )
            """)
            
            await conn.execute("""
                CREATE INDEX idx_politician_contractors_politician 
                ON politician_contractors(politician_id)
            """)
            await conn.execute("""
                CREATE INDEX idx_politician_contractors_name 
                ON politician_contractors(contractor_name)
            """)
            
            print("  ✅ politician_contractors table created with indexes")
        else:
            print("  ✓ politician_contractors table exists")
        
        # Create politician_party_list table if it doesn't exist
        print("\n🔧 Checking politician_party_list table...")
        
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'politician_party_list'
            )
        """)
        
        if not table_exists:
            print("  ➕ Creating politician_party_list table...")
            await conn.execute("""
                CREATE TABLE politician_party_list (
                    id SERIAL PRIMARY KEY,
                    politician_id INTEGER NOT NULL,
                    party_list_number INTEGER,
                    party_name VARCHAR(255) NOT NULL,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (politician_id) REFERENCES political_dynasties(id) ON DELETE CASCADE,
                    UNIQUE(politician_id, party_name)
                )
            """)
            
            await conn.execute("""
                CREATE INDEX idx_politician_party_list_politician 
                ON politician_party_list(politician_id)
            """)
            
            print("  ✅ politician_party_list table created with indexes")
        else:
            print("  ✓ politician_party_list table exists")
        
        print("\n✅ All tables and columns fixed successfully!")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(fix_table())


#!/usr/bin/env python3
"""
Update Dynasty Database with Relationship Data from CSV
"""

import asyncio
import asyncpg
import csv
import os
from typing import Dict, List, Optional

class DynastyRelationshipUpdater:
    def __init__(self):
        self.db_conn = None
        self.connection_type_map = {}
        
    async def connect(self):
        """Connect to the dynasty database"""
        self.db_conn = await asyncpg.connect(
            host='localhost',
            port='5432',
            user='budget_admin',
            password='wuQ5gBYCKkZiOGb61chLcByMu',
            database='dynasty'
        )
        print("✅ Connected to dynasty database")
        
    async def close(self):
        """Close database connection"""
        if self.db_conn:
            await self.db_conn.close()
            print("✅ Database connection closed")
    
    async def setup_connection_types(self):
        """Setup connection types mapping"""
        print("🔗 Setting up connection types...")
        
        # Get existing connection types
        types = await self.db_conn.fetch("SELECT code, name FROM connection_types ORDER BY code")
        self.connection_type_map = {ct['name'].upper(): ct['code'] for ct in types}
        
        print(f"📋 Found {len(self.connection_type_map)} connection types")
        for name, code in self.connection_type_map.items():
            print(f"   {code}: {name}")
    
    async def find_person_by_name(self, full_name: str) -> Optional[Dict]:
        """Find a person in the database by full name with proper hyphenated name handling"""
        try:
            # Try exact match first
            person = await self.db_conn.fetchrow("""
                SELECT id, first_name, last_name, province, position, year
                FROM political_dynasties 
                WHERE CONCAT(first_name, ' ', last_name) = $1
                ORDER BY year DESC
                LIMIT 1
            """, full_name)
            
            if person:
                return dict(person)
            
            # Handle hyphenated names (maiden name - married name)
            name_parts = full_name.strip().split()
            if len(name_parts) >= 2:
                first_name = name_parts[0]
                last_name = ' '.join(name_parts[1:])
                
                # Check if the last name contains a hyphen (maiden-married format)
                if '-' in last_name:
                    # For hyphenated names, try both parts
                    maiden_name, married_name = last_name.split('-', 1)
                    maiden_name = maiden_name.strip()
                    married_name = married_name.strip()
                    
                    # Try matching with maiden name
                    person = await self.db_conn.fetchrow("""
                        SELECT id, first_name, last_name, province, position, year
                        FROM political_dynasties 
                        WHERE first_name = $1 AND last_name = $2
                        ORDER BY year DESC
                        LIMIT 1
                    """, first_name, maiden_name)
                    
                    if person:
                        return dict(person)
                    
                    # Try matching with married name
                    person = await self.db_conn.fetchrow("""
                        SELECT id, first_name, last_name, province, position, year
                        FROM political_dynasties 
                        WHERE first_name = $1 AND last_name = $2
                        ORDER BY year DESC
                        LIMIT 1
                    """, first_name, married_name)
                    
                    if person:
                        return dict(person)
                    
                    # Try matching with full hyphenated name
                    person = await self.db_conn.fetchrow("""
                        SELECT id, first_name, last_name, province, position, year
                        FROM political_dynasties 
                        WHERE first_name = $1 AND last_name = $2
                        ORDER BY year DESC
                        LIMIT 1
                    """, first_name, last_name)
                    
                    if person:
                        return dict(person)
                else:
                    # Regular name without hyphen
                    person = await self.db_conn.fetchrow("""
                        SELECT id, first_name, last_name, province, position, year
                        FROM political_dynasties 
                        WHERE first_name = $1 AND last_name = $2
                        ORDER BY year DESC
                        LIMIT 1
                    """, first_name, last_name)
                    
                    if person:
                        return dict(person)
            
            # Only as last resort, try fuzzy match but with word boundaries
            # This prevents "TAN" from matching "CATACUTAN" but allows legitimate matches
            person = await self.db_conn.fetchrow("""
                SELECT id, first_name, last_name, province, position, year
                FROM political_dynasties 
                WHERE CONCAT(first_name, ' ', last_name) ~* $1
                ORDER BY year DESC
                LIMIT 1
            """, f"\\y{full_name}\\y")  # Word boundary regex
            
            return dict(person) if person else None
            
        except Exception as e:
            print(f"❌ Error finding person '{full_name}': {e}")
            return None
    
    async def create_relationships_table(self):
        """Check and update relationships table structure"""
        print("🔨 Checking relationships table...")
        
        # Check if we need to add new columns
        columns = await self.db_conn.fetch("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'relationships'
        """)
        
        existing_columns = [col['column_name'] for col in columns]
        print(f"📋 Existing columns: {existing_columns}")
        
        # Add missing columns if needed
        if 'source_url' not in existing_columns:
            await self.db_conn.execute("ALTER TABLE relationships ADD COLUMN source_url VARCHAR(500)")
            print("✅ Added source_url column")
        
        if 'confidence_level' not in existing_columns:
            await self.db_conn.execute("ALTER TABLE relationships ADD COLUMN confidence_level INTEGER")
            print("✅ Added confidence_level column")
        
        if 'verified' not in existing_columns:
            await self.db_conn.execute("ALTER TABLE relationships ADD COLUMN verified BOOLEAN DEFAULT FALSE")
            print("✅ Added verified column")
        
        if 'created_by' not in existing_columns:
            await self.db_conn.execute("ALTER TABLE relationships ADD COLUMN created_by VARCHAR(100) DEFAULT 'CSV_Import'")
            print("✅ Added created_by column")
        
        print("✅ Relationships table structure verified")
    
    async def get_reverse_relationship_type(self, relationship_type_id: int) -> int:
        """Get the reverse relationship type ID"""
        # Get the current relationship type name
        current_type = await self.db_conn.fetchrow("""
            SELECT name FROM connection_types WHERE code = $1
        """, relationship_type_id)
        
        if not current_type:
            return relationship_type_id  # Return same if not found
        
        current_name = current_type['name'].upper()
        
        # Define reverse relationship mappings
        reverse_mappings = {
            'HUSBAND': 'WIFE',
            'WIFE': 'HUSBAND',
            'FATHER': 'SON',  # or DAUGHTER, but we'll use SON as default
            'MOTHER': 'SON',  # or DAUGHTER, but we'll use SON as default
            'SON': 'FATHER',  # or MOTHER, but we'll use FATHER as default
            'DAUGHTER': 'FATHER',  # or MOTHER, but we'll use FATHER as default
            'BROTHER': 'BROTHER',
            'SISTER': 'SISTER',
            'FATHER-IN-LAW': 'SON-IN-LAW',
            'MOTHER-IN-LAW': 'DAUGHTER-IN-LAW',
            'SON-IN-LAW': 'FATHER-IN-LAW',
            'DAUGHTER-IN-LAW': 'MOTHER-IN-LAW',
            'UNCLE': 'NEPHEW',  # or NIECE, but we'll use NEPHEW as default
            'AUNT': 'NIECE',   # or NEPHEW, but we'll use NIECE as default
            'NEPHEW': 'UNCLE',  # or AUNT, but we'll use UNCLE as default
            'NIECE': 'AUNT'     # or UNCLE, but we'll use AUNT as default
        }
        
        reverse_name = reverse_mappings.get(current_name, current_name)
        
        # Get the reverse relationship type ID
        reverse_type = await self.db_conn.fetchrow("""
            SELECT code FROM connection_types WHERE name = $1
        """, reverse_name)
        
        if reverse_type:
            return reverse_type['code']
        else:
            # If reverse type not found, return the original type
            return relationship_type_id
    
    def create_reverse_description(self, relationship_type: str, original_description: str, person1_name: str, person2_name: str) -> str:
        """Create a reverse description for the relationship"""
        # Simple reverse description
        return f"{person2_name} is {relationship_type.lower()} of {person1_name}"
    
    async def process_csv_file(self, csv_file: str):
        """Process the CSV file and update the database"""
        print(f"📊 Processing CSV file: {csv_file}")
        
        relationships_processed = 0
        relationships_created = 0
        relationships_skipped = 0
        
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                relationships_processed += 1
                
                # Extract data from CSV
                person1_name = row['person1_name'].strip()
                person2_name = row['person2_name'].strip()
                relationship_type = row['relationship_type'].strip()
                description = row['relationship_description'].strip()
                source_url = row['source_url'].strip()
                confidence_level = int(row['confidence_level'])
                
                print(f"\n🔍 Processing: {person1_name} → {relationship_type} → {person2_name}")
                
                # Find both persons in database
                person1 = await self.find_person_by_name(person1_name)
                person2 = await self.find_person_by_name(person2_name)
                
                if not person1:
                    print(f"   ❌ Person1 not found: {person1_name}")
                    relationships_skipped += 1
                    continue
                    
                if not person2:
                    print(f"   ❌ Person2 not found: {person2_name}")
                    relationships_skipped += 1
                    continue
                
                # Get relationship type ID
                relationship_type_upper = relationship_type.upper()
                if relationship_type_upper not in self.connection_type_map:
                    print(f"   ❌ Unknown relationship type: {relationship_type}")
                    relationships_skipped += 1
                    continue
                
                relationship_type_id = self.connection_type_map[relationship_type_upper]
                
                # Check if relationship already exists
                existing = await self.db_conn.fetchrow("""
                    SELECT id FROM relationships 
                    WHERE person_id = $1 AND related_person_id = $2 AND relationship_type = $3
                """, person1['id'], person2['id'], relationship_type_id)
                
                if existing:
                    print(f"   ⚠️  Relationship already exists (ID: {existing['id']})")
                    relationships_skipped += 1
                    continue
                
                # Insert new relationship (forward direction)
                try:
                    await self.db_conn.execute("""
                        INSERT INTO relationships (
                            person_id, related_person_id, relationship_type,
                            relationship_description, source_url, confidence_level,
                            verified, created_by
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """, 
                    person1['id'], person2['id'], relationship_type_id,
                    description, source_url, confidence_level,
                    confidence_level >= 9, 'CSV_Import'
                    )
                    
                    print(f"   ✅ Created relationship (ID: {person1['id']} → {person2['id']})")
                    relationships_created += 1
                    
                except Exception as e:
                    print(f"   ❌ Error creating forward relationship: {e}")
                    relationships_skipped += 1
                    continue
                
                # Create reverse relationship
                try:
                    # Get reverse relationship type
                    reverse_relationship_type_id = await self.get_reverse_relationship_type(relationship_type_id)
                    
                    # Create reverse description
                    reverse_description = self.create_reverse_description(relationship_type, description, person1_name, person2_name)
                    
                    # Check if reverse relationship already exists
                    existing_reverse = await self.db_conn.fetchrow("""
                        SELECT id FROM relationships 
                        WHERE person_id = $1 AND related_person_id = $2 AND relationship_type = $3
                    """, person2['id'], person1['id'], reverse_relationship_type_id)
                    
                    if not existing_reverse:
                        await self.db_conn.execute("""
                            INSERT INTO relationships (
                                person_id, related_person_id, relationship_type,
                                relationship_description, source_url, confidence_level,
                                verified, created_by
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        """, 
                        person2['id'], person1['id'], reverse_relationship_type_id,
                        reverse_description, source_url, confidence_level,
                        confidence_level >= 9, 'CSV_Import'
                        )
                        
                        print(f"   ✅ Created reverse relationship (ID: {person2['id']} → {person1['id']})")
                        relationships_created += 1
                    else:
                        print(f"   ⚠️  Reverse relationship already exists")
                        
                except Exception as e:
                    print(f"   ❌ Error creating reverse relationship: {e}")
                    relationships_skipped += 1
        
        print(f"\n📊 Processing Summary:")
        print(f"   Total processed: {relationships_processed}")
        print(f"   Created: {relationships_created}")
        print(f"   Skipped: {relationships_skipped}")
    
    async def show_relationship_summary(self):
        """Show summary of relationships in database"""
        print("\n📋 Relationship Summary:")
        
        # Total relationships
        total = await self.db_conn.fetchval("SELECT COUNT(*) FROM relationships")
        print(f"   Total relationships: {total}")
        
        # By type
        by_type = await self.db_conn.fetch("""
            SELECT ct.name, COUNT(*) as count
            FROM relationships r
            JOIN connection_types ct ON r.relationship_type = ct.code
            GROUP BY ct.name
            ORDER BY count DESC
        """)
        
        print("   By relationship type:")
        for rt in by_type:
            print(f"     {rt['name']}: {rt['count']}")
        
        # By dynasty
        by_dynasty = await self.db_conn.fetch("""
            SELECT 
                p1.last_name as dynasty1,
                p2.last_name as dynasty2,
                COUNT(*) as count
            FROM relationships r
            JOIN political_dynasties p1 ON r.person_id = p1.id
            JOIN political_dynasties p2 ON r.related_person_id = p2.id
            GROUP BY p1.last_name, p2.last_name
            ORDER BY count DESC
            LIMIT 10
        """)
        
        print("   By dynasty combinations:")
        for bd in by_dynasty:
            print(f"     {bd['dynasty1']} ↔ {bd['dynasty2']}: {bd['count']}")

async def main():
    """Main function"""
    updater = DynastyRelationshipUpdater()
    
    try:
        await updater.connect()
        await updater.setup_connection_types()
        await updater.create_relationships_table()
        
        # Process the CSV file
        csv_file = "database/philippine_political_dynasty_relationships.csv"
        if os.path.exists(csv_file):
            await updater.process_csv_file(csv_file)
            await updater.show_relationship_summary()
        else:
            print(f"❌ CSV file not found: {csv_file}")
        
    finally:
        await updater.close()

if __name__ == "__main__":
    asyncio.run(main())

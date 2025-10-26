#!/usr/bin/env python3
"""
Parse Multiple Relationship CSV Files
Processes 10 new relationship CSV files and imports them into the dynasty database
"""

import asyncio
import asyncpg
import csv
import os
from typing import List, Dict, Any
from datetime import datetime

class MultipleRelationshipCSVParser:
    def __init__(self):
        self.db_conn = None
        self.csv_files = [
            'database/philippine_politicians_relationships_batch2.csv',
            'database/philippine_politicians_relationships_batch3.csv',
            'database/philippine_politicians_relationships_batch4.csv',
            'database/philippine_politicians_relationships_batch5.csv',
            'database/philippine_politicians_relationships_batch6.csv',
            'database/philippine_politicians_relationships_batch7.csv',
            'database/philippine_politicians_relationships_batch8.csv',
            'database/philippine_politicians_relationships_batch9.csv',
            'database/philippine_politicians_relationships_batch10.csv',
            'database/philippine_politicians_relationships_batch11.csv',
            'database/philippine_political_dynasty_relationships.csv'
        ]
        
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
        """Set up connection types in the database"""
        print("\n🔧 SETTING UP CONNECTION TYPES")
        print("=" * 60)
        
        connection_types = [
            (1, 'Father', 'Parent-child relationship'),
            (2, 'Mother', 'Parent-child relationship'),
            (3, 'Son', 'Parent-child relationship'),
            (4, 'Daughter', 'Parent-child relationship'),
            (5, 'Husband', 'Marriage relationship'),
            (6, 'Wife', 'Marriage relationship'),
            (7, 'Brother', 'Sibling relationship'),
            (8, 'Sister', 'Sibling relationship'),
            (9, 'Uncle', 'Extended family relationship'),
            (10, 'Aunt', 'Extended family relationship'),
            (11, 'Nephew', 'Extended family relationship'),
            (12, 'Niece', 'Extended family relationship'),
            (13, 'Cousin', 'Extended family relationship'),
            (14, 'Grandfather', 'Extended family relationship'),
            (15, 'Grandmother', 'Extended family relationship'),
            (16, 'Grandson', 'Extended family relationship'),
            (17, 'Granddaughter', 'Extended family relationship'),
            (18, 'Father-in-law', 'In-law relationship'),
            (19, 'Mother-in-law', 'In-law relationship'),
            (20, 'Son-in-law', 'In-law relationship'),
            (21, 'Daughter-in-law', 'In-law relationship'),
            (22, 'Political Ally', 'Political relationship'),
            (23, 'Business Partner', 'Business relationship'),
            (24, 'Successor', 'Political succession relationship'),
            (25, 'Predecessor', 'Political succession relationship')
        ]
        
        for code, name, description in connection_types:
            await self.db_conn.execute("""
                INSERT INTO connection_types (code, name, description)
                VALUES ($1, $2, $3)
                ON CONFLICT (code) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description
            """, code, name, description)
        
        print(f"✅ Set up {len(connection_types)} connection types")
    
    async def create_relationships_table(self):
        """Check and update relationships table structure"""
        print("\n🔨 CHECKING RELATIONSHIPS TABLE")
        print("=" * 60)
        
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
    
    def parse_csv_file(self, file_path: str) -> List[Dict[str, Any]]:
        """Parse a single CSV file and return relationships"""
        print(f"\n📄 PARSING {file_path}")
        print("=" * 60)
        
        relationships = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as csvfile:
                # Try to detect delimiter
                sample = csvfile.read(1024)
                csvfile.seek(0)
                sniffer = csv.Sniffer()
                delimiter = sniffer.sniff(sample).delimiter
                
                reader = csv.DictReader(csvfile, delimiter=delimiter)
                
                for row_num, row in enumerate(reader, 1):
                    try:
                        # Clean and validate data
                        person1_name = row.get('person1_name', '').strip()
                        person2_name = row.get('person2_name', '').strip()
                        relationship_type = row.get('relationship_type', '').strip()
                        relationship_description = row.get('relationship_description', '').strip()
                        dynasty1 = row.get('dynasty1', '').strip()
                        dynasty2 = row.get('dynasty2', '').strip()
                        source_url = row.get('source_url', '').strip()
                        confidence_level = row.get('confidence_level', '').strip()
                        
                        # Skip empty rows
                        if not person1_name or not person2_name or not relationship_type:
                            continue
                        
                        # Convert confidence level to integer
                        try:
                            confidence_level = int(confidence_level) if confidence_level else 5
                        except ValueError:
                            confidence_level = 5
                        
                        # Ensure confidence level is between 1-10
                        confidence_level = max(1, min(10, confidence_level))
                        
                        relationships.append({
                            'person1_name': person1_name,
                            'person2_name': person2_name,
                            'relationship_type': relationship_type,
                            'relationship_description': relationship_description,
                            'dynasty1': dynasty1,
                            'dynasty2': dynasty2,
                            'source_url': source_url,
                            'confidence_level': confidence_level
                        })
                        
                    except Exception as e:
                        print(f"⚠️  Error parsing row {row_num} in {file_path}: {e}")
                        continue
                
                print(f"✅ Parsed {len(relationships)} relationships from {file_path}")
                
        except Exception as e:
            print(f"❌ Error reading {file_path}: {e}")
            return []
        
        return relationships
    
    async def find_person_id(self, full_name: str) -> int:
        """Find person ID by full name"""
        try:
            # Try exact match first
            person_id = await self.db_conn.fetchval("""
                SELECT id FROM political_dynasties 
                WHERE CONCAT(first_name, ' ', last_name) = $1
                LIMIT 1
            """, full_name)
            
            if person_id:
                return person_id
            
            # Try word-boundary match to prevent substring issues
            # Split the name into parts and match each part exactly
            name_parts = full_name.split()
            if len(name_parts) >= 2:
                first_name = name_parts[0]
                last_name = ' '.join(name_parts[1:])
                
                person_id = await self.db_conn.fetchval("""
                    SELECT id FROM political_dynasties 
                    WHERE first_name = $1 AND last_name = $2
                    LIMIT 1
                """, first_name, last_name)
                
                if person_id:
                    return person_id
            
            # Only as last resort, try fuzzy matching with word boundaries
            # This prevents "TAN" from matching "CATACUTAN"
            person_id = await self.db_conn.fetchval("""
                SELECT id FROM political_dynasties 
                WHERE CONCAT(first_name, ' ', last_name) ~* $1
                LIMIT 1
            """, f"\\y{full_name}\\y")  # Word boundary regex
            
            return person_id
            
        except Exception as e:
            print(f"⚠️  Error finding person ID for {full_name}: {e}")
            return None
    
    async def get_connection_type_id(self, relationship_type: str) -> int:
        """Get connection type ID by relationship type"""
        try:
            # Try exact match first
            type_id = await self.db_conn.fetchval("""
                SELECT code FROM connection_types 
                WHERE name ILIKE $1
            """, relationship_type)
            
            if type_id:
                return type_id
            
            # Try fuzzy matching
            type_id = await self.db_conn.fetchval("""
                SELECT code FROM connection_types 
                WHERE name ILIKE $1
            """, f"%{relationship_type}%")
            
            if type_id:
                return type_id
            
            # Default to "Political Ally" if no match
            return 22
            
        except Exception as e:
            print(f"⚠️  Error finding connection type for {relationship_type}: {e}")
            return 22
    
    async def import_relationships(self, relationships: List[Dict[str, Any]], file_name: str):
        """Import relationships into the database"""
        print(f"\n💾 IMPORTING RELATIONSHIPS FROM {file_name}")
        print("=" * 60)
        
        imported_count = 0
        skipped_count = 0
        error_count = 0
        
        for relationship in relationships:
            try:
                # Find person IDs
                person1_id = await self.find_person_id(relationship['person1_name'])
                person2_id = await self.find_person_id(relationship['person2_name'])
                
                if not person1_id or not person2_id:
                    skipped_count += 1
                    continue
                
                # Get connection type ID
                connection_type_id = await self.get_connection_type_id(relationship['relationship_type'])
                
                # Check if relationship already exists
                existing = await self.db_conn.fetchval("""
                    SELECT id FROM relationships 
                    WHERE person_id = $1 AND related_person_id = $2 AND relationship_type = $3
                """, person1_id, person2_id, connection_type_id)
                
                if existing:
                    skipped_count += 1
                    continue
                
                # Insert new relationship
                await self.db_conn.execute("""
                    INSERT INTO relationships (
                        person_id, related_person_id, relationship_type, 
                        relationship_description, dynasty1, dynasty2,
                        source_url, confidence_level, verified, created_by
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """, 
                person1_id, person2_id, connection_type_id,
                relationship['relationship_description'], relationship['dynasty1'], relationship['dynasty2'],
                relationship['source_url'], relationship['confidence_level'], False, 'CSV_Import')
                
                imported_count += 1
                
            except Exception as e:
                print(f"⚠️  Error importing relationship {relationship['person1_name']} -> {relationship['person2_name']}: {e}")
                error_count += 1
                continue
        
        print(f"✅ Imported {imported_count} relationships")
        print(f"⚠️  Skipped {skipped_count} existing relationships")
        print(f"❌ Errors: {error_count} relationships")
        
        return imported_count, skipped_count, error_count
    
    async def get_relationship_summary(self):
        """Get summary of relationships in the database"""
        print("\n📊 RELATIONSHIP SUMMARY")
        print("=" * 60)
        
        # Total relationships
        total_relationships = await self.db_conn.fetchval("SELECT COUNT(*) FROM relationships")
        print(f"📈 Total relationships: {total_relationships:,}")
        
        # By relationship type
        relationship_types = await self.db_conn.fetch("""
            SELECT ct.name, COUNT(*) as count
            FROM relationships r
            JOIN connection_types ct ON r.relationship_type = ct.code
            GROUP BY ct.name
            ORDER BY count DESC
            LIMIT 10
        """)
        
        print("\n🔗 Top Relationship Types:")
        for rt in relationship_types:
            print(f"   {rt['count']:>4} - {rt['name']}")
        
        # By confidence level
        confidence_levels = await self.db_conn.fetch("""
            SELECT confidence_level, COUNT(*) as count
            FROM relationships 
            WHERE confidence_level IS NOT NULL
            GROUP BY confidence_level
            ORDER BY confidence_level DESC
        """)
        
        print("\n🎯 By Confidence Level:")
        for cl in confidence_levels:
            print(f"   {cl['count']:>4} - Level {cl['confidence_level']}")
        
        # Average confidence
        avg_confidence = await self.db_conn.fetchval("""
            SELECT AVG(confidence_level) FROM relationships 
            WHERE confidence_level IS NOT NULL
        """)
        
        if avg_confidence:
            print(f"\n📊 Average confidence level: {avg_confidence:.2f}")
        
        # Recent imports
        recent_imports = await self.db_conn.fetchval("""
            SELECT COUNT(*) FROM relationships 
            WHERE created_by = 'CSV_Import'
        """)
        
        print(f"📥 Recent CSV imports: {recent_imports:,}")
    
    async def process_all_csv_files(self):
        """Process all CSV files"""
        print("🚀 PROCESSING MULTIPLE RELATIONSHIP CSV FILES")
        print("=" * 70)
        
        total_imported = 0
        total_skipped = 0
        total_errors = 0
        
        for csv_file in self.csv_files:
            if not os.path.exists(csv_file):
                print(f"⚠️  File not found: {csv_file}")
                continue
            
            # Parse CSV file
            relationships = self.parse_csv_file(csv_file)
            
            if not relationships:
                print(f"⚠️  No relationships found in {csv_file}")
                continue
            
            # Import relationships
            imported, skipped, errors = await self.import_relationships(relationships, csv_file)
            
            total_imported += imported
            total_skipped += skipped
            total_errors += errors
        
        print(f"\n✅ PROCESSING COMPLETE!")
        print("=" * 70)
        print(f"📥 Total imported: {total_imported:,}")
        print(f"⚠️  Total skipped: {total_skipped:,}")
        print(f"❌ Total errors: {total_errors:,}")
        
        # Get final summary
        await self.get_relationship_summary()
    
    async def run_processing(self):
        """Run the complete processing"""
        try:
            await self.connect()
            await self.setup_connection_types()
            await self.create_relationships_table()
            await self.process_all_csv_files()
            
        finally:
            await self.close()

async def main():
    """Main function"""
    parser = MultipleRelationshipCSVParser()
    await parser.run_processing()

if __name__ == "__main__":
    asyncio.run(main())

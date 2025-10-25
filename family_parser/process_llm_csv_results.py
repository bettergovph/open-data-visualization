#!/usr/bin/env python3
"""
Process CSV Results from LLM Analysis
"""

import asyncio
import asyncpg
import csv
import os
from typing import Dict, List, Optional

class LLMCSVProcessor:
    def __init__(self):
        self.db_conn = None
        self.connection_type_map = {}
        self.processed_count = 0
        self.created_count = 0
        self.skipped_count = 0
        
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
        types = await self.db_conn.fetch("SELECT code, name FROM connection_types ORDER BY code")
        self.connection_type_map = {ct['name'].upper(): ct['code'] for ct in types}
        print(f"📋 Loaded {len(self.connection_type_map)} connection types")
    
    async def find_person_by_name(self, full_name: str) -> Optional[Dict]:
        """Find a person in the database by full name"""
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
            
            # Try fuzzy match
            person = await self.db_conn.fetchrow("""
                SELECT id, first_name, last_name, province, position, year
                FROM political_dynasties 
                WHERE CONCAT(first_name, ' ', last_name) ILIKE $1
                ORDER BY year DESC
                LIMIT 1
            """, f"%{full_name}%")
            
            return dict(person) if person else None
            
        except Exception as e:
            print(f"❌ Error finding person '{full_name}': {e}")
            return None
    
    async def process_csv_file(self, csv_file: str):
        """Process a CSV file from LLM analysis"""
        print(f"📊 Processing CSV file: {csv_file}")
        
        if not os.path.exists(csv_file):
            print(f"❌ File not found: {csv_file}")
            return
        
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                self.processed_count += 1
                
                # Extract data from CSV
                person1_name = row.get('person1_name', '').strip()
                person2_name = row.get('person2_name', '').strip()
                relationship_type = row.get('relationship_type', '').strip()
                description = row.get('relationship_description', '').strip()
                source_url = row.get('source_url', '').strip()
                confidence_level = int(row.get('confidence_level', 0)) if row.get('confidence_level') else 0
                
                if not person1_name or not person2_name or not relationship_type:
                    print(f"   ⚠️  Skipping incomplete row: {person1_name} → {person2_name}")
                    self.skipped_count += 1
                    continue
                
                print(f"🔍 Processing: {person1_name} → {relationship_type} → {person2_name}")
                
                # Find both persons in database
                person1 = await self.find_person_by_name(person1_name)
                person2 = await self.find_person_by_name(person2_name)
                
                if not person1:
                    print(f"   ❌ Person1 not found: {person1_name}")
                    self.skipped_count += 1
                    continue
                    
                if not person2:
                    print(f"   ❌ Person2 not found: {person2_name}")
                    self.skipped_count += 1
                    continue
                
                # Get relationship type ID
                relationship_type_upper = relationship_type.upper()
                if relationship_type_upper not in self.connection_type_map:
                    print(f"   ❌ Unknown relationship type: {relationship_type}")
                    self.skipped_count += 1
                    continue
                
                relationship_type_id = self.connection_type_map[relationship_type_upper]
                
                # Check if relationship already exists
                existing = await self.db_conn.fetchrow("""
                    SELECT id FROM relationships 
                    WHERE person_id = $1 AND related_person_id = $2 AND relationship_type = $3
                """, person1['id'], person2['id'], relationship_type_id)
                
                if existing:
                    print(f"   ⚠️  Relationship already exists (ID: {existing['id']})")
                    self.skipped_count += 1
                    continue
                
                # Insert new relationship
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
                    confidence_level >= 8, 'LLM_Analysis'
                    )
                    
                    print(f"   ✅ Created relationship (ID: {person1['id']} → {person2['id']})")
                    self.created_count += 1
                    
                except Exception as e:
                    print(f"   ❌ Error creating relationship: {e}")
                    self.skipped_count += 1
        
        print(f"\n📊 Processing Summary for {csv_file}:")
        print(f"   Total processed: {self.processed_count}")
        print(f"   Created: {self.created_count}")
        print(f"   Skipped: {self.skipped_count}")
    
    async def show_relationship_summary(self):
        """Show summary of relationships in database"""
        print("\n📋 Database Relationship Summary:")
        
        # Total relationships
        total = await self.db_conn.fetchval("SELECT COUNT(*) FROM relationships")
        print(f"   Total relationships: {total}")
        
        # By source
        by_source = await self.db_conn.fetch("""
            SELECT created_by, COUNT(*) as count
            FROM relationships 
            GROUP BY created_by
            ORDER BY count DESC
        """)
        
        print("   By source:")
        for bs in by_source:
            print(f"     {bs['created_by']}: {bs['count']}")
        
        # High confidence relationships
        high_conf = await self.db_conn.fetchval("""
            SELECT COUNT(*) FROM relationships 
            WHERE confidence_level >= 8
        """)
        print(f"   High confidence (≥8): {high_conf}")

async def main():
    """Main function to process CSV files"""
    processor = LLMCSVProcessor()
    
    try:
        await processor.connect()
        await processor.setup_connection_types()
        
        # Look for CSV files to process
        csv_files = [f for f in os.listdir('.') if f.endswith('.csv') and 'llm' in f.lower()]
        
        if not csv_files:
            print("📁 No LLM CSV files found in current directory")
            print("   Place CSV files from LLM analysis in this directory")
            print("   Expected format: person1_name,person2_name,relationship_type,relationship_description,dynasty1,dynasty2,source_url,confidence_level")
            return
        
        print(f"📊 Found {len(csv_files)} CSV files to process:")
        for csv_file in csv_files:
            print(f"   - {csv_file}")
        
        # Process each CSV file
        for csv_file in csv_files:
            await processor.process_csv_file(csv_file)
            print()  # Add spacing between files
        
        # Show final summary
        await processor.show_relationship_summary()
        
    finally:
        await processor.close()

if __name__ == "__main__":
    asyncio.run(main())

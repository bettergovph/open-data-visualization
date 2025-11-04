#!/usr/bin/env python3
"""
Parse senators-relationships.json and import relationships into dynasty database
"""

import asyncio
import asyncpg
import json
import re
import os
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

class SenatorRelationshipsImporter:
    def __init__(self):
        self.db_conn = None
        self.connection_type_map = {}
        
        # Relationship type mappings (including special cases)
        self.relationship_mappings = {
            'BROTHER': 'Brother',
            'SISTER': 'Sister',
            'SON': 'Son',
            'DAUGHTER': 'Daughter',
            'FATHER': 'Father',
            'MOTHER': 'Mother',
            'HUSBAND': 'Husband',
            'WIFE': 'Wife',
            'UNCLE': 'Uncle',
            'AUNT': 'Aunt',
            'NEPHEW': 'Nephew',
            'NIECE': 'Niece',
            'COUSIN': 'Cousin',
            'BROTHER-IN-LAW': 'Brother',  # Map to Brother for now
            'SISTER-IN-LAW': 'Sister',    # Map to Sister for now
            'COUSIN-IN-LAW': 'Cousin',    # Map to Cousin for now
            'SON-IN-LAW': 'Son-in-law',
            'DAUGHTER-IN-LAW': 'Daughter-in-law',
            'FATHER-IN-LAW': 'Father-in-law',
            'MOTHER-IN-LAW': 'Mother-in-law',
            'GRANDFATHER': 'Grandfather',
            'GRANDMOTHER': 'Grandmother',
            'GRANDSON': 'Grandson',
            'GRANDDAUGHTER': 'Granddaughter',
        }
        
    async def connect(self):
        """Connect to the dynasty database"""
        self.db_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD'),
            database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
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
    
    async def find_person_by_name(self, full_name: str) -> Optional[Dict]:
        """Find a person in the database by full name with improved matching"""
        try:
            # Clean up the name
            full_name = full_name.strip()
            
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
            
            # Try splitting by first and last name
            name_parts = full_name.split()
            if len(name_parts) >= 2:
                first_name = name_parts[0]
                last_name = ' '.join(name_parts[1:])
                
                person = await self.db_conn.fetchrow("""
                    SELECT id, first_name, last_name, province, position, year
                    FROM political_dynasties 
                    WHERE first_name = $1 AND last_name = $2
                    ORDER BY year DESC
                    LIMIT 1
                """, first_name, last_name)
                
                if person:
                    return dict(person)
                
                # Try with first name matching and last name containing (for middle names)
                person = await self.db_conn.fetchrow("""
                    SELECT id, first_name, last_name, province, position, year
                    FROM political_dynasties 
                    WHERE first_name = $1 AND last_name LIKE $2
                    ORDER BY year DESC
                    LIMIT 1
                """, first_name, f"%{last_name}%")
                
                if person:
                    return dict(person)
            
            # Try fuzzy match with ILIKE (contains)
            person = await self.db_conn.fetchrow("""
                SELECT id, first_name, last_name, province, position, year
                FROM political_dynasties 
                WHERE CONCAT(first_name, ' ', last_name) ILIKE $1
                ORDER BY year DESC
                LIMIT 1
            """, f"%{full_name}%")
            
            if person:
                return dict(person)
            
            # Try reverse - if searching for "JINGGOY ESTRADA", search for names containing both
            if len(name_parts) >= 2:
                first = name_parts[0]
                last = name_parts[-1]  # Last part
                person = await self.db_conn.fetchrow("""
                    SELECT id, first_name, last_name, province, position, year
                    FROM political_dynasties 
                    WHERE first_name ILIKE $1 AND last_name ILIKE $2
                    ORDER BY year DESC
                    LIMIT 1
                """, f"%{first}%", f"%{last}%")
                
                if person:
                    return dict(person)
            
            return None
            
        except Exception as e:
            print(f"❌ Error finding person '{full_name}': {e}")
            return None
    
    async def create_person(self, full_name: str, position: str = "", source: str = "") -> Optional[Dict]:
        """Create a new person in the database"""
        try:
            # Parse name
            name_parts = full_name.strip().split()
            if len(name_parts) < 2:
                print(f"   ⚠️  Cannot create person: name '{full_name}' is too short")
                return None
            
            first_name = name_parts[0]
            last_name = ' '.join(name_parts[1:])
            
            # Insert person
            person_id = await self.db_conn.fetchval("""
                INSERT INTO political_dynasties 
                (first_name, last_name, position, year)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            """, first_name, last_name, position if position else None, 2025)
            
            # Fetch the created person
            person = await self.db_conn.fetchrow("""
                SELECT id, first_name, last_name, province, position, year
                FROM political_dynasties 
                WHERE id = $1
            """, person_id)
            
            return dict(person) if person else None
            
        except Exception as e:
            print(f"   ❌ Error creating person '{full_name}': {e}")
            return None
    
    def extract_senator_name(self, text: str) -> Optional[str]:
        """Extract senator name from OCR text"""
        # Pattern: "RELATIVES OF\nSENATOR [FIRST]\n\n[LAST]\n\nIN THE GOVERNMENT"
        # or "RELATIVES OF\nSENATOR [FULL NAME]"
        patterns = [
            r'RELATIVES OF\s+SENATOR\s+([A-Z]+)\s*\n\s*\n\s*([A-Z]+)\s*\n',
            r'RELATIVES OF\s+SENATOR\s+([A-Z\s]+?)(?:\n|IN THE GOVERNMENT)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                if len(match.groups()) == 2:
                    # First and last name on separate lines
                    first = match.group(1).strip()
                    last = match.group(2).strip()
                    name = f"{first} {last}"
                else:
                    name = match.group(1).strip()
                
                # Clean up extra whitespace
                name = ' '.join(name.split())
                if name:
                    return name
        
        return None
    
    def parse_relationships(self, text: str, senator_name: str) -> List[Dict]:
        """Parse relationships from OCR text
        Structure: 
        - Top: SENATOR [NAME] (centered)
        - Bottom: 2-column layout with entries:
          - NAME (first line)
          - RELATIONSHIP (second line)
          - POSITION (third line)
        """
        relationships = []
        
        # Remove the header part (everything before "IN THE GOVERNMENT")
        text = re.sub(r'RELATIVES OF\s+SENATOR.*?IN THE GOVERNMENT', '', text, flags=re.IGNORECASE | re.DOTALL)
        
        # Remove email/watermark at the end
        text = re.sub(r'@.*?gmail\.com.*$', '', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'©.*$', '', text, flags=re.IGNORECASE | re.DOTALL)
        
        # Position keywords to identify position lines
        position_keywords = ['MAYOR', 'GOVERNOR', 'SENATOR', 'REPRESENTATIVE', 'COUNCILOR', 
                            'SECRETARY', 'UNDERSECRETARY', 'DIRECTOR', 'OFFICER', 'CAPTAIN', 
                            'VICE', 'MEMBER', 'BOARD', 'BRGY', 'BARANGAY', 'CITY', 'PROVINCE',
                            'DISTRICT', 'OFFICE', 'STAFF', 'CLERK', 'TECHNOLOGIST', 'KEEPER',
                            'DRIVER', 'LICENSING', 'REVENUE', 'COLLECTION', 'MEDICAL',
                            'ANIMAL', 'PRIVATE SECTOR', 'ADVISORY', 'COUNCIL', 'CHIEF', 'MANAGER',
                            'SUPERVISING', 'LEGISLATIVE', 'POLITICAL', 'AFFAIRS', 'ASSISTANT']
        
        # Split into lines
        lines = [line.strip() for line in text.split('\n')]
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Skip empty lines
            if not line:
                i += 1
                continue
            
            # Look for a name pattern: uppercase, 2+ words, not a position
            # Names are typically in all caps and have 2-4 words
            is_name_candidate = (
                line.isupper() and 
                len(line.split()) >= 2 and 
                len(line.split()) <= 5 and
                len(line) > 5 and
                not any(keyword in line for keyword in position_keywords) and
                not line.startswith('RELATIVES') and
                'OF ' not in line and  # Skip lines like "VICE MAYOR OF CITY"
                not line.startswith('IN THE')  # Skip "IN THE GOVERNMENT"
            )
            
            if is_name_candidate:
                name = line
                position = ""
                relationship = None
                
                # Look ahead for position and relationship
                # Format: NAME -> POSITION -> RELATIONSHIP (at bottom)
                # Some entries are 1 column, some are 2 columns (when many members)
                j = i + 1
                
                # Collect next few non-empty lines (up to 6 lines ahead to handle 2-column layouts)
                next_lines = []
                k = i + 1
                while k < len(lines) and k < i + 7:
                    if lines[k].strip():
                        next_lines.append((k, lines[k].strip()))
                    k += 1
                
                # Try to find position and relationship in the next lines
                relationship_found = False
                
                # First priority: Look for POSITION first (format: NAME -> POSITION -> RELATIONSHIP)
                position_line_idx = None
                for line_idx, next_line in next_lines:
                    if any(keyword in next_line.upper() for keyword in position_keywords):
                        position = next_line
                        position_line_idx = line_idx
                        break
                
                # Then look for relationship (usually after position, but could be before)
                if position_line_idx is not None:
                    # First check lines after position (most common)
                    for line_idx, next_line in next_lines:
                        if line_idx > position_line_idx:
                            next_line_upper = next_line.upper().strip()
                            for rel_key, rel_name in self.relationship_mappings.items():
                                # Relationship is usually standalone or at end of line
                                if rel_key == next_line_upper or next_line_upper.endswith(rel_key):
                                    relationship = rel_name
                                    relationship_found = True
                                    j = line_idx
                                    break
                            if relationship_found:
                                break
                    
                    # If not found after, check lines before position (for OCR variations)
                    if not relationship_found:
                        for line_idx, next_line in next_lines:
                            if line_idx < position_line_idx:
                                next_line_upper = next_line.upper().strip()
                                for rel_key, rel_name in self.relationship_mappings.items():
                                    if rel_key == next_line_upper or next_line_upper.endswith(rel_key):
                                        relationship = rel_name
                                        relationship_found = True
                                        j = line_idx
                                        break
                                if relationship_found:
                                    break
                else:
                    # If position not found, try to find relationship anyway (might be in different column)
                    for line_idx, next_line in next_lines:
                        next_line_upper = next_line.upper().strip()
                        for rel_key, rel_name in self.relationship_mappings.items():
                            if rel_key == next_line_upper or next_line_upper.endswith(rel_key):
                                relationship = rel_name
                                relationship_found = True
                                j = line_idx
                                
                                # Try to find position near the relationship
                                for pos_idx, pos_line in next_lines:
                                    if abs(pos_idx - line_idx) <= 2:  # Within 2 lines
                                        if any(keyword in pos_line.upper() for keyword in position_keywords):
                                            position = pos_line
                                            break
                                break
                        if relationship_found:
                            break
                
                # If we found a relationship, add it
                if relationship:
                    # Clean up name - remove special characters but keep hyphens
                    name = re.sub(r'[^\w\s-]', '', name)
                    name = ' '.join(name.split())
                    
                    # Clean up position
                    if position:
                        position = re.sub(r'[^\w\s\.,\-/]', '', position)
                        position = ' '.join(position.split())
                    
                    # Final validation: ensure name is valid
                    if name and len(name.split()) >= 2 and len(name) > 5:
                        # Check if we already have this person
                        if not any(r['name'].upper().strip() == name.upper().strip() for r in relationships):
                            relationships.append({
                                'name': name,
                                'position': position,
                                'relationship': relationship,
                                'raw_relationship': relationship
                            })
                            # Skip past this entry (name, relationship, position)
                            i = j + (2 if position else 1)
                            continue
            
            i += 1
        
        return relationships
    
    async def get_relationship_type_code(self, relationship_type: str) -> Optional[int]:
        """Get connection type code for relationship type"""
        relationship_upper = relationship_type.upper()
        
        # Map to standard name
        mapped_name = self.relationship_mappings.get(relationship_upper, relationship_type)
        
        # Get code from connection types
        return self.connection_type_map.get(mapped_name.upper())
    
    async def get_reverse_relationship_type(self, relationship_type_id: int) -> int:
        """Get the reverse relationship type ID"""
        current_type = await self.db_conn.fetchrow("""
            SELECT name FROM connection_types WHERE code = $1
        """, relationship_type_id)
        
        if not current_type:
            return relationship_type_id
        
        current_name = current_type['name'].upper()
        
        reverse_mappings = {
            'HUSBAND': 'WIFE',
            'WIFE': 'HUSBAND',
            'FATHER': 'SON',
            'MOTHER': 'SON',
            'SON': 'FATHER',
            'DAUGHTER': 'FATHER',
            'BROTHER': 'BROTHER',
            'SISTER': 'SISTER',
            'UNCLE': 'NEPHEW',
            'AUNT': 'NIECE',
            'NEPHEW': 'UNCLE',
            'NIECE': 'AUNT',
            'COUSIN': 'COUSIN',
            'SON-IN-LAW': 'FATHER-IN-LAW',
            'DAUGHTER-IN-LAW': 'MOTHER-IN-LAW',
            'FATHER-IN-LAW': 'SON-IN-LAW',
            'MOTHER-IN-LAW': 'DAUGHTER-IN-LAW',
        }
        
        reverse_name = reverse_mappings.get(current_name, current_name)
        reverse_type = await self.db_conn.fetchrow("""
            SELECT code FROM connection_types WHERE name = $1
        """, reverse_name)
        
        if reverse_type:
            return reverse_type['code']
        else:
            return relationship_type_id
    
    async def import_relationships_from_json(self, json_file: str):
        """Import relationships from JSON file"""
        print(f"📖 Reading JSON file: {json_file}")
        
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        total_relationships = 0
        relationships_created = 0
        relationships_skipped = 0
        persons_not_found = 0
        
        for image_file, ocr_text in data.items():
            print(f"\n📋 Processing {image_file}...")
            
            # Extract senator name
            senator_name = self.extract_senator_name(ocr_text)
            if not senator_name:
                print(f"   ⚠️  Could not extract senator name from {image_file}")
                continue
            
            print(f"   👤 Senator: {senator_name}")
            
            # Find senator in database
            senator = await self.find_person_by_name(senator_name)
            
            # If senator not found, try variations
            if not senator:
                # Try with "EJERCITO" added for JINGGOY ESTRADA case
                if "JINGGOY" in senator_name.upper() and "ESTRADA" in senator_name.upper():
                    senator = await self.find_person_by_name("JINGGOY EJERCITO ESTRADA")
                elif "JINGGOY" in senator_name.upper():
                    senator = await self.find_person_by_name("JINGGOY EJERCITO ESTRADA")
                
                # If still not found, create the senator
                if not senator:
                    print(f"   ➕ Senator not found, creating: {senator_name}")
                    senator = await self.create_person(senator_name, "SENATOR OF THE PHILIPPINES", image_file)
                    
                    if not senator:
                        print(f"   ❌ Failed to create senator: {senator_name}")
                        persons_not_found += 1
                        continue
                    
                    print(f"   ✅ Created senator: {senator['first_name']} {senator['last_name']} (ID: {senator['id']})")
                else:
                    print(f"   ✅ Found senator: {senator['first_name']} {senator['last_name']} (ID: {senator['id']})")
            else:
                print(f"   ✅ Found senator: {senator['first_name']} {senator['last_name']} (ID: {senator['id']})")
            
            # Parse relationships
            relatives = self.parse_relationships(ocr_text, senator_name)
            print(f"   📝 Found {len(relatives)} relatives")
            
            for relative in relatives:
                total_relationships += 1
                rel_name = relative['name']
                rel_position = relative['position']
                rel_type = relative['relationship']
                
                print(f"      🔍 Processing: {rel_name} ({rel_type})")
                
                # Find relative in database
                relative_person = await self.find_person_by_name(rel_name)
                
                # If not found, create the person
                if not relative_person:
                    print(f"         ➕ Person not found, creating: {rel_name}")
                    relative_person = await self.create_person(rel_name, rel_position, image_file)
                    
                    if not relative_person:
                        print(f"         ❌ Failed to create person: {rel_name}")
                        persons_not_found += 1
                        continue
                    
                    print(f"         ✅ Created person: {relative_person['first_name']} {relative_person['last_name']} (ID: {relative_person['id']})")
                
                # Get relationship type code
                relationship_type_code = await self.get_relationship_type_code(rel_type)
                if not relationship_type_code:
                    print(f"         ⚠️  Unknown relationship type: {rel_type}")
                    relationships_skipped += 1
                    continue
                
                # Check if relationship already exists
                existing = await self.db_conn.fetchrow("""
                    SELECT id FROM relationships 
                    WHERE person_id = $1 AND related_person_id = $2 AND relationship_type = $3
                """, senator['id'], relative_person['id'], relationship_type_code)
                
                if existing:
                    print(f"         ⚠️  Relationship already exists")
                    relationships_skipped += 1
                    continue
                
                # Create relationship description
                description = f"{senator['first_name']} {senator['last_name']} is {rel_type.lower()} of {rel_name}"
                if rel_position:
                    description += f" ({rel_position})"
                
                # Insert relationship
                try:
                    await self.db_conn.execute("""
                        INSERT INTO relationships (
                            person_id, related_person_id, relationship_type,
                            relationship_description, source_url, confidence_level,
                            verified, created_by
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """, 
                    senator['id'], relative_person['id'], relationship_type_code,
                    description, f"OCR:{image_file}", 8,  # High confidence from official source
                    False, 'Senator_Relationships_OCR'
                    )
                    
                    print(f"         ✅ Created relationship")
                    relationships_created += 1
                    
                    # Create reverse relationship
                    try:
                        reverse_type_code = await self.get_reverse_relationship_type(relationship_type_code)
                        # Get the relationship type name for description
                        reverse_type_name = await self.db_conn.fetchval("""
                            SELECT name FROM connection_types WHERE code = $1
                        """, reverse_type_code)
                        reverse_description = f"{rel_name} is {reverse_type_name.lower()} of {senator['first_name']} {senator['last_name']}"
                        
                        existing_reverse = await self.db_conn.fetchrow("""
                            SELECT id FROM relationships 
                            WHERE person_id = $1 AND related_person_id = $2 AND relationship_type = $3
                        """, relative_person['id'], senator['id'], reverse_type_code)
                        
                        if not existing_reverse:
                            await self.db_conn.execute("""
                                INSERT INTO relationships (
                                    person_id, related_person_id, relationship_type,
                                    relationship_description, source_url, confidence_level,
                                    verified, created_by
                                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                            """, 
                            relative_person['id'], senator['id'], reverse_type_code,
                            reverse_description, f"OCR:{image_file}", 8,
                            False, 'Senator_Relationships_OCR'
                            )
                    except Exception as e:
                        print(f"         ⚠️  Error creating reverse relationship: {e}")
                        
                except Exception as e:
                    print(f"         ❌ Error creating relationship: {e}")
                    relationships_skipped += 1
        
        print(f"\n📊 Import Summary:")
        print(f"   Total relationships processed: {total_relationships}")
        print(f"   Relationships created: {relationships_created}")
        print(f"   Relationships skipped: {relationships_skipped}")
        print(f"   Persons not found: {persons_not_found}")

async def main():
    """Main function"""
    importer = SenatorRelationshipsImporter()
    
    try:
        await importer.connect()
        await importer.setup_connection_types()
        
        json_file = "senators-relationships.json"
        if os.path.exists(json_file):
            await importer.import_relationships_from_json(json_file)
        else:
            print(f"❌ JSON file not found: {json_file}")
        
    finally:
        await importer.close()

if __name__ == "__main__":
    asyncio.run(main())


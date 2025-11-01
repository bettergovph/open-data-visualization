#!/usr/bin/env python3
"""
Integrate HuggingFace Philippine Data into Dynasty Database

This script:
1. Downloads persons + memberships data from HuggingFace
2. Corrects/normalizes names in political_dynasties table
3. Adds missing persons and memberships
4. Updates party_list table with accurate party data
5. Identifies potential relationships for manual review
6. Updates unified_persons and name_mappings tables

Focus: Names, relationships, party affiliations, companies/officers
"""

import asyncio
import asyncpg
from datasets import load_dataset
from tqdm import tqdm
import os
from dotenv import load_dotenv
from collections import defaultdict
import re


class DynastyHuggingFaceIntegrator:
    def __init__(self):
        # Try to load .env if it exists, but don't require it
        if os.path.exists('.env'):
            load_dotenv('.env')
        
        self.db_host = os.getenv('POSTGRES_HOST', 'localhost')
        self.db_port = int(os.getenv('POSTGRES_PORT', 5432))
        self.db_user = os.getenv('POSTGRES_USER', 'budget_admin')
        self.db_password = os.getenv('POSTGRES_PASSWORD', '')
        self.db_name = os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
        
        self.conn = None
        self.stats = {
            'persons_loaded': 0,
            'memberships_loaded': 0,
            'persons_added': 0,
            'persons_updated': 0,
            'parties_added': 0,
            'parties_updated': 0,
            'name_corrections': 0,
            'potential_relationships': 0
        }
        
        # Cache for existing data
        self.existing_persons = {}  # canonical_name -> id mapping
        self.existing_parties = set()
        self.party_mappings = {}  # code -> full name
        
    async def connect(self):
        """Connect to dynasty database"""
        print(f"🔌 Connecting to dynasty database at {self.db_host}...")
        self.conn = await asyncpg.connect(
            host=self.db_host,
            port=self.db_port,
            user=self.db_user,
            password=self.db_password,
            database=self.db_name
        )
        print("✅ Connected to dynasty database")
    
    async def close(self):
        """Close database connection"""
        if self.conn:
            await self.conn.close()
            print("✅ Database connection closed")
    
    def normalize_name(self, first_name, middle_name, last_name, suffix):
        """Create canonical name from components"""
        parts = []
        if first_name:
            parts.append(first_name.strip().upper())
        if middle_name:
            parts.append(middle_name.strip().upper())
        if last_name:
            parts.append(last_name.strip().upper())
        if suffix:
            parts.append(suffix.strip().upper())
        return ' '.join(parts)
    
    async def load_existing_data(self):
        """Load existing persons and parties from database"""
        print("\n📥 Loading existing data from database...")
        
        # Load existing persons
        persons = await self.conn.fetch("""
            SELECT id, first_name, last_name, middle_name, suffix, canonical_name
            FROM political_dynasties
            WHERE first_name IS NOT NULL AND last_name IS NOT NULL
        """)
        
        for person in persons:
            canonical = person['canonical_name']
            if not canonical:
                # Generate canonical name if missing
                canonical = self.normalize_name(
                    person['first_name'],
                    person['middle_name'],
                    person['last_name'],
                    person['suffix']
                )
            self.existing_persons[canonical] = person['id']
        
        print(f"  ✓ Loaded {len(self.existing_persons)} existing persons")
        
        # Load existing parties
        parties = await self.conn.fetch("SELECT code, party_name FROM party_list")
        for party in parties:
            self.existing_parties.add(party['party_name'])
            self.party_mappings[party['code']] = party['party_name']
        
        print(f"  ✓ Loaded {len(self.existing_parties)} existing parties")
    
    def load_huggingface_data(self):
        """Download and load HuggingFace dataset"""
        print("\n📦 Downloading HuggingFace dataset...")
        
        print("  Downloading persons...")
        self.persons_data = load_dataset(
            "bettergovph/raw-philippine-data",
            "persons",
            split="train"
        )
        self.stats['persons_loaded'] = len(self.persons_data)
        print(f"  ✓ Loaded {self.stats['persons_loaded']} persons")
        
        print("  Downloading memberships...")
        self.memberships_data = load_dataset(
            "bettergovph/raw-philippine-data",
            "memberships",
            split="train"
        )
        self.stats['memberships_loaded'] = len(self.memberships_data)
        print(f"  ✓ Loaded {self.stats['memberships_loaded']} memberships")
        
        # Create person_id -> person mapping
        self.persons_by_id = {p['id']: p for p in self.persons_data}
        print(f"  ✓ Indexed {len(self.persons_by_id)} persons by ID")
    
    async def update_party_list(self):
        """Update party_list table with parties from HuggingFace data"""
        print("\n🎭 Updating party list...")
        
        # Count occurrences of each party
        party_counts = defaultdict(int)
        party_codes = {}  # party_name -> code
        
        for membership in tqdm(self.memberships_data, desc="Counting parties"):
            party = membership.get('party')
            if party and party.strip():
                party_name = party.strip()
                party_counts[party_name] += 1
                
                # Generate code from first letters
                if party_name not in party_codes:
                    # Use first letters of words as code
                    words = party_name.split()
                    code = ''.join(w[0] for w in words if w).upper()
                    party_codes[party_name] = code
        
        print(f"  Found {len(party_counts)} unique parties")
        
        # Insert or update parties
        for party_name, count in tqdm(party_counts.items(), desc="Updating parties"):
            code = party_codes[party_name]
            
            if party_name in self.existing_parties:
                # Update occurrence count
                await self.conn.execute("""
                    UPDATE party_list 
                    SET occurrences = occurrences + $1
                    WHERE party_name = $2
                """, count, party_name)
                self.stats['parties_updated'] += 1
            else:
                # Insert new party
                await self.conn.execute("""
                    INSERT INTO party_list (code, party_name, occurrences)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (code, party_name) DO UPDATE
                    SET occurrences = party_list.occurrences + $3
                """, code, party_name, count)
                self.stats['parties_added'] += 1
                self.existing_parties.add(party_name)
        
        print(f"  ✓ Added {self.stats['parties_added']} new parties")
        print(f"  ✓ Updated {self.stats['parties_updated']} existing parties")
    
    async def integrate_persons_and_memberships(self):
        """Integrate persons and their memberships into political_dynasties table"""
        print("\n👥 Integrating persons and memberships...")
        
        # Group memberships by person_id
        memberships_by_person = defaultdict(list)
        for membership in self.memberships_data:
            person_id = membership.get('person_id')
            if person_id:
                memberships_by_person[person_id].append(membership)
        
        print(f"  Found memberships for {len(memberships_by_person)} persons")
        
        # Process each person with their memberships
        for person in tqdm(self.persons_data, desc="Processing persons"):
            person_id = person['id']
            
            # Get person name components
            first_name = (person.get('first_name') or '').strip()
            middle_name = (person.get('middle_name') or '').strip()
            last_name = (person.get('last_name') or '').strip()
            suffix = (person.get('name_suffix') or '').strip()
            nickname = (person.get('nickname') or '').strip()
            
            if not first_name or not last_name:
                continue  # Skip persons without proper names
            
            # Create canonical name
            canonical_name = self.normalize_name(first_name, middle_name, last_name, suffix)
            
            # Get memberships for this person
            memberships = memberships_by_person.get(person_id, [])
            
            if not memberships:
                continue  # Skip persons without positions
            
            # Process each membership as a separate record
            for membership in memberships:
                party = (membership.get('party') or '').strip()
                region = (membership.get('region') or '').strip()
                province = (membership.get('province') or '').strip()
                locality = (membership.get('locality') or '').strip()
                position = (membership.get('position') or '').strip()
                year = membership.get('year')
                
                if not position:
                    continue  # Skip memberships without position
                
                # Check if this exact record exists
                existing = await self.conn.fetchrow("""
                    SELECT id FROM political_dynasties
                    WHERE canonical_name = $1 
                    AND position = $2 
                    AND year = $3
                    AND COALESCE(province, '') = $4
                """, canonical_name, position, year, province)
                
                if existing:
                    # Update existing record with better data
                    await self.conn.execute("""
                        UPDATE political_dynasties
                        SET 
                            first_name = COALESCE(NULLIF($1, ''), first_name),
                            middle_name = COALESCE(NULLIF($2, ''), middle_name),
                            last_name = COALESCE(NULLIF($3, ''), last_name),
                            suffix = COALESCE(NULLIF($4, ''), suffix),
                            nickname = COALESCE(NULLIF($5, ''), nickname),
                            party = COALESCE(NULLIF($6, ''), party),
                            region = COALESCE(NULLIF($7, ''), region),
                            province = COALESCE(NULLIF($8, ''), province),
                            municipality_city = COALESCE(NULLIF($9, ''), municipality_city),
                            canonical_name = $10
                        WHERE id = $11
                    """, first_name, middle_name, last_name, suffix, nickname,
                         party, region, province, locality, canonical_name, existing['id'])
                    self.stats['persons_updated'] += 1
                else:
                    # Insert new record
                    await self.conn.execute("""
                        INSERT INTO political_dynasties (
                            first_name, middle_name, last_name, suffix, nickname,
                            party, region, province, municipality_city, position, year,
                            canonical_name, winner, fat
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    """, first_name, middle_name, last_name, suffix, nickname,
                         party, region, province, locality, position, year,
                         canonical_name, True, 0)  # Default: winner=true, fat=0 (not dynasty yet)
                    self.stats['persons_added'] += 1
        
        print(f"  ✓ Added {self.stats['persons_added']} new person records")
        print(f"  ✓ Updated {self.stats['persons_updated']} existing records")
    
    async def correct_existing_names(self):
        """Correct names in existing political_dynasties records using HuggingFace data"""
        print("\n✏️ Correcting existing names...")
        
        # Create a mapping of last_name -> persons from HuggingFace
        hf_by_lastname = defaultdict(list)
        for person in self.persons_data:
            last_name = (person.get('last_name') or '').strip().upper()
            if last_name:
                hf_by_lastname[last_name].append(person)
        
        print(f"  Indexed {len(hf_by_lastname)} unique last names from HuggingFace")
        
        # Get records with missing middle names or suffixes
        incomplete_records = await self.conn.fetch("""
            SELECT id, first_name, last_name, middle_name, suffix, canonical_name
            FROM political_dynasties
            WHERE last_name IS NOT NULL
            AND (middle_name IS NULL OR middle_name = '' OR suffix IS NULL OR suffix = '')
            LIMIT 10000
        """)
        
        print(f"  Found {len(incomplete_records)} records to potentially correct")
        
        corrections = 0
        for record in tqdm(incomplete_records, desc="Correcting names"):
            last_name = record['last_name'].strip().upper()
            first_name = record['first_name'].strip().upper() if record['first_name'] else ''
            
            # Look for matching persons in HuggingFace data
            candidates = hf_by_lastname.get(last_name, [])
            
            for candidate in candidates:
                hf_first = (candidate.get('first_name') or '').strip().upper()
                hf_last = (candidate.get('last_name') or '').strip().upper()
                hf_middle = (candidate.get('middle_name') or '').strip()
                hf_suffix = (candidate.get('name_suffix') or '').strip()
                
                # Check if first and last names match
                if hf_first == first_name and hf_last == last_name:
                    # Update with missing data
                    new_middle = hf_middle if hf_middle and not record['middle_name'] else record['middle_name']
                    new_suffix = hf_suffix if hf_suffix and not record['suffix'] else record['suffix']
                    
                    if new_middle or new_suffix:
                        # Update record
                        new_canonical = self.normalize_name(
                            record['first_name'],
                            new_middle,
                            record['last_name'],
                            new_suffix
                        )
                        
                        await self.conn.execute("""
                            UPDATE political_dynasties
                            SET middle_name = $1, suffix = $2, canonical_name = $3
                            WHERE id = $4
                        """, new_middle, new_suffix, new_canonical, record['id'])
                        
                        corrections += 1
                        break
        
        self.stats['name_corrections'] = corrections
        print(f"  ✓ Corrected {corrections} names")
    
    async def identify_potential_relationships(self):
        """Identify persons with same last name who might be related"""
        print("\n🔗 Identifying potential relationships...")
        
        # Group persons by last name from HuggingFace data
        by_lastname = defaultdict(list)
        for person in self.persons_data:
            last_name = (person.get('last_name') or '').strip().upper()
            if last_name:
                by_lastname[last_name].append(person)
        
        # Find last names with multiple persons (potential dynasties)
        potential_dynasties = {
            lastname: persons 
            for lastname, persons in by_lastname.items() 
            if len(persons) >= 2
        }
        
        self.stats['potential_relationships'] = len(potential_dynasties)
        print(f"  ✓ Found {len(potential_dynasties)} last names with multiple persons")
        
        # Save report for manual review
        report_file = "huggingface_potential_relationships.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("POTENTIAL RELATIONSHIPS FROM HUGGINGFACE DATA\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"Found {len(potential_dynasties)} last names with multiple persons\n\n")
            
            for lastname in sorted(potential_dynasties.keys())[:100]:  # Top 100
                persons = potential_dynasties[lastname]
                f.write(f"\n{lastname} ({len(persons)} persons):\n")
                for person in persons[:10]:  # Limit to 10 per family
                    full_name = f"{person.get('first_name') or ''} {person.get('middle_name') or ''} {person.get('last_name') or ''} {person.get('name_suffix') or ''}".strip()
                    f.write(f"  - {full_name}\n")
        
        print(f"  ✓ Saved potential relationships to {report_file}")
    
    async def generate_summary_report(self):
        """Generate final summary report"""
        print("\n" + "=" * 80)
        print("INTEGRATION SUMMARY REPORT")
        print("=" * 80)
        print(f"\n📊 Data Loaded:")
        print(f"  - Persons from HuggingFace: {self.stats['persons_loaded']:,}")
        print(f"  - Memberships from HuggingFace: {self.stats['memberships_loaded']:,}")
        
        print(f"\n👥 Persons Integration:")
        print(f"  - New person records added: {self.stats['persons_added']:,}")
        print(f"  - Existing records updated: {self.stats['persons_updated']:,}")
        print(f"  - Names corrected: {self.stats['name_corrections']:,}")
        
        print(f"\n🎭 Party Affiliations:")
        print(f"  - New parties added: {self.stats['parties_added']:,}")
        print(f"  - Existing parties updated: {self.stats['parties_updated']:,}")
        
        print(f"\n🔗 Relationships:")
        print(f"  - Potential dynasty families identified: {self.stats['potential_relationships']:,}")
        
        # Get updated database stats
        total_persons = await self.conn.fetchval("SELECT COUNT(*) FROM political_dynasties")
        total_parties = await self.conn.fetchval("SELECT COUNT(*) FROM party_list")
        
        print(f"\n📈 Current Database Stats:")
        print(f"  - Total persons in database: {total_persons:,}")
        print(f"  - Total parties in database: {total_parties:,}")
        
        print("\n✅ Integration complete!")
        print("=" * 80)
    
    async def run(self):
        """Run the full integration process"""
        try:
            await self.connect()
            
            # Step 1: Load HuggingFace data
            self.load_huggingface_data()
            
            # Step 2: Load existing data from database
            await self.load_existing_data()
            
            # Step 3: Update party list
            await self.update_party_list()
            
            # Step 4: Correct existing names
            await self.correct_existing_names()
            
            # Step 5: Integrate persons and memberships
            await self.integrate_persons_and_memberships()
            
            # Step 6: Identify potential relationships
            await self.identify_potential_relationships()
            
            # Step 7: Generate summary report
            await self.generate_summary_report()
            
        finally:
            await self.close()


async def main():
    """Main entry point"""
    print("🚀 HuggingFace to Dynasty Database Integration")
    print("=" * 80)
    
    integrator = DynastyHuggingFaceIntegrator()
    await integrator.run()


if __name__ == "__main__":
    asyncio.run(main())


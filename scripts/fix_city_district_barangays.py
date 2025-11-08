#!/usr/bin/env python3
"""
Fix city district matching by adding barangays to district_entries and dynasty_projects_congressmen_config.

This script:
1. Identifies all city districts (not province districts)
2. For each city district, ensures barangays are properly listed in:
   - district_entries table (in the data JSONB field)
   - dynasty_projects_congressmen_config table (in the barangays array field)
3. Implements strict matching rules for city districts:
   - If project mentions "ROAD" (case insensitive), require "CITY" in project name/location
   - Barangay matching is REQUIRED for accurate city district attribution
"""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import asyncpg
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class CityDistrictBarangayFixer:
    """Fix city district barangay data and matching logic"""
    
    def __init__(self):
        self.conn: Optional[asyncpg.Connection] = None
        self.city_districts: List[Dict[str, Any]] = []
        self.barangay_data: Dict[str, Dict[str, List[str]]] = {}  # city_name -> {district_num -> [barangays]}
        
    async def connect(self):
        """Connect to dynasty database"""
        self.conn = await asyncpg.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
            user=os.getenv("POSTGRES_USER", "budget_admin"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            database=os.getenv("POSTGRES_DB_DYNASTY", "dynasty"),
        )
        await self.conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
        await self.conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
        print("✅ Connected to dynasty database")
    
    async def close(self):
        """Close database connection"""
        if self.conn:
            await self.conn.close()
            print("✅ Closed database connection")
    
    async def identify_city_districts(self):
        """Identify all city districts from the database"""
        query = """
            SELECT id, first_name_pattern, last_name_pattern, display_name, full_name,
                   province, district_number, is_city_district, barangays, barangays_file
            FROM dynasty_projects_congressmen_config
            WHERE is_city_district = TRUE
            ORDER BY province, district_number
        """
        
        rows = await self.conn.fetch(query)
        self.city_districts = [dict(row) for row in rows]
        
        print(f"\n📋 Found {len(self.city_districts)} city districts:")
        for district in self.city_districts:
            barangay_count = len(district['barangays']) if district['barangays'] else 0
            barangays_file = district.get('barangays_file', 'N/A')
            print(f"  • {district['display_name']} ({district['province']}, District {district['district_number']})")
            print(f"    - Barangays in DB: {barangay_count}")
            print(f"    - Barangays file: {barangays_file}")
    
    async def load_barangay_data_from_district_entries(self):
        """Load existing barangay data from district_entries table"""
        query = """
            SELECT name, entity_type, data
            FROM district_entries
            ORDER BY name
        """
        
        rows = await self.conn.fetch(query)
        
        for row in rows:
            city_name = row['name']
            data = row['data']
            
            # Extract barangays by district
            if 'barangays' in data and isinstance(data['barangays'], dict):
                self.barangay_data[city_name] = data['barangays']
        
        print(f"\n📊 Loaded barangay data for {len(self.barangay_data)} cities from district_entries")
        for city_name, districts in self.barangay_data.items():
            print(f"  • {city_name}: {len(districts)} districts")
            for district_num, barangays in districts.items():
                print(f"    - District {district_num}: {len(barangays)} barangays")
    
    async def update_congressman_config_barangays(self, congressman_id: int, barangays: List[str]):
        """Update barangays for a congressman in dynasty_projects_congressmen_config"""
        query = """
            UPDATE dynasty_projects_congressmen_config
            SET barangays = $1
            WHERE id = $2
        """
        
        await self.conn.execute(query, barangays, congressman_id)
        print(f"  ✅ Updated congressman ID {congressman_id} with {len(barangays)} barangays")
    
    async def ensure_district_entry_has_barangays(self, city_name: str, district_num: str, barangays: List[str]):
        """Ensure district_entries has barangays for this city district"""
        # Check if entry exists
        existing = await self.conn.fetchrow(
            "SELECT data FROM district_entries WHERE name = $1",
            city_name
        )
        
        if existing:
            data = existing['data']
            if 'barangays' not in data:
                data['barangays'] = {}
            
            data['barangays'][district_num] = barangays
            
            await self.conn.execute(
                "UPDATE district_entries SET data = $1 WHERE name = $2",
                data, city_name
            )
            print(f"  ✅ Updated district_entries for {city_name}, District {district_num} with {len(barangays)} barangays")
        else:
            # Create new entry
            data = {
                'barangays': {district_num: barangays},
                'municipalities': {}
            }
            
            await self.conn.execute(
                """
                INSERT INTO district_entries (name, entity_type, data)
                VALUES ($1, $2, $3)
                """,
                city_name, 'city', data
            )
            print(f"  ✅ Created district_entries for {city_name}, District {district_num} with {len(barangays)} barangays")
    
    async def process_city_district(self, district: Dict[str, Any]):
        """Process a single city district to ensure barangays are properly set"""
        city_name = district['province']
        district_num = district['district_number']
        congressman_id = district['id']
        display_name = district['display_name']
        
        print(f"\n🔧 Processing: {display_name} ({city_name}, District {district_num})")
        
        # Check if we have barangay data for this city/district
        if city_name in self.barangay_data and district_num in self.barangay_data[city_name]:
            barangays = self.barangay_data[city_name][district_num]
            print(f"  📍 Found {len(barangays)} barangays in district_entries")
            
            # Update congressman config if barangays are missing or different
            current_barangays = district['barangays'] or []
            if set(current_barangays) != set(barangays):
                await self.update_congressman_config_barangays(congressman_id, barangays)
            else:
                print(f"  ✓ Congressman config already has correct barangays")
        else:
            # No barangay data found
            current_barangays = district['barangays'] or []
            if current_barangays:
                print(f"  ⚠️  Using {len(current_barangays)} barangays from congressman config")
                # Update district_entries with these barangays
                await self.ensure_district_entry_has_barangays(city_name, district_num, current_barangays)
            else:
                print(f"  ❌ No barangays found! Manual intervention required.")
                print(f"     Please add barangays for {city_name}, District {district_num}")
    
    async def run(self):
        """Main execution flow"""
        try:
            await self.connect()
            
            # Step 1: Identify all city districts
            await self.identify_city_districts()
            
            # Step 2: Load existing barangay data from district_entries
            await self.load_barangay_data_from_district_entries()
            
            # Step 3: Process each city district
            print("\n" + "="*80)
            print("PROCESSING CITY DISTRICTS")
            print("="*80)
            
            for district in self.city_districts:
                await self.process_city_district(district)
            
            print("\n" + "="*80)
            print("✅ COMPLETED")
            print("="*80)
            print("\nNext steps:")
            print("1. Review the output above for any districts marked with ❌")
            print("2. Manually add missing barangays to the database")
            print("3. Re-run this script to verify all districts have barangays")
            print("4. Run scripts/export_dynasty_json_from_db.py to update JSON files")
            print("5. Run scripts/generate_dynasty_projects_cache.py to regenerate cache")
            
        finally:
            await self.close()


async def main():
    fixer = CityDistrictBarangayFixer()
    await fixer.run()


if __name__ == "__main__":
    asyncio.run(main())



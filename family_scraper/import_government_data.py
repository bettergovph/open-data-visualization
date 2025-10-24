#!/usr/bin/env python3
"""
Government Data Import Script for Dynasty Database
Imports local government officials from ~/bettergov/government data
"""

import json
import os
import asyncio
import asyncpg
from typing import List, Dict, Any
import re
from datetime import datetime

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'dynasty',
    'user': 'budget_admin',
    'password': 'wuQ5gBYCKkZiOGb61chLcByMu'
}

# Data source configuration
GOVERNMENT_DATA_PATH = '/home/joebert/bettergov/src/data/directory/lgu'
YEAR = 2022
DATA_SOURCE = 'GOVERNMENT_2022'

class GovernmentDataImporter:
    def __init__(self):
        self.connection = None
        self.imported_count = 0
        self.errors = []
        
    async def connect_database(self):
        """Connect to the dynasty database"""
        try:
            self.connection = await asyncpg.connect(**DB_CONFIG)
            print("✅ Connected to dynasty database")
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            raise
    
    async def close_database(self):
        """Close database connection"""
        if self.connection:
            await self.connection.close()
            print("✅ Database connection closed")
    
    def parse_name(self, full_name: str) -> tuple[str, str]:
        """Parse full name into first_name and last_name"""
        if not full_name or full_name.strip() == "":
            return "", ""
        
        # Clean up the name
        name = full_name.strip().upper()
        
        # Handle common prefixes
        prefixes = ['H.E.', 'HON.', 'HONORABLE', 'DR.', 'PROF.', 'ATTY.', 'ENG.', 'ARCH.']
        for prefix in prefixes:
            if name.startswith(prefix):
                name = name[len(prefix):].strip()
        
        # Split by spaces
        parts = name.split()
        
        if len(parts) == 0:
            return "", ""
        elif len(parts) == 1:
            return parts[0], ""
        elif len(parts) == 2:
            return parts[0], parts[1]
        else:
            # For Filipino names: First Name + Middle Name + Last Name
            # Last name is typically the last part, everything else is first name
            last_name = parts[-1]  # Last part is the surname
            first_name = " ".join(parts[:-1])  # Everything before the last part
            return first_name, last_name
    
    def standardize_position(self, position: str) -> str:
        """Standardize position names"""
        position_map = {
            'mayor': 'MAYOR',
            'vice_mayor': 'VICE MAYOR',
            'governor': 'GOVERNOR',
            'vice_governor': 'VICE GOVERNOR',
            'senator': 'SENATOR',
            'president': 'PRESIDENT',
            'vice_president': 'VICE PRESIDENT'
        }
        
        position_lower = position.lower().strip()
        return position_map.get(position_lower, position.upper())
    
    def extract_officials_from_region(self, region_data: Dict) -> List[Dict]:
        """Extract officials from a region's data"""
        officials = []
        region_name = region_data.get('region', 'UNKNOWN')
        
        # Handle cities (NCR structure)
        if 'cities' in region_data:
            for city_data in region_data['cities']:
                city_name = city_data.get('city', 'UNKNOWN')
                
                # Extract mayor
                if 'mayor' in city_data and city_data['mayor']:
                    mayor = city_data['mayor']
                    if 'name' in mayor and mayor['name']:
                        first_name, last_name = self.parse_name(mayor['name'])
                        officials.append({
                            'first_name': first_name,
                            'last_name': last_name,
                            'position': 'MAYOR',
                            'region': region_name,
                            'province': city_name,
                            'municipality_city': city_name,
                            'year': YEAR,
                            'fat': 1,
                            'party': 'UNKNOWN',
                            'data_source': DATA_SOURCE
                        })
                
                # Extract vice mayor
                if 'vice_mayor' in city_data and city_data['vice_mayor']:
                    vice_mayor = city_data['vice_mayor']
                    if 'name' in vice_mayor and vice_mayor['name']:
                        first_name, last_name = self.parse_name(vice_mayor['name'])
                        officials.append({
                            'first_name': first_name,
                            'last_name': last_name,
                            'position': 'VICE MAYOR',
                            'region': region_name,
                            'province': city_name,
                            'municipality_city': city_name,
                            'year': YEAR,
                            'fat': 1,
                            'party': 'UNKNOWN',
                            'data_source': DATA_SOURCE
                        })
        
        # Handle provinces (other regions structure)
        if 'provinces' in region_data:
            for province_data in region_data['provinces']:
                province_name = province_data.get('province', 'UNKNOWN')
                
                # Extract governor
                if 'governor' in province_data and province_data['governor']:
                    governor = province_data['governor']
                    if 'name' in governor and governor['name']:
                        first_name, last_name = self.parse_name(governor['name'])
                        officials.append({
                            'first_name': first_name,
                            'last_name': last_name,
                            'position': 'GOVERNOR',
                            'region': region_name,
                            'province': province_name,
                            'municipality_city': province_name,
                            'year': YEAR,
                            'fat': 1,
                            'party': 'UNKNOWN',
                            'data_source': DATA_SOURCE
                        })
                
                # Extract vice governor
                if 'vice_governor' in province_data and province_data['vice_governor']:
                    vice_governor = province_data['vice_governor']
                    if 'name' in vice_governor and vice_governor['name']:
                        first_name, last_name = self.parse_name(vice_governor['name'])
                        officials.append({
                            'first_name': first_name,
                            'last_name': last_name,
                            'position': 'VICE GOVERNOR',
                            'region': region_name,
                            'province': province_name,
                            'municipality_city': province_name,
                            'year': YEAR,
                            'fat': 1,
                            'party': 'UNKNOWN',
                            'data_source': DATA_SOURCE
                        })
                
                # Extract mayors and vice mayors from municipalities
                if 'municipalities' in province_data:
                    for municipality_data in province_data['municipalities']:
                        municipality_name = municipality_data.get('municipality', 'UNKNOWN')
                        
                        # Extract mayor
                        if 'mayor' in municipality_data and municipality_data['mayor']:
                            mayor = municipality_data['mayor']
                            if 'name' in mayor and mayor['name']:
                                first_name, last_name = self.parse_name(mayor['name'])
                                officials.append({
                                    'first_name': first_name,
                                    'last_name': last_name,
                                    'position': 'MAYOR',
                                    'region': region_name,
                                    'province': province_name,
                                    'municipality_city': municipality_name,
                                    'year': YEAR,
                                    'fat': 1,
                                    'party': 'UNKNOWN',
                                    'data_source': DATA_SOURCE
                                })
                        
                        # Extract vice mayor
                        if 'vice_mayor' in municipality_data and municipality_data['vice_mayor']:
                            vice_mayor = municipality_data['vice_mayor']
                            if 'name' in vice_mayor and vice_mayor['name']:
                                first_name, last_name = self.parse_name(vice_mayor['name'])
                                officials.append({
                                    'first_name': first_name,
                                    'last_name': last_name,
                                    'position': 'VICE MAYOR',
                                    'region': region_name,
                                    'province': province_name,
                                    'municipality_city': municipality_name,
                                    'year': YEAR,
                                    'fat': 1,
                                    'party': 'UNKNOWN',
                                    'data_source': DATA_SOURCE
                                })
        
        return officials
    
    async def load_region_data(self, region_file: str) -> List[Dict]:
        """Load and parse a single region's data"""
        file_path = os.path.join(GOVERNMENT_DATA_PATH, region_file)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                region_data = json.load(f)
            
            officials = self.extract_officials_from_region(region_data)
            print(f"📊 Loaded {len(officials)} officials from {region_file}")
            return officials
            
        except Exception as e:
            error_msg = f"Error loading {region_file}: {e}"
            print(f"❌ {error_msg}")
            self.errors.append(error_msg)
            return []
    
    async def load_all_region_data(self) -> List[Dict]:
        """Load data from all region files"""
        all_officials = []
        
        # Get all JSON files in the LGU directory
        region_files = [f for f in os.listdir(GOVERNMENT_DATA_PATH) if f.endswith('.json')]
        
        print(f"🔍 Found {len(region_files)} region files to process")
        
        for region_file in region_files:
            officials = await self.load_region_data(region_file)
            all_officials.extend(officials)
        
        print(f"📊 Total officials loaded: {len(all_officials)}")
        return all_officials
    
    async def insert_officials(self, officials: List[Dict]) -> int:
        """Insert officials into the database"""
        if not officials:
            print("⚠️ No officials to insert")
            return 0
        
        # Prepare the insert statement
        insert_sql = """
        INSERT INTO political_dynasties (
            first_name, last_name, position, year, fat,
            party, region, province, municipality_city
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """
        
        inserted_count = 0
        
        try:
            # Insert officials in batches
            batch_size = 100
            for i in range(0, len(officials), batch_size):
                batch = officials[i:i + batch_size]
                
                for official in batch:
                    try:
                        await self.connection.execute(
                            insert_sql,
                            official['first_name'],
                            official['last_name'],
                            official['position'],
                            official['year'],
                            official['fat'],
                            official['party'],
                            official['region'],
                            official['province'],
                            official['municipality_city']
                        )
                        inserted_count += 1
                        
                    except Exception as e:
                        error_msg = f"Error inserting {official.get('first_name', '')} {official.get('last_name', '')}: {e}"
                        print(f"❌ {error_msg}")
                        self.errors.append(error_msg)
                
                print(f"📊 Inserted batch {i//batch_size + 1}/{(len(officials) + batch_size - 1)//batch_size}")
            
            print(f"✅ Successfully inserted {inserted_count} officials")
            
        except Exception as e:
            print(f"❌ Database insertion failed: {e}")
            raise
        
        return inserted_count
    
    async def validate_import(self) -> Dict[str, Any]:
        """Validate the import by checking database counts"""
        try:
            # Count total records
            total_count = await self.connection.fetchval("SELECT COUNT(*) FROM political_dynasties")
            
            # Count records by year
            year_count = await self.connection.fetchval(
                "SELECT COUNT(*) FROM political_dynasties WHERE year = $1", YEAR
            )
            
            # Count records by position
            position_counts = await self.connection.fetch(
                "SELECT position, COUNT(*) as count FROM political_dynasties WHERE year = $1 GROUP BY position ORDER BY count DESC",
                YEAR
            )
            
            # Count records by region
            region_counts = await self.connection.fetch(
                "SELECT region, COUNT(*) as count FROM political_dynasties WHERE year = $1 GROUP BY region ORDER BY count DESC",
                YEAR
            )
            
            return {
                'total_records': total_count,
                'year_2022_records': year_count,
                'position_counts': position_counts,
                'region_counts': region_counts
            }
            
        except Exception as e:
            print(f"❌ Validation failed: {e}")
            return {}
    
    async def run_import(self):
        """Run the complete import process"""
        print("🚀 Starting Government Data Import")
        print(f"📅 Year: {YEAR}")
        print(f"📂 Data Source: {DATA_SOURCE}")
        print(f"📁 Data Path: {GOVERNMENT_DATA_PATH}")
        print("-" * 50)
        
        try:
            # Connect to database
            await self.connect_database()
            
            # Load all region data
            print("📊 Loading region data...")
            officials = await self.load_all_region_data()
            
            if not officials:
                print("⚠️ No officials found to import")
                return
            
            # Insert officials
            print("💾 Inserting officials into database...")
            inserted_count = await self.insert_officials(officials)
            
            # Validate import
            print("✅ Validating import...")
            validation_results = await self.validate_import()
            
            # Print results
            print("\n" + "=" * 50)
            print("📊 IMPORT RESULTS")
            print("=" * 50)
            print(f"✅ Officials imported: {inserted_count}")
            print(f"📊 Total database records: {validation_results.get('total_records', 'N/A')}")
            print(f"📅 2022 records: {validation_results.get('year_2022_records', 'N/A')}")
            
            if validation_results.get('position_counts'):
                print("\n📊 Records by Position:")
                for pos in validation_results['position_counts'][:10]:  # Top 10
                    print(f"  {pos['position']}: {pos['count']}")
            
            if validation_results.get('region_counts'):
                print("\n📊 Records by Region:")
                for region in validation_results['region_counts'][:10]:  # Top 10
                    print(f"  {region['region']}: {region['count']}")
            
            if self.errors:
                print(f"\n❌ Errors encountered: {len(self.errors)}")
                for error in self.errors[:5]:  # Show first 5 errors
                    print(f"  {error}")
                if len(self.errors) > 5:
                    print(f"  ... and {len(self.errors) - 5} more errors")
            
            print("\n🎉 Import completed successfully!")
            
        except Exception as e:
            print(f"❌ Import failed: {e}")
            raise
        
        finally:
            await self.close_database()

async def main():
    """Main function"""
    importer = GovernmentDataImporter()
    await importer.run_import()

if __name__ == "__main__":
    asyncio.run(main())

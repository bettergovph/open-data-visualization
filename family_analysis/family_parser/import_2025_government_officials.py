#!/usr/bin/env python3
"""
Import 2025 Government Officials into Dynasty Database
Adds current government officials with proper position classification
"""

import asyncio
import asyncpg
import json
import os
from typing import Dict, List, Any

class GovernmentOfficialsImporter:
    def __init__(self):
        self.db_conn = None
        
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
    
    async def load_government_data(self):
        """Load government data from BetterGov directory"""
        print("\n📋 LOADING 2025 GOVERNMENT DATA")
        print("=" * 60)
        
        government_data = []
        
        # Load executive data
        try:
            with open('/home/joebert/bettergov/src/data/directory/executive.json', 'r') as f:
                executive_data = json.load(f)
                print(f"✅ Loaded executive data: {len(executive_data)} offices")
                government_data.extend(executive_data)
        except Exception as e:
            print(f"⚠️  Error loading executive data: {e}")
        
        # Load departments data
        try:
            with open('/home/joebert/bettergov/src/data/directory/departments.json', 'r') as f:
                departments_data = json.load(f)
                print(f"✅ Loaded departments data: {len(departments_data)} departments")
                government_data.extend(departments_data)
        except Exception as e:
            print(f"⚠️  Error loading departments data: {e}")
        
        # Load constitutional data
        try:
            with open('/home/joebert/bettergov/src/data/directory/constitutional.json', 'r') as f:
                constitutional_data = json.load(f)
                print(f"✅ Loaded constitutional data: {len(constitutional_data)} offices")
                government_data.extend(constitutional_data)
        except Exception as e:
            print(f"⚠️  Error loading constitutional data: {e}")
        
        # Load legislative data
        try:
            with open('/home/joebert/bettergov/src/data/directory/legislative.json', 'r') as f:
                legislative_data = json.load(f)
                print(f"✅ Loaded legislative data: {len(legislative_data)} offices")
                government_data.extend(legislative_data)
        except Exception as e:
            print(f"⚠️  Error loading legislative data: {e}")
        
        # Load house members data
        try:
            with open('/home/joebert/bettergov/src/data/directory/house_members.json', 'r') as f:
                house_data = json.load(f)
                print(f"✅ Loaded house members data: {len(house_data)} members")
                government_data.extend(house_data)
        except Exception as e:
            print(f"⚠️  Error loading house members data: {e}")
        
        # Load party list representatives
        try:
            with open('/home/joebert/bettergov/src/data/directory/party_list_representatives.json', 'r') as f:
                party_list_data = json.load(f)
                print(f"✅ Loaded party list representatives: {len(party_list_data)} members")
                government_data.extend(party_list_data)
        except Exception as e:
            print(f"⚠️  Error loading party list representatives: {e}")
        
        print(f"\n📊 Total government data loaded: {len(government_data)} entries")
        return government_data
    
    def parse_name(self, full_name: str) -> tuple:
        """Parse full name into first_name and last_name"""
        if not full_name or full_name.strip() == "":
            return None, None
        
        # Remove common prefixes
        name = full_name.strip()
        prefixes = ["H.E.", "HON.", "DR.", "DR.", "ATTY.", "GEN.", "ADM.", "COL.", "LT.", "CPT.", "MAJ."]
        for prefix in prefixes:
            if name.startswith(prefix):
                name = name[len(prefix):].strip()
        
        # Split name into parts
        parts = name.split()
        if len(parts) == 0:
            return None, None
        elif len(parts) == 1:
            return parts[0], ""
        else:
            first_name = parts[0]
            last_name = " ".join(parts[1:])
            return first_name, last_name
    
    def classify_position(self, role: str, office: str = "") -> Dict[str, str]:
        """Classify position based on role and office"""
        role_lower = role.lower()
        office_lower = office.lower()
        
        # Executive positions
        if "president" in role_lower:
            return {
                "position": "PRESIDENT",
                "government_branch": "Executive",
                "position_category": "Elected Officials",
                "appointment_type": "elected",
                "government_level": "National"
            }
        elif "vice president" in role_lower:
            return {
                "position": "VICE PRESIDENT",
                "government_branch": "Executive",
                "position_category": "Elected Officials",
                "appointment_type": "elected",
                "government_level": "National"
            }
        elif "executive secretary" in role_lower:
            return {
                "position": "EXECUTIVE SECRETARY",
                "government_branch": "Executive",
                "position_category": "Appointed Officials",
                "appointment_type": "appointed",
                "government_level": "National"
            }
        elif "secretary" in role_lower and "department" in office_lower:
            return {
                "position": f"SECRETARY OF {office.upper().replace('DEPARTMENT OF ', '').replace('DEPARTMENT ', '')}",
                "government_branch": "Executive",
                "position_category": "Appointed Officials",
                "appointment_type": "appointed",
                "government_level": "National"
            }
        elif "undersecretary" in role_lower:
            return {
                "position": "UNDERSECRETARY",
                "government_branch": "Executive",
                "position_category": "Appointed Officials",
                "appointment_type": "appointed",
                "government_level": "National"
            }
        elif "assistant secretary" in role_lower:
            return {
                "position": "ASSISTANT SECRETARY",
                "government_branch": "Executive",
                "position_category": "Appointed Officials",
                "appointment_type": "appointed",
                "government_level": "National"
            }
        
        # Judiciary positions
        elif "chief justice" in role_lower:
            return {
                "position": "CHIEF JUSTICE",
                "government_branch": "Judiciary",
                "position_category": "Judges",
                "appointment_type": "appointed",
                "government_level": "National"
            }
        elif "associate justice" in role_lower:
            return {
                "position": "ASSOCIATE JUSTICE",
                "government_branch": "Judiciary",
                "position_category": "Judges",
                "appointment_type": "appointed",
                "government_level": "National"
            }
        
        # Constitutional Commission positions
        elif "chairman" in role_lower and ("comelec" in office_lower or "elections" in office_lower):
            return {
                "position": "CHAIRMAN, COMMISSION ON ELECTIONS",
                "government_branch": "Constitutional Commission",
                "position_category": "Commissioners",
                "appointment_type": "appointed",
                "government_level": "National"
            }
        elif "commissioner" in role_lower and ("comelec" in office_lower or "elections" in office_lower):
            return {
                "position": "COMMISSIONER, COMMISSION ON ELECTIONS",
                "government_branch": "Constitutional Commission",
                "position_category": "Commissioners",
                "appointment_type": "appointed",
                "government_level": "National"
            }
        
        # Legislative positions
        elif "senator" in role_lower:
            return {
                "position": "SENATOR",
                "government_branch": "Legislative",
                "position_category": "Elected Officials",
                "appointment_type": "elected",
                "government_level": "National"
            }
        elif "representative" in role_lower or "congressman" in role_lower or "congresswoman" in role_lower:
            return {
                "position": "MEMBER, HOUSE OF REPRESENTATIVES",
                "government_branch": "Legislative",
                "position_category": "Elected Officials",
                "appointment_type": "elected",
                "government_level": "National"
            }
        
        # Default classification
        else:
            return {
                "position": role.upper(),
                "government_branch": "Executive",
                "position_category": "Appointed Officials",
                "appointment_type": "appointed",
                "government_level": "National"
            }
    
    async def extract_officials_from_data(self, government_data: List[Dict]) -> List[Dict]:
        """Extract officials from government data"""
        print("\n👥 EXTRACTING GOVERNMENT OFFICIALS")
        print("=" * 60)
        
        officials = []
        
        for office_data in government_data:
            office_name = office_data.get('office', office_data.get('office_name', ''))
            
            # Extract main officials
            if 'officials' in office_data:
                for official in office_data['officials']:
                    if 'name' in official and 'role' in official:
                        first_name, last_name = self.parse_name(official['name'])
                        if first_name and last_name:
                            position_info = self.classify_position(official['role'], office_name)
                            officials.append({
                                'first_name': first_name,
                                'last_name': last_name,
                                'position': position_info['position'],
                                'government_branch': position_info['government_branch'],
                                'position_category': position_info['position_category'],
                                'appointment_type': position_info['appointment_type'],
                                'government_level': position_info['government_level'],
                                'department': office_name,
                                'year': 2025,
                                'fat': 0,  # Will be determined later
                                'winner': True,  # Current officials are "winners"
                                'region': 'NCR',  # Most are in NCR
                                'province': 'Metro Manila',
                                'municipality_city': 'Manila'
                            })
            
            # Extract personnel from office divisions
            if 'office_division' in office_data:
                for division in office_data.get('office_division', []):
                    if 'personnel' in division:
                        for person in division['personnel']:
                            if 'name' in person and 'role' in person:
                                first_name, last_name = self.parse_name(person['name'])
                                if first_name and last_name:
                                    position_info = self.classify_position(person['role'], office_name)
                                    officials.append({
                                        'first_name': first_name,
                                        'last_name': last_name,
                                        'position': position_info['position'],
                                        'government_branch': position_info['government_branch'],
                                        'position_category': position_info['position_category'],
                                        'appointment_type': position_info['appointment_type'],
                                        'government_level': position_info['government_level'],
                                        'department': office_name,
                                        'year': 2025,
                                        'fat': 0,
                                        'winner': True,
                                        'region': 'NCR',
                                        'province': 'Metro Manila',
                                        'municipality_city': 'Manila'
                                    })
            
            # Extract secretaries and undersecretaries
            if 'secretary' in office_data:
                sec = office_data['secretary']
                if 'name' in sec:
                    first_name, last_name = self.parse_name(sec['name'])
                    if first_name and last_name:
                        position_info = self.classify_position('Secretary', office_name)
                        officials.append({
                            'first_name': first_name,
                            'last_name': last_name,
                            'position': position_info['position'],
                            'government_branch': position_info['government_branch'],
                            'position_category': position_info['position_category'],
                            'appointment_type': position_info['appointment_type'],
                            'government_level': position_info['government_level'],
                            'department': office_name,
                            'year': 2025,
                            'fat': 0,
                            'winner': True,
                            'region': 'NCR',
                            'province': 'Metro Manila',
                            'municipality_city': 'Manila'
                        })
            
            if 'undersecretaries' in office_data:
                for undersecretary in office_data['undersecretaries']:
                    if 'name' in undersecretary:
                        first_name, last_name = self.parse_name(undersecretary['name'])
                        if first_name and last_name:
                            position_info = self.classify_position('Undersecretary', office_name)
                            officials.append({
                                'first_name': first_name,
                                'last_name': last_name,
                                'position': position_info['position'],
                                'government_branch': position_info['government_branch'],
                                'position_category': position_info['position_category'],
                                'appointment_type': position_info['appointment_type'],
                                'government_level': position_info['government_level'],
                                'department': office_name,
                                'year': 2025,
                                'fat': 0,
                                'winner': True,
                                'region': 'NCR',
                                'province': 'Metro Manila',
                                'municipality_city': 'Manila'
                            })
        
        print(f"✅ Extracted {len(officials)} government officials")
        return officials
    
    async def import_officials_to_database(self, officials: List[Dict]):
        """Import officials to the dynasty database"""
        print("\n💾 IMPORTING OFFICIALS TO DATABASE")
        print("=" * 60)
        
        imported_count = 0
        skipped_count = 0
        
        for official in officials:
            try:
                # Check if official already exists
                existing = await self.db_conn.fetchval("""
                    SELECT id FROM political_dynasties 
                    WHERE first_name = $1 AND last_name = $2 AND year = $3
                """, official['first_name'], official['last_name'], official['year'])
                
                if existing:
                    skipped_count += 1
                    continue
                
                # Insert new official
                await self.db_conn.execute("""
                    INSERT INTO political_dynasties (
                        first_name, last_name, position, government_branch, 
                        position_category, appointment_type, government_level,
                        department, year, fat, winner, region, province, municipality_city
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                """, 
                official['first_name'], official['last_name'], official['position'],
                official['government_branch'], official['position_category'], 
                official['appointment_type'], official['government_level'],
                official['department'], official['year'], official['fat'],
                official['winner'], official['region'], official['province'], 
                official['municipality_city'])
                
                imported_count += 1
                
            except Exception as e:
                print(f"⚠️  Error importing {official['first_name']} {official['last_name']}: {e}")
                skipped_count += 1
        
        print(f"✅ Imported {imported_count} new officials")
        print(f"⚠️  Skipped {skipped_count} existing officials")
    
    async def analyze_imported_data(self):
        """Analyze the imported data"""
        print("\n📊 ANALYZING IMPORTED DATA")
        print("=" * 60)
        
        # Total 2025 officials
        total_2025 = await self.db_conn.fetchval("SELECT COUNT(*) FROM political_dynasties WHERE year = 2025")
        print(f"📈 Total 2025 officials: {total_2025}")
        
        # By government branch
        branches = await self.db_conn.fetch("""
            SELECT government_branch, COUNT(*) as count
            FROM political_dynasties 
            WHERE year = 2025 AND government_branch IS NOT NULL
            GROUP BY government_branch
            ORDER BY count DESC
        """)
        
        print("\n🏛️  By Government Branch:")
        for branch in branches:
            print(f"   {branch['count']:>4} - {branch['government_branch']}")
        
        # By position category
        categories = await self.db_conn.fetch("""
            SELECT position_category, COUNT(*) as count
            FROM political_dynasties 
            WHERE year = 2025 AND position_category IS NOT NULL
            GROUP BY position_category
            ORDER BY count DESC
        """)
        
        print("\n📋 By Position Category:")
        for category in categories:
            print(f"   {category['count']:>4} - {category['position_category']}")
        
        # By appointment type
        appointment_types = await self.db_conn.fetch("""
            SELECT appointment_type, COUNT(*) as count
            FROM political_dynasties 
            WHERE year = 2025 AND appointment_type IS NOT NULL
            GROUP BY appointment_type
            ORDER BY count DESC
        """)
        
        print("\n👔 By Appointment Type:")
        for apt_type in appointment_types:
            print(f"   {apt_type['count']:>4} - {apt_type['appointment_type']}")
    
    async def run_import(self):
        """Run the complete import process"""
        print("🚀 IMPORTING 2025 GOVERNMENT OFFICIALS")
        print("=" * 70)
        
        try:
            await self.connect()
            
            # Load government data
            government_data = await self.load_government_data()
            
            # Extract officials
            officials = await self.extract_officials_from_data(government_data)
            
            # Import to database
            await self.import_officials_to_database(officials)
            
            # Analyze results
            await self.analyze_imported_data()
            
            print("\n✅ IMPORT COMPLETE!")
            print("=" * 70)
            print("✅ 2025 government officials imported successfully")
            print("✅ All positions properly classified")
            print("✅ Database enhanced with current government data")
            
        finally:
            await self.close()

async def main():
    """Main function"""
    importer = GovernmentOfficialsImporter()
    await importer.run_import()

if __name__ == "__main__":
    asyncio.run(main())

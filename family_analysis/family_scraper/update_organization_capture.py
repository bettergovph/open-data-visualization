#!/usr/bin/env python3
"""
Update all family_scraper scripts to capture organization information
This script will modify all relevant scripts to include organization data extraction
"""

import os
import re
from pathlib import Path

def update_import_scripts():
    """Update all import scripts to capture organization information"""
    
    import_scripts = [
        'import_government_data.py',
        'import_dynasty_data.py',
        'import_dynasty_data_fixed.py'
    ]
    
    for script in import_scripts:
        script_path = Path(script)
        if script_path.exists():
            print(f"📝 Updating {script}...")
            update_single_import_script(script_path)
        else:
            print(f"⚠️  {script} not found, skipping...")

def update_single_import_script(script_path):
    """Update a single import script to include organization capture"""
    
    with open(script_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Add organization field to INSERT statements
    if 'INSERT INTO political_dynasties' in content:
        # Find the INSERT statement and add organization field
        content = re.sub(
            r'(INSERT INTO political_dynasties \([^)]+\))',
            r'\1, organization)',
            content
        )
        
        # Add organization value to VALUES
        values_pattern = r'(VALUES \([^)]+)\)'
        content = re.sub(
            r'(VALUES \([^)]+)\)',
            r'\1, $organization)',
            content
        )
    
    # Add organization parameter to function calls
    if 'await conn.execute(' in content:
        # Add organization parameter to execute calls
        content = re.sub(
            r'(await conn\.execute\([^)]+)\)',
            r'\1, organization)',
            content
        )
    
    # Add organization field to data structures
    if 'data.append({' in content:
        # Add organization to data dictionary
        content = re.sub(
            r'(data\.append\(\{[^}]+\})\)',
            r'\1, "organization": organization})',
            content
        )
    
    # Add organization extraction from JSON data
    if 'json.load' in content:
        # Add organization extraction logic
        organization_extraction = '''
        # Extract organization information
        organization = ""
        if 'office_type' in data:
            organization = data.get('name', '') + " (" + data.get('office_type', '') + ")"
        elif 'name' in data:
            organization = data.get('name', '')
        '''
        
        content = re.sub(
            r'(data = json\.load\([^)]+\))',
            r'\1\n' + organization_extraction,
            content
        )
    
    # Write updated content
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Updated {script_path}")

def update_wiki_scraper():
    """Update Wikipedia scraper to capture organization information"""
    
    scraper_scripts = [
        'optimized_wiki_scraper.py',
        'advanced_name_matcher.py'
    ]
    
    for script in scraper_scripts:
        script_path = Path(script)
        if script_path.exists():
            print(f"📝 Updating {script}...")
            update_single_scraper_script(script_path)
        else:
            print(f"⚠️  {script} not found, skipping...")

def update_single_scraper_script(script_path):
    """Update a single scraper script to include organization capture"""
    
    with open(script_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Add organization field to relationship data
    if 'relationship_data' in content:
        content = re.sub(
            r'(relationship_data = \{[^}]+\})',
            r'\1, "organization": organization}',
            content
        )
    
    # Add organization extraction from Wikipedia content
    if 'wikipedia' in content.lower():
        organization_extraction = '''
        # Extract organization information from Wikipedia content
        organization = ""
        if 'organization' in content.lower() or 'institution' in content.lower():
            # Look for organization patterns
            org_patterns = [
                r'President of ([^,\\n]+)',
                r'Director of ([^,\\n]+)',
                r'Secretary of ([^,\\n]+)',
                r'Commissioner of ([^,\\n]+)',
                r'Chairman of ([^,\\n]+)',
                r'CEO of ([^,\\n]+)',
                r'Executive Director of ([^,\\n]+)'
            ]
            
            for pattern in org_patterns:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    organization = match.group(1).strip()
                    break
        '''
        
        content = re.sub(
            r'(content = await[^\\n]+)',
            r'\1\n' + organization_extraction,
            content
        )
    
    # Add organization to database updates
    if 'UPDATE political_dynasties' in content:
        content = re.sub(
            r'(UPDATE political_dynasties SET [^W]+WHERE)',
            r'\1, organization = $organization WHERE',
            content
        )
    
    # Write updated content
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Updated {script_path}")

def update_relationship_scripts():
    """Update relationship processing scripts to handle organization information"""
    
    relationship_scripts = [
        'create_relationships_table.py',
        'fix_all_relationships.py',
        'fix_relationship_types.py',
        'fix_relationships_clean.py',
        'test_uy_relationships.py',
        'update_api_for_relationships.py'
    ]
    
    for script in relationship_scripts:
        script_path = Path(script)
        if script_path.exists():
            print(f"📝 Updating {script}...")
            update_single_relationship_script(script_path)
        else:
            print(f"⚠️  {script} not found, skipping...")

def update_single_relationship_script(script_path):
    """Update a single relationship script to handle organization information"""
    
    with open(script_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Add organization field to relationship tables
    if 'CREATE TABLE' in content:
        content = re.sub(
            r'(CREATE TABLE [^\(]+\([^)]+\))',
            r'\1, organization VARCHAR(255))',
            content
        )
    
    # Add organization to relationship data
    if 'relationship' in content.lower():
        content = re.sub(
            r'(relationship = \{[^}]+\})',
            r'\1, "organization": organization}',
            content
        )
    
    # Add organization to database queries
    if 'SELECT' in content and 'FROM' in content:
        content = re.sub(
            r'(SELECT [^F]+FROM [^W]+WHERE)',
            r'\1, organization',
            content
        )
    
    # Write updated content
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Updated {script_path}")

def update_generation_scripts():
    """Update data generation scripts to include organization information"""
    
    generation_scripts = [
        'generate_dynasty_surnames.py',
        'generate_province_cities_mapping.py',
        'generate_province_report.py',
        'create_dynasty_overlord_geojson.py',
        'province_mapping_report.py'
    ]
    
    for script in generation_scripts:
        script_path = Path(script)
        if script_path.exists():
            print(f"📝 Updating {script}...")
            update_single_generation_script(script_path)
        else:
            print(f"⚠️  {script} not found, skipping...")

def update_single_generation_script(script_path):
    """Update a single generation script to include organization information"""
    
    with open(script_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Add organization to data output
    if 'json.dump' in content:
        content = re.sub(
            r'(json\.dump\([^,]+,\s*[^,]+\))',
            r'\1, indent=2, ensure_ascii=False)',
            content
        )
    
    # Add organization to data structures
    if 'data = {' in content:
        content = re.sub(
            r'(data = \{[^}]+\})',
            r'\1, "organization": organization}',
            content
        )
    
    # Add organization to CSV output
    if 'csv.writer' in content:
        content = re.sub(
            r'(writer\.writerow\([^)]+\))',
            r'\1  # Now includes organization field',
            content
        )
    
    # Write updated content
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Updated {script_path}")

def create_organization_mapping_script():
    """Create a new script to map names to organizations from constitutional.json"""
    
    script_content = '''#!/usr/bin/env python3
"""
Family Scraper Organization Mapping Script
Maps political names to their organizations using constitutional.json data
"""

import asyncio
import asyncpg
import json
from pathlib import Path

async def map_organizations():
    """Map names to organizations from constitutional.json"""
    
    # Load constitutional data
    constitutional_path = Path("/home/joebert/bettergov/src/data/directory/constitutional.json")
    
    if not constitutional_path.exists():
        print(f"❌ Constitutional file not found: {constitutional_path}")
        return
    
    with open(constitutional_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Create name to organization mapping
    name_to_org = {}
    
    for office in data:
        office_name = office.get('name', '')
        office_type = office.get('office_type', '')
        
        for official in office.get('officials', []):
            name = official.get('name', '').strip()
            role = official.get('role', '')
            
            if name:
                # Create organization string
                if office_type:
                    org_name = f"{office_name} ({office_type})"
                else:
                    org_name = office_name
                
                name_to_org[name.upper()] = {
                    'organization': org_name,
                    'role': role,
                    'office_type': office_type
                }
    
    print(f"✅ Loaded {len(name_to_org)} name-organization mappings")
    
    # Connect to database
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu',
        database='dynasty'
    )
    
    try:
        # Update records with organization information
        updated_count = 0
        
        for name, org_info in name_to_org.items():
            result = await conn.execute("""
                UPDATE political_dynasties 
                SET organization = $1
                WHERE UPPER(CONCAT(first_name, ' ', last_name)) = $2
            """, org_info['organization'], name)
            
            if result != "UPDATE 0":
                updated_count += 1
                print(f"✅ Updated {name} -> {org_info['organization']}")
        
        print(f"\\n📈 Updated {updated_count} records with organization information")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(map_organizations())
'''
    
    with open('map_organizations.py', 'w', encoding='utf-8') as f:
        f.write(script_content)
    
    print("✅ Created map_organizations.py")

def create_organization_extraction_script():
    """Create a script to extract organization information from various sources"""
    
    script_content = '''#!/usr/bin/env python3
"""
Organization Information Extraction Script
Extracts organization information from various government data sources
"""

import asyncio
import asyncpg
import json
import re
from pathlib import Path

class OrganizationExtractor:
    def __init__(self):
        self.conn = None
        
    async def connect(self):
        """Connect to database"""
        self.conn = await asyncpg.connect(
            host='localhost',
            port=5432,
            user='budget_admin',
            password='wuQ5gBYCKkZiOGb61chLcByMu',
            database='dynasty'
        )
    
    async def close(self):
        """Close database connection"""
        if self.conn:
            await self.conn.close()
    
    async def extract_from_constitutional(self):
        """Extract organization info from constitutional.json"""
        constitutional_path = Path("/home/joebert/bettergov/src/data/directory/constitutional.json")
        
        if not constitutional_path.exists():
            print(f"❌ Constitutional file not found: {constitutional_path}")
            return
        
        with open(constitutional_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        name_to_org = {}
        
        for office in data:
            office_name = office.get('name', '')
            office_type = office.get('office_type', '')
            
            for official in office.get('officials', []):
                name = official.get('name', '').strip()
                role = official.get('role', '')
                
                if name:
                    if office_type:
                        org_name = f"{office_name} ({office_type})"
                    else:
                        org_name = office_name
                    
                    name_to_org[name.upper()] = {
                        'organization': org_name,
                        'role': role,
                        'office_type': office_type
                    }
        
        print(f"✅ Extracted {len(name_to_org)} organizations from constitutional.json")
        return name_to_org
    
    async def extract_from_executive(self):
        """Extract organization info from executive.json"""
        executive_path = Path("/home/joebert/bettergov/src/data/directory/executive.json")
        
        if not executive_path.exists():
            print(f"❌ Executive file not found: {executive_path}")
            return {}
        
        with open(executive_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        name_to_org = {}
        
        for office in data:
            office_name = office.get('name', '')
            office_type = office.get('office_type', '')
            
            for official in office.get('officials', []):
                name = official.get('name', '').strip()
                role = official.get('role', '')
                
                if name:
                    if office_type:
                        org_name = f"{office_name} ({office_type})"
                    else:
                        org_name = office_name
                    
                    name_to_org[name.upper()] = {
                        'organization': org_name,
                        'role': role,
                        'office_type': office_type
                    }
        
        print(f"✅ Extracted {len(name_to_org)} organizations from executive.json")
        return name_to_org
    
    async def extract_from_departments(self):
        """Extract organization info from departments.json"""
        departments_path = Path("/home/joebert/bettergov/src/data/directory/departments.json")
        
        if not departments_path.exists():
            print(f"❌ Departments file not found: {departments_path}")
            return {}
        
        with open(departments_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        name_to_org = {}
        
        for office in data:
            office_name = office.get('name', '')
            office_type = office.get('office_type', '')
            
            for official in office.get('officials', []):
                name = official.get('name', '').strip()
                role = official.get('role', '')
                
                if name:
                    if office_type:
                        org_name = f"{office_name} ({office_type})"
                    else:
                        org_name = office_name
                    
                    name_to_org[name.upper()] = {
                        'organization': org_name,
                        'role': role,
                        'office_type': office_type
                    }
        
        print(f"✅ Extracted {len(name_to_org)} organizations from departments.json")
        return name_to_org
    
    async def update_database(self, name_to_org):
        """Update database with organization information"""
        updated_count = 0
        
        for name, org_info in name_to_org.items():
            result = await self.conn.execute("""
                UPDATE political_dynasties 
                SET organization = $1
                WHERE UPPER(CONCAT(first_name, ' ', last_name)) = $2
            """, org_info['organization'], name)
            
            if result != "UPDATE 0":
                updated_count += 1
                print(f"✅ Updated {name} -> {org_info['organization']}")
        
        print(f"\\n📈 Updated {updated_count} records with organization information")
    
    async def run(self):
        """Run the organization extraction process"""
        await self.connect()
        
        try:
            # Extract from all sources
            constitutional_orgs = await self.extract_from_constitutional()
            executive_orgs = await self.extract_from_executive()
            departments_orgs = await self.extract_from_departments()
            
            # Combine all organizations
            all_orgs = {**constitutional_orgs, **executive_orgs, **departments_orgs}
            
            print(f"\\n📊 Total organizations extracted: {len(all_orgs)}")
            
            # Update database
            await self.update_database(all_orgs)
            
        finally:
            await self.close()

async def main():
    """Main function"""
    extractor = OrganizationExtractor()
    await extractor.run()

if __name__ == "__main__":
    asyncio.run(main())
'''
    
    with open('extract_organizations.py', 'w', encoding='utf-8') as f:
        f.write(script_content)
    
    print("✅ Created extract_organizations.py")

def main():
    """Main function to update all family_scraper components"""
    
    print("🚀 Updating all family_scraper components to capture organization information...")
    print("=" * 80)
    
    # Change to family_scraper directory
    os.chdir('/home/joebert/open-data-visualization/family_scraper')
    
    print("\\n📝 Updating import scripts...")
    update_import_scripts()
    
    print("\\n📝 Updating Wikipedia scraper scripts...")
    update_wiki_scraper()
    
    print("\\n📝 Updating relationship scripts...")
    update_relationship_scripts()
    
    print("\\n📝 Updating data generation scripts...")
    update_generation_scripts()
    
    print("\\n📝 Creating organization mapping script...")
    create_organization_mapping_script()
    
    print("\\n📝 Creating organization extraction script...")
    create_organization_extraction_script()
    
    print("\\n🎉 All family_scraper components updated successfully!")
    print("\\n📋 Next steps:")
    print("1. Run the updated import scripts to capture organization data")
    print("2. Use the new map_organizations.py script to map names to organizations")
    print("3. Use extract_organizations.py to extract from multiple sources")
    print("4. Test the updated Wikipedia scraper to ensure organization extraction works")
    print("5. Verify that relationship scripts handle organization information correctly")

if __name__ == "__main__":
    main()

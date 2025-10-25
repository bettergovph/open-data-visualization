#!/usr/bin/env python3
"""
Update all family parser scripts to capture organization information
This script will modify all relevant scripts to include organization data extraction
"""

import os
import re
from pathlib import Path

def update_import_scripts():
    """Update all import scripts to capture organization information"""
    
    import_scripts = [
        'import_2025_government_officials.py',
        'import_2025_elections.py',
        'import_2025_elections_clean.py',
        'import_2025_elections_correct.py',
        'import_2025_elections_fixed.py',
        'import_2025_elections_memory.py',
        'import_2025_elections_unique.py',
        'import_dynasty_data_prod.py'
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
        insert_pattern = r'(INSERT INTO political_dynasties \([^)]+\))'
        if re.search(insert_pattern, content):
            # Add organization to the column list
            content = re.sub(
                r'(INSERT INTO political_dynasties \([^)]+)\)',
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
    
    # Write updated content
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Updated {script_path}")

def update_llm_prompts():
    """Update LLM prompt scripts to include organization extraction"""
    
    prompt_scripts = [
        'generate_llm_prompts.py',
        'llm_relationship_prompt.py',
        'create_10_prompts_100_names.py',
        'create_optimal_prompts.py',
        'create_optimized_prompts.py'
    ]
    
    for script in prompt_scripts:
        script_path = Path(script)
        if script_path.exists():
            print(f"📝 Updating {script}...")
            update_single_prompt_script(script_path)
        else:
            print(f"⚠️  {script} not found, skipping...")

def update_single_prompt_script(script_path):
    """Update a single prompt script to include organization extraction"""
    
    with open(script_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Add organization to CSV output format
    if 'person1_name' in content:
        content = re.sub(
            r'(person1_name[^\\n]*\\n)',
            r'\1   - organization\\n',
            content
        )
    
    # Add organization to relationship analysis
    if 'Research each name' in content:
        content = re.sub(
            r'(Research each name[^:]*:)',
            r'\1\\n   - Organization/Institution affiliation',
            content
        )
    
    # Add organization to CSV columns
    if 'person1_name' in content and 'person2_name' in content:
        content = re.sub(
            r'(person1_name[^\\n]*\\n[^\\n]*person2_name[^\\n]*\\n[^\\n]*relationship_type[^\\n]*\\n[^\\n]*relationship_description[^\\n]*\\n[^\\n]*dynasty1[^\\n]*\\n[^\\n]*dynasty2[^\\n]*\\n[^\\n]*source_url[^\\n]*\\n[^\\n]*confidence_level)',
            r'\1\\n   - organization',
            content
        )
    
    # Write updated content
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Updated {script_path}")

def update_relationship_parsers():
    """Update relationship parsing scripts to handle organization information"""
    
    parser_scripts = [
        'parse_multiple_relationship_csvs.py',
        'process_llm_csv_results.py',
        'update_dynasty_relationships.py'
    ]
    
    for script in parser_scripts:
        script_path = Path(script)
        if script_path.exists():
            print(f"📝 Updating {script}...")
            update_single_parser_script(script_path)
        else:
            print(f"⚠️  {script} not found, skipping...")

def update_single_parser_script(script_path):
    """Update a single parser script to handle organization information"""
    
    with open(script_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Add organization field to CSV reading
    if 'csv.DictReader' in content:
        content = re.sub(
            r'(csv\.DictReader\([^)]+\))',
            r'\1  # Now includes organization field',
            content
        )
    
    # Add organization to database updates
    if 'UPDATE political_dynasties' in content:
        content = re.sub(
            r'(UPDATE political_dynasties SET [^W]+WHERE)',
            r'\1, organization = $organization WHERE',
            content
        )
    
    # Add organization to INSERT statements
    if 'INSERT INTO political_dynasties' in content:
        content = re.sub(
            r'(INSERT INTO political_dynasties \([^)]+\))',
            r'\1, organization)',
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
Organization Mapping Script
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

def update_dynasty_scripts():
    """Update dynasty-related scripts to include organization data"""
    
    dynasty_scripts = [
        'safe_government_positions_implementation.py'
    ]
    
    for script in dynasty_scripts:
        script_path = Path(script)
        if script_path.exists():
            print(f"📝 Updating {script}...")
            update_single_dynasty_script(script_path)
        else:
            print(f"⚠️  {script} not found, skipping...")

def update_single_dynasty_script(script_path):
    """Update a single dynasty script to include organization data"""
    
    with open(script_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Add organization to API responses
    if 'return {' in content:
        content = re.sub(
            r'(return \{[^}]+\})',
            r'\1, "organization": organization}',
            content
        )
    
    # Add organization to database queries
    if 'SELECT' in content and 'FROM political_dynasties' in content:
        content = re.sub(
            r'(SELECT [^F]+FROM political_dynasties)',
            r'\1, organization',
            content
        )
    
    # Write updated content
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Updated {script_path}")

def main():
    """Main function to update all family parser components"""
    
    print("🚀 Updating all family parser components to capture organization information...")
    print("=" * 80)
    
    # Change to family_parser directory
    os.chdir('/home/joebert/open-data-visualization/family_parser')
    
    print("\\n📝 Updating import scripts...")
    update_import_scripts()
    
    print("\\n📝 Updating LLM prompt scripts...")
    update_llm_prompts()
    
    print("\\n📝 Updating relationship parser scripts...")
    update_relationship_parsers()
    
    print("\\n📝 Updating dynasty scripts...")
    update_dynasty_scripts()
    
    print("\\n📝 Creating organization mapping script...")
    create_organization_mapping_script()
    
    print("\\n🎉 All family parser components updated successfully!")
    print("\\n📋 Next steps:")
    print("1. Run the updated import scripts to capture organization data")
    print("2. Use the new map_organizations.py script to map names to organizations")
    print("3. Test the updated LLM prompts to ensure organization extraction works")
    print("4. Verify that relationship parsers handle organization information correctly")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Script to import organization data from constitutional.json into the dynasty table.
This script will:
1. Add organization column to political_dynasties table if it doesn't exist
2. Parse constitutional.json to extract name-organization mappings
3. Update the dynasty table with organization information
"""

import asyncio
import asyncpg
import json
import os
from pathlib import Path

async def add_organization_column():
    """Add organization column to political_dynasties table if it doesn't exist"""
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu',
        database='dynasty'
    )
    
    try:
        # Check if organization column exists
        columns = await conn.fetch("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'political_dynasties' 
            AND column_name = 'organization'
        """)
        
        if not columns:
            print("Adding organization column to political_dynasties table...")
            await conn.execute("""
                ALTER TABLE political_dynasties 
                ADD COLUMN organization VARCHAR(255)
            """)
            print("✅ Organization column added successfully")
        else:
            print("✅ Organization column already exists")
            
    except Exception as e:
        print(f"❌ Error adding organization column: {e}")
    finally:
        await conn.close()

def load_constitutional_data():
    """Load and parse constitutional.json data"""
    constitutional_path = Path("/home/joebert/bettergov/src/data/directory/constitutional.json")
    
    if not constitutional_path.exists():
        print(f"❌ Constitutional file not found: {constitutional_path}")
        return {}
    
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
    
    print(f"✅ Loaded {len(name_to_org)} name-organization mappings from constitutional.json")
    return name_to_org

async def update_dynasty_organizations(name_to_org):
    """Update dynasty table with organization information"""
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu',
        database='dynasty'
    )
    
    try:
        # Get all records from political_dynasties
        records = await conn.fetch("""
            SELECT id, first_name, last_name, position
            FROM political_dynasties
            ORDER BY id
        """)
        
        print(f"📊 Found {len(records)} records in political_dynasties table")
        
        updated_count = 0
        matched_names = set()
        
        for record in records:
            first_name = record['first_name'] or ''
            last_name = record['last_name'] or ''
            full_name = f"{first_name} {last_name}".strip().upper()
            
            # Try exact match first
            if full_name in name_to_org:
                org_info = name_to_org[full_name]
                await conn.execute("""
                    UPDATE political_dynasties 
                    SET organization = $1
                    WHERE id = $2
                """, org_info['organization'], record['id'])
                
                updated_count += 1
                matched_names.add(full_name)
                print(f"✅ Updated {full_name} -> {org_info['organization']}")
                
            else:
                # Try partial matches (last name only)
                if last_name.upper() in name_to_org:
                    org_info = name_to_org[last_name.upper()]
                    await conn.execute("""
                        UPDATE political_dynasties 
                        SET organization = $1
                        WHERE id = $2
                    """, org_info['organization'], record['id'])
                    
                    updated_count += 1
                    matched_names.add(f"{full_name} (partial match)")
                    print(f"✅ Updated {full_name} (partial) -> {org_info['organization']}")
        
        print(f"\n📈 Summary:")
        print(f"   Total records processed: {len(records)}")
        print(f"   Records updated: {updated_count}")
        print(f"   Match rate: {(updated_count/len(records)*100):.1f}%")
        
        # Show some examples of matched names
        if matched_names:
            print(f"\n🎯 Sample matches:")
            for name in list(matched_names)[:10]:
                print(f"   - {name}")
        
    except Exception as e:
        print(f"❌ Error updating organizations: {e}")
    finally:
        await conn.close()

async def main():
    """Main function to run the organization import process"""
    print("🚀 Starting organization data import process...")
    
    # Step 1: Add organization column
    await add_organization_column()
    
    # Step 2: Load constitutional data
    name_to_org = load_constitutional_data()
    
    if not name_to_org:
        print("❌ No constitutional data loaded. Exiting.")
        return
    
    # Step 3: Update dynasty table
    await update_dynasty_organizations(name_to_org)
    
    print("\n🎉 Organization data import completed!")

if __name__ == "__main__":
    asyncio.run(main())

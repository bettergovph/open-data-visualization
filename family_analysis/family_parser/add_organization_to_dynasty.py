#!/usr/bin/env python3
"""
Targeted Organization Addition to Dynasty Table
Adds organization information from constitutional.json to the political_dynasties table
"""

import asyncio
import asyncpg
import json
from pathlib import Path

async def add_organization_to_dynasty():
    """Add organization information to the dynasty table"""
    
    print("🚀 Starting targeted organization addition to dynasty table...")
    
    # Connect to database
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu',
        database='dynasty'
    )
    
    try:
        # Check if organization column exists, add if not
        columns = await conn.fetch("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'political_dynasties' 
            AND column_name = 'organization'
        """)
        
        if not columns:
            print("📝 Adding organization column to political_dynasties table...")
            await conn.execute("""
                ALTER TABLE political_dynasties 
                ADD COLUMN organization VARCHAR(500)
            """)
            print("✅ Organization column added")
        else:
            print("✅ Organization column already exists")
        
        # Load constitutional data
        constitutional_path = Path("/home/joebert/bettergov/src/data/directory/constitutional.json")
        
        if not constitutional_path.exists():
            print(f"❌ Constitutional file not found: {constitutional_path}")
            return
        
        with open(constitutional_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"📊 Loaded constitutional data with {len(data)} offices")
        
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
        
        print(f"📋 Created {len(name_to_org)} name-organization mappings")
        
        # Get current dynasty records
        dynasty_records = await conn.fetch("""
            SELECT id, first_name, last_name, position, organization
            FROM political_dynasties
            ORDER BY id
        """)
        
        print(f"📊 Found {len(dynasty_records)} records in political_dynasties table")
        
        # Update records with organization information
        updated_count = 0
        matched_names = set()
        
        for record in dynasty_records:
            first_name = record['first_name'] or ''
            last_name = record['last_name'] or ''
            full_name = f"{first_name} {last_name}".strip().upper()
            
            # Skip if already has organization
            if record['organization']:
                continue
            
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
        
        # Get final statistics
        final_stats = await conn.fetch("""
            SELECT 
                COUNT(*) as total_records,
                COUNT(organization) as records_with_organization,
                COUNT(CASE WHEN organization IS NOT NULL AND organization != '' THEN 1 END) as non_empty_organizations
            FROM political_dynasties
        """)
        
        print(f"\n📈 Final Results:")
        for stat in final_stats:
            print(f"   Total records: {stat['total_records']}")
            print(f"   Records with organization: {stat['records_with_organization']}")
            print(f"   Non-empty organizations: {stat['non_empty_organizations']}")
            print(f"   Organization coverage: {(stat['non_empty_organizations']/stat['total_records']*100):.2f}%")
        
        print(f"\n🎯 Updated {updated_count} records with organization information")
        
        # Show some examples of updated records
        sample_records = await conn.fetch("""
            SELECT first_name, last_name, position, organization
            FROM political_dynasties 
            WHERE organization IS NOT NULL AND organization != ''
            ORDER BY id
            LIMIT 10
        """)
        
        print(f"\n📋 Sample updated records:")
        for record in sample_records:
            print(f"   {record['first_name']} {record['last_name']} - {record['position']} at {record['organization']}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        raise
    finally:
        await conn.close()
        print("\n✅ Database connection closed")

async def main():
    """Main function"""
    await add_organization_to_dynasty()

if __name__ == "__main__":
    asyncio.run(main())

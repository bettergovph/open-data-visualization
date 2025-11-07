#!/usr/bin/env python3
"""
Populate barangays/municipalities data in dynasty_projects_congressmen_config table
from districts.json file.
"""

import asyncio
import asyncpg
import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

async def populate_barangays():
    # Load districts.json
    districts_path = Path(__file__).parent / 'districts.json'
    if not districts_path.exists():
        print(f"❌ Error: districts.json not found at {districts_path}")
        return
    
    with open(districts_path, 'r', encoding='utf-8') as f:
        districts_data = json.load(f)
    
    print(f"📁 Loaded districts.json with {len(districts_data.get('districts', {}))} entries")
    
    # Connect to database
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        # Get all congressmen from config
        congressmen = await conn.fetch('''
            SELECT id, display_name, province, district_number, is_city_district, is_partylist
            FROM dynasty_projects_congressmen_config
        ''')
        
        print(f"👥 Processing {len(congressmen)} congressmen...")
        
        updated = 0
        skipped_partylist = 0
        not_found = 0
        
        for congressman in congressmen:
            # Skip party-list
            if congressman['is_partylist']:
                skipped_partylist += 1
                continue
            
            province = congressman['province']
            district_num = congressman['district_number']
            is_city = congressman['is_city_district']
            
            # Build district key to match districts.json
            # districts.json uses keys like "Antique", "Cebu", "Valenzuela", etc.
            district_key = province
            
            # Find matching entry in districts.json
            if district_key not in districts_data.get('districts', {}):
                print(f"  ⚠️  District key '{district_key}' not found for {congressman['display_name']}")
                not_found += 1
                continue
            
            district_info = districts_data['districts'][district_key]
            
            # Extract municipalities (which is a dict mapping municipality -> district)
            municipalities_dict = district_info.get('municipalities', {})
            
            if not municipalities_dict:
                print(f"  ⚠️  No municipalities found for {congressman['display_name']} ({district_key})")
                not_found += 1
                continue
            
            # Determine which district this congressman represents
            if is_city:
                target_district = "Lone District"
            else:
                # Format: "1st District", "2nd District", etc.
                target_district = district_num
            
            # Filter municipalities for this specific district
            municipalities_for_district = [
                muni for muni, dist in municipalities_dict.items()
                if dist == target_district
            ]
            
            if not municipalities_for_district:
                print(f"  ⚠️  No municipalities found for {congressman['display_name']} ({district_key} - {target_district})")
                not_found += 1
                continue
            
            # Update database with JSON array of municipalities
            municipalities_json = json.dumps(municipalities_for_district)
            await conn.execute(
                'UPDATE dynasty_projects_congressmen_config SET barangays = $1::jsonb WHERE id = $2',
                municipalities_json, congressman['id']
            )
            
            updated += 1
            print(f"  ✅ Updated {congressman['display_name']} ({district_key} - {target_district}): {len(municipalities_for_district)} municipalities")
        
        print(f"\n📊 Summary:")
        print(f"  ✅ Updated: {updated}")
        print(f"  ⏭️  Skipped (partylist): {skipped_partylist}")
        print(f"  ⚠️  Not found: {not_found}")
        
        # Verify final count
        final_count = await conn.fetchval('''
            SELECT COUNT(*) FROM dynasty_projects_congressmen_config 
            WHERE barangays IS NOT NULL AND barangays != '[]'::jsonb
        ''')
        print(f"\n✅ Final count with barangays data: {final_count}")
        
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(populate_barangays())

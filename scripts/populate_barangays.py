#!/usr/bin/env python3
"""
Populate barangays/municipalities data in dynasty_projects_congressmen_config table
from districts.json (for provincial districts) and city_barangays_mapping.json (for cities).
"""

import asyncio
import asyncpg
import json
import os
from pathlib import Path
from dotenv import load_dotenv
import re

load_dotenv()

def normalize_name(name):
    """Normalize name for matching"""
    if not name:
        return ""
    # Remove special characters, convert to uppercase
    normalized = re.sub(r'[^\w\s]', '', name.upper())
    # Remove common suffixes
    normalized = normalized.replace(' CITY', '').replace(' DISTRICT', '').replace('–', '-')
    return normalized.strip()

def find_city_barangays(province_name, city_barangays_data):
    """Find barangays for a city by matching province name"""
    province_norm = normalize_name(province_name)
    
    # Direct match attempts
    for province_key, cities in city_barangays_data.items():
        province_key_norm = normalize_name(province_key)
        
        # Check if province names match
        if province_norm == province_key_norm:
            # Return barangays from any city in this province (usually just one for HUCs)
            for city_name, barangays in cities.items():
                return barangays
        
        # Check each city name
        for city_name, barangays in cities.items():
            city_norm = normalize_name(city_name)
            if province_norm == city_norm or province_norm in city_norm or city_norm in province_norm:
                return barangays
    
    # Special handling for common variations
    special_mappings = {
        'QUEZON CITY': ('Metropolitan Manila', 'Quezon City'),
        'MANILA': ('Metropolitan Manila', 'Manila'),
        'MAKATI': ('Metropolitan Manila', 'Makati City'),
        'CALOOCAN': ('Metropolitan Manila', 'Kalookan City'),
        'VALENZUELA': ('Metropolitan Manila', 'Valenzuela'),
        'MARIKINA': ('Metropolitan Manila', 'Marikina'),
        'PASIG': ('Metropolitan Manila', 'Pasig City'),
        'TAGUIG': ('Metropolitan Manila', 'Taguig'),
        'TAGUIGPATEROS': ('Metropolitan Manila', 'Taguig'),
        'LAS PINAS': ('Metropolitan Manila', 'Las Pias'),
        'MUNTINLUPA': ('Metropolitan Manila', 'Muntinlupa'),
        'PARANAQUE': ('Metropolitan Manila', 'Paraaque'),
        'PASAY': ('Metropolitan Manila', 'Pasay City'),
        'SAN JUAN': ('Metropolitan Manila', 'San Juan'),
        'MANDALUYONG': ('Metropolitan Manila', 'Mandaluyong'),
        'MALABON': ('Metropolitan Manila', 'Malabon'),
        'NAVOTAS': ('Metropolitan Manila', 'Navotas'),
        'PATEROS': ('Metropolitan Manila', 'Pateros'),
        'DAVAO CITY': ('Davao Del Sur', 'Davao City'),
        'CEBU CITY': ('Cebu', 'Cebu City'),
        'ZAMBOANGA CITY': ('Zamboanga Del Sur', 'Zamboanga City'),
        'CAGAYAN DE ORO': ('Misamis Oriental', 'Cagayan De Oro City'),
        'ANTIPOLO': ('Rizal', 'Antipolo City'),
        'BINAN': ('Laguna', 'Biñan City'),
    }
    
    if province_norm in special_mappings:
        prov, city = special_mappings[province_norm]
        if prov in city_barangays_data and city in city_barangays_data[prov]:
            return city_barangays_data[prov][city]
    
    return []

async def populate_barangays():
    # Load districts.json for provincial districts
    districts_path = Path(__file__).parent / 'static' / 'data' / 'districts.json'
    if not districts_path.exists():
        print(f"❌ Error: districts.json not found at {districts_path}")
        return
    
    with open(districts_path, 'r', encoding='utf-8') as f:
        districts_data = json.load(f)
    
    print(f"📁 Loaded districts.json with {len(districts_data.get('districts', {}))} entries")
    
    # Load city_barangays_mapping.json for city districts
    city_barangays_path = Path(__file__).parent / 'city_barangays_mapping.json'
    city_barangays_data = {}
    if city_barangays_path.exists():
        with open(city_barangays_path, 'r', encoding='utf-8') as f:
            city_barangays_data = json.load(f)
        print(f"📁 Loaded city_barangays_mapping.json with {sum(len(cities) for cities in city_barangays_data.values())} cities")
    else:
        print(f"⚠️  Warning: city_barangays_mapping.json not found, skipping city barangays")
    
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
            
            if not province:
                print(f"  ⚠️  No province for {congressman['display_name']}")
                not_found += 1
                continue
            
            municipalities_for_district = []
            
            # Try to find barangays for city districts
            if is_city:
                # Try city barangays mapping first
                municipalities_for_district = find_city_barangays(province, city_barangays_data)
                
                # If not found in city mapping, try districts.json
                if not municipalities_for_district:
                    district_key = province
                    if district_key in districts_data.get('districts', {}):
                        district_info = districts_data['districts'][district_key]
                        municipalities_dict = district_info.get('municipalities', {})
                        if municipalities_dict:
                            target_district = "Lone District"
                            municipalities_for_district = [
                                muni for muni, dist in municipalities_dict.items()
                                if dist == target_district
                            ]
            else:
                # Provincial district - use districts.json
                district_key = province
                
                if district_key not in districts_data.get('districts', {}):
                    print(f"  ⚠️  District key '{district_key}' not found for {congressman['display_name']}")
                    not_found += 1
                    continue
                
                district_info = districts_data['districts'][district_key]
                municipalities_dict = district_info.get('municipalities', {})
                
                if not municipalities_dict:
                    print(f"  ⚠️  No municipalities found for {congressman['display_name']} ({district_key})")
                    not_found += 1
                    continue
                
                # Determine which district this congressman represents
                target_district = district_num
                
                # Filter municipalities for this specific district
                municipalities_for_district = [
                    muni for muni, dist in municipalities_dict.items()
                    if dist == target_district
                ]
            
            if not municipalities_for_district:
                print(f"  ⚠️  No municipalities/barangays found for {congressman['display_name']} ({province} - {district_num if not is_city else 'City'})")
                not_found += 1
                continue
            
            # Update database with JSON array of municipalities/barangays
            municipalities_json = json.dumps(municipalities_for_district)
            await conn.execute(
                'UPDATE dynasty_projects_congressmen_config SET barangays = $1::jsonb WHERE id = $2',
                municipalities_json, congressman['id']
            )
            
            updated += 1
            entity_type = "barangays" if is_city else "municipalities"
            print(f"  ✅ Updated {congressman['display_name']} ({province} - {district_num if not is_city else 'City'}): {len(municipalities_for_district)} {entity_type}")
        
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

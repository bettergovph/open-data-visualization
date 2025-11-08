#!/usr/bin/env python3
"""
Audit script to check which province districts are missing municipality data
and which city districts are missing barangay data.

Logs results for later database population.
"""

import asyncio
import asyncpg
import json
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

async def main():
    # Load environment variables
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    # Connect to dynasty database
    dynasty_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD'),
        database=os.getenv('POSTGRES_DB_DYNASTY')
    )
    
    print("✅ Connected to dynasty database\n")
    
    # Load districts.json to check what municipalities are available
    districts_file = Path(__file__).parent.parent / 'districts.json'
    with open(districts_file, 'r') as f:
        districts_data = json.load(f)
    
    # Fetch all congressmen
    query = """
        SELECT 
            id,
            display_name,
            province,
            district_number,
            is_city_district,
            barangays
        FROM dynasty_projects_congressmen_config
        WHERE province IS NOT NULL
        ORDER BY province, district_number, display_name
    """
    
    rows = await dynasty_conn.fetch(query)
    
    print("=" * 80)
    print("AUDIT REPORT: District Municipality & Barangay Data")
    print("=" * 80)
    print()
    
    missing_municipalities = []
    missing_barangays = []
    conflicting_names = []
    
    # Build list of all province and city names for conflict detection
    all_provinces = set()
    all_cities = set()
    for province_key in districts_data.get('districts', {}).keys():
        all_provinces.add(province_key.upper())
        # Check if this is a city (has city districts)
        districts_info = districts_data.get('districts', {}).get(province_key, {})
        if any('City' in dist for dist in districts_info.get('all_districts', [])):
            all_cities.add(province_key.upper())
    
    for row in rows:
        congressman_id = row['id']
        display_name = row['display_name']
        province = row['province']
        district_number = row['district_number']
        is_city_district = row['is_city_district']
        barangays = row['barangays'] if row['barangays'] else []
        
        if is_city_district:
            # City districts should have barangays
            if not barangays or len(barangays) == 0:
                missing_barangays.append({
                    'id': congressman_id,
                    'name': display_name,
                    'city': province,
                    'district': district_number
                })
            else:
                # Check for naming conflicts: barangays should not be province/city names
                for barangay in barangays:
                    barangay_upper = barangay.upper()
                    if barangay_upper in all_provinces or barangay_upper in all_cities:
                        conflicting_names.append({
                            'id': congressman_id,
                            'name': display_name,
                            'type': 'city_district',
                            'location': f"{province}, {district_number}",
                            'conflicting_item': barangay,
                            'conflict_type': 'barangay matches province/city name',
                            'issue': f"Barangay '{barangay}' is also a province/city name"
                        })
        else:
            # Province districts should have municipalities in districts.json
            # Check if districts.json has municipalities for this district
            province_key = None
            for key in districts_data.get('districts', {}).keys():
                if key.upper() == province.upper():
                    province_key = key
                    break
            
            district_municipalities = []
            if province_key:
                districts_info = districts_data.get('districts', {}).get(province_key, {})
                municipalities_map = districts_info.get('municipalities', {})
                for mun_key, mun_district in municipalities_map.items():
                    if mun_district and mun_district.upper() == district_number.upper():
                        district_municipalities.append(mun_key)
            
            if not district_municipalities:
                missing_municipalities.append({
                    'id': congressman_id,
                    'name': display_name,
                    'province': province,
                    'district': district_number
                })
            else:
                # Check for naming conflicts: municipalities should not be province/city names
                for municipality in district_municipalities:
                    municipality_upper = municipality.upper()
                    if municipality_upper in all_provinces or municipality_upper in all_cities:
                        conflicting_names.append({
                            'id': congressman_id,
                            'name': display_name,
                            'type': 'province_district',
                            'location': f"{province}, {district_number}",
                            'conflicting_item': municipality,
                            'conflict_type': 'municipality matches province/city name',
                            'issue': f"Municipality '{municipality}' is also a province/city name"
                        })
    
    # Print missing municipalities for province districts
    if missing_municipalities:
        print(f"⚠️  PROVINCE DISTRICTS MISSING MUNICIPALITY DATA ({len(missing_municipalities)})")
        print("=" * 80)
        print()
        for item in missing_municipalities:
            print(f"  • {item['name']}")
            print(f"    Province: {item['province']}, District: {item['district']}")
            print(f"    ID: {item['id']}")
            print()
        
        # Write to log file
        log_file = Path(__file__).parent.parent / 'missing_municipalities.log'
        with open(log_file, 'w') as f:
            f.write("PROVINCE DISTRICTS MISSING MUNICIPALITY DATA\n")
            f.write("=" * 80 + "\n\n")
            for item in missing_municipalities:
                f.write(f"ID: {item['id']}\n")
                f.write(f"Name: {item['name']}\n")
                f.write(f"Province: {item['province']}\n")
                f.write(f"District: {item['district']}\n")
                f.write("\n")
        print(f"📝 Written to: {log_file}")
        print()
    else:
        print("✅ All province districts have municipality data in districts.json")
        print()
    
    # Print missing barangays for city districts
    if missing_barangays:
        print(f"⚠️  CITY DISTRICTS MISSING BARANGAY DATA ({len(missing_barangays)})")
        print("=" * 80)
        print()
        for item in missing_barangays:
            print(f"  • {item['name']}")
            print(f"    City: {item['city']}, District: {item['district']}")
            print(f"    ID: {item['id']}")
            print()
        
        # Write to log file
        log_file = Path(__file__).parent.parent / 'missing_barangays.log'
        with open(log_file, 'w') as f:
            f.write("CITY DISTRICTS MISSING BARANGAY DATA\n")
            f.write("=" * 80 + "\n\n")
            for item in missing_barangays:
                f.write(f"ID: {item['id']}\n")
                f.write(f"Name: {item['name']}\n")
                f.write(f"City: {item['city']}\n")
                f.write(f"District: {item['district']}\n")
                f.write("\n")
        print(f"📝 Written to: {log_file}")
        print()
    else:
        print("✅ All city districts have barangay data in database")
        print()
    
    # Print naming conflicts
    if conflicting_names:
        print(f"🚨 NAMING CONFLICTS DETECTED ({len(conflicting_names)})")
        print("=" * 80)
        print("These barangays/municipalities have the same name as provinces/cities.")
        print("This may cause false matches in project attribution!")
        print()
        for item in conflicting_names:
            print(f"  • {item['name']} ({item['type']})")
            print(f"    Location: {item['location']}")
            print(f"    Issue: {item['issue']}")
            print(f"    ID: {item['id']}")
            print()
        
        # Write to log file
        log_file = Path(__file__).parent.parent / 'naming_conflicts.log'
        with open(log_file, 'w') as f:
            f.write("NAMING CONFLICTS: Barangays/Municipalities matching Province/City names\n")
            f.write("=" * 80 + "\n\n")
            f.write("These names may cause false matches in project attribution.\n")
            f.write("Review each case to determine if it's legitimate or needs correction.\n\n")
            for item in conflicting_names:
                f.write(f"ID: {item['id']}\n")
                f.write(f"Congressman: {item['name']}\n")
                f.write(f"Type: {item['type']}\n")
                f.write(f"Location: {item['location']}\n")
                f.write(f"Conflicting Item: {item['conflicting_item']}\n")
                f.write(f"Conflict Type: {item['conflict_type']}\n")
                f.write(f"Issue: {item['issue']}\n")
                f.write("\n")
        print(f"📝 Written to: {log_file}")
        print()
    else:
        print("✅ No naming conflicts detected")
        print()
    
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Province districts missing municipalities: {len(missing_municipalities)}")
    print(f"City districts missing barangays: {len(missing_barangays)}")
    print(f"Naming conflicts detected: {len(conflicting_names)}")
    print()
    
    await dynasty_conn.close()
    print("✅ Closed database connection")

if __name__ == '__main__':
    asyncio.run(main())


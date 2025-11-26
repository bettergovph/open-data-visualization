#!/usr/bin/env python3
"""Debug why Romualdez isn't matching projects"""

import json
from pathlib import Path

# Load config
config_path = Path(__file__).parent.parent / 'static' / 'data' / 'dynasty-projects-config.json'
with open(config_path, 'r', encoding='utf-8') as f:
    config_data = json.load(f)

# Load districts
districts_path = Path(__file__).parent.parent / 'static' / 'data' / 'districts.json'
with open(districts_path, 'r', encoding='utf-8') as f:
    districts_data = json.load(f)

# Find Romualdez entries
romualdez_entries = [
    entry for entry in config_data.get('target_congressmen', [])
    if 'Romualdez' in entry.get('display_name', '')
]

print(f"Found {len(romualdez_entries)} Romualdez entries:\n")

for entry in romualdez_entries:
    print(f"Display Name: {entry.get('display_name')}")
    print(f"Province: {entry.get('province')}")
    print(f"District: {entry.get('district_number')}")
    print(f"Is City District: {entry.get('is_city_district')}")
    
    # Simulate loading municipalities
    config_province = entry.get('province')
    config_district_number = entry.get('district_number')
    
    district_municipalities = []
    if districts_data and config_province and config_district_number:
        province_key = None
        for key in districts_data.get('districts', {}).keys():
            if key.upper() == config_province.upper():
                province_key = key
                break
        
        if province_key:
            print(f"✅ Found province key: {province_key}")
            districts_info = districts_data.get('districts', {}).get(province_key, {})
            municipalities_map = districts_info.get('municipalities', {})
            print(f"   Total municipalities in {province_key}: {len(municipalities_map)}")
            
            for mun_key, mun_district in municipalities_map.items():
                if mun_district and mun_district.upper() == config_district_number.upper():
                    district_municipalities.append(mun_key)
            
            print(f"   Municipalities for {config_district_number}: {district_municipalities}")
        else:
            print(f"❌ Province key not found for: {config_province}")
    else:
        print(f"❌ Missing data: province={config_province}, district={config_district_number}")
    
    print()


















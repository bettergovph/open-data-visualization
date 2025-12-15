#!/usr/bin/env python3
"""
Add missing city districts to districts.json based on Wikipedia data.
These cities have their own congressional districts but aren't in districts.json yet.
"""
import json
import shutil
from pathlib import Path

DISTRICTS_FILE = Path("static/data/districts.json")
WIKI_FILE = Path("static/data/20th_congress_representatives.json")

# Cities that need to be added (from Wikipedia merge failures)
MISSING_CITIES = [
    'Bacolod', 'Baguio', 'Butuan', 'Calamba', 'General Santos', 
    'Iligan', 'Lapu-Lapu City', 'Mandaue', 'San Jose del Monte', 
    'Santa Rosa', 'Taguig', 'Maguindanao del Norte', 'Maguindanao del Sur'
]

def add_missing_cities():
    print("🔄 Loading data...")
    
    with open(DISTRICTS_FILE, 'r', encoding='utf-8') as f:
        d_data = json.load(f)
    with open(WIKI_FILE, 'r', encoding='utf-8') as f:
        wiki_list = json.load(f)
    
    # Backup
    shutil.copy(DISTRICTS_FILE, str(DISTRICTS_FILE) + ".pre-cities-backup")
    print(f"📦 Backup created")
    
    added_count = 0
    
    for entry in wiki_list:
        prov = entry['province']
        dist = entry['district']
        rep = entry['representative']
        
        # Check if this is one of the missing cities
        if prov not in MISSING_CITIES:
            continue
        
        # Normalize district key
        dist_key = dist
        if dist.lower() == 'lone':
            dist_key = 'Lone District'
        elif dist == '1st':
            dist_key = '1st District'
        elif dist == '2nd':
            dist_key = '2nd District'
        elif dist == '3rd':
            dist_key = '3rd District'
        
        # Check if city already exists in districts.json
        city_key = None
        for k in d_data['districts'].keys():
            if k.upper() == prov.upper() or k.upper() == f"{prov} City".upper():
                city_key = k
                break
        
        if not city_key:
            # Create new city entry
            city_key = prov
            d_data['districts'][city_key] = {
                'entity_type': 'city',
                'all_districts': [dist_key],
                'municipalities': {city_key: dist_key},
                'representatives': {}
            }
            print(f"  NEW CITY: {city_key}")
        
        # Add representative
        if 'representatives' not in d_data['districts'][city_key]:
            d_data['districts'][city_key]['representatives'] = {}
        
        rep_str = f"{rep} (2022-present)"
        d_data['districts'][city_key]['representatives'][dist_key] = rep_str
        print(f"    {dist_key}: {rep_str}")
        added_count += 1
    
    # Save
    with open(DISTRICTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(d_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Added/Updated {added_count} city district entries")
    print(f"💾 Saved to {DISTRICTS_FILE}")

if __name__ == '__main__':
    add_missing_cities()

#!/usr/bin/env python3
"""Fix location database by reclassifying cities without 'CITY' in name as municipalities."""

import json
import re
from pathlib import Path

def normalize_name(name: str) -> str:
    """Normalize location name."""
    if not name:
        return ""
    name = re.sub(r'\s+(PROVINCE|MUNICIPALITY|MUN\.?)\s*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+(CITY OF|CITY OF THE)\s*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+', ' ', name).strip()
    return name.upper()

def main():
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    db_path = project_root / 'database' / 'philippine_locations.json'
    
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        return
    
    print(f"📖 Loading database...")
    with open(db_path, 'r', encoding='utf-8') as f:
        db = json.load(f)
    
    cities = db.get('cities', {})
    municipalities = db.get('municipalities', {})
    
    print(f"   Before: {len(cities)} cities, {sum(len(m) for m in municipalities.values())} municipalities")
    
    # Reclassify cities that don't have "CITY" in name
    cities_to_keep = {}
    reclassified_count = 0
    
    for city_key, city_data in cities.items():
        city_name = city_data.get('name', '')
        # Only keep if name contains "CITY" (or is from /city/ directory - but we can't check that now)
        if 'CITY' in city_name.upper():
            cities_to_keep[city_key] = city_data
        else:
            # Reclassify as municipality
            prov_name = city_data.get('province', '')
            mun_key = normalize_name(city_name)
            
            if mun_key not in municipalities:
                municipalities[mun_key] = []
            
            # Check if already exists
            existing = [m for m in municipalities[mun_key] 
                       if m.get('province_normalized') == normalize_name(prov_name)]
            if not existing:
                municipalities[mun_key].append({
                    'name': city_name,
                    'normalized': mun_key,
                    'province': prov_name,
                    'province_normalized': normalize_name(prov_name),
                    'region_id': city_data.get('region_id', ''),
                    'region_name': city_data.get('region_name', ''),
                    'municipality_id': city_data.get('city_id', ''),
                })
                reclassified_count += 1
    
    # Update database
    db['cities'] = cities_to_keep
    db['municipalities'] = municipalities
    db['metadata']['total_cities'] = len(cities_to_keep)
    db['metadata']['total_municipalities'] = sum(len(m) for m in municipalities.values())
    db['metadata']['reclassified_cities_to_municipalities'] = reclassified_count
    
    # Save
    with open(db_path, 'w', encoding='utf-8') as f:
        json.dump(db, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Database fixed!")
    print(f"   📊 After:")
    print(f"      - Provinces: {db['metadata']['total_provinces']}")
    print(f"      - Cities: {db['metadata']['total_cities']} (kept {len(cities_to_keep)} with 'CITY' in name)")
    print(f"      - Municipalities: {db['metadata']['total_municipalities']} (added {reclassified_count})")
    print(f"      - Regions: {db['metadata']['total_regions']}")

if __name__ == '__main__':
    main()

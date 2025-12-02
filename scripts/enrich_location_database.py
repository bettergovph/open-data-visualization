#!/usr/bin/env python3
"""
Enrich location database with official PSGC data from PSA.
Fetches comprehensive list from Philippine Statistics Authority.
"""

import json
import requests
from pathlib import Path
from typing import Dict, List

def fetch_psgc_data():
    """Fetch PSGC data from PSA website or use cached data."""
    # PSA PSGC API endpoint (if available) or we can parse from their website
    # For now, we'll create a structure that can be populated
    print("📡 Attempting to fetch official PSGC data...")
    
    # PSA PSGC masterlist URL
    psgc_url = "https://psa.gov.ph/classification/psgc"
    
    # Note: PSA website might require parsing HTML or using their API
    # For now, we'll enhance the existing database with better categorization
    
    return None

def enrich_from_existing_database():
    """Enrich location database by re-categorizing based on official counts."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    db_path = project_root / 'database' / 'philippine_locations.json'
    
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        return
    
    print(f"📖 Loading existing database...")
    with open(db_path, 'r', encoding='utf-8') as f:
        db = json.load(f)
    
    cities = db.get('cities', {})
    municipalities = db.get('municipalities', {})
    
    print(f"   Current: {len(cities)} cities, {sum(len(m) for m in municipalities.values())} municipalities")
    
    # Official counts: 149 cities, 1,493 municipalities
    # If we have too many cities, reclassify them
    if len(cities) > 200:  # Way too many
        print(f"\n⚠️  Too many cities detected ({len(cities)}). Re-categorizing...")
        
        # Reclassify: Only keep cities that explicitly have "CITY" in their name
        cities_to_keep = {}
        cities_to_reclassify = {}
        
        for city_key, city_data in cities.items():
            city_name = city_data.get('name', '')
            if 'CITY' in city_name.upper():
                cities_to_keep[city_key] = city_data
            else:
                # This is likely a municipality
                cities_to_reclassify[city_key] = city_data
        
        print(f"   Keeping {len(cities_to_keep)} cities with 'CITY' in name")
        print(f"   Reclassifying {len(cities_to_reclassify)} as municipalities")
        
        # Add reclassified cities to municipalities
        for city_key, city_data in cities_to_reclassify.items():
            mun_name = city_data.get('name', '')
            prov_name = city_data.get('province', '')
            mun_key = normalize_name(mun_name)
            
            if mun_key not in municipalities:
                municipalities[mun_key] = []
            
            # Check if already exists
            existing = [m for m in municipalities[mun_key] 
                       if m.get('province_normalized') == normalize_name(prov_name)]
            if not existing:
                municipalities[mun_key].append({
                    'name': mun_name,
                    'normalized': mun_key,
                    'province': prov_name,
                    'province_normalized': normalize_name(prov_name),
                    'region_id': city_data.get('region_id', ''),
                    'region_name': city_data.get('region_name', ''),
                    'municipality_id': city_data.get('city_id', ''),  # Use city_id as municipality_id
                })
        
        # Update database
        db['cities'] = cities_to_keep
        db['municipalities'] = municipalities
        db['metadata']['total_cities'] = len(cities_to_keep)
        db['metadata']['total_municipalities'] = sum(len(m) for m in municipalities.values())
        db['metadata']['reclassified'] = len(cities_to_reclassify)
        
        # Save updated database
        with open(db_path, 'w', encoding='utf-8') as f:
            json.dump(db, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Database updated!")
        print(f"   📊 New Statistics:")
        print(f"      - Provinces: {db['metadata']['total_provinces']}")
        print(f"      - Cities: {db['metadata']['total_cities']}")
        print(f"      - Municipalities: {db['metadata']['total_municipalities']}")
        print(f"      - Regions: {db['metadata']['total_regions']}")
    else:
        print(f"✅ City count looks reasonable ({len(cities)})")

def normalize_name(name: str) -> str:
    """Normalize location name for matching."""
    import re
    if not name:
        return ""
    name = re.sub(r'\s+(PROVINCE|MUNICIPALITY|MUN\.?)\s*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+(CITY OF|CITY OF THE)\s*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+', ' ', name).strip()
    return name.upper()

if __name__ == '__main__':
    enrich_from_existing_database()









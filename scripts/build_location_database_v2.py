#!/usr/bin/env python3
"""
Build comprehensive Philippine location database from GeoJSON files.
V2: More conservative approach - only classify as city if explicitly a city.
"""

import json
import re
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set

def normalize_name(name: str) -> str:
    """Normalize location name for matching."""
    if not name:
        return ""
    # Remove common suffixes but KEEP "CITY" for identification
    name = re.sub(r'\s+(PROVINCE|MUNICIPALITY|MUN\.?)\s*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+(CITY OF|CITY OF THE)\s*$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+', ' ', name).strip()
    return name.upper()

def extract_from_geojson(geojson_path: Path) -> Dict:
    """Extract location data from a GeoJSON file."""
    try:
        with open(geojson_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        props = data.get('properties', {})
        return {
            'type': props.get('type', '').lower(),
            'level': str(props.get('level', '')),
            'name': props.get('province_name') or props.get('city_name') or props.get('municipality_name') or props.get('name', ''),
            'region_id': props.get('region_id', ''),
            'region_name': props.get('region_name', ''),
            'region_reference': props.get('region_reference', ''),
            'province_id': props.get('province_id', ''),
            'province_name': props.get('province_name', ''),
            'province_reference': props.get('province_reference', ''),
            'city_id': props.get('city_id', ''),
            'city_name': props.get('city_name', ''),
            'municipality_id': props.get('municipality_id', ''),
            'municipality_name': props.get('municipality_name', ''),
        }
    except Exception as e:
        return None

def build_location_database(geojson_dir: Path) -> Dict:
    """Build comprehensive location database from GeoJSON files."""
    print("🔍 Scanning GeoJSON files...")
    
    provinces = {}
    cities = {}
    municipalities = defaultdict(list)
    regions = {}
    
    # Region mappings
    region_mappings = {
        '1': 'Ilocos Region (Region I)',
        '2': 'Cagayan Valley (Region II)',
        '3': 'Central Luzon (Region III)',
        '4-A': 'CALABARZON (Region IV-A)',
        '4-B': 'MIMAROPA (Region IV-B)',
        '5': 'Bicol Region (Region V)',
        '6': 'Western Visayas (Region VI)',
        '7': 'Central Visayas (Region VII)',
        '8': 'Eastern Visayas (Region VIII)',
        '9': 'Zamboanga Peninsula (Region IX)',
        '10': 'Northern Mindanao (Region X)',
        '11': 'Davao Region (Region XI)',
        '12': 'SOCCSKSARGEN (Region XII)',
        '13': 'Caraga (Region XIII)',
        'CAR': 'Cordillera Administrative Region (CAR)',
        'NCR': 'National Capital Region (NCR)',
        'ARMM': 'Autonomous Region in Muslim Mindanao (ARMM)',
    }
    
    geojson_files = list(geojson_dir.rglob('*.geo.json'))
    print(f"📁 Found {len(geojson_files)} GeoJSON files")
    
    stats = {'province': 0, 'city': 0, 'municipality': 0, 'barangay': 0, 'unknown': 0, 'skipped_city': 0}
    
    for geojson_path in geojson_files:
        data = extract_from_geojson(geojson_path)
        if not data:
            continue
        
        loc_type = data.get('type', '').lower()
        level = data.get('level', '')
        path_str = str(geojson_path).lower()
        
        region_ref = data.get('region_reference', '') or data.get('region_id', '')
        region_name = data.get('region_name', '')
        
        # Normalize region reference
        if region_ref == '10':
            region_ref = 'X'
        elif region_ref in ['4-B', '4B', 'IV-B', 'IVB']:
            region_ref = 'IV-B'
        elif region_ref in ['4-A', '4A', 'IV-A', 'IVA']:
            region_ref = 'IV-A'
        
        # Skip barangays
        if '/barangay/' in path_str or level == '4':
            stats['barangay'] += 1
            continue
        
        # Get all name fields
        prov_name = data.get('province_name') or data.get('name', '')
        city_name = data.get('city_name', '')
        municipality_name = data.get('municipality_name', '')
        name = data.get('name', '')
        
        # Collect all possible names to check for "CITY"
        all_name_fields = [n for n in [prov_name, city_name, municipality_name, name] if n]
        all_names_text = ' '.join(all_name_fields).upper()
        
        # Provinces: level 2 or /province/ directory or type == 'province'
        if '/province/' in path_str or loc_type == 'province' or level == '2':
            if prov_name:
                prov_name_norm = normalize_name(prov_name)
                provinces[prov_name_norm] = {
                    'name': prov_name,
                    'normalized': prov_name_norm,
                    'region_id': region_ref,
                    'region_name': region_name,
                    'province_id': data.get('province_id', ''),
                }
                stats['province'] += 1
        
        # Cities: VERY STRICT - only if:
        # 1. Explicitly in /city/ directory, OR
        # 2. type == 'city' AND name contains "CITY", OR
        # 3. name contains "CITY" (check all name fields)
        elif '/city/' in path_str:
            # From /city/ directory - trust it's a city
            city_name_val = city_name or name
            if city_name_val:
                city_name_norm = normalize_name(city_name_val)
                if city_name_norm not in cities:
                    cities[city_name_norm] = {
                        'name': city_name_val,
                        'normalized': city_name_norm,
                        'province': prov_name,
                        'province_normalized': normalize_name(prov_name),
                        'region_id': region_ref,
                        'region_name': region_name,
                        'city_id': data.get('city_id', ''),
                    }
                    stats['city'] += 1
        elif loc_type == 'city' and 'CITY' in all_names_text:
            # Explicitly marked as city type AND has "CITY" in name
            city_name_val = city_name or name
            if city_name_val and 'CITY' in city_name_val.upper():
                city_name_norm = normalize_name(city_name_val)
                if city_name_norm not in cities:
                    cities[city_name_norm] = {
                        'name': city_name_val,
                        'normalized': city_name_norm,
                        'province': prov_name,
                        'province_normalized': normalize_name(prov_name),
                        'region_id': region_ref,
                        'region_name': region_name,
                        'city_id': data.get('city_id', ''),
                    }
                    stats['city'] += 1
        elif 'CITY' in all_names_text and not municipality_name:
            # Has "CITY" in any name field and no municipality_name - likely a city
            city_name_val = city_name or name
            if city_name_val and 'CITY' in city_name_val.upper():
                city_name_norm = normalize_name(city_name_val)
                if city_name_norm not in cities:
                    cities[city_name_norm] = {
                        'name': city_name_val,
                        'normalized': city_name_norm,
                        'province': prov_name,
                        'province_normalized': normalize_name(prov_name),
                        'region_id': region_ref,
                        'region_name': region_name,
                        'city_id': data.get('city_id', ''),
                    }
                    stats['city'] += 1
            else:
                stats['skipped_city'] += 1
        
        # Municipalities: everything else at level 3 that's not a city
        elif level == '3' or loc_type == 'municipality' or '/municipality/' in path_str or municipality_name:
            mun_name_val = municipality_name or name or city_name
            if mun_name_val:
                # Skip if it's actually a city (has "CITY" in name)
                if 'CITY' in mun_name_val.upper():
                    # This is actually a city, skip
                    stats['skipped_city'] += 1
                    continue
                
                mun_name_norm = normalize_name(mun_name_val)
                existing = [m for m in municipalities.get(mun_name_norm, []) 
                           if m.get('province_normalized') == normalize_name(prov_name)]
                if not existing:
                    municipalities[mun_name_norm].append({
                        'name': mun_name_val,
                        'normalized': mun_name_norm,
                        'province': prov_name,
                        'province_normalized': normalize_name(prov_name),
                        'region_id': region_ref,
                        'region_name': region_name,
                        'municipality_id': data.get('municipality_id', ''),
                    })
                    stats['municipality'] += 1
        else:
            stats['unknown'] += 1
    
    # Build region mappings
    for region_id, region_name in region_mappings.items():
        regions[region_id] = {
            'name': region_name,
            'provinces': [],
            'cities': [],
        }
    
    # Populate regions
    for prov_name_norm, prov_data in provinces.items():
        region_id = prov_data.get('region_id', '')
        if region_id in regions:
            regions[region_id]['provinces'].append(prov_data['name'])
    
    for city_name_norm, city_data in cities.items():
        region_id = city_data.get('region_id', '')
        if region_id in regions:
            regions[region_id]['cities'].append(city_data['name'])
    
    database = {
        'metadata': {
            'source': 'GeoJSON files from ~/geoph',
            'total_provinces': len(provinces),
            'total_cities': len(cities),
            'total_municipalities': sum(len(muns) for muns in municipalities.values()),
            'total_regions': len(regions),
            'processing_stats': stats,
        },
        'provinces': {k: v for k, v in sorted(provinces.items())},
        'cities': {k: v for k, v in sorted(cities.items())},
        'municipalities': {k: v for k, v in sorted(municipalities.items())},
        'regions': regions,
        'region_province_mappings': {
            region_id: {
                'name': region_data['name'],
                'provinces': region_data['provinces'],
            }
            for region_id, region_data in regions.items()
        },
    }
    
    return database

def main():
    """Main function."""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    geojson_dir = Path.home() / 'geoph' / 'geojson'
    if not geojson_dir.exists():
        print(f"❌ GeoJSON directory not found: {geojson_dir}")
        return
    
    database = build_location_database(geojson_dir)
    
    output_path = project_root / 'database' / 'philippine_locations.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(database, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Location database created: {output_path}")
    print(f"   📊 Statistics:")
    print(f"      - Provinces: {database['metadata']['total_provinces']}")
    print(f"      - Cities: {database['metadata']['total_cities']}")
    print(f"      - Municipalities: {database['metadata']['total_municipalities']}")
    print(f"      - Regions: {database['metadata']['total_regions']}")
    print(f"\n   🔍 Processing breakdown:")
    for k, v in sorted(database['metadata']['processing_stats'].items()):
        print(f"      - {k}: {v}")

if __name__ == '__main__':
    main()












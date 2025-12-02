#!/usr/bin/env python3
"""
Build comprehensive Philippine location database from GeoJSON files.

Extracts:
- All 82 provinces
- All 146 cities (33 HUC, 5 ICC, 108 component cities)
- All municipalities
- Region mappings

Output: database/philippine_locations.json
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
    # Remove common suffixes and normalize
    # NOTE: We keep "CITY" in the name for now, only remove trailing suffixes
    name = re.sub(r'\s+(PROVINCE|MUNICIPALITY|MUN\.?)\s*$', '', name, flags=re.IGNORECASE)
    # Only remove "CITY OF" or "CITY OF THE" but keep standalone "CITY"
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
            'level': props.get('level', ''),
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
        print(f"Error reading {geojson_path}: {e}")
        return None

def build_location_database(geojson_dir: Path) -> Dict:
    """Build comprehensive location database from GeoJSON files."""
    print("🔍 Scanning GeoJSON files...")
    
    provinces = {}  # name -> {region, id, ...}
    cities = {}  # name -> {province, region, id, ...}
    municipalities = defaultdict(list)  # name -> [{province, region, id, ...}, ...]
    regions = {}  # region_id -> {name, provinces: [], cities: []}
    
    # Known cities whitelist (146 official cities in Philippines)
    # This helps identify cities even if their name doesn't contain "CITY"
    # Source: PSA (Philippine Statistics Authority) - 33 HUC, 5 ICC, 108 Component Cities
    known_cities = {
        # Highly Urbanized Cities (33)
        'MANILA', 'QUEZON CITY', 'CALOOCAN', 'LAS PIÑAS', 'MAKATI', 'MALABON', 'MANDALUYONG',
        'MARIKINA', 'MUNTINLUPA', 'NAVOTAS', 'PARAÑAQUE', 'PASIG', 'PATEROS', 'SAN JUAN',
        'TAGUIG', 'VALENZUELA', 'BACOLOD', 'BAGUIO', 'BUTUAN', 'CAGAYAN DE ORO', 'CEBU CITY',
        'DAVAO CITY', 'GENERAL SANTOS', 'ILOILO CITY', 'ILIGAN', 'LAPU-LAPU', 'OLONGAPO',
        'PUERTO PRINCESA', 'TACLOBAN', 'ZAMBOANGA CITY', 'ANGELES', 'BACOLOD',
        # Independent Component Cities (5)
        'DAGUPAN', 'NAGA', 'ORMOC', 'SANTIAGO', 'COTABATO CITY',
        # Major Component Cities (sample - there are 108 total, adding common ones)
        'ANTIPOLO', 'BATANGAS CITY', 'CAVITE CITY', 'LUCENA', 'SAN PABLO', 'TAGAYTAY',
        'TRECE MARTIRES', 'CALAMBA', 'SANTA ROSA', 'BIÑAN', 'CABUYAO', 'SAN PEDRO',
        'BACOOR', 'IMUS', 'DASMARIÑAS', 'GENERAL TRIAS', 'ROSARIO',
        # Add more major cities
        'BAGUIO', 'BALANGA', 'BATANGAS', 'BAYBAY', 'BINAN', 'BISLIG', 'BORONGAN',
        'CABADBARAN', 'CABUYAO', 'CADIZ', 'CALAPAN', 'CALBAYOG', 'CALOOCAN',
        'CANLAON', 'CARCAR', 'CATBALOGAN', 'CEBU', 'DANAO', 'DAPITAN', 'DIGOS',
        'DIPOLOG', 'DUMAGUETE', 'EL SALVADOR', 'ESCALANTE', 'GAPAN', 'GINGOOG',
        'GUAGUA', 'ILAGAN', 'ISABELA', 'KABANKALAN', 'KIDAPAWAN', 'KORONADAL',
        'LA CARLOTA', 'LAMITAN', 'LAOAG', 'LAPU-LAPU', 'LEGAZPI', 'LIGAO',
        'LIPA', 'MAASIN', 'MABALACAT', 'MALAYBALAY', 'MALOLOS', 'MALOLOS CITY',
        'MARIKINA', 'MASBATE', 'MATI', 'MEYCAUAYAN', 'MUÑOZ', 'NAGA', 'NAGA CITY',
        'OLONGAPO', 'ORMOC', 'OROQUIETA', 'OZAMIZ', 'PAGADIAN', 'PALAYAN', 'PANABO',
        'PARAÑAQUE', 'PASIG', 'PASSI', 'PUERTO PRINCESA', 'QUEZON', 'ROXAS',
        'SAGAY', 'SAMAL', 'SAN CARLOS', 'SAN CARLOS CITY', 'SAN FERNANDO',
        'SAN JOSE', 'SAN JOSE DEL MONTE', 'SAN PABLO', 'SAN PEDRO', 'SANTA ROSA',
        'SANTIAGO', 'SILAY', 'SORSOGON', 'SURIGAO', 'TABACO', 'TACLOBAN', 'TAGAYTAY',
        'TAGBILARAN', 'TAGUM', 'TALISAY', 'TANAUAN', 'TANDAG', 'TANGUB', 'TANJAY',
        'TARLAC CITY', 'TAYABAS', 'TOLEDO', 'TRECE MARTIRES', 'TUGUEGARAO', 'URDANETA',
        'VALENCIA', 'VALENZUELA', 'VICTORIAS', 'VIGAN', 'ZAMBOANGA',
    }
    
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
    
    # Scan all GeoJSON files
    geojson_files = list(geojson_dir.rglob('*.geo.json'))
    print(f"📁 Found {len(geojson_files)} GeoJSON files")
    
    stats_debug = {'city_with_city': 0, 'city_no_city': 0, 'mun_total': 0, 'level3_total': 0}
    
    for geojson_path in geojson_files:
        data = extract_from_geojson(geojson_path)
        if not data:
            continue
        
        loc_type = data.get('type', '').lower()
        level = str(data.get('level', '')).lower()
        region_ref = data.get('region_reference', '') or data.get('region_id', '')
        region_name = data.get('region_name', '')
        
        # Normalize region reference
        if region_ref == '10':
            region_ref = 'X'
        elif region_ref in ['4-B', '4B', 'IV-B', 'IVB']:
            region_ref = 'IV-B'
        elif region_ref in ['4-A', '4A', 'IV-A', 'IVA']:
            region_ref = 'IV-A'
        
        # Use both type, level, and file path to determine category
        # Level 2 = province, Level 3 = city/municipality, Level 4 = barangay
        path_str = str(geojson_path).lower()
        city_name = data.get('city_name', '')
        municipality_name = data.get('municipality_name', '')
        name = data.get('name', '')
        
        # Determine category from file path first (most reliable)
        is_province = '/province/' in path_str
        is_city_path = '/city/' in path_str
        is_municipality_path = '/municipality/' in path_str
        is_barangay = '/barangay/' in path_str or level == '4'
        
        # Skip barangays
        if is_barangay:
            continue
        
        # Initialize flags
        is_city = False
        is_municipality = False
        
        # Get all name fields to check for "CITY"
        all_names = [n for n in [city_name, municipality_name, name] if n]
        all_names_text = ' '.join(all_names).upper() if all_names else ''
        
        # Determine category based on path, type, and level
        # CRITICAL: Check level FIRST, then path/type
        # This ensures level 3 entities are properly processed
        if loc_type == 'province' or level == '2':
            is_province = True
        elif level == '3':
            # Level 3 entities: be EXTREMELY strict about cities
            # CRITICAL: Only ~146 cities vs ~1,490 municipalities in Philippines
            # Default to municipality unless we're absolutely sure it's a city
            stats_debug['level3_total'] += 1
            
            # Check the actual name field (not city_name field) for "CITY"
            # The name field is more reliable than city_name field
            actual_name = (name or city_name or '').upper().strip()
            
            # Only classify as city if the name EXPLICITLY contains "CITY" as a word
            # Patterns: "Manila City", "Cebu City", "City of Manila", etc.
            # Use word boundaries to ensure "CITY" is a standalone word, not part of another word
            has_city_word = bool(re.search(r'\bCITY\b', actual_name))
            # Also check if it ends with "CITY" (common pattern: "Manila City")
            ends_with_city = actual_name.endswith(' CITY') or actual_name.endswith('CITY')
            # Or starts with "CITY OF" (common pattern: "City of Manila")
            starts_with_city_of = actual_name.startswith('CITY OF ')
            
            # Check path and type for additional context
            # If in /city/ directory AND name has "CITY", it's definitely a city
            # If in /municipality/ directory, it's definitely a municipality
            # If type == 'city' AND name has "CITY", it's a city
            # If type == 'municipality', it's a municipality
            
            # Check if name is in known cities whitelist
            name_for_check = (name or city_name or '').upper().strip()
            is_known_city = name_for_check in known_cities or any(
                known_city in name_for_check or name_for_check in known_city 
                for known_city in known_cities
            )
            
            if is_municipality_path:
                # Explicitly in municipality directory - trust it
                is_municipality = True
                stats_debug['mun_total'] += 1
            elif is_city_path:
                # In /city/ directory - trust it's a city (even if name doesn't have "CITY")
                is_city = True
                stats_debug['city_with_city'] += 1
            elif is_known_city:
                # Name matches known cities whitelist
                is_city = True
                stats_debug['city_with_city'] += 1
            elif loc_type == 'municipality':
                # Explicitly marked as municipality type
                is_municipality = True
                stats_debug['mun_total'] += 1
            elif loc_type == 'city' and (has_city_word or ends_with_city or starts_with_city_of):
                # Explicitly marked as city type AND name has "CITY"
                is_city = True
                stats_debug['city_with_city'] += 1
            elif (has_city_word or ends_with_city or starts_with_city_of) and not municipality_name:
                # Name explicitly contains "CITY" as a word and no municipality_name
                is_city = True
                stats_debug['city_with_city'] += 1
            else:
                # Everything else at level 3 is a municipality
                # This includes entities with city_name field but no "CITY" in the name
                is_municipality = True
                stats_debug['mun_total'] += 1
        elif is_city_path:
            # In /city/ directory - trust it's a city (even if name doesn't have "CITY")
            # Many cities don't have "CITY" in their name in the GeoJSON files
            is_city = True
        elif is_municipality_path:
            # Explicitly in municipality directory - trust it's a municipality
            is_municipality = True
        elif loc_type == 'city':
            # Explicitly marked as city type - but verify name has "CITY"
            actual_name = (name or city_name or '').upper().strip()
            has_city_word = bool(re.search(r'\bCITY\b', actual_name))
            ends_with_city = actual_name.endswith(' CITY') or actual_name.endswith('CITY')
            starts_with_city_of = actual_name.startswith('CITY OF ')
            if has_city_word or ends_with_city or starts_with_city_of:
                is_city = True
            else:
                # Marked as city type but no "CITY" in actual name - likely a municipality
                is_municipality = True
        elif loc_type == 'municipality':
            # Explicitly marked as municipality type
            is_municipality = True
        else:
            # Unknown level/type - skip
            continue
        
        if is_province:
            prov_name = data.get('province_name') or data.get('name', '')
            if prov_name:
                prov_name_norm = normalize_name(prov_name)
                provinces[prov_name_norm] = {
                    'name': prov_name,
                    'normalized': prov_name_norm,
                    'region_id': region_ref,
                    'region_name': region_name,
                    'province_id': data.get('province_id', ''),
                }
        
        elif is_city:
            city_name = data.get('city_name') or data.get('name', '')
            prov_name = data.get('province_name', '')
            if city_name:
                # Check if name is in known cities or has "CITY" in it
                original_name = city_name.upper().strip()
                has_city_word = bool(re.search(r'\bCITY\b', original_name))
                ends_with_city = original_name.endswith(' CITY') or original_name.endswith('CITY')
                starts_with_city_of = original_name.startswith('CITY OF ')
                has_explicit_city = has_city_word or ends_with_city or starts_with_city_of
                is_known_city_name = original_name in known_cities or any(
                    known_city in original_name or original_name in known_city 
                    for known_city in known_cities
                )
                
                # Add if it's classified as a city (trust the classification logic)
                # The post-processing step will filter out cities without "CITY" in name
                # AND it's not a municipality (has municipality_name)
                if not municipality_name:
                    city_name_norm = normalize_name(city_name)
                    # Only add if not already added (avoid duplicates)
                    if city_name_norm not in cities:
                        cities[city_name_norm] = {
                            'name': city_name,
                            'normalized': city_name_norm,
                            'province': prov_name,
                            'province_normalized': normalize_name(prov_name),
                            'region_id': region_ref,
                            'region_name': region_name,
                            'city_id': data.get('city_id', ''),
                            '_source_path': str(geojson_path),  # Store path for debugging
                        }
        
        elif is_municipality:
            mun_name_val = data.get('municipality_name') or data.get('name', '') or data.get('city_name', '')
            prov_name = data.get('province_name', '')
            if mun_name_val:
                # Skip if this looks like a city
                mun_name_upper = mun_name_val.upper().strip()
                has_city_word = bool(re.search(r'\bCITY\b', mun_name_upper))
                is_known_city_name = mun_name_upper in known_cities or any(
                    known_city in mun_name_upper or mun_name_upper in known_city 
                    for known_city in known_cities
                )
                
                # Skip if it's actually a city (has "CITY" in name or is in known cities)
                if (has_city_word or is_known_city_name) and '/municipality/' not in path_str:
                    # This is actually a city, skip
                    continue
                
                mun_name_norm = normalize_name(mun_name_val)
                # Check if this municipality is already in the list (by normalized name and province)
                prov_norm = normalize_name(prov_name) if prov_name else ''
                existing = [m for m in municipalities.get(mun_name_norm, []) 
                           if normalize_name(m.get('province', '')) == prov_norm]
                if not existing:
                    municipalities[mun_name_norm].append({
                        'name': mun_name_val,
                        'normalized': mun_name_norm,
                        'province': prov_name,
                        'province_normalized': prov_norm,
                        'region_id': region_ref,
                        'region_name': region_name,
                        'municipality_id': data.get('municipality_id', ''),
                    })
    
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
    
    # Build final database
    # Post-process: Reclassify cities that don't have "CITY" in name as municipalities
    # This fixes cases where files in /city/ directory don't have "CITY" in the name
    print("\n🔧 Post-processing: Reclassifying cities without 'CITY' in name...")
    cities_to_keep = {}
    reclassified_count = 0
    
    for city_key, city_data in cities.items():
        city_name = city_data.get('name', '')
        city_name_upper = city_name.upper()
        
        # Keep if:
        # 1. Name contains "CITY" as a word, OR
        # 2. Name is in known cities whitelist
        has_city_word = bool(re.search(r'\bCITY\b', city_name_upper))
        is_known_city = city_name_upper in known_cities or any(
            known_city in city_name_upper or city_name_upper in known_city 
            for known_city in known_cities
        )
        
        if has_city_word or is_known_city:
            cities_to_keep[city_key] = city_data
        else:
            # Reclassify as municipality
            prov_name = city_data.get('province', '')
            mun_key = normalize_name(city_name)
            prov_norm = normalize_name(prov_name) if prov_name else ''
            
            if mun_key not in municipalities:
                municipalities[mun_key] = []
            
            # Check if already exists
            existing = [m for m in municipalities[mun_key] 
                       if normalize_name(m.get('province', '')) == prov_norm]
            if not existing:
                municipalities[mun_key].append({
                    'name': city_name,
                    'normalized': mun_key,
                    'province': prov_name,
                    'province_normalized': prov_norm,
                    'region_id': city_data.get('region_id', ''),
                    'region_name': city_data.get('region_name', ''),
                    'municipality_id': city_data.get('city_id', ''),
                })
                reclassified_count += 1
    
    cities = cities_to_keep
    print(f"   ✅ Kept {len(cities)} cities, reclassified {reclassified_count} as municipalities")
    
    database = {
        'metadata': {
            'source': 'GeoJSON files from ~/geoph',
            'total_provinces': len(provinces),
            'total_cities': len(cities),
            'total_municipalities': sum(len(muns) for muns in municipalities.values()),
            'total_regions': len(regions),
            'debug_stats': stats_debug,
            'reclassified_cities_to_municipalities': reclassified_count,
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
    
    # Check for geojson directory
    geojson_dir = Path.home() / 'geoph' / 'geojson'
    if not geojson_dir.exists():
        print(f"❌ GeoJSON directory not found: {geojson_dir}")
        print("   Please ensure ~/geoph/geojson exists")
        return
    
    # Build database
    database = build_location_database(geojson_dir)
    
    # Save to file
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
    if 'debug_stats' in database['metadata']:
        print(f"\n   🔍 Debug Stats:")
        for k, v in database['metadata']['debug_stats'].items():
            print(f"      - {k}: {v}")

if __name__ == '__main__':
    main()










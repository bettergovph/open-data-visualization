#!/usr/bin/env python3
"""
Extract barangay names from geoph repository for all cities
and create a JSON mapping file.
"""

import json
import os
from pathlib import Path
from collections import defaultdict

def extract_barangay_name(filename):
    """Extract barangay name from geojson filename"""
    # Format: ph.region.province.city.barangay.geo.json
    parts = filename.replace('.geo.json', '').split('.')
    if len(parts) >= 5:
        # Join all parts after city as barangay name (handles multi-word barangays)
        barangay = '.'.join(parts[4:])
        return barangay.replace('-', ' ').title()
    return None

def normalize_city_name(city_part):
    """Normalize city name for matching"""
    return city_part.replace('-', ' ').title()

def main():
    geoph_path = Path('/home/joebert/geoph/geojson/barangay')
    
    if not geoph_path.exists():
        print(f"❌ Error: {geoph_path} not found")
        return
    
    print(f"📁 Scanning {geoph_path}...")
    
    # Dictionary to store city -> barangays mapping
    city_barangays = defaultdict(lambda: defaultdict(list))
    
    # Scan all geojson files
    for filename in os.listdir(geoph_path):
        if not filename.endswith('.geo.json'):
            continue
        
        # Parse filename: ph.region.province.city.barangay.geo.json
        parts = filename.replace('.geo.json', '').split('.')
        
        if len(parts) < 5:
            continue
        
        region = parts[1]
        province = parts[2]
        city = parts[3]
        barangay_parts = parts[4:]
        
        # Skip if not a city
        if 'city' not in city and 'metropolitan-manila' not in province:
            continue
        
        # Normalize names
        city_normalized = normalize_city_name(city)
        barangay_name = ' '.join(barangay_parts).replace('-', ' ').title()
        
        # Store barangay under province -> city
        province_normalized = normalize_city_name(province)
        city_barangays[province_normalized][city_normalized].append(barangay_name)
    
    # Convert to regular dict and sort
    result = {}
    for province in sorted(city_barangays.keys()):
        result[province] = {}
        for city in sorted(city_barangays[province].keys()):
            result[province][city] = sorted(set(city_barangays[province][city]))
    
    # Save to JSON
    output_path = Path(__file__).parent / 'city_barangays_mapping.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    # Print summary
    print(f"\n✅ Extracted barangays for cities:")
    total_cities = 0
    total_barangays = 0
    for province, cities in result.items():
        for city, barangays in cities.items():
            total_cities += 1
            total_barangays += len(barangays)
            print(f"  {province} - {city}: {len(barangays)} barangays")
    
    print(f"\n📊 Total: {total_cities} cities, {total_barangays} barangays")
    print(f"💾 Saved to {output_path}")

if __name__ == '__main__':
    main()


#!/usr/bin/env python3
"""
Generate a report of provinces with and without dynasty data
"""

import requests
import json
import os
import glob

def get_provinces_with_dynasty_data():
    """Get provinces that have dynasty data"""
    try:
        response = requests.get('http://172.30.147.217:8001/api/dynasty/top-surnames')
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                provinces_with_data = set()
                for surname in data.get('data', []):
                    provinces_with_data.add(surname['province'])
                return provinces_with_data
    except Exception as e:
        print(f"Error fetching dynasty data: {e}")
    return set()

def get_geojson_provinces():
    """Get all provinces from GeoJSON files"""
    geojson_files = glob.glob('static/data/*.geo.json')
    provinces = set()
    
    for file_path in geojson_files:
        # Extract province name from filename
        # Example: ph.calabarzon-region-iv-a.batangas.any.any.geo.json -> batangas
        filename = os.path.basename(file_path)
        parts = filename.split('.')
        if len(parts) >= 3:
            province_name = parts[2].replace('-', ' ').upper()
            provinces.add(province_name)
    
    return provinces

def main():
    print("🔍 Generating Province Dynasty Data Report")
    print("=" * 60)
    
    # Get provinces with dynasty data
    provinces_with_dynasty = get_provinces_with_dynasty_data()
    print(f"\n📊 Provinces WITH dynasty data ({len(provinces_with_dynasty)}):")
    for province in sorted(provinces_with_dynasty):
        print(f"  ✅ {province}")
    
    # Get all GeoJSON provinces
    geojson_provinces = get_geojson_provinces()
    print(f"\n🗺️ Total GeoJSON provinces ({len(geojson_provinces)}):")
    for province in sorted(geojson_provinces):
        print(f"  🗺️ {province}")
    
    # Find provinces without dynasty data
    provinces_without_dynasty = geojson_provinces - provinces_with_dynasty
    print(f"\n❌ Provinces WITHOUT dynasty data ({len(provinces_without_dynasty)}):")
    for province in sorted(provinces_without_dynasty):
        print(f"  ❌ {province}")
    
    # Summary
    print(f"\n📈 SUMMARY:")
    print(f"  • Total GeoJSON provinces: {len(geojson_provinces)}")
    print(f"  • Provinces with dynasty data: {len(provinces_with_dynasty)}")
    print(f"  • Provinces without dynasty data: {len(provinces_without_dynasty)}")
    print(f"  • Coverage: {len(provinces_with_dynasty)/len(geojson_provinces)*100:.1f}%")
    
    # Save report to file
    report_data = {
        "summary": {
            "total_geojson_provinces": len(geojson_provinces),
            "provinces_with_dynasty": len(provinces_with_dynasty),
            "provinces_without_dynasty": len(provinces_without_dynasty),
            "coverage_percentage": round(len(provinces_with_dynasty)/len(geojson_provinces)*100, 1)
        },
        "provinces_with_dynasty": sorted(list(provinces_with_dynasty)),
        "provinces_without_dynasty": sorted(list(provinces_without_dynasty)),
        "all_geojson_provinces": sorted(list(geojson_provinces))
    }
    
    with open('province_dynasty_report.json', 'w') as f:
        json.dump(report_data, f, indent=2)
    
    print(f"\n💾 Report saved to: province_dynasty_report.json")

if __name__ == "__main__":
    main()

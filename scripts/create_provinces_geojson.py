#!/usr/bin/env python3
"""
Script to create a consolidated Philippine provinces GeoJSON file
from individual province GeoJSON files.
"""

import json
import os
import glob

def create_provinces_geojson():
    """Create a consolidated provinces GeoJSON file."""
    
    # Directory containing individual province GeoJSON files
    data_dir = '/home/joebert/open-data-visualization/static/data'
    
    # Find all individual province GeoJSON files
    province_files = glob.glob(os.path.join(data_dir, 'ph.*.geo.json'))
    
    print(f"Found {len(province_files)} province files")
    
    # Initialize the consolidated GeoJSON structure
    consolidated_geojson = {
        "type": "FeatureCollection",
        "features": []
    }
    
    # Process each province file
    for i, province_file in enumerate(sorted(province_files)):
        try:
            with open(province_file, 'r', encoding='utf-8') as f:
                province_data = json.load(f)
            
            # Extract the province name from the filename
            filename = os.path.basename(province_file)
            # Example: ph.cagayan-valley-region-ii.cagayan.any.any.geo.json
            parts = filename.replace('.geo.json', '').split('.')
            if len(parts) >= 3:
                province_name = parts[2].replace('-', ' ').title()
                
                # Check if this is a single feature or feature collection
                if province_data.get('type') == 'Feature':
                    # Single feature - add it directly
                    feature = province_data.copy()
                    feature['properties'] = {
                        'name': province_name,
                        'id': i + 1
                    }
                    consolidated_geojson['features'].append(feature)
                    print(f"Added: {province_name}")
                elif 'features' in province_data and province_data['features']:
                    # Feature collection - take the first feature
                    feature = province_data['features'][0]
                    feature['properties'] = {
                        'name': province_name,
                        'id': i + 1
                    }
                    consolidated_geojson['features'].append(feature)
                    print(f"Added: {province_name}")
            
        except Exception as e:
            print(f"Error processing {province_file}: {e}")
    
    # Save the consolidated GeoJSON
    output_file = os.path.join(data_dir, 'philippines-provinces.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(consolidated_geojson, f, indent=2)
    
    print(f"\n✅ Created consolidated provinces GeoJSON: {output_file}")
    print(f"Total provinces: {len(consolidated_geojson['features'])}")

if __name__ == "__main__":
    create_provinces_geojson()

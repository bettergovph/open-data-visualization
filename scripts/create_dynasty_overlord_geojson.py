#!/usr/bin/env python3
"""
Script to create a dynasty overlord GeoJSON file showing which dynasty controls which province.
"""

import json
import os
import glob

def create_dynasty_overlord_geojson():
    """Create a dynasty overlord GeoJSON file."""
    
    # Load dynasty surnames cache
    dynasty_cache_file = '/home/joebert/open-data-visualization/static/data/dynasty_surnames_cache.json'
    
    try:
        with open(dynasty_cache_file, 'r', encoding='utf-8') as f:
            dynasty_data = json.load(f)
    except Exception as e:
        print(f"Error loading dynasty cache: {e}")
        return
    
    # Load province mapping
    mapping_file = '/home/joebert/open-data-visualization/static/data/dynasty_province_mapping.json'
    
    try:
        with open(mapping_file, 'r', encoding='utf-8') as f:
            mapping_data = json.load(f)
        province_mapping = mapping_data['mapping']
        print(f"✅ Loaded province mapping with {len(province_mapping)} mappings")
    except Exception as e:
        print(f"❌ Error loading province mapping: {e}")
        province_mapping = {}
    
    # Process dynasty data to find overlords (strongest dynasty per province)
    province_overlords = {}
    
    # Group by province and find the strongest dynasty
    for surname_data in dynasty_data['surnames']:
        province = surname_data['province']
        surname = surname_data['surname']
        dynasty_count = surname_data['dynasty_count']
        
        if province not in province_overlords:
            province_overlords[province] = {
                'surname': surname,
                'dynasty_count': dynasty_count,
                'total_count': surname_data['total_count']
            }
        else:
            # If this dynasty has more members, it becomes the overlord
            if dynasty_count > province_overlords[province]['dynasty_count']:
                province_overlords[province] = {
                    'surname': surname,
                    'dynasty_count': dynasty_count,
                    'total_count': surname_data['total_count']
                }
    
    print(f"Found overlords for {len(province_overlords)} provinces")
    for province, overlord in province_overlords.items():
        print(f"  {province}: {overlord['surname']} ({overlord['dynasty_count']} dynasty members)")
    
    # Load individual province GeoJSON files and create consolidated file
    data_dir = '/home/joebert/open-data-visualization/static/data'
    province_files = glob.glob(os.path.join(data_dir, 'ph.*.geo.json'))
    
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
                
                # Use province mapping to get the correct database name
                province_key = province_name.lower()
                mapped_province = province_mapping.get(province_key, province_name.upper())
                
                # Find matching overlord data using the mapped province name
                overlord_data = province_overlords.get(mapped_province)
                
                if overlord_data:
                    print(f"✅ Mapped {province_name} → {mapped_province} → {overlord_data['surname']}")
                else:
                    print(f"⚠️ No overlord data for {province_name} (mapped to {mapped_province})")
                
                # Add the feature to our consolidated GeoJSON
                # Handle FeatureCollection, individual Feature, and direct coordinate arrays
                if 'features' in province_data and province_data['features']:
                    # Standard GeoJSON FeatureCollection format
                    feature = province_data['features'][0]
                    feature['properties'] = {
                        'name': province_name,
                        'id': i + 1,
                        'overlord_surname': overlord_data['surname'] if overlord_data else 'Unknown',
                        'dynasty_count': overlord_data['dynasty_count'] if overlord_data else 0,
                        'total_count': overlord_data['total_count'] if overlord_data else 0,
                        'control_intensity': (overlord_data['dynasty_count'] / overlord_data['total_count'] * 100) if overlord_data and overlord_data['total_count'] > 0 else 0
                    }
                    consolidated_geojson['features'].append(feature)
                    print(f"Added: {province_name} - Overlord: {feature['properties']['overlord_surname']}")
                elif 'type' in province_data and province_data['type'] == 'Feature':
                    # Individual GeoJSON Feature format
                    feature = province_data.copy()
                    feature['properties'] = {
                        'name': province_name,
                        'id': i + 1,
                        'overlord_surname': overlord_data['surname'] if overlord_data else 'Unknown',
                        'dynasty_count': overlord_data['dynasty_count'] if overlord_data else 0,
                        'total_count': overlord_data['total_count'] if overlord_data else 0,
                        'control_intensity': (overlord_data['dynasty_count'] / overlord_data['total_count'] * 100) if overlord_data and overlord_data['total_count'] > 0 else 0
                    }
                    consolidated_geojson['features'].append(feature)
                    print(f"Added: {province_name} - Overlord: {feature['properties']['overlord_surname']}")
                elif 'coordinates' in province_data or isinstance(province_data, list):
                    # Direct coordinate array format - create a proper GeoJSON Feature
                    coordinates = province_data if isinstance(province_data, list) else province_data.get('coordinates', [])
                    if coordinates:
                        feature = {
                            'type': 'Feature',
                            'geometry': {
                                'type': 'Polygon',
                                'coordinates': coordinates
                            },
                            'properties': {
                                'name': province_name,
                                'id': i + 1,
                                'overlord_surname': overlord_data['surname'] if overlord_data else 'Unknown',
                                'dynasty_count': overlord_data['dynasty_count'] if overlord_data else 0,
                                'total_count': overlord_data['total_count'] if overlord_data else 0,
                                'control_intensity': (overlord_data['dynasty_count'] / overlord_data['total_count'] * 100) if overlord_data and overlord_data['total_count'] > 0 else 0
                            }
                        }
                        consolidated_geojson['features'].append(feature)
                        print(f"Added: {province_name} - Overlord: {feature['properties']['overlord_surname']}")
                    else:
                        print(f"⚠️ No coordinates found for {province_name}")
                else:
                    print(f"⚠️ No GeoJSON features or coordinates found for {province_name}")
            
        except Exception as e:
            print(f"Error processing {province_file}: {e}")
    
    # Save the consolidated GeoJSON
    output_file = os.path.join(data_dir, 'dynasty-overlord-provinces.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(consolidated_geojson, f, indent=2)
    
    print(f"\n✅ Created dynasty overlord GeoJSON: {output_file}")
    print(f"Total provinces: {len(consolidated_geojson['features'])}")

if __name__ == "__main__":
    create_dynasty_overlord_geojson()

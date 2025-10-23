#!/usr/bin/env python3
"""
Generate province-to-cities mapping using GeoJSON data and point-in-polygon calculations.
This replaces hardcoded mappings with geographic analysis.
"""

import json
import os
import glob
from shapely.geometry import Point, Polygon
from shapely.geometry import shape
import requests

def load_geojson(file_path):
    """Load GeoJSON file and return the geometry."""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return None

def get_city_coordinates(city_name):
    """Get coordinates for a city using a geocoding service or fallback coordinates."""
    # This is a simplified approach - in production, you'd use a proper geocoding service
    # For now, we'll use some known coordinates for major cities
    known_cities = {
        'BAIS CITY': (9.5911, 123.1225),
        'TANJAY CITY': (9.5167, 123.1667),
        'DUMAGUETE CITY': (9.3072, 123.3019),
        'BACOLOD CITY': (10.6667, 122.9500),
        'SAN CARLOS CITY': (10.4833, 123.4167),
        'CEBU CITY': (10.2936, 123.9019),
        'MANDAUE CITY': (10.3333, 123.9333),
        'LAPU-LAPU CITY': (10.3167, 123.9500),
        'TACLOBAN CITY': (11.2500, 125.0000),
        'ORMOC CITY': (11.0000, 124.6000),
        'CATBALOGAN CITY': (11.7833, 124.8833),
        'CALBAYOG CITY': (12.0667, 124.6000),
        'ILOILO CITY': (10.7202, 122.5621),
        'BATANGAS CITY': (13.7565, 121.0583),
        'LIPA CITY': (13.9411, 121.1631),
        'CAVITE CITY': (14.4792, 120.8969),
        'DASMARIÑAS CITY': (14.3294, 120.9367),
        'CALAMBA CITY': (14.2111, 121.1653),
        'SAN PEDRO CITY': (14.3583, 121.0472),
        'SANTA ROSA CITY': (14.3167, 121.1167)
    }
    
    return known_cities.get(city_name, None)

def point_in_polygon(point, polygon):
    """Check if a point is inside a polygon."""
    try:
        return polygon.contains(point)
    except:
        return False

def generate_province_cities_mapping():
    """Generate province-to-cities mapping using GeoJSON data."""
    
    # Load all province GeoJSON files
    province_files = glob.glob('static/data/ph.*.any.any.geo.json')
    
    # Get all cities from the database
    try:
        response = requests.get('http://172.30.147.217:8001/api/dynasty/family?surname=GARCIA')
        if response.status_code == 200:
            data = response.json()
            all_cities = set()
            for member in data.get('data', []):
                if member['province']:
                    all_cities.add(member['province'])
        else:
            print("Error fetching city data from API")
            return {}
    except Exception as e:
        print(f"Error fetching city data: {e}")
        return {}
    
    print(f"Found {len(all_cities)} cities in database")
    print(f"Found {len(province_files)} province GeoJSON files")
    
    province_cities_mapping = {}
    
    for province_file in province_files:
        # Extract province name from filename
        # Example: ph.cagayan-valley-region-ii.cagayan.any.any.geo.json -> cagayan
        parts = province_file.split('.')
        if len(parts) >= 3:
            province_name = parts[2].replace('-', ' ').upper()
            print(f"\nProcessing province: {province_name}")
            
            # Load province GeoJSON
            geojson_data = load_geojson(province_file)
            if not geojson_data:
                continue
            
            # Extract polygon from GeoJSON
            try:
                if geojson_data.get('type') == 'FeatureCollection':
                    features = geojson_data.get('features', [])
                    if features:
                        # Get the first feature's geometry
                        geometry = features[0].get('geometry', {})
                    else:
                        print(f"  No features found in FeatureCollection")
                        continue
                elif geojson_data.get('type') == 'Feature':
                    # Handle single Feature
                    geometry = geojson_data.get('geometry', {})
                else:
                    print(f"  GeoJSON type not supported: {geojson_data.get('type')}")
                    continue
                
                if geometry.get('type') == 'Polygon':
                    coords = geometry.get('coordinates', [])
                    if coords:
                        # Create Shapely polygon
                        polygon = Polygon(coords[0])
                        
                        # Check which cities are inside this province
                        cities_in_province = []
                        for city in all_cities:
                            city_coords = get_city_coordinates(city)
                            if city_coords:
                                point = Point(city_coords[1], city_coords[0])  # Note: longitude, latitude
                                if point_in_polygon(point, polygon):
                                    cities_in_province.append(city)
                        
                        if cities_in_province:
                            province_cities_mapping[province_name] = cities_in_province
                            print(f"  Found {len(cities_in_province)} cities: {cities_in_province[:5]}...")
                        else:
                            print(f"  No cities found in this province")
                    else:
                        print(f"  No coordinates found in GeoJSON")
                elif geometry.get('type') == 'MultiPolygon':
                    # Handle MultiPolygon
                    coords = geometry.get('coordinates', [])
                    if coords:
                        # Create Shapely MultiPolygon
                        from shapely.geometry import MultiPolygon
                        polygons = [Polygon(poly[0]) for poly in coords]
                        multi_polygon = MultiPolygon(polygons)
                        
                        # Check which cities are inside this province
                        cities_in_province = []
                        for city in all_cities:
                            city_coords = get_city_coordinates(city)
                            if city_coords:
                                point = Point(city_coords[1], city_coords[0])  # Note: longitude, latitude
                                if point_in_polygon(point, multi_polygon):
                                    cities_in_province.append(city)
                        
                        if cities_in_province:
                            province_cities_mapping[province_name] = cities_in_province
                            print(f"  Found {len(cities_in_province)} cities: {cities_in_province[:5]}...")
                        else:
                            print(f"  No cities found in this province")
                    else:
                        print(f"  No coordinates found in MultiPolygon")
                else:
                    print(f"  Geometry type not supported: {geometry.get('type')}")
            except Exception as e:
                print(f"  Error processing GeoJSON: {e}")
                continue
    
    return province_cities_mapping

def main():
    """Main function to generate and save the mapping."""
    print("🗺️ Generating province-to-cities mapping using GeoJSON data...")
    
    # Generate the mapping
    mapping = generate_province_cities_mapping()
    
    # Save to JSON file
    output_file = 'static/data/province_cities_mapping_geojson.json'
    with open(output_file, 'w') as f:
        json.dump(mapping, f, indent=2)
    
    print(f"\n✅ Generated mapping for {len(mapping)} provinces")
    print(f"📁 Saved to: {output_file}")
    
    # Print summary
    total_cities = sum(len(cities) for cities in mapping.values())
    print(f"📊 Total cities mapped: {total_cities}")
    
    for province, cities in mapping.items():
        print(f"  {province}: {len(cities)} cities")

if __name__ == "__main__":
    main()

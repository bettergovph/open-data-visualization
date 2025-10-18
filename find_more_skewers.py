#!/usr/bin/env python3
"""Find vertical alignment skewers across all of Philippines, excluding Metro Manila range"""

import requests
import os
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv('.env')

# Parse MEILI_HTTP_ADDR
meili_addr = os.getenv('MEILI_HTTP_ADDR', 'localhost:7700')
if ':' in meili_addr:
    meilisearch_host, meilisearch_port = meili_addr.split(':')
else:
    meilisearch_host = 'localhost'
    meilisearch_port = '7700'

meilisearch_key = os.getenv('MEILI_MASTER_KEY', '')

url = f'http://{meilisearch_host}:{meilisearch_port}/indexes/bettergov_flood_control/documents'

headers = {}
if meilisearch_key:
    headers['Authorization'] = f'Bearer {meilisearch_key}'

all_projects = []
offset = 0
limit = 1000

print("🔍 Fetching flood control projects from MeiliSearch...")

while True:
    response = requests.get(f'{url}?offset={offset}&limit={limit}', headers=headers)
    if not response.ok:
        print(f"⚠️  MeiliSearch request failed: {response.status_code}")
        break
    
    data = response.json()
    results = data.get('results', [])
    
    if not results:
        break
    
    all_projects.extend(results)
    offset += len(results)
    
    if len(results) < limit:
        break

print(f"✅ Fetched {len(all_projects)} projects total\n")

# Existing Metro Manila skewers latitude ranges (to exclude)
existing_ranges = [
    (14.394145, 14.603226),  # Lng 121.00206: 23.2km
]

# Group by longitude (round to 5 decimals)
longitude_groups = defaultdict(list)
for project in all_projects:
    lng = None
    lat = None
    coords = project.get('_geo')
    if coords and coords.get('lng') and coords.get('lat'):
        lng = coords['lng']
        lat = coords['lat']
    elif project.get('Longitude') and project.get('Latitude'):
        lng = project.get('Longitude')
        lat = project.get('Latitude')
    
    if lng is not None and lat is not None:
        lng_rounded = round(lng, 5)
        longitude_groups[lng_rounded].append({
            'lng': lng,
            'lat': lat,
            'project': project
        })

# Find vertical alignments with different latitudes
all_alignments = []
for lng, projects in longitude_groups.items():
    if len(projects) > 1:
        # Check if latitudes are different
        latitudes = set(round(p['lat'], 6) for p in projects)
        if len(latitudes) > 1:
            # Calculate latitude range
            min_lat = min(p['lat'] for p in projects)
            max_lat = max(p['lat'] for p in projects)
            lat_range = max_lat - min_lat
            
            # Check if this range overlaps with existing Metro Manila skewers
            overlaps_existing = any(
                not (max_lat < existing[0] or min_lat > existing[1])
                for existing in existing_ranges
            )
            
            if not overlaps_existing and lat_range > 0.01:  # At least 1km apart
                distance_km = lat_range * 111
                
                all_alignments.append({
                    'lng': lng,
                    'projects': projects,
                    'lat_range': lat_range,
                    'distance_km': distance_km,
                    'min_lat': min_lat,
                    'max_lat': max_lat,
                    'count': len(projects)
                })

# Sort by distance (longest skewers first)
all_alignments.sort(key=lambda x: x['distance_km'], reverse=True)

print(f"🔍 Found {len(all_alignments)} NEW vertical alignments (excluding Metro Manila range)")
print(f"    Showing top 20:\n")

for idx, alignment in enumerate(all_alignments[:20], 1):
    lng = alignment['lng']
    projects = alignment['projects']
    distance_km = alignment['distance_km']
    
    print(f"#{idx} Longitude {lng}: {len(projects)} projects, {distance_km:.1f} km apart")
    print(f"   Lat range: {alignment['min_lat']:.6f} to {alignment['max_lat']:.6f}")
    
    # Show sample projects
    for p in sorted(projects, key=lambda x: x['lat'])[:5]:
        proj = p['project']
        name = (proj.get('ProjectDescription') or 'Unnamed')[:70]
        city = ((proj.get('City') or proj.get('Municipality') or 'Unknown')[:25])
        province = (proj.get('Province') or 'Unknown')[:20]
        print(f"   Lat: {p['lat']:>10.6f} | {province:20} | {city:25} | {name}")
    
    if len(projects) > 5:
        print(f"   ... and {len(projects) - 5} more projects on this longitude")
    print()

# Export top 10 for adding to the circles page
print("\n📋 JavaScript data for top 10 NEW skewers:\n")
print("const newSkewers = [")
for alignment in all_alignments[:10]:
    projects = sorted(alignment['projects'], key=lambda x: x['lat'])
    print(f"    {{")
    print(f"        longitude: {alignment['lng']},")
    print(f"        projectCount: {len(projects)},")
    print(f"        distanceKm: {alignment['distance_km']:.1f},")
    print(f"        projects: [")
    for p in projects[:6]:  # Limit to 6 projects per skewer for clarity
        proj = p['project']
        name = (proj.get('ProjectDescription') or 'Unnamed')[:60].replace("'", "\\'")
        city = ((proj.get('City') or proj.get('Municipality') or 'Unknown')[:30]).replace("'", "\\'")
        print(f"            {{ lat: {p['lat']}, lng: {p['lng']}, city: '{city}', name: '{name}' }},")
    print(f"        ]")
    print(f"    }},")
print("];")


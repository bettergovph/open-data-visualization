#!/usr/bin/env python3
"""Check for vertically aligned projects from Benguet down to Angeles City area"""

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

url = f"http://{meilisearch_host}:{meilisearch_port}/indexes/bettergov_flood_control/documents"

headers = {}
if meilisearch_key:
    headers['Authorization'] = f'Bearer {meilisearch_key}'

all_projects = []
offset = 0
limit = 1000

print("🔍 Fetching flood control projects from MeiliSearch...")

while True:
    response = requests.get(f"{url}?offset={offset}&limit={limit}", headers=headers)
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

print(f"✅ Fetched {len(all_projects)} projects")

# Filter for area from Benguet to Angeles (approx lat 15.0 to 16.5, lng 120.0 to 121.0)
# Benguet: ~16.4°N, 120.6°E
# Angeles: ~15.1°N, 120.6°E
region_projects = []
for p in all_projects:
    coords = p.get('_geo')
    if coords and coords.get('lat') and coords.get('lng'):
        lat = coords['lat']
        lng = coords['lng']
        # Northern Luzon corridor
        if 15.0 <= lat <= 16.6 and 120.0 <= lng <= 121.2:
            region_projects.append(p)

print(f"📍 Found {len(region_projects)} projects in Benguet-to-Angeles corridor")
print()

# Group by exact longitude (to find vertical alignment)
longitude_groups = defaultdict(list)
for project in region_projects:
    coords = project.get('_geo')
    if coords and coords.get('lng') is not None:
        lng = coords['lng']
        longitude_groups[lng].append(project)

# Find longitudes with multiple projects (vertically aligned)
aligned = [(lng, projects) for lng, projects in longitude_groups.items() if len(projects) > 1]
aligned.sort(key=lambda x: len(x[1]), reverse=True)

print(f"🔍 Found {len(aligned)} longitudes with multiple projects (VERTICALLY ALIGNED)")
print(f"    This means projects are on the SAME VERTICAL LINE on the map\n")

# Show top alignments
for lng, projects in aligned[:30]:  # Show top 30
    print(f"📍 Longitude: {lng} - {len(projects)} projects PERFECTLY VERTICALLY ALIGNED")
    
    # Show all projects on this longitude with their different latitudes
    for p in projects[:15]:  # Limit to 15 per longitude
        lat = p.get('_geo', {}).get('lat', 'N/A')
        name = p.get('ProjectDescription', 'Unnamed')[:60]
        city = p.get('City', 'Unknown')
        province = p.get('Province', 'Unknown')
        cost = p.get('ProjectCost', 0)
        try:
            cost_formatted = f"₱{float(cost):,.0f}" if cost else 'N/A'
        except:
            cost_formatted = 'N/A'
        print(f"   Lat: {lat:>10.6f} | {province:15} | {city:20} | {cost_formatted:>15} | {name}")
    
    if len(projects) > 15:
        print(f"   ... and {len(projects) - 15} more projects on this exact longitude")
    print()

print(f"\n📊 Summary:")
print(f"   Total projects in region: {len(region_projects)}")
print(f"   Unique longitudes: {len(longitude_groups)}")
print(f"   Longitudes with >1 project (vertically aligned): {len(aligned)}")
total_aligned = sum(len(projects) for _, projects in aligned)
print(f"   Total projects on aligned longitudes: {total_aligned}")
if len(region_projects) > 0:
    print(f"   Percentage of projects with vertical alignment: {(total_aligned/len(region_projects)*100):.2f}%")

print(f"\n🔝 Top 15 most aligned longitudes:")
for lng, projects in aligned[:15]:
    print(f"   {lng}: {len(projects)} projects on same vertical line")


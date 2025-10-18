#!/usr/bin/env python3
"""Check for vertically aligned projects (same longitude) in Pampanga"""

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

# Filter for Pampanga
pampanga_projects = [p for p in all_projects if p.get('Province', '').upper() == 'PAMPANGA']
print(f"📍 Found {len(pampanga_projects)} projects in Pampanga")
print()

# Group by longitude (rounded to 4 decimals for ~10m tolerance)
longitude_groups = defaultdict(list)
for project in pampanga_projects:
    coords = project.get('_geo')
    if coords and coords.get('lng') is not None:
        lng = round(coords['lng'], 4)  # Round to 4 decimals (~11m tolerance)
        longitude_groups[lng].append(project)

# Find longitudes with multiple projects (vertically aligned)
aligned = [(lng, projects) for lng, projects in longitude_groups.items() if len(projects) > 1]
aligned.sort(key=lambda x: len(x[1]), reverse=True)

print(f"🔍 Found {len(aligned)} longitudes with multiple Pampanga projects (vertically aligned)")
print()

for lng, projects in aligned[:30]:  # Show top 30
    print(f"📍 Longitude: {lng} - {len(projects)} projects aligned vertically")
    
    # Show all projects on this longitude
    for p in projects[:10]:  # Limit to 10 for readability
        lat = p.get('_geo', {}).get('lat', 'N/A')
        name = p.get('ProjectDescription', 'Unnamed')[:70]
        city = p.get('City', 'N/A')
        cost = p.get('ProjectCost', 'N/A')
        print(f"   - Lat: {lat:>10}, City: {city:20}, Cost: {cost}")
        print(f"     {name}")
    
    if len(projects) > 10:
        print(f"   ... and {len(projects) - 10} more projects on this longitude")
    print()

print(f"\n📊 Summary:")
print(f"   Total Pampanga projects: {len(pampanga_projects)}")
print(f"   Longitudes with alignment (>1 project): {len(aligned)}")
total_aligned = sum(len(projects) for _, projects in aligned)
print(f"   Total projects on aligned longitudes: {total_aligned}")
if len(pampanga_projects) > 0:
    print(f"   Percentage: {(total_aligned/len(pampanga_projects)*100):.2f}%")

# Find the most common longitudes
print(f"\n🔝 Top 10 most aligned longitudes:")
for lng, projects in aligned[:10]:
    print(f"   {lng}: {len(projects)} projects")


#!/usr/bin/env python3
"""Check for vertically aligned projects (same longitude) in Angeles City"""

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

# Filter for Angeles City
angeles_projects = [p for p in all_projects if 'ANGELES' in p.get('City', '').upper()]
print(f"📍 Found {len(angeles_projects)} projects in Angeles City")
print()

# Show all unique longitudes first
all_longitudes = set()
for project in angeles_projects:
    coords = project.get('_geo')
    if coords and coords.get('lng') is not None:
        all_longitudes.add(coords['lng'])

print(f"📊 Total unique longitudes: {len(all_longitudes)}")
print(f"   (If much less than {len(angeles_projects)} projects, there's alignment)")
print()

# Group by exact longitude
longitude_groups = defaultdict(list)
for project in angeles_projects:
    coords = project.get('_geo')
    if coords and coords.get('lng') is not None:
        lng = coords['lng']
        longitude_groups[lng].append(project)

# Find longitudes with multiple projects (vertically aligned)
aligned = [(lng, projects) for lng, projects in longitude_groups.items() if len(projects) > 1]
aligned.sort(key=lambda x: len(x[1]), reverse=True)

print(f"🔍 Found {len(aligned)} longitudes with multiple Angeles projects (EXACT vertical alignment)")
print()

for lng, projects in aligned[:20]:  # Show top 20
    print(f"📍 Longitude: {lng} - {len(projects)} projects PERFECTLY VERTICALLY ALIGNED")
    
    # Show all projects on this longitude
    for p in projects:
        lat = p.get('_geo', {}).get('lat', 'N/A')
        name = p.get('ProjectDescription', 'Unnamed')[:70]
        cost = p.get('ProjectCost', 0)
        try:
            cost_formatted = f"₱{float(cost):,.2f}" if cost else 'N/A'
        except:
            cost_formatted = 'N/A'
        print(f"   Lat: {lat:>11.7f} | {cost_formatted:>20} | {name}")
    print()

print(f"\n📊 Summary:")
print(f"   Total Angeles City projects: {len(angeles_projects)}")
print(f"   Unique longitudes: {len(all_longitudes)}")
print(f"   Longitudes with >1 project (vertically aligned): {len(aligned)}")
total_aligned = sum(len(projects) for _, projects in aligned)
print(f"   Total projects on aligned longitudes: {total_aligned}")
if len(angeles_projects) > 0:
    print(f"   Percentage of projects with alignment: {(total_aligned/len(angeles_projects)*100):.2f}%")

# List the most aligned longitudes
print(f"\n🔝 Top 10 most aligned longitudes in Angeles City:")
for lng, projects in aligned[:10]:
    print(f"   {lng}: {len(projects)} projects")


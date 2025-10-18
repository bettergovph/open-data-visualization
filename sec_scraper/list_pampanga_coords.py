#!/usr/bin/env python3
"""List all Pampanga project coordinates to identify visual patterns"""

import requests
import os
from dotenv import load_dotenv

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

while True:
    response = requests.get(f"{url}?offset={offset}&limit={limit}", headers=headers)
    if not response.ok:
        break
    
    data = response.json()
    results = data.get('results', [])
    
    if not results:
        break
    
    all_projects.extend(results)
    offset += len(results)
    
    if len(results) < limit:
        break

# Filter for Pampanga
pampanga_projects = [p for p in all_projects if p.get('Province', '').upper() == 'PAMPANGA']

print(f"📍 Found {len(pampanga_projects)} projects in Pampanga\n")
print("Longitude, Latitude, City, Project Name")
print("-" * 120)

# Sort by longitude to see patterns
pampanga_with_coords = []
for p in pampanga_projects:
    coords = p.get('_geo')
    if coords and coords.get('lng') is not None and coords.get('lat') is not None:
        pampanga_with_coords.append({
            'lng': coords['lng'],
            'lat': coords['lat'],
            'city': p.get('City', 'N/A'),
            'name': p.get('ProjectDescription', 'Unnamed')[:60]
        })

pampanga_with_coords.sort(key=lambda x: x['lng'])

for p in pampanga_with_coords:
    print(f"{p['lng']:>12.6f}, {p['lat']:>11.6f}, {p['city']:20}, {p['name']}")


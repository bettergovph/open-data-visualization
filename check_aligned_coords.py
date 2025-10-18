#!/usr/bin/env python3
"""Check for projects with suspiciously aligned coordinates (same longitude)"""

import requests
import os
from dotenv import load_dotenv
from collections import Counter

load_dotenv('.env')

# Parse MEILI_HTTP_ADDR (format: "127.0.0.1:7700")
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
print()

# Count projects by longitude
longitude_counts = Counter()
for project in all_projects:
    coords = project.get('_geo')
    if coords and coords.get('lng'):
        longitude_counts[coords['lng']] += 1

# Find longitudes with many projects
suspicious = [(lng, count) for lng, count in longitude_counts.items() if count > 5]
suspicious.sort(key=lambda x: x[1], reverse=True)

print(f"🔍 Found {len(suspicious)} longitudes with >5 projects (suspiciously aligned)")
print()

for lng, count in suspicious[:20]:
    print(f"📍 Longitude: {lng} - {count} projects perfectly aligned")
    
    # Show sample projects
    samples = [p for p in all_projects if p.get('_geo', {}).get('lng') == lng][:5]
    for p in samples:
        lat = p.get('_geo', {}).get('lat', 'N/A')
        name = p.get('ProjectDescription', 'Unnamed')[:60]
        print(f"   - Lat: {lat}, Name: {name}")
    
    if count > 5:
        print(f"   ... and {count - 5} more projects on this exact longitude")
    print()

print(f"\n📊 Summary:")
print(f"   Total projects: {len(all_projects)}")
print(f"   Suspicious longitudes (>5 projects): {len(suspicious)}")
total_suspicious = sum(count for _, count in suspicious)
print(f"   Total projects on suspicious longitudes: {total_suspicious}")
if len(all_projects) > 0:
    print(f"   Percentage: {(total_suspicious/len(all_projects)*100):.2f}%")


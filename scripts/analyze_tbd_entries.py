#!/usr/bin/env python3
"""
Analyze and fix TBD/Unknown congressman entries
"""
import json

# Load data
with open('static/data/districts.json', 'r') as f:
    districts = json.load(f)

with open('static/data/integrated_matrix.json', 'r') as f:
    matrix = json.load(f)

# Find TBD entries
print("=== TBD/Unknown Entries in Matrix ===")
for entry in matrix['ranking']:
    if entry['congressman'] in ['TBD', 'Unknown', 'TBA']:
        print(f"  {entry['congressman']}: {entry['district']}, {entry['province']}")
        print(f"    Projects: {entry['project_count']}")
        if entry['projects']:
            print(f"    Sample: {entry['projects'][0]['name'][:100]}")
        print()

# Check Bulacan
print("\n=== Bulacan Districts ===")
bulacan = districts['districts'].get('Bulacan', {})
print(f"Representatives: {bulacan.get('representatives', {})}")
print(f"Municipalities count: {len(bulacan.get('municipalities', {}))}")

# Check San Jose del Monte
print("\n=== San Jose del Monte Check ===")
sjdm = districts['districts'].get('San Jose del Monte', {})
print(f"SJDM as city entry: {sjdm}")

# List all city entries that might be in Bulacan
print("\n=== City entries that might be Bulacan ===")
for key in districts['districts'].keys():
    if 'monte' in key.lower() or 'malolos' in key.lower() or 'meycauayan' in key.lower():
        print(f"  {key}: {districts['districts'][key].get('representatives', {})}")

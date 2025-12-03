#!/usr/bin/env python3
"""Diagnose GeoJSON file structure to understand categorization."""

import json
from pathlib import Path
from collections import Counter

geojson_dir = Path.home() / 'geoph' / 'geojson'
files = list(geojson_dir.rglob('*.geo.json'))

print(f"Total files: {len(files)}\n")

# Check directory structure
path_types = Counter()
type_counts = Counter()
level_counts = Counter()
has_city_name = 0
has_municipality_name = 0
has_province_name = 0

for f in files[:1000]:  # Sample first 1000
    path_str = str(f).lower()
    if '/province/' in path_str:
        path_types['province'] += 1
    elif '/city/' in path_str:
        path_types['city'] += 1
    elif '/municipality/' in path_str:
        path_types['municipality'] += 1
    elif '/barangay/' in path_str:
        path_types['barangay'] += 1
    else:
        path_types['other'] += 1
    
    try:
        d = json.load(open(f))
        p = d.get('properties', {})
        t = p.get('type', '').lower()
        l = str(p.get('level', ''))
        type_counts[t] += 1
        level_counts[l] += 1
        
        if p.get('city_name'):
            has_city_name += 1
        if p.get('municipality_name'):
            has_municipality_name += 1
        if p.get('province_name'):
            has_province_name += 1
    except:
        pass

print("Path-based categorization (first 1000 files):")
for k, v in sorted(path_types.items()):
    print(f"  {k}: {v}")

print("\nType field values (first 1000 files):")
for k, v in sorted(type_counts.items()):
    print(f"  {k}: {v}")

print("\nLevel field values (first 1000 files):")
for k, v in sorted(level_counts.items()):
    print(f"  {k}: {v}")

print(f"\nHas city_name: {has_city_name}")
print(f"Has municipality_name: {has_municipality_name}")
print(f"Has province_name: {has_province_name}")

# Check a few sample files
print("\n\nSample files:")
for f in files[:5]:
    try:
        d = json.load(open(f))
        p = d.get('properties', {})
        print(f"\n{f.name}:")
        print(f"  Path: {str(f)[:100]}")
        print(f"  Type: {p.get('type')}")
        print(f"  Level: {p.get('level')}")
        print(f"  Name fields: province={bool(p.get('province_name'))}, city={bool(p.get('city_name'))}, municipality={bool(p.get('municipality_name'))}")
    except Exception as e:
        print(f"  Error: {e}")












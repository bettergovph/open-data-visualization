#!/usr/bin/env python3
"""Debug Patricia Calderon and Isidro Ungab projects"""
import json

with open('static/data/integrated_matrix.json', 'r') as f:
    matrix = json.load(f)

print("=== Patricia Calderon (Cebu 7th) - projects should NOT be Cebu City ===")
for entry in matrix['ranking']:
    if 'Calderon' in entry.get('congressman', ''):
        print(f"  {entry['congressman']}: {entry['district']}, {entry['province']}")
        print(f"    Project count: {entry['project_count']}")
        for p in entry['projects'][:5]:
            print(f"    - {p['name'][:100]}")
        print()

print("\n=== Isidro Ungab (Davao City 3rd) - which projects are wrong? ===")
for entry in matrix['ranking']:
    if 'Ungab' in entry.get('congressman', ''):
        print(f"  {entry['congressman']}: {entry['district']}, {entry['province']}")
        print(f"    Project count: {entry['project_count']}")
        # Show first 10 projects
        for p in entry['projects'][:10]:
            print(f"    - {p['name'][:100]}")
        print()

print("\n=== Cebu City congressmen in matrix ===")
for entry in matrix['ranking']:
    if 'cebu city' in entry.get('province', '').lower() or 'cebu city' in entry.get('district', '').lower():
        print(f"  {entry['congressman']}: {entry['district']}, {entry['province']}")
        print(f"    Project count: {entry['project_count']}")

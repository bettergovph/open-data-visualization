#!/usr/bin/env python3
"""Fix Batangas municipality district mappings - Tanauan City and Lipa City should be 6th District"""
import json

with open('static/data/districts.json', 'r') as f:
    data = json.load(f)

batangas = data['districts']['Batangas']
munis = batangas['municipalities']

# Fix Tanauan City and Lipa City - they should be 6th District, not 1st
fixes = {
    'Tanauan City': '6th District',
    'City of Tanauan': '6th District', 
    'Lipa City': '6th District',
    'City of Lipa': '6th District'
}

for muni, correct_dist in fixes.items():
    if muni in munis:
        old = munis[muni]
        munis[muni] = correct_dist
        print(f"  ✅ {muni}: {old} → {correct_dist}")
    else:
        munis[muni] = correct_dist
        print(f"  ➕ Added {muni}: {correct_dist}")

# Save
with open('static/data/districts.json', 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("💾 Saved districts.json")

#!/usr/bin/env python3
"""Fix Batangas district assignments - Leandro Leviste is 6th District not 1st"""
import json

with open('static/data/districts.json', 'r') as f:
    data = json.load(f)

# Check current Batangas representatives
batangas = data['districts'].get('Batangas', {})
reps = batangas.get('representatives', {})

print("Current Batangas representatives:")
for k, v in reps.items():
    print(f"  {k}: {v}")

# Based on user feedback: Leandro Legarda Leviste should be 6th District
# Let me check Wikipedia 20th Congress data for correct assignments
print("\n--- Wikipedia 20th Congress data for Batangas ---")
with open('static/data/20th_congress_representatives.json', 'r') as f:
    wiki = json.load(f)
for entry in wiki:
    if entry.get('province') == 'Batangas':
        print(f"  {entry['district']}: {entry['representative']}")

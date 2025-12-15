#!/usr/bin/env python3
"""Check and fix Batangas congressman data"""
import json

# Load data
with open('static/data/20th_congress_representatives.json', 'r') as f:
    wiki = json.load(f)

with open('static/data/districts.json', 'r') as f:
    districts = json.load(f)

print("=== Wikipedia Data for Batangas ===")
for entry in wiki:
    if 'Batangas' in entry.get('province', ''):
        print(f"  {entry['district']}: {entry['representative']}")

print("\n=== districts.json for Batangas ===")
batangas = districts['districts'].get('Batangas', {})
reps = batangas.get('representatives', {})
for dist, rep in reps.items():
    print(f"  {dist}: {rep}")

print("\n=== Fixing 6th District ===")
# Find Wikipedia entry for 6th District
for entry in wiki:
    if entry.get('province') == 'Batangas' and entry.get('district') == '6th':
        correct_rep = entry['representative']
        print(f"Correct representative from Wikipedia: {correct_rep}")
        
        # Update districts.json
        if '6th District' in reps:
            old_rep = reps['6th District']
            print(f"Old value: {old_rep}")
            districts['districts']['Batangas']['representatives']['6th District'] = f"{correct_rep} (2022-present)"
            print(f"New value: {correct_rep} (2022-present)")
            
            # Save
            with open('static/data/districts.json', 'w') as f:
                json.dump(districts, f, indent=2, ensure_ascii=False)
            print("Saved!")
        break

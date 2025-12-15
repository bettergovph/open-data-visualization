#!/usr/bin/env python3
"""Add Pateros and Biñan to districts.json"""
import json

with open('static/data/districts.json', 'r') as f:
    data = json.load(f)

# Add Pateros (municipality in Metro Manila with Taguig)
# Taguig-Pateros is a combined district
if 'Pateros' not in data['districts']:
    data['districts']['Pateros'] = {
        "entity_type": "municipality",
        "all_districts": ["Lone District"],
        "municipalities": {"Pateros": "Lone District"},
        "representatives": {
            "Lone District": "Daniel Bocobo (2022-present)"
        }
    }
    print("✅ Added Pateros")

# Add Biñan (city in Laguna)
if 'Biñan' not in data['districts']:
    data['districts']['Biñan'] = {
        "entity_type": "city",
        "all_districts": ["Lone District"],
        "municipalities": {"Biñan": "Lone District"},
        "representatives": {
            "Lone District": "Len Alonte (2022-present)"
        }
    }
    print("✅ Added Biñan")

with open('static/data/districts.json', 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print("💾 Saved")

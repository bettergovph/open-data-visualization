#!/usr/bin/env python3
"""
Add remaining missing city/province congressmen to districts.json
"""
import json
from pathlib import Path

DISTRICTS_FILE = Path("static/data/districts.json")

# Remaining TBD entries that need congressmen:
# CITY OF PARAÑAQUE, CEBU (Cordova), LEYTE (Isabel), BUKIDNON, CAMARINES SUR, CITY OF ANGELES, CITY OF MAKATI
# Using Wikipedia 20th Congress data

ADDITIONS = {
    # Cities that need to be added as top-level entries
    "Parañaque": {
        "entity_type": "city",
        "all_districts": ["1st District", "2nd District"],
        "municipalities": {"Parañaque": "1st District"},
        "representatives": {
            "1st District": "Eric Olivarez (2022-present)",
            "2nd District": "Gustavo Tambunting (2022-present)"
        }
    },
    "Angeles": {
        "entity_type": "city", 
        "all_districts": ["Lone District"],
        "municipalities": {"Angeles": "Lone District"},
        "representatives": {
            "Lone District": "Carmela Lazatin (2022-present)"
        }
    },
    "Makati": {
        "entity_type": "city",
        "all_districts": ["1st District", "2nd District"],
        "municipalities": {"Makati": "1st District"},
        "representatives": {
            "1st District": "Luis Jose Campos Jr. (2022-present)",
            "2nd District": "Mar-len Abigail Binay (2022-present)"
        }
    }
}

def add_missing_cities():
    print("🔄 Loading districts.json...")
    with open(DISTRICTS_FILE, 'r') as f:
        data = json.load(f)
    
    for city, info in ADDITIONS.items():
        if city not in data['districts']:
            data['districts'][city] = info
            print(f"  ✅ Added {city}")
        else:
            print(f"  ⏭️ {city} already exists")
    
    with open(DISTRICTS_FILE, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"💾 Saved {DISTRICTS_FILE}")

if __name__ == '__main__':
    add_missing_cities()

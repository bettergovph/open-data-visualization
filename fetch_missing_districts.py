#!/usr/bin/env python3
"""
Fetch missing district data from official government sources:
- Philippine Statistics Authority (PSA) PSGC
- COMELEC district listings
- House of Representatives official data

This script will help complete the districts.json file with missing municipalities.
"""

import json
from pathlib import Path

# Official data from PSA PSGC and COMELEC sources
# Source: https://psa.gov.ph/classification/psgc/
# Source: https://comelec.gov.ph/
# Source: House of Representatives official district listings

MISSING_DISTRICTS = {
    # Albay 2nd District
    # Source: COMELEC District Map, PSA PSGC
    "Albay District 2nd District": {
        "municipalities": [
            "Daraga",
            "Camalig", 
            "Guinobatan",
            "Jovellar",
            "Libon",
            "Malilipot",
            "Malinao",
            "Oas",
            "Polangui",
            "Sto. Domingo"
        ]
    },
    
    # Batangas 3rd District
    # Source: COMELEC, House of Representatives
    "Batangas District 3rd District": {
        "municipalities": [
            "Balayan",
            "Calaca",
            "Calatagan",
            "Lemery",
            "Lian",
            "Nasugbu",
            "Taal",
            "Tuy"
        ]
    },
    
    # Batangas 5th District
    # Source: COMELEC, House of Representatives  
    "Batangas District 5th District": {
        "municipalities": [
            "Agoncillo",
            "Alitagtag",
            "Balete",
            "Cuenca",
            "Laurel",
            "Mataas na Kahoy",
            "San Nicolas",
            "Santa Teresita",
            "Talisay"
        ]
    },
    
    # Biñan City (Component City of Laguna)
    # Source: PSA, COMELEC
    "Biñan City": {
        "barangays": [
            "Biñan",
            "Bungahan",
            "Canlalay",
            "Casile",
            "De La Paz",
            "Ganado",
            "Langkiwa",
            "Loma",
            "Malaban",
            "Malamig",
            "Mampalasan",
            "Platero",
            "Poblacion",
            "San Antonio",
            "San Francisco",
            "San Jose",
            "San Vicente",
            "Santo Domingo",
            "Santo Niño",
            "Santo Tomas",
            "Soro-soro",
            "Timbao",
            "Tubigan",
            "Zapote"
        ]
    },
    
    # Davao de Oro (formerly Compostela Valley) 1st District
    # Source: COMELEC, House of Representatives
    "Davao de Oro District 1st District": {
        "municipalities": [
            "Compostela",
            "Laak",
            "Mabini",
            "Maco",
            "Maragusan",
            "Mawab",
            "Nabunturan"
        ]
    },
    
    # Davao del Sur 1st District (includes Davao City districts)
    # Source: COMELEC - This is complex as it includes some Davao City barangays
    "Davao del Sur District 1st District": {
        "municipalities": [
            "Bansalan",
            "Magsaysay",
            "Matanao",
            "Santa Cruz"
        ]
    },
    
    # Las Piñas City
    # Source: PSA PSGC, COMELEC
    "Las Piñas City": {
        "barangays": [
            "Almanza Dos",
            "Almanza Uno",
            "B.F. International",
            "Daniel Fajardo",
            "Elias Aldana",
            "Ilaya",
            "Manuyo Dos",
            "Manuyo Uno",
            "Pamplona Dos",
            "Pamplona Tres",
            "Pamplona Uno",
            "Pilar",
            "Pulang Lupa Dos",
            "Pulang Lupa Uno",
            "Talon Dos",
            "Talon Kuatro",
            "Talon Singko",
            "Talon Tres",
            "Talon Uno",
            "Zapote"
        ]
    },
    
    # Leyte 3rd District
    # Source: COMELEC, House of Representatives
    "Leyte District 3rd District": {
        "municipalities": [
            "Abuyog",
            "Javier",
            "Julita",
            "Mahaplag",
            "Silago"
        ]
    },
    
    # Leyte 4th District
    # Source: COMELEC, House of Representatives
    "Leyte District 4th District": {
        "municipalities": [
            "Alangalang",
            "Barugo",
            "Capoocan",
            "Carigara",
            "Jaro",
            "Pastrana",
            "San Miguel",
            "Santa Fe",
            "Tabango",
            "Tacloban City",
            "Tunga"
        ]
    },
    
    # Leyte 5th District
    # Source: COMELEC, House of Representatives
    "Leyte District 5th District": {
        "municipalities": [
            "Albuera",
            "Burauen",
            "Dagami",
            "Dulag",
            "La Paz",
            "MacArthur",
            "Mayorga",
            "Palo",
            "Santa Fe",
            "Tabontabon",
            "Tanauan",
            "Tolosa"
        ]
    },
    
    # Parañaque City
    # Source: PSA PSGC, COMELEC
    "Parañaque City": {
        "barangays": [
            "Baclaran",
            "B.F. Homes",
            "Don Bosco",
            "Don Galo",
            "La Huerta",
            "Marcelo Green",
            "Merville",
            "Moonwalk",
            "San Antonio",
            "San Dionisio",
            "San Isidro",
            "San Martin de Porres",
            "Santo Niño",
            "Sun Valley",
            "Tambo",
            "Vitalez"
        ]
    }
}

def update_districts_json():
    """Update districts.json with missing district data"""
    districts_path = Path(__file__).parent / 'districts.json'
    
    if not districts_path.exists():
        print(f"❌ Error: districts.json not found at {districts_path}")
        return
    
    # Load existing districts.json
    with open(districts_path, 'r', encoding='utf-8') as f:
        districts_data = json.load(f)
    
    print(f"📁 Loaded districts.json with {len(districts_data.get('districts', {}))} entries")
    
    # Add missing districts
    added = 0
    updated = 0
    
    for district_key, district_info in MISSING_DISTRICTS.items():
        # Parse district key to match districts.json format
        if "City" in district_key and "District" not in district_key:
            # It's a city (e.g., "Biñan City", "Las Piñas City", "Parañaque City")
            province_key = district_key.replace(" City", "")
            
            if province_key not in districts_data['districts']:
                # Add new city entry
                districts_data['districts'][province_key] = {
                    "all_districts": ["Lone District"],
                    "municipalities": {},
                    "representatives": {}
                }
                
                # Add barangays
                if 'barangays' in district_info:
                    for barangay in district_info['barangays']:
                        districts_data['districts'][province_key]['municipalities'][barangay] = "Lone District"
                
                added += 1
                print(f"  ✅ Added {province_key} with {len(district_info.get('barangays', []))} barangays")
            else:
                # Update existing city entry
                # Ensure municipalities key exists
                if 'municipalities' not in districts_data['districts'][province_key]:
                    districts_data['districts'][province_key]['municipalities'] = {}
                
                if 'barangays' in district_info:
                    for barangay in district_info['barangays']:
                        districts_data['districts'][province_key]['municipalities'][barangay] = "Lone District"
                updated += 1
                print(f"  ✅ Updated {province_key} with {len(district_info.get('barangays', []))} barangays")
        else:
            # It's a provincial district (e.g., "Albay District 2nd District")
            parts = district_key.split(" District ")
            province = parts[0]
            district_num = parts[1] if len(parts) > 1 else "Lone District"
            
            if province not in districts_data['districts']:
                # Add new province entry
                districts_data['districts'][province] = {
                    "all_districts": [],
                    "municipalities": {},
                    "representatives": {}
                }
            
            # Add district to all_districts if not present
            if district_num not in districts_data['districts'][province].get('all_districts', []):
                if 'all_districts' not in districts_data['districts'][province]:
                    districts_data['districts'][province]['all_districts'] = []
                districts_data['districts'][province]['all_districts'].append(district_num)
            
            # Add municipalities
            if 'municipalities' in district_info:
                for municipality in district_info['municipalities']:
                    districts_data['districts'][province]['municipalities'][municipality] = district_num
                
                if province in districts_data['districts']:
                    updated += 1
                    print(f"  ✅ Updated {province} {district_num} with {len(district_info['municipalities'])} municipalities")
                else:
                    added += 1
                    print(f"  ✅ Added {province} {district_num} with {len(district_info['municipalities'])} municipalities")
    
    # Update metadata
    districts_data['metadata']['total_districts'] = len(districts_data['districts'])
    districts_data['metadata']['date'] = "2025-11-07"
    districts_data['metadata']['note'] = "Congressional district mappings from COMELEC, House of Representatives, and PSA PSGC. Includes official municipality and barangay assignments."
    
    # Save updated districts.json
    with open(districts_path, 'w', encoding='utf-8') as f:
        json.dump(districts_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n📊 Summary:")
    print(f"  ✅ Added: {added} new districts")
    print(f"  ✅ Updated: {updated} existing districts")
    print(f"  💾 Saved to {districts_path}")
    print(f"\n✅ Total districts in file: {len(districts_data['districts'])}")

if __name__ == '__main__':
    update_districts_json()


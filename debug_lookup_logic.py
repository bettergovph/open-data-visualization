import json
import pandas as pd

def normalize_location_name(name):
    if name is None: return ""
    name = str(name).upper().strip()
    name = name.replace("CITY OF ", "").replace(" CITY", "")
    return name

def get_congressman(districts_data, province, district):
    prov_data = districts_data.get(province)
    
    # Priority 1: Case-Insensitive Match
    if not prov_data:
        province_lower = str(province).lower().strip()
        for k, v in districts_data.items():
            if k.lower().strip() == province_lower:
                prov_data = v
                break
    
    if not prov_data:
        # scan keys
        norm_prov = normalize_location_name(province)
        for k, v in districts_data.items():
            if normalize_location_name(k) == norm_prov:
                prov_data = v
                break
                
    if not prov_data: return f"TBD (Prov {province} not found)"
    
    reps = prov_data.get('representatives', {})
    rep = reps.get(district)
    return rep or f"TBD (Dist {district} not found in {province})"

with open('static/data/districts.json', 'r') as f:
    data = json.load(f)

districts = data.get('districts', {})

print(f"NCR, 4th District -> {get_congressman(districts, 'NCR', '4th District')}")
print(f"Quezon City, 4th District -> {get_congressman(districts, 'Quezon City', '4th District')}")
print(f"QUEZON CITY, 4th District -> {get_congressman(districts, 'QUEZON CITY', '4th District')}")

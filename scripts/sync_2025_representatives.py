
import json
import re
from pathlib import Path

BASE_DIR = Path("/home/joebert/open-data-visualization")
SOURCE_FILE = BASE_DIR / "static" / "data" / "20th_congress_representatives.json"
TARGET_FILE = BASE_DIR / "static" / "data" / "districts.json"

def normalize_key(name):
    # Normalize for key matching: remove "ctiy", "province", etc.
    if not name: return ""
    name = str(name).upper().strip()
    name = name.replace("CITY OF ", "").replace(" CITY", "").replace(" PROVINCE", "")
    return name

def format_district_key(raw_dist):
    # "1st" -> "1st District", "Lone" -> "Lone District"
    raw = str(raw_dist).strip()
    if raw.lower() == "lone":
        return "Lone District"
    # If it ends with "st", "nd", "rd", "th" but usually the source only has "1st", "2nd"
    # Source has "1st", "2nd", "Lone".
    # Districts.json expects "1st District".
    if raw.lower().endswith("district"):
        return raw # Already formatted?
    return f"{raw} District"

def sync_reps():
    print(f"Loading source: {SOURCE_FILE}")
    with open(SOURCE_FILE, 'r') as f:
        source_data = json.load(f)
    
    print(f"Loading target: {TARGET_FILE}")
    with open(TARGET_FILE, 'r') as f:
        districts_data = json.load(f)
        
    districts_map = districts_data.get("districts", {})
    
    updated_count = 0
    not_found_count = 0
    
    # Pre-compute target keys for easier lookup
    # Map NORMALIZED KEY -> REAL KEY
    target_keys_norm = {normalize_key(k): k for k in districts_map.keys()}

    for item in source_data:
        prov = item.get("province")
        dist_code = item.get("district")
        rep_name = item.get("representative")
        party = item.get("party")
        
        if not rep_name:
            continue
            
        # Find Province/City in Target
        norm_prov = normalize_key(prov)
        target_key = target_keys_norm.get(norm_prov)
        
        if not target_key:
            # Try fuzzy or specific overrides?
            # e.g. "Davao de Oro" vs "Compostela Valley" (if old name used)
            # e.g. "Samar (Western Samar)" vs "Samar"
            # Try searching substring
            for k_norm, k_real in target_keys_norm.items():
                if norm_prov in k_norm or k_norm in norm_prov:
                    target_key = k_real
                    print(f"  > Soft match: Source '{prov}' -> Target '{k_real}'")
                    break
        
        if not target_key:
            print(f"⚠️  Province/City NOT FOUND: {prov} ({rep_name})")
            not_found_count += 1
            continue
            
        # Get District Key
        target_dist_block = districts_map[target_key]
        dist_key = format_district_key(dist_code)
        
        # Check if district exists in target "representatives" map
        # If "representatives" doesn't exist, create it
        if "representatives" not in target_dist_block:
            target_dist_block["representatives"] = {}
            
        old_rep = target_dist_block["representatives"].get(dist_key, "TBD")
        
        # Update
        target_dist_block["representatives"][dist_key] = rep_name
        updated_count += 1
        
        # Debug small changes
        # print(f"Updated {target_key} - {dist_key}: {old_rep} -> {rep_name}")

    print(f"Sync Complete.")
    print(f"Updated: {updated_count} representatives")
    print(f"Not Found: {not_found_count} provinces")
    
    # Save
    with open(TARGET_FILE, 'w') as f:
        json.dump(districts_data, f, indent=4)
    print(f"Saved to {TARGET_FILE}")

if __name__ == "__main__":
    sync_reps()

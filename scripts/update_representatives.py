import json
import re
import os

def normalize_district(d):
    d = str(d).strip()
    if d.lower() == "lone": return "Lone District"
    if d.isdigit() or re.match(r"^\d+(st|nd|rd|th)$", d):
        if re.match(r"^\d+$", d):
            # 1 -> 1st
            if d == "1": d = "1st"
            elif d == "2": d = "2nd"
            elif d == "3": d = "3rd"
            else: d = d + "th"
        return f"{d} District"
    return d

def normalize_name(name):
    """Simple normalization for fuzzy matching."""
    return re.sub(r'[^a-zA-Z ]', '', name).lower()

def update_reps():
    districts_path = "static/data/districts.json"
    congress_path = "static/data/20th_congress_representatives.json"
    
    with open(districts_path, "r") as f:
        d_data = json.load(f)
        
    with open(congress_path, "r") as f:
        c_data = json.load(f)
        
    districts_map = d_data.get("districts", {})
    updates_count = 0
    
    for item in c_data:
        prov = item.get("province")
        dist = item.get("district")
        new_rep = item.get("representative")
        
        if not new_rep: continue
        
        # Normalize keys
        norm_dist = normalize_district(dist)
        
        # Locate in districts.json
        # Direct lookup first
        target_prov = None
        if prov in districts_map:
            target_prov = districts_map[prov]
        else:
            # Try fuzzy/alias match if needed?
            # For now assume mostly correct.
            # print(f"Warning: Province '{prov}' not found in districts.json")
            continue
            
        current_reps_map = target_prov.get("representatives", {})
        if norm_dist not in current_reps_map:
            # print(f"Warning: District '{norm_dist}' not found in {prov}")
            continue
            
        current_rep_str = current_reps_map[norm_dist]
        
        # Check if new rep is already there
        # We check if the name (or significant part) is present
        # current: "Jb Bernos (2025-present)" vs new: "Joseph Bernos"
        # Match by last name?
        new_last = new_rep.split()[-1]
        
        if new_last.lower() in current_rep_str.lower():
            # Assume matched. Check if string contains "present"
            # If it says (20xx-2025), maybe we need to reopen? 
            # But task says "new congressman with additional..."
            continue
        
        # If not matched, it's a NEW rep.
        # 1. Close old term: (xxxx-present) -> (xxxx-2025)
        updated_str = re.sub(r'\((\d{4})-present\)', r'(\1-2025)', current_rep_str)
        
        # 2. Append new term
        # Check if already has 2025-present to avoid dupes (unlikely if loop check passed but safety)
        if "2025-present" not in updated_str:
            updated_str += f"; {new_rep} (2025-present)"
            
        print(f"Updating {prov} {norm_dist}:")
        print(f"  Old: {current_rep_str}")
        print(f"  New: {updated_str}")
        
        target_prov["representatives"][norm_dist] = updated_str
        updates_count += 1

    print(f"Total Updates: {updates_count}")
    
    # Save
    with open(districts_path, "w") as f:
        json.dump(d_data, f, indent=4)

if __name__ == "__main__":
    update_reps()

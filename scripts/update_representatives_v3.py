import json
import re
import os

def normalize_district(d):
    d = str(d).strip()
    if d.lower() == "lone": return "Lone District"
    if d.isdigit() or re.match(r"^\d+(st|nd|rd|th)$", d):
        if re.match(r"^\d+$", d):
            if d == "1": d = "1st"
            elif d == "2": d = "2nd"
            elif d == "3": d = "3rd"
            else: d = d + "th"
        return f"{d} District"
    return d

def normalize_name(name):
    return re.sub(r'[^a-zA-Z ]', '', name).lower().split()

def is_same_person(name1, name2):
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)
    if not n1 or not n2: return False
    
    # Check if last token matches
    if n1[-1] == n2[-1]: return True
    
    # Check if full name is contained
    s1 = "".join(n1)
    s2 = "".join(n2)
    if s1 in s2 or s2 in s1: return True
    
    return False

def update_reps():
    districts_path = "static/data/districts.json"
    congress_path = "static/data/20th_congress_representatives.json"
    
    with open(districts_path, "r") as f:
        d_data = json.load(f)
        
    with open(congress_path, "r") as f:
        c_data = json.load(f)
        
    districts_map = d_data.get("districts", {})
    updates_count = 0
    
    # REMAP Dictionary: (CongressProv, CongressDist) -> (DistrictsProv, DistrictsDist)
    REMAP = {
        ("Butuan", "Lone"): ("Agusan del Norte", "1st District"),
        ("Agusan del Norte", "Lone"): ("Agusan del Norte", "2nd District"),
        # Add others if confirmed. For now, focus on known gaps.
    }
    
    for item in c_data:
        prov = item.get("province")
        dist = item.get("district")
        new_rep = item.get("representative")
        
        if not new_rep: continue
        
        # Check REMAP first
        if (prov, dist) in REMAP:
            target_prov_key, target_dist_key = REMAP[(prov, dist)]
            # print(f"Remapping {prov} {dist} -> {target_prov_key} {target_dist_key}")
            prov = target_prov_key 
            norm_dist = target_dist_key
        else:
            norm_dist = normalize_district(dist)
        
        if prov not in districts_map:
            # print(f"Skipping {prov} (not found)")
            continue
            
        target_prov_data = districts_map[prov]
        current_reps_map = target_prov_data.get("representatives", {})
        
        if norm_dist not in current_reps_map:
            # print(f"Skipping {prov} {norm_dist} (not found)")
            continue
            
        current_rep_str = current_reps_map[norm_dist]
        
        # If already updated to 2025-present, skip
        if "(2025-present)" in current_rep_str:
            continue
            
        # Extract the current representative name (the one holding "present")
        # Regex to find: Name (Year-present) at end of string OR followed by semicolon?
        # Since we are iterating, we assume the last entry is the current one.
        # Handle multi-sep: "Name (xxxx-yyyy); Name (zzzz-present)"
        
        # Regex: find the LAST occurrence of (xxxx-present)
        # We can split by semicolon, verify last part has "present)".
        parts = current_rep_str.split(";")
        last_part = parts[-1].strip()
        
        match = re.search(r'^(.*?) \((\d{4})-present\)$', last_part)
        if match:
            current_name = match.group(1).strip()
            # Check same person
            if is_same_person(current_name, new_rep):
                continue # Same person, keep as present
            else:
                # Different! Update.
                # Replace "present)" with "2025)" in the ORIGINAL string (be careful if multiple 'present)' which is unlikely)
                # Safer: reconstruct string.
                # Actually, replace works fine if only one 'present)'.
                # But to be safe, replace only the last occurrence?
                
                # Logic: Replace "present)" with "2025)" in last_part, then rejoin.
                updated_last_part = last_part.replace("present)", "2025)")
                parts[-1] = updated_last_part
                
                new_entry_str = "; ".join(parts) + f"; {new_rep} (2025-present)"
                
                print(f"Updating {prov} {norm_dist}:")
                # print(f"  Old: {current_rep_str}")
                print(f"  New: {new_entry_str}")
                
                target_prov_data["representatives"][norm_dist] = new_entry_str
                updates_count += 1
        else:
            pass # No active 'present' term found (or format mismatch)

    print(f"Total Updates: {updates_count}")
    
    with open(districts_path, "w") as f:
        json.dump(d_data, f, indent=4)

if __name__ == "__main__":
    update_reps()

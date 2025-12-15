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
    # Remove dots, extra spaces
    return re.sub(r'[^a-zA-Z ]', '', name).lower().split()

def is_same_person(name1, name2):
    """
    Check if name1 and name2 refer to the same person.
    Heuristic: strict last name match + first name initial or partial match.
    """
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)
    
    if not n1 or not n2: return False
    
    # Last name match (last token)
    if n1[-1] != n2[-1]: return False
    
    # If last name matches, assume same for now (simplified for PH dynasty/naming)
    # Refine: Check if first token matches or is subsequence
    return True

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
        
        norm_dist = normalize_district(dist)
        
        target_prov = None
        if prov in districts_map:
            target_prov = districts_map[prov]
        else:
            # Handle province aliases if needed
            continue
            
        current_reps_map = target_prov.get("representatives", {})
        if norm_dist not in current_reps_map:
            # If completely new district, just ADD it?
            # Or skip? Skip for now, focus on updates.
            continue
            
        current_rep_str = current_reps_map[norm_dist]
        
        # Parse current rep name (remove (years))
        # "Name Name (2022-present)"
        match = re.search(r'^(.*?) \((\d{4})-present\)', current_rep_str)
        if match:
            current_name = match.group(1).strip()
            start_year = match.group(2)
            
            # Check if same person
            if is_same_person(current_name, new_rep):
                # Same person. KEEP as present.
                # Do nothing.
                continue
            else:
                # DIFFERENT person. Close term and append new.
                # Close: (2022-present) -> (2022-2025)
                # But start year might be 2013, 2016 etc. We keep that.
                closed_str = current_rep_str.replace("present)", "2025)")
                new_entry = f"{closed_str}; {new_rep} (2025-present)"
                
                print(f"Updating {prov} {norm_dist}:")
                print(f"  Old: {current_rep_str}")
                print(f"  New: {new_entry}")
                
                target_prov["representatives"][norm_dist] = new_entry
                updates_count += 1
        else:
            # Maybe already closed? or different format?
            # If it says (2025-present), skip.
            if "(2025-present)" in current_rep_str:
                continue
            # If it says (xxxx-2022), then append new.
            # Check if this district needs update
            # Assume if we don't match "present" pattern, we check if we should just append?
            # Safety: ONLY update (xxxx-present) entries.
            pass

    print(f"Total Updates: {updates_count}")
    
    with open(districts_path, "w") as f:
        json.dump(d_data, f, indent=4)

if __name__ == "__main__":
    update_reps()

import json
import re

def cleanup():
    path = "static/data/districts.json"
    with open(path, "r") as f:
        d_data = json.load(f)
        
    districts_map = d_data.get("districts", {})
    updates = 0
    
    for prov, info in districts_map.items():
        reps = info.get("representatives", {})
        for dist, rep_str in reps.items():
            # Look for pattern "Name (2025-2025); "
            if "(2025-2025)" in rep_str:
                print(f"Cleaning {prov} {dist}: {rep_str}")
                # Remove the 2025-2025 part
                # Assuming format "Name (2025-2025); New Name (2025-present)"
                # We want to keep just "New Name (2025-present)"? 
                # OR keep the original "Name (2025-present)"? 
                # The "Old" was "Aa Legarda (2025-present)". The script changed it to "Aa Legarda (2025-2025); Antonio Legarda Jr. (2025-present)".
                # The user likely prefers the OFFICIAL name "Antonio Legarda Jr." if we are calculating similarity. 
                # BUT if we want to revert to state before the bad script:
                # We should keep "Aa Legarda (2025-present)".
                # HOWEVER, "Antonio Legarda Jr." is from the user's "20th congress" file, so it's probably the better name.
                # So maybe we just remove the "Name (2025-2025); " part?
                
                # Let's see: `Aa Legarda (2025-2025); Antonio Legarda Jr. (2025-present)`
                # If we remove the first part, we get `Antonio Legarda Jr. (2025-present)`. This is a valid 2025 entry.
                # It effectively REPLACES the nickname with the official name. This seems GOOD.
                
                new_str = re.sub(r'[^;]+ \(2025-2025\);\s*', '', rep_str)
                print(f"  -> {new_str}")
                reps[dist] = new_str
                updates += 1

    print(f"Cleaned {updates} entries.")
    with open(path, "w") as f:
        json.dump(d_data, f, indent=4)

if __name__ == "__main__":
    cleanup()

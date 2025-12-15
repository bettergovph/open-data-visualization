import json

def check_json():
    try:
        with open("static/data/districts.json", "r") as f:
            data = json.load(f)
            dists = data.get('districts', {})
            
        targets = [
            "Agusan del Norte", "Caloocan City", "City of Caloocan", 
            "Cebu City", "City of Cebu", 
            "Davao City", "City of Davao", 
            "Lucena City", "City of Lucena", 
            "Marikina City", "City of Marikina",
            "Davao del Sur"
        ]
        
        print("Checking keys in districts.json:")
        for t in targets:
            if t in dists:
                print(f"✅ Found '{t}'")
                entry = dists[t]
                print(f"   Keys: {list(entry.keys())}")
                if 'barangays' in entry:
                     print(f"   Districts (via barangays): {list(entry['barangays'].keys())}")
                elif 'municipalities' in entry:
                     print(f"   Municipalities: {list(entry['municipalities'].keys())[:5]}...")
                     # Check first municipality
                     first_m = list(entry['municipalities'].keys())[0]
                     print(f"   Sample Municipality '{first_m}': {entry['municipalities'][first_m]}")
            else:
                # fuzzy check
                found = [k for k in dists.keys() if t.lower() in k.lower()]
                if found:
                    print(f"⚠️ Partial match for '{t}': {found}")
                    for f_key in found:
                         entry = dists[f_key]
                         if 'barangays' in entry:
                             print(f"   Districts ({f_key}): {list(entry['barangays'].keys())}")
                         elif 'municipalities' in entry:
                             print(f"   Municipalities ({f_key}): {list(entry['municipalities'].keys())[:5]}")
                else:
                    print(f"❌ '{t}' not found.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_json()

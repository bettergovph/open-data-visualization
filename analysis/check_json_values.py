import json

def check_values():
    try:
        with open("static/data/districts.json", "r") as f:
            data = json.load(f)
            dists = data.get('districts', {})
            
        for city in ["Caloocan", "Marikina"]:
            if city in dists:
                print(f"\n--- {city} (JSON) ---")
                entry = dists[city]
                if 'barangays' in entry:
                    for dist, brgys in entry['barangays'].items():
                        print(f"{dist}: {brgys[:5]}...") # show first 5
                        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_values()

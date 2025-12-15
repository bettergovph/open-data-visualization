import json

def find_nested():
    # 1. Marikina
    path1 = "static/data/districts_generated.json"
    print(f"Scanning {path1}...")
    with open(path1, "r") as f:
        d1 = json.load(f)
        # Check specific NCR key found in previous step
        ncr_key = "National Capital Region - Second District"
        if ncr_key in d1:
            print(f"Found '{ncr_key}'. Keys inside:")
            print(list(d1[ncr_key].keys()))
        else:
            print(f"'{ncr_key}' not found.")

    # 2. Davao del Sur
    path2 = "static/data/districts.json.wiki-backup"
    print(f"\nScanning {path2}...")
    with open(path2, "r") as f:
        d2 = json.load(f)
        # Standard search
        for k in d2.keys():
            if "Davao" in k and "Sur" in k:
                print(f"Found Key: '{k}'")
                if "municipalities" in d2[k]:
                    print("  Has 'municipalities'")
                    print("  Sample:", list(d2[k]["municipalities"].keys())[:5])

if __name__ == "__main__":
    find_nested()

import json

def check_2025():
    path = "static/data/districts.json"
    with open(path, "r") as f:
        d_data = json.load(f)
        
    districts = d_data.get("districts", {})
    missing_2025 = []
    total_districts = 0
    has_2025_count = 0
    
    for prov, info in districts.items():
        reps = info.get("representatives", {})
        for dist, rep_str in reps.items():
            total_districts += 1
            if "2025-present" in rep_str:
                has_2025_count += 1
            else:
                missing_2025.append(f"{prov} - {dist}: {rep_str}")

    print(f"Total Districts Checked: {total_districts}")
    print(f"Districts with '2025-present': {has_2025_count}")
    print(f"Missing 2025 Data: {len(missing_2025)}")
    
    if missing_2025:
        print("\n--- Missing 2025 Data (Sample) ---")
        for m in missing_2025[:20]:
            print(m)

if __name__ == "__main__":
    check_2025()

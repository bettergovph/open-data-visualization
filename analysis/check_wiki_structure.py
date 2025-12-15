import json

def check_structure():
    path = "static/data/districts.json.wiki-backup"
    with open(path, "r") as f:
        data = json.load(f)
        print(f"Root Type: {type(data)}")
        if isinstance(data, dict):
            print(f"Root Keys Sample: {list(data.keys())[:5]}")
            # Try exact match again
            if "Davao del Sur" in data:
                print("Direct Key 'Davao del Sur' FOUND.")
            elif "Davao Del Sur" in data:
                print("Direct Key 'Davao Del Sur' FOUND.")
        elif isinstance(data, list):
            print(f"Root is List. Length: {len(data)}")
            print(f"Sample Item 0: {data[0]}")

if __name__ == "__main__":
    check_structure()

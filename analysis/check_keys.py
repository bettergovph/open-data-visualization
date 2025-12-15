import json

def check_keys():
    print("--- checking districts_generated.json ---")
    with open("static/data/districts_generated.json", "r") as f:
        data = json.load(f)
        keys = list(data.keys())
        print("Keys:", keys)
        if "City Of Marikina" in data:
            print("Found 'City Of Marikina'")
        if "City of Marikina" in data:
             print("Found 'City of Marikina'")

    print("\n--- checking districts.json.wiki-backup ---")
    with open("static/data/districts.json.wiki-backup", "r") as f:
        data = json.load(f)
        keys = list(data.keys())
        # It's huge, print only if target exists or close match
        if "Davao del Sur" in data:
            print("Found 'Davao del Sur'")
        else:
            print("Target 'Davao del Sur' NOT found.")
            # Search
            for k in keys:
                if "Davao" in k:
                    print(f"Possible match: {k}")

if __name__ == "__main__":
    check_keys()

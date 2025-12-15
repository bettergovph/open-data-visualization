import json

def find_keys():
    try:
        with open("static/data/districts.json", "r") as f:
            data = json.load(f)
            keys = list(data.get('districts', {}).keys())
            
        search_terms = ["Caloocan", "Lucena", "Marikina"]
        
        print(f"Total keys in districts.json: {len(keys)}")
        for term in search_terms:
            matches = [k for k in keys if term.lower() in k.lower()]
            print(f"Matches for '{term}': {matches}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    find_keys()

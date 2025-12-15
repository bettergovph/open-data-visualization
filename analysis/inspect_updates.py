import json

def inspect_updates():
    with open("static/data/districts.json", "r") as f:
        data = json.load(f)
        
    districts = data.get("districts", {})
    
    # Check Agusan del Norte
    adn = districts.get("Agusan del Norte", {})
    print("--- Agusan del Norte ---")
    print(json.dumps(adn.get("representatives"), indent=2))
    
    # Check Quezon
    qzn = districts.get("Quezon", {})
    print("\n--- Quezon ---")
    print(json.dumps(qzn.get("representatives"), indent=2))

if __name__ == "__main__":
    inspect_updates()

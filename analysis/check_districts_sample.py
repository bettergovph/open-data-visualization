import json

def check_sample():
    with open("static/data/districts.json", "r") as f:
        data = json.load(f)
        
    districts = data.get("districts", {})
    targets = ["Antique", "Abra", "Agusan del Norte"]
    
    for t in targets:
        if t in districts:
            print(f"--- {t} ---")
            print(json.dumps(districts[t].get("representatives"), indent=2))

if __name__ == "__main__":
    check_sample()

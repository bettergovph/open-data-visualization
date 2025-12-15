import json

def check():
    path = "static/data/districts.json"
    with open(path, "r") as f:
        data = json.load(f)
        
    districts = data.get("districts", {})
    count = 0
    for prov, info in districts.items():
        reps = info.get("representatives", {})
        for dist, rep_data in reps.items():
            print(f"Province: {prov}, District: {dist}")
            print(f"Type: {type(rep_data)}")
            print(f"Value: {rep_data}")
            print("-" * 20)
            count += 1
            if count >= 5: return

if __name__ == "__main__":
    check()

import json

with open('static/data/districts.json', 'r') as f:
    data = json.load(f)

districts = data.get('districts', {})

print("Finding 'Quezon City' keys:")
for k in districts.keys():
    if k.lower() == "quezon city":
        print(f"Key: '{k}'")
        reps = districts[k].get('representatives', {})
        print(f"  Reps: {json.dumps(reps, indent=2)}")

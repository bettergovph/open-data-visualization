import json

with open('static/data/dynasty-projects-config.json', 'r') as f:
    config = json.load(f)

names = []
for key, val in config.items():
    if isinstance(val, dict) and 'name' in val:
        names.append(val['name'])

print(f"Total names found: {len(names)}")
if 'Mikee Romero' in names:
    print("Mikee Romero is in the list")
else:
    print("Mikee Romero is NOT in the list")
    # Print similar names
    for n in names:
        if "Romero" in n:
            print(f"Found similar: {n}")








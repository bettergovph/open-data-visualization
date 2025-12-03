import json

with open('static/data/dynasty-projects-config.json', 'r') as f:
    config = json.load(f)

found = False
for key, val in config.items():
    if key == "metadata":
        continue
    
    # val should be the congressman object
    if isinstance(val, dict) and val.get('name') == 'Mikee Romero':
        print(json.dumps(val, indent=2))
        found = True
        break

if not found:
    print("Mikee Romero not found")

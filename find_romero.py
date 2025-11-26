import json

with open('static/data/dynasty-projects-config.json', 'r') as f:
    config = json.load(f)

for key, val in config.items():
    if key == "metadata":
        continue
    if "romero" in key.lower():
        print(f"Found key: {key}")
        print(json.dumps(val, indent=2))








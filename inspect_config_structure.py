import json

with open('static/data/dynasty-projects-config.json', 'r') as f:
    config = json.load(f)

print(type(config))
if isinstance(config, dict):
    first_key = list(config.keys())[0]
    print(f"Key: {first_key}")
    print(f"Value type: {type(config[first_key])}")
    print(json.dumps(config[first_key], indent=2))
elif isinstance(config, list):
    print("Config is a list")
    print(json.dumps(config[0], indent=2))








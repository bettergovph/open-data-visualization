import json

with open('static/data/dynasty-projects-config.json', 'r') as f:
    config = json.load(f)

print(config.keys())








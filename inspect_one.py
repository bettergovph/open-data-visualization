import json

with open('static/data/dynasty-projects-config.json', 'r') as f:
    config = json.load(f)

congressmen = config.get('target_congressmen', [])
if congressmen:
    print(json.dumps(congressmen[0], indent=2))
else:
    print("No congressmen found")








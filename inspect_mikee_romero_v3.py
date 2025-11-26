import json

with open('static/data/dynasty-projects-config.json', 'r') as f:
    config = json.load(f)

congressmen = config.get('target_congressmen', [])
found = False

for cm_data in congressmen:
    if cm_data.get('name') == 'Mikee Romero':
        print(json.dumps(cm_data, indent=2))
        found = True
        break

if not found:
    print("Mikee Romero not found in target_congressmen list")








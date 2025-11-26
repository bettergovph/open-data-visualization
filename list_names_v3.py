import json

with open('static/data/dynasty-projects-config.json', 'r') as f:
    config = json.load(f)

congressmen = config.get('target_congressmen', [])
names = [c.get('name') for c in congressmen if c.get('name')]
print(f"Count: {len(names)}")
for n in names:
    if "Romero" in n:
        print(f"Match: {n}")








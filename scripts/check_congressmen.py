import json

with open('static/data/congressman-ranking.json', 'r') as f:
    data = json.load(f)

print("=== Checking specific congressmen ===\n")
for entry in data:
    if isinstance(entry, dict):
        name = entry.get('name', '')
        if 'Abante' in name or 'Duterte' in name or 'Baronda' in name:
            print(f"{name}: {entry.get('totalProjects', 0)} projects, ₱{entry.get('totalAmount', 0):,.2f}")

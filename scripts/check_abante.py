import json
import random

# Load Benny Abante's cache
with open('static/data/congressmen/bienvenido-abante.json', 'r') as f:
    data = json.load(f)

# Count Metro Manila matches
metro_matches = [p for p in data if 'METRO' in p.get('location', '').upper()]

print(f'Total projects: {len(data)}')
print(f'Metro Manila matches: {len(metro_matches)}')
print(f'\nSample Metro Manila locations:')
for p in metro_matches[:10]:
    print(f'  - {p.get("location", "N/A")} | {p.get("source", "N/A")}')

print(f'\nSample of all locations:')
sample = random.sample(data, min(20, len(data)))
for p in sample:
    print(f'  - {p.get("location", "N/A")}')

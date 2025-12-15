import json

with open('static/data/districts.json', 'r') as f:
    data = json.load(f)

qc = data.get('districts', {}).get('Quezon City', {})
print(json.dumps(qc, indent=2))


import json

with open("repeated_targets.json", "r") as f:
    data = json.load(f)

print(f"Project Count: {len(data)}")
for p in data:
    for link in p.get('transparency_links', []):
        cid = link['id']
        url = f"https://transparency.dpwh.gov.ph/?project={cid}"
        print(f"TARGET|{cid}|{url}")

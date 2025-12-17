import json
from pathlib import Path

path = Path('static/data/congressmen_consolidated.json')
if not path.exists():
    print("Consolidated JSON not found!")
    exit(1)

with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)


found = False
for cm in data:
    if 'Elizaldy' in str(cm.get('display_name')) or 'Elizaldy' in str(cm.get('fullname')):
        print(f"ID: {cm.get('id')}")
        print(f"Full Entry: {json.dumps(cm, indent=2)}")
        found = True
        
        # Check cache file - Try ID and Slug
        if cm.get('id'):
             fname = f"congressman-projects-{cm.get('id')}.json"
             fpath = Path('static/data') / fname
             if fpath.exists():
                 print(f"Cache file exists: {fpath}")
             else:
                 print(f"Cache file MISSING: {fpath}")

        if cm.get('slug'):
             fname_slug = f"congressman-projects-{cm.get('slug')}.json"
             fpath_slug = Path('static/data') / fname_slug
             if fpath_slug.exists():
                 print(f"Cache file (slug) exists: {fpath_slug}")

if not found:
    print("Elizaldy Co not found in consolidated JSON!")

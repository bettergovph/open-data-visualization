import json
from collections import Counter

cache_path = 'static/data/congressman-projects-bernadette-herrera/all-projects-cache.json'

try:
    with open(cache_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not data.get('success'):
        print("Cache file indicates failure.")
        exit()

    projects = data.get('projects', [])
    print(f"Total Projects: {len(projects)}")

    match_types = Counter()
    locations = Counter()
    
    sample_district_match = None
    sample_contractor_match = None

    for p in projects:
        mt = p.get('match_type', 'unknown')
        match_types[mt] += 1
        
        loc = p.get('location', 'unknown')
        locations[loc] += 1
        
        if mt == 'district' and not sample_district_match:
            sample_district_match = p
        
        if mt == 'contractor' and not sample_contractor_match:
            sample_contractor_match = p
            
    print("\nMatch Types Breakdown:")
    for mt, count in match_types.items():
        print(f"  {mt}: {count}")

    print("\nTop 10 Locations:")
    for loc, count in locations.most_common(10):
        print(f"  {loc}: {count}")

    if sample_district_match:
        print("\nSample District Match:")
        print(json.dumps(sample_district_match, indent=2))
        
    if sample_contractor_match:
        print("\nSample Contractor Match:")
        print(json.dumps(sample_contractor_match, indent=2))

except Exception as e:
    print(f"Error: {e}")

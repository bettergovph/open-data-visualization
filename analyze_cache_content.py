

import json
from pathlib import Path
import glob

data_dir = Path('static/data')
cache_files = list(data_dir.glob('congressman-projects-*.json'))

print(f"Found {len(cache_files)} individual cache files.")

zero_projects_files = []
non_zero_count = 0

for cf in cache_files:
    try:
        with open(cf, 'r', encoding='utf-8') as f:
            cdata = json.load(f)
            # Structure: {name: "...", projects: [...], stats: ...}
            projects = cdata.get('projects', [])
            name = cdata.get('name', 'Unknown')
            
            if not projects or len(projects) == 0:
                zero_projects_files.append(name)
            else:
                non_zero_count += 1
    except Exception as e:
        print(f"Error reading {cf}: {e}")

print(f"Congressmen with projects: {non_zero_count}")
print(f"Congressmen with ZERO projects: {len(zero_projects_files)}")

party_list_keywords = ['PARTY', 'LIST', 'ACT-CIS', 'AKO', 'BICOL', 'SAGIP', 'TINGOG', 'FW', 'PHILRECA', 'RECOBODA', 'BH', 'CIBAC', 'GABRIELA', 'KABATAAN', 'DUMPER', 'TGP', 'PATROL', 'SENIOR', 'TEACHER', 'USWAG', '4PS', 'APEC', 'ALONA', 'ABANG', 'LINGKOD', 'AGAP', 'PBA', 'COOP', 'AN', 'WARAY', 'DIWA', 'KALINGA', 'MANILA', 'PROBINSYANO', 'MAGSASAKA', 'GMA', 'GP', 'KABAYAN', 'OFW', 'TUCP']

likely_party_list = 0
likely_district = 0
suspicious_district = []

for name in zero_projects_files:
    upper_name = name.upper()
    matched = False
    for kw in party_list_keywords:
         if kw in upper_name: 
             matched = True
             break
    
    # Also manual check for known names if needed
    if matched:
        likely_party_list += 1
    else:
        likely_district += 1
        suspicious_district.append(name)

print(f"Likely Party-List (by name match): {likely_party_list}")
print(f"Likely District / Unidentified: {likely_district}")

if suspicious_district:
    print("\n--- Suspicious District Zero-Projects (First 30) ---")
    for n in sorted(suspicious_district)[:30]:
        print(n)
else:
    print("\nNo suspicious district zero-projects found.")


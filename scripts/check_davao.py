import json
import sys

# Load all projects from integrated cache
try:
    with open('static/data/dynasty-projects-cache.json', 'r') as f:
        cache_data = json.load(f)
        all_projects = cache_data.get('projects', [])
except FileNotFoundError:
    print("Cache file not found!")
    sys.exit(1)

print(f"=== Searching for Davao City projects ===\n")
print(f"Total projects in cache: {len(all_projects)}\n")

davao_city_projects = []
davao_del_sur_projects = []

for project in all_projects:
    location = (project.get('location') or '').upper()
    
    if 'DAVAO CITY' in location:
        davao_city_projects.append(project)
    elif 'DAVAO DEL SUR' in location:
        davao_del_sur_projects.append(project)

print(f"Projects with 'DAVAO CITY' in location: {len(davao_city_projects)}")
print(f"Projects with 'DAVAO DEL SUR' in location: {len(davao_del_sur_projects)}")

# Check if any are assigned to Paolo Duterte
paolo_davao_city = [p for p in davao_city_projects if 'paolo duterte' in (p.get('district_congressman') or '').lower()]
paolo_davao_del_sur = [p for p in davao_del_sur_projects if 'paolo duterte' in (p.get('district_congressman') or '').lower()]

print(f"\nDavao City projects assigned to Paolo Duterte: {len(paolo_davao_city)}")
print(f"Davao del Sur projects assigned to Paolo Duterte: {len(paolo_davao_del_sur)}")

# Show sample Davao City projects
print(f"\nSample Davao City projects (first 5):")
for p in davao_city_projects[:5]:
    print(f"  - {p.get('project_name', 'N/A')[:80]}")
    print(f"    Location: {p.get('location')}")
    print(f"    Assigned to: {p.get('district_congressman', 'NONE')}")
    print()

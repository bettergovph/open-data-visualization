import json

# Check Paolo Duterte's data
with open('static/data/congressman-ranking.json', 'r') as f:
    data = json.load(f)

print("=== Searching for Paolo Duterte ===\n")
ranking_by_count = data.get('ranking_by_count', [])

# Find Paolo in rankings
paolo_entries = []
for idx, entry in enumerate(ranking_by_count, 1):
    name = entry.get('name', '')
    if 'paolo' in name.lower() and 'duterte' in name.lower():
        paolo_entries.append((idx, entry))
        print(f"Rank #{idx}: {name}")
        print(f"  Projects: {entry.get('count', 0)}")
        print(f"  Total Cost: ₱{entry.get('total_cost', 0):,.2f}")
        print(f"  Flood: {entry.get('flood_control_count', 0)} projects")
        print()

if not paolo_entries:
    print("Paolo Duterte NOT FOUND in rankings!")
    print("\nSearching all entries for 'Paolo'...")
    for idx, entry in enumerate(ranking_by_count, 1):
        if 'paolo' in entry.get('name', '').lower():
            print(f"  #{idx}: {entry.get('name')} - {entry.get('count', 0)} projects")

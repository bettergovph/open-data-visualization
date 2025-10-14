"""
Analyze Proximity Data Patterns

Check if matches are:
1. Just duplicate entries (everything identical)
2. Multi-year tracking (same project, different years)
3. Genuinely different projects (different descriptions, contractors, etc.)
"""

import json
import sys
from collections import defaultdict

# Load the proximity data
with open('static/data/flood_same_amount_proximity_results.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# Filter to 0-1km matches
matches_0_1km = [m for m in data['matches'] if m['distance_km'] <= 1.0]

print(f"Total matches 0-1km: {len(matches_0_1km)}")
print("=" * 80)

# Categorize matches
duplicate_entries = []
multi_year_same_project = []
different_projects_same_amount = []

for match in matches_0_1km:
    p1 = match['project1']
    p2 = match['project2']
    
    # Check if it's a duplicate entry (same GlobalID)
    if p1['GlobalID'] == p2['GlobalID']:
        duplicate_entries.append(match)
        continue
    
    # Check if everything is the same except year
    same_description = (p1.get('ProjectDescription', '') == p2.get('ProjectDescription', ''))
    same_contractor = (p1.get('Contractor', '') == p2.get('Contractor', ''))
    same_location = (p1.get('Latitude') == p2.get('Latitude') and 
                     p1.get('Longitude') == p2.get('Longitude'))
    same_municipality = (p1.get('Municipality') == p2.get('Municipality'))
    same_province = (p1.get('Province') == p2.get('Province'))
    different_year = (p1.get('Year') != p2.get('Year'))
    
    # Multi-year tracking: same everything except year
    if (same_description and same_contractor and same_location and 
        same_municipality and same_province and different_year):
        multi_year_same_project.append(match)
    else:
        # Different projects with same amount
        different_projects_same_amount.append(match)

print(f"\n📊 CATEGORIZATION RESULTS:")
print(f"=" * 80)
print(f"1. Duplicate Entries (same GlobalID): {len(duplicate_entries)}")
print(f"2. Multi-Year Tracking (same project, different years): {len(multi_year_same_project)}")
print(f"3. Different Projects (genuinely different): {len(different_projects_same_amount)}")
print()

# Show examples of multi-year tracking
if multi_year_same_project:
    print(f"\n🔍 EXAMPLES OF MULTI-YEAR TRACKING:")
    print(f"=" * 80)
    for i, match in enumerate(multi_year_same_project[:5], 1):
        p1 = match['project1']
        p2 = match['project2']
        print(f"\nExample {i}:")
        print(f"  Cost: ₱{match['cost']:,.2f}")
        print(f"  Distance: {match['distance_km']:.3f} km")
        print(f"  Description: {p1['ProjectDescription'][:80]}...")
        print(f"  Contractor: {p1['Contractor']}")
        print(f"  Location: {p1['Province']}, {p1['Municipality']}")
        print(f"  Years: {p1['Year']} vs {p2['Year']}")

# Show examples of different projects
if different_projects_same_amount:
    print(f"\n🔍 EXAMPLES OF DIFFERENT PROJECTS (Same Amount):")
    print(f"=" * 80)
    for i, match in enumerate(different_projects_same_amount[:10], 1):
        p1 = match['project1']
        p2 = match['project2']
        print(f"\nExample {i}:")
        print(f"  Cost: ₱{match['cost']:,.2f}")
        print(f"  Distance: {match['distance_km']:.3f} km")
        print(f"  Project 1: {p1['ProjectDescription'][:60]}...")
        print(f"    Year: {p1['Year']} | Contractor: {p1['Contractor']}")
        print(f"  Project 2: {p2['ProjectDescription'][:60]}...")
        print(f"    Year: {p2['Year']} | Contractor: {p2['Contractor']}")
        
        # Highlight differences
        diffs = []
        if p1.get('ProjectDescription') != p2.get('ProjectDescription'):
            diffs.append("Description")
        if p1.get('Contractor') != p2.get('Contractor'):
            diffs.append("Contractor")
        if p1.get('Year') != p2.get('Year'):
            diffs.append("Year")
        if p1.get('Municipality') != p2.get('Municipality'):
            diffs.append("Municipality")
        
        print(f"    Differences: {', '.join(diffs)}")

# Analyze same contractor patterns
print(f"\n📊 CONTRACTOR ANALYSIS:")
print(f"=" * 80)
same_contractor_count = sum(1 for m in different_projects_same_amount 
                           if m['project1'].get('Contractor') == m['project2'].get('Contractor'))
print(f"Different projects, same contractor: {same_contractor_count}")
print(f"Different projects, different contractor: {len(different_projects_same_amount) - same_contractor_count}")

# Year difference analysis for multi-year tracking
print(f"\n📅 YEAR DIFFERENCE ANALYSIS (Multi-Year Tracking):")
print(f"=" * 80)
year_diffs = defaultdict(int)
for match in multi_year_same_project:
    p1 = match['project1']
    p2 = match['project2']
    if p1.get('Year') and p2.get('Year'):
        diff = abs(p1['Year'] - p2['Year'])
        year_diffs[diff] += 1

for diff in sorted(year_diffs.keys()):
    print(f"  {diff} year(s) difference: {year_diffs[diff]} pairs")

# Create filtered output for frontend (exclude duplicate entries and multi-year tracking)
filtered_matches = different_projects_same_amount

output_data = {
    "analysis_summary": {
        "total_0_1km": len(matches_0_1km),
        "duplicate_entries": len(duplicate_entries),
        "multi_year_tracking": len(multi_year_same_project),
        "different_projects": len(different_projects_same_amount)
    },
    "filtered_matches": filtered_matches
}

with open('analysis/proximity_filtered_results.json', 'w', encoding='utf-8') as f:
    json.dump(output_data, f, indent=2, ensure_ascii=False)

print(f"\n💾 Filtered results saved to: analysis/proximity_filtered_results.json")
print(f"   Contains {len(filtered_matches)} genuinely different projects with same amounts")


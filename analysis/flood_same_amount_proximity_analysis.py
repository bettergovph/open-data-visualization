"""
Flood Data Analysis: Find Projects with Same Amount in Close Proximity

This script analyzes flood control projects from Meilisearch to identify
projects with identical contract amounts that are located within 10km of each other.
This could indicate potential duplicate entries, data quality issues, or genuinely
interesting patterns worth investigating.
"""

import asyncio
import sys
import os
from math import radians, cos, sin, asin, sqrt
from collections import defaultdict
from typing import List, Dict, Tuple
import json

# Add parent directory to path to import flood_client
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flood_client import FloodControlClient, FloodControlProject

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance in kilometers between two points 
    on the earth (specified in decimal degrees)
    """
    # Convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371  # Radius of earth in kilometers
    return c * r

def parse_contract_cost(cost_str) -> float:
    """Parse contract cost string to float"""
    if not cost_str:
        return 0.0
    
    try:
        if isinstance(cost_str, (int, float)):
            return float(cost_str)
        
        # Remove currency symbols and commas
        cleaned = str(cost_str).replace("₱", "").replace(",", "").replace(" ", "").strip()
        return float(cleaned) if cleaned else 0.0
    except (ValueError, TypeError):
        return 0.0

def parse_coordinate(coord_str) -> float:
    """Parse coordinate string to float"""
    if not coord_str:
        return None
    
    try:
        return float(coord_str)
    except (ValueError, TypeError):
        return None

async def analyze_flood_proximity():
    """Main analysis function"""
    print("🔍 Analyzing Flood Control Projects for Same Amount & Close Proximity...")
    print("=" * 80)
    
    # Initialize client
    client = FloodControlClient()
    
    # Check health
    is_healthy = await client.health_check()
    if not is_healthy:
        print("❌ Meilisearch connection failed!")
        return
    
    print("✅ Connected to Meilisearch")
    
    # Get all projects
    print("\n📥 Fetching all flood control projects...")
    all_projects = []
    limit = 1000
    offset = 0
    
    while True:
        projects, metadata = await client.search_projects("", limit=limit, offset=offset)
        if not projects:
            break
        
        all_projects.extend(projects)
        offset += limit
        print(f"   Retrieved {len(all_projects)} projects so far...")
        
        if len(projects) < limit:
            break
    
    print(f"✅ Total projects retrieved: {len(all_projects)}")
    
    # Group by contract cost
    print("\n📊 Grouping projects by contract cost...")
    cost_groups = defaultdict(list)
    projects_without_coords = 0
    projects_with_zero_cost = 0
    
    for project in all_projects:
        cost = parse_contract_cost(project.ContractCost)
        lat = parse_coordinate(project.Latitude)
        lon = parse_coordinate(project.Longitude)
        
        # Skip projects with zero or missing cost
        if cost == 0.0:
            projects_with_zero_cost += 1
            continue
        
        # Skip projects without coordinates
        if lat is None or lon is None:
            projects_without_coords += 1
            continue
        
        cost_groups[cost].append({
            'project': project,
            'lat': lat,
            'lon': lon,
            'cost': cost
        })
    
    print(f"   Projects with zero/missing cost: {projects_with_zero_cost}")
    print(f"   Projects without coordinates: {projects_without_coords}")
    print(f"   Unique cost values: {len(cost_groups)}")
    print(f"   Cost groups with multiple projects: {sum(1 for g in cost_groups.values() if len(g) > 1)}")
    
    # Find projects with same cost within 10km
    print("\n🔎 Finding projects with same amount within 10km proximity...")
    proximity_matches = []
    max_distance_km = 10.0
    
    for cost, projects_list in cost_groups.items():
        if len(projects_list) < 2:
            continue
        
        # Compare each pair
        for i in range(len(projects_list)):
            for j in range(i + 1, len(projects_list)):
                proj1 = projects_list[i]
                proj2 = projects_list[j]
                
                distance = haversine_distance(
                    proj1['lat'], proj1['lon'],
                    proj2['lat'], proj2['lon']
                )
                
                if distance <= max_distance_km:
                    proximity_matches.append({
                        'cost': cost,
                        'distance_km': distance,
                        'project1': proj1['project'],
                        'project2': proj2['project'],
                        'lat1': proj1['lat'],
                        'lon1': proj1['lon'],
                        'lat2': proj2['lat'],
                        'lon2': proj2['lon']
                    })
    
    print(f"✅ Found {len(proximity_matches)} pairs of projects with same cost within {max_distance_km}km")
    
    # Sort by distance
    proximity_matches.sort(key=lambda x: x['distance_km'])
    
    # Display results
    print("\n" + "=" * 80)
    print("📋 DETAILED RESULTS")
    print("=" * 80)
    
    if not proximity_matches:
        print("\n❌ No matching projects found within 10km proximity with same contract cost.")
        return
    
    # Display top 50 matches
    display_count = min(50, len(proximity_matches))
    print(f"\n🎯 Top {display_count} Matches (sorted by distance):\n")
    
    for idx, match in enumerate(proximity_matches[:display_count], 1):
        print(f"\n{'─' * 80}")
        print(f"Match #{idx}")
        print(f"{'─' * 80}")
        print(f"💰 Contract Cost: ₱{match['cost']:,.2f}")
        print(f"📏 Distance: {match['distance_km']:.2f} km")
        print()
        
        # Project 1
        p1 = match['project1']
        print(f"📍 Project 1:")
        print(f"   ID: {p1.GlobalID}")
        print(f"   Description: {p1.ProjectDescription[:100] if p1.ProjectDescription else 'N/A'}...")
        print(f"   Location: {p1.Municipality}, {p1.Province}, {p1.Region}")
        print(f"   Coordinates: {match['lat1']:.6f}, {match['lon1']:.6f}")
        print(f"   Year: {p1.InfraYear}")
        print(f"   Contractor: {p1.Contractor}")
        print(f"   Type of Work: {p1.TypeofWork}")
        print()
        
        # Project 2
        p2 = match['project2']
        print(f"📍 Project 2:")
        print(f"   ID: {p2.GlobalID}")
        print(f"   Description: {p2.ProjectDescription[:100] if p2.ProjectDescription else 'N/A'}...")
        print(f"   Location: {p2.Municipality}, {p2.Province}, {p2.Region}")
        print(f"   Coordinates: {match['lat2']:.6f}, {match['lon2']:.6f}")
        print(f"   Year: {p2.InfraYear}")
        print(f"   Contractor: {p2.Contractor}")
        print(f"   Type of Work: {p2.TypeofWork}")
    
    # Summary statistics
    print(f"\n\n{'=' * 80}")
    print("📊 SUMMARY STATISTICS")
    print(f"{'=' * 80}\n")
    
    distances = [m['distance_km'] for m in proximity_matches]
    costs = [m['cost'] for m in proximity_matches]
    
    print(f"Total matches found: {len(proximity_matches)}")
    print(f"\nDistance Statistics:")
    print(f"   Min distance: {min(distances):.2f} km")
    print(f"   Max distance: {max(distances):.2f} km")
    print(f"   Avg distance: {sum(distances)/len(distances):.2f} km")
    print(f"\nContract Cost Statistics:")
    print(f"   Min cost: ₱{min(costs):,.2f}")
    print(f"   Max cost: ₱{max(costs):,.2f}")
    print(f"   Avg cost: ₱{sum(costs)/len(costs):,.2f}")
    
    # Distance distribution
    print(f"\nDistance Distribution:")
    dist_ranges = [(0, 1), (1, 2), (2, 3), (3, 5), (5, 10)]
    for min_d, max_d in dist_ranges:
        count = sum(1 for d in distances if min_d <= d < max_d)
        print(f"   {min_d}-{max_d}km: {count} pairs")
    
    # Save results to JSON file
    output_file = "flood_same_amount_proximity_results.json"
    output_data = {
        "analysis_date": asyncio.get_event_loop().time(),
        "total_matches": len(proximity_matches),
        "max_distance_km": max_distance_km,
        "summary": {
            "min_distance_km": min(distances),
            "max_distance_km": max(distances),
            "avg_distance_km": sum(distances)/len(distances),
            "min_cost": min(costs),
            "max_cost": max(costs),
            "avg_cost": sum(costs)/len(costs)
        },
        "matches": [
            {
                "cost": m['cost'],
                "distance_km": m['distance_km'],
                "project1": {
                    "GlobalID": m['project1'].GlobalID,
                    "ProjectDescription": m['project1'].ProjectDescription,
                    "Municipality": m['project1'].Municipality,
                    "Province": m['project1'].Province,
                    "Region": m['project1'].Region,
                    "Year": m['project1'].InfraYear,
                    "Contractor": m['project1'].Contractor,
                    "TypeofWork": m['project1'].TypeofWork,
                    "Latitude": m['lat1'],
                    "Longitude": m['lon1']
                },
                "project2": {
                    "GlobalID": m['project2'].GlobalID,
                    "ProjectDescription": m['project2'].ProjectDescription,
                    "Municipality": m['project2'].Municipality,
                    "Province": m['project2'].Province,
                    "Region": m['project2'].Region,
                    "Year": m['project2'].InfraYear,
                    "Contractor": m['project2'].Contractor,
                    "TypeofWork": m['project2'].TypeofWork,
                    "Latitude": m['lat2'],
                    "Longitude": m['lon2']
                }
            }
            for m in proximity_matches
        ]
    }
    
    output_path = os.path.join(os.path.dirname(__file__), output_file)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Results saved to: {output_path}")
    print("\n✅ Analysis complete!")

if __name__ == "__main__":
    asyncio.run(analyze_flood_proximity())


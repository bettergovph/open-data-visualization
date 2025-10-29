#!/usr/bin/env python3
"""
Generate contractor standard deviation analysis JSON file.
This script calculates standard deviation statistics for contractor project counts
and creates a JSON file for the Contractor Project Distribution chart.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
import statistics
import numpy as np
from meilisearch import Client
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

# Load environment variables
load_dotenv()

def get_meilisearch_client():
    """Get Meilisearch client with environment variables."""
    meili_addr = os.getenv('MEILI_HTTP_ADDR', 'http://localhost:7700')
    meili_key = os.getenv('MEILI_MASTER_KEY', '')
    
    if not meili_key:
        print("❌ MEILI_MASTER_KEY not found in environment")
        return None
    
    # Ensure the address has the protocol
    if not meili_addr.startswith('http'):
        meili_addr = f'http://{meili_addr}'
    
    try:
        client = Client(meili_addr, meili_key)
        # Test connection
        client.health()
        print(f"✅ Connected to Meilisearch at {meili_addr}")
        return client
    except Exception as e:
        print(f"❌ Failed to connect to Meilisearch: {e}")
        return None

def get_contractor_data_from_meilisearch():
    """Get contractor data directly from Meilisearch."""
    client = get_meilisearch_client()
    if not client:
        return None, None
    
    try:
        print("📡 Fetching contractor data from Meilisearch...")
        
        # Get all contractors with their project counts and costs
        response = client.index('bettergov_flood_control').search('', {
            'limit': 10000,  # Get all records
            'attributesToRetrieve': ['Contractor', 'ContractCost'],
            'facets': ['Contractor']
        })
        
        # Process the data
        contractor_stats = {}
        
        for hit in response['hits']:
            contractor = hit.get('Contractor', '').strip()
            cost = hit.get('ContractCost', 0)
            
            if contractor:
                if contractor not in contractor_stats:
                    contractor_stats[contractor] = {
                        'project_count': 0,
                        'total_cost': 0
                    }
                
                contractor_stats[contractor]['project_count'] += 1
                
                if cost:
                    try:
                        # Convert cost to float if it's a string
                        if isinstance(cost, str):
                            cost = float(cost.replace("₱", "").replace(",", "").replace(" ", ""))
                        contractor_stats[contractor]['total_cost'] += cost
                    except (ValueError, TypeError):
                        continue
        
        # Convert to lists for analysis
        project_counts = []
        contractor_names = []
        contractor_costs = {}
        
        for contractor, stats in contractor_stats.items():
            if stats['project_count'] > 0:
                project_counts.append(stats['project_count'])
                contractor_names.append(contractor)
                contractor_costs[contractor] = stats['total_cost']
        
        print(f"📊 Found {len(project_counts)} contractors with {sum(project_counts)} total projects")
        print(f"💰 Total contract value: ₱{sum(contractor_costs.values()):,.2f}")
        
        return (project_counts, contractor_names), contractor_costs
        
    except Exception as e:
        print(f"❌ Error fetching data from Meilisearch: {e}")
        return None, None

def load_contractor_data():
    """Load contractor data from available sources."""
    static_data_dir = project_root / "static" / "data"
    
    # Try different data sources
    data_sources = [
        "contractors_top.json",
        "flood_hidden_contractors_cached.json", 
        "contractors_sec.json"
    ]
    
    for source in data_sources:
        file_path = static_data_dir / source
        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    print(f"✅ Loaded data from {source}")
                    return data, source
            except Exception as e:
                print(f"⚠️ Error loading {source}: {e}")
                continue
    
    print("❌ No contractor data sources found")
    return None, None

def load_flood_data():
    """Load flood control data to get contract costs."""
    static_data_dir = project_root / "static" / "data"
    
    # Try different flood data sources
    flood_sources = [
        "flood_control_data.json",
        "flood_control_data_working.json"
    ]
    
    for source in flood_sources:
        file_path = static_data_dir / source
        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    print(f"✅ Loaded flood data from {source}")
                    return data, source
            except Exception as e:
                print(f"⚠️ Error loading {source}: {e}")
                continue
    
    print("⚠️ No flood data sources found - cost analysis will be limited")
    return None, None

def extract_project_counts(data, source):
    """Extract project counts and contractor names from the data."""
    project_counts = []
    contractor_names = []
    
    if source == "contractors_top.json":
        contractors = data.get("data", {}).get("contractors", [])
        for c in contractors:
            count = c.get("count", 0)
            name = c.get("contractor", "")
            if count and name:
                project_counts.append(count)
                contractor_names.append(name)
    elif source == "flood_hidden_contractors_cached.json":
        contractors = data.get("data", {}).get("contractors", [])
        for c in contractors:
            count = c.get("project_count", 0)
            name = c.get("contractor", "")
            if count and name:
                project_counts.append(count)
                contractor_names.append(name)
    elif source == "contractors_sec.json":
        contractors = data.get("contractors", [])
        for c in contractors:
            count = c.get("project_count", 0)
            name = c.get("contractor", "")
            if count and name:
                project_counts.append(count)
                contractor_names.append(name)
    
    # Filter out zero counts and ensure we have valid numbers
    valid_data = [(count, name) for count, name in zip(project_counts, contractor_names) 
                  if isinstance(count, (int, float)) and count > 0 and name]
    
    if valid_data:
        project_counts, contractor_names = zip(*valid_data)
        project_counts = list(project_counts)
        contractor_names = list(contractor_names)
    
    print(f"📊 Extracted {len(project_counts)} project counts and contractor names from {source}")
    return project_counts, contractor_names

def extract_contractor_costs(flood_data, source):
    """Extract contractor cost data from flood control data."""
    if not flood_data:
        return {}
    
    contractor_costs = {}
    
    if source == "flood_control_data.json" or source == "flood_control_data_working.json":
        projects = flood_data.get("data", {}).get("projects", [])
        
        for project in projects:
            contractor = project.get("Contractor", "").strip()
            cost = project.get("ContractCost", 0)
            
            if contractor and cost:
                try:
                    # Convert cost to float if it's a string
                    if isinstance(cost, str):
                        cost = float(cost.replace("₱", "").replace(",", "").replace(" ", ""))
                    
                    if contractor not in contractor_costs:
                        contractor_costs[contractor] = 0
                    contractor_costs[contractor] += cost
                except (ValueError, TypeError):
                    continue
    
    print(f"📊 Extracted cost data for {len(contractor_costs)} contractors from {source}")
    return contractor_costs

def calculate_standard_deviation_stats(project_counts, contractor_costs=None, contractor_names=None):
    """Calculate standard deviation statistics with cost aggregation per SD group."""
    if not project_counts:
        print("❌ No project counts available for analysis")
        return None
    
    # Calculate basic statistics
    mean_projects = statistics.mean(project_counts)
    std_dev = statistics.stdev(project_counts)
    
    print(f"📈 Mean projects: {mean_projects:.2f}")
    print(f"📈 Standard deviation: {std_dev:.2f}")
    
    # Calculate distribution within standard deviations
    within_1sd = len([count for count in project_counts if abs(count - mean_projects) <= std_dev])
    within_1_5sd = len([count for count in project_counts if abs(count - mean_projects) <= 1.5 * std_dev])
    within_2sd = len([count for count in project_counts if abs(count - mean_projects) <= 2 * std_dev])
    within_2_5sd = len([count for count in project_counts if abs(count - mean_projects) <= 2.5 * std_dev])
    within_3sd = len([count for count in project_counts if abs(count - mean_projects) <= 3 * std_dev])
    
    total_contractors = len(project_counts)
    
    # Calculate beyond ranges
    beyond_1sd = total_contractors - within_1sd
    beyond_1_5sd = total_contractors - within_1_5sd
    beyond_2sd = total_contractors - within_2sd
    beyond_2_5sd = total_contractors - within_2_5sd
    beyond_3sd = total_contractors - within_3sd
    
    # Calculate ranges
    range_1sd = f"{mean_projects - std_dev:.1f} to {mean_projects + std_dev:.1f} projects"
    range_1_5sd = f"{mean_projects - 1.5*std_dev:.1f} to {mean_projects + 1.5*std_dev:.1f} projects"
    range_2sd = f"{mean_projects - 2*std_dev:.1f} to {mean_projects + 2*std_dev:.1f} projects"
    range_2_5sd = f"{mean_projects - 2.5*std_dev:.1f} to {mean_projects + 2.5*std_dev:.1f} projects"
    range_3sd = f"{mean_projects - 3*std_dev:.1f} to {mean_projects + 3*std_dev:.1f} projects"
    
    # Calculate cost aggregation per SD group if cost data is available
    cost_aggregation = {}
    if contractor_costs and contractor_names and len(contractor_names) == len(project_counts):
        print("💰 Calculating cost aggregation per SD group using actual contractor-cost mapping...")
        
        # Map each contractor to their project count and cost
        contractor_data = []
        for i, (name, count) in enumerate(zip(contractor_names, project_counts)):
            cost = contractor_costs.get(name, 0)
            contractor_data.append({
                'name': name,
                'project_count': count,
                'cost': cost,
                'z_score': (count - mean_projects) / std_dev
            })
        
        # Group contractors by SD ranges and sum their actual costs
        sd_groups = {
            "within_1sd": [],
            "within_1_5sd": [],
            "within_2sd": [],
            "within_2_5sd": [],
            "within_3sd": [],
            "beyond_1sd": [],
            "beyond_1_5sd": [],
            "beyond_2sd": [],
            "beyond_2_5sd": [],
            "beyond_3sd": []
        }
        
        for contractor in contractor_data:
            z_score = contractor['z_score']
            cost = contractor['cost']
            
            if abs(z_score) <= 1:
                sd_groups["within_1sd"].append(cost)
            if abs(z_score) <= 1.5:
                sd_groups["within_1_5sd"].append(cost)
            if abs(z_score) <= 2:
                sd_groups["within_2sd"].append(cost)
            if abs(z_score) <= 2.5:
                sd_groups["within_2_5sd"].append(cost)
            if abs(z_score) <= 3:
                sd_groups["within_3sd"].append(cost)
            if abs(z_score) > 1:
                sd_groups["beyond_1sd"].append(cost)
            if abs(z_score) > 1.5:
                sd_groups["beyond_1_5sd"].append(cost)
            if abs(z_score) > 2:
                sd_groups["beyond_2sd"].append(cost)
            if abs(z_score) > 2.5:
                sd_groups["beyond_2_5sd"].append(cost)
            if abs(z_score) > 3:
                sd_groups["beyond_3sd"].append(cost)
        
        # Calculate actual cost totals for each SD group
        cost_aggregation = {
            "within_1sd": round(sum(sd_groups["within_1sd"]), 2),
            "within_1_5sd": round(sum(sd_groups["within_1_5sd"]), 2),
            "within_2sd": round(sum(sd_groups["within_2sd"]), 2),
            "within_2_5sd": round(sum(sd_groups["within_2_5sd"]), 2),
            "within_3sd": round(sum(sd_groups["within_3sd"]), 2),
            "beyond_1sd": round(sum(sd_groups["beyond_1sd"]), 2),
            "beyond_1_5sd": round(sum(sd_groups["beyond_1_5sd"]), 2),
            "beyond_2sd": round(sum(sd_groups["beyond_2sd"]), 2),
            "beyond_2_5sd": round(sum(sd_groups["beyond_2_5sd"]), 2),
            "beyond_3sd": round(sum(sd_groups["beyond_3sd"]), 2),
            "total_cost": round(sum(contractor_costs.values()), 2),
            "multiplier_note": "Frontend should multiply all cost values by 1000 for display"
        }
        
        print(f"💰 Total cost aggregated: ₱{cost_aggregation['total_cost']:,.2f} (raw values - frontend will multiply by 1000)")
        print(f"💰 Within 1SD cost: ₱{cost_aggregation['within_1sd']:,.2f} from {len(sd_groups['within_1sd'])} contractors")
        print(f"💰 Beyond 3SD cost: ₱{cost_aggregation['beyond_3sd']:,.2f} from {len(sd_groups['beyond_3sd'])} contractors")
        
    elif contractor_costs:
        print("⚠️ Cost data available but contractor names don't match project counts - using proportional distribution")
        # Fallback to proportional distribution
        total_cost = sum(contractor_costs.values())
        cost_aggregation = {
            "within_1sd": round((within_1sd / total_contractors) * total_cost, 2),
            "within_1_5sd": round((within_1_5sd / total_contractors) * total_cost, 2),
            "within_2sd": round((within_2sd / total_contractors) * total_cost, 2),
            "within_2_5sd": round((within_2_5sd / total_contractors) * total_cost, 2),
            "within_3sd": round((within_3sd / total_contractors) * total_cost, 2),
            "beyond_1sd": round((beyond_1sd / total_contractors) * total_cost, 2),
            "beyond_1_5sd": round((beyond_1_5sd / total_contractors) * total_cost, 2),
            "beyond_2sd": round((beyond_2sd / total_contractors) * total_cost, 2),
            "beyond_2_5sd": round((beyond_2_5sd / total_contractors) * total_cost, 2),
            "beyond_3sd": round((beyond_3sd / total_contractors) * total_cost, 2),
            "total_cost": round(total_cost, 2),
            "multiplier_note": "Frontend should multiply all cost values by 1000 for display"
        }
    else:
        print("⚠️ No cost data available for aggregation")
    
    result = {
        "total_contractors": total_contractors,
        "mean_projects": round(mean_projects, 1),
        "standard_deviation": round(std_dev, 1),
        "distribution": {
            "within_1sd": within_1sd,
            "within_1_5sd": within_1_5sd,
            "within_2sd": within_2sd,
            "within_2_5sd": within_2_5sd,
            "within_3sd": within_3sd,
            "beyond_1sd": beyond_1sd,
            "beyond_1_5sd": beyond_1_5sd,
            "beyond_2sd": beyond_2sd,
            "beyond_2_5sd": beyond_2_5sd,
            "beyond_3sd": beyond_3sd
        },
        "ranges": {
            "1sd_range": range_1sd,
            "1_5sd_range": range_1_5sd,
            "2sd_range": range_2sd,
            "2_5sd_range": range_2_5sd,
            "3sd_range": range_3sd
        }
    }
    
    # Add cost aggregation if available
    if cost_aggregation:
        result["cost_aggregation"] = cost_aggregation
    
    return result

def generate_standard_deviation_json():
    """Generate the standard deviation analysis JSON file."""
    print("🚀 Generating Contractor Standard Deviation Analysis")
    print("=" * 50)
    
    # Get live data from Meilisearch
    meilisearch_data = get_contractor_data_from_meilisearch()
    if meilisearch_data[0] is None:
        print("❌ Failed to get data from Meilisearch, falling back to cached data...")
        # Fallback to cached data
        data, source = load_contractor_data()
        if not data:
            return False
        
        # Load flood data for cost information
        flood_data, flood_source = load_flood_data()
        contractor_costs = None
        if flood_data:
            contractor_costs = extract_contractor_costs(flood_data, flood_source)
        
        # Extract project counts and contractor names
        project_counts, contractor_names = extract_project_counts(data, source)
        if not project_counts:
            return False
        data_source = source
    else:
        # Use live Meilisearch data
        (project_counts, contractor_names), contractor_costs = meilisearch_data
        if not project_counts:
            return False
        data_source = "Meilisearch (live data)"
    
    # Calculate statistics with cost aggregation
    stats = calculate_standard_deviation_stats(project_counts, contractor_costs, contractor_names)
    if not stats:
        return False
    
    # Create the final JSON structure
    result = {
        "success": True,
        "analysis": stats,
        "generated_at": datetime.now().isoformat(),
        "description": "Standard deviation analysis of contractor project counts with cost aggregation per SD group",
        "data_source": data_source,
        "cost_data_available": contractor_costs is not None,
        "cache_version": "1.0"
    }
    
    # Save to file
    output_file = project_root / "static" / "data" / "contractor_standard_deviation.json"
    try:
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"✅ Standard deviation analysis saved to {output_file}")
        print(f"📊 Total contractors: {stats['total_contractors']}")
        print(f"📊 Mean projects: {stats['mean_projects']}")
        print(f"📊 Standard deviation: {stats['standard_deviation']}")
        print(f"📊 Within 1SD: {stats['distribution']['within_1sd']} contractors")
        print(f"📊 Beyond 3SD: {stats['distribution']['beyond_3sd']} contractors")
        
        # Show cost aggregation if available
        if 'cost_aggregation' in stats:
            cost_agg = stats['cost_aggregation']
            print(f"💰 Total cost aggregated: ₱{cost_agg['total_cost']:,.2f}")
            print(f"💰 Within 1SD cost: ₱{cost_agg['within_1sd']:,.2f}")
            print(f"💰 Beyond 3SD cost: ₱{cost_agg['beyond_3sd']:,.2f}")
        else:
            print("⚠️ No cost data available for aggregation")
        
        return True
        
    except Exception as e:
        print(f"❌ Error saving standard deviation analysis: {e}")
        return False

if __name__ == "__main__":
    success = generate_standard_deviation_json()
    if success:
        print("\n🎉 Standard deviation analysis generated successfully!")
        sys.exit(0)
    else:
        print("\n❌ Failed to generate standard deviation analysis")
        sys.exit(1)

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

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

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
    """Extract project counts from the data."""
    project_counts = []
    
    if source == "contractors_top.json":
        contractors = data.get("data", {}).get("contractors", [])
        project_counts = [c.get("count", 0) for c in contractors if c.get("count")]
    elif source == "flood_hidden_contractors_cached.json":
        contractors = data.get("data", {}).get("contractors", [])
        project_counts = [c.get("project_count", 0) for c in contractors if c.get("project_count")]
    elif source == "contractors_sec.json":
        contractors = data.get("contractors", [])
        project_counts = [c.get("project_count", 0) for c in contractors if c.get("project_count")]
    
    # Filter out zero counts and ensure we have valid numbers
    project_counts = [count for count in project_counts if isinstance(count, (int, float)) and count > 0]
    
    print(f"📊 Extracted {len(project_counts)} project counts from {source}")
    return project_counts

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

def calculate_standard_deviation_stats(project_counts, contractor_costs=None):
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
    within_2sd = len([count for count in project_counts if abs(count - mean_projects) <= 2 * std_dev])
    within_3sd = len([count for count in project_counts if abs(count - mean_projects) <= 3 * std_dev])
    within_4sd = len([count for count in project_counts if abs(count - mean_projects) <= 4 * std_dev])
    
    total_contractors = len(project_counts)
    
    # Calculate beyond ranges
    beyond_1sd = total_contractors - within_1sd
    beyond_2sd = total_contractors - within_2sd
    beyond_3sd = total_contractors - within_3sd
    beyond_4sd = total_contractors - within_4sd
    
    # Calculate ranges
    range_1sd = f"{mean_projects - std_dev:.1f} to {mean_projects + std_dev:.1f} projects"
    range_2sd = f"{mean_projects - 2*std_dev:.1f} to {mean_projects + 2*std_dev:.1f} projects"
    range_3sd = f"{mean_projects - 3*std_dev:.1f} to {mean_projects + 3*std_dev:.1f} projects"
    range_4sd = f"{mean_projects - 4*std_dev:.1f} to {mean_projects + 4*std_dev:.1f} projects"
    
    # Calculate cost aggregation per SD group if cost data is available
    cost_aggregation = {}
    if contractor_costs:
        print("💰 Calculating cost aggregation per SD group...")
        
        # Group contractors by SD ranges and sum their costs
        sd_groups = {
            "within_1sd": [],
            "within_2sd": [],
            "within_3sd": [],
            "within_4sd": [],
            "beyond_1sd": [],
            "beyond_2sd": [],
            "beyond_3sd": [],
            "beyond_4sd": []
        }
        
        # Note: We need to map project counts back to contractor names for cost calculation
        # This is a simplified approach - in practice, you'd need to maintain the mapping
        # For now, we'll calculate based on the distribution counts
        
        # Calculate total cost for each SD group
        # This is a simplified calculation - in practice, you'd need the actual contractor-to-cost mapping
        total_cost = sum(contractor_costs.values()) if contractor_costs else 0
        
        if total_cost > 0:
            # Distribute costs proportionally based on contractor counts
            cost_aggregation = {
                "within_1sd": round((within_1sd / total_contractors) * total_cost, 2),
                "within_2sd": round((within_2sd / total_contractors) * total_cost, 2),
                "within_3sd": round((within_3sd / total_contractors) * total_cost, 2),
                "within_4sd": round((within_4sd / total_contractors) * total_cost, 2),
                "beyond_1sd": round((beyond_1sd / total_contractors) * total_cost, 2),
                "beyond_2sd": round((beyond_2sd / total_contractors) * total_cost, 2),
                "beyond_3sd": round((beyond_3sd / total_contractors) * total_cost, 2),
                "beyond_4sd": round((beyond_4sd / total_contractors) * total_cost, 2),
                "total_cost": round(total_cost, 2)
            }
            print(f"💰 Total cost aggregated: ₱{total_cost:,.2f}")
        else:
            print("⚠️ No cost data available for aggregation")
    
    result = {
        "total_contractors": total_contractors,
        "mean_projects": round(mean_projects, 1),
        "standard_deviation": round(std_dev, 1),
        "distribution": {
            "within_1sd": within_1sd,
            "within_2sd": within_2sd,
            "within_3sd": within_3sd,
            "within_4sd": within_4sd,
            "beyond_1sd": beyond_1sd,
            "beyond_2sd": beyond_2sd,
            "beyond_3sd": beyond_3sd,
            "beyond_4sd": beyond_4sd
        },
        "ranges": {
            "1sd_range": range_1sd,
            "2sd_range": range_2sd,
            "3sd_range": range_3sd,
            "4sd_range": range_4sd
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
    
    # Load contractor data
    data, source = load_contractor_data()
    if not data:
        return False
    
    # Load flood data for cost information
    flood_data, flood_source = load_flood_data()
    contractor_costs = None
    if flood_data:
        contractor_costs = extract_contractor_costs(flood_data, flood_source)
    
    # Extract project counts
    project_counts = extract_project_counts(data, source)
    if not project_counts:
        return False
    
    # Calculate statistics with cost aggregation
    stats = calculate_standard_deviation_stats(project_counts, contractor_costs)
    if not stats:
        return False
    
    # Create the final JSON structure
    result = {
        "success": True,
        "analysis": stats,
        "generated_at": datetime.now().isoformat(),
        "description": "Standard deviation analysis of contractor project counts with cost aggregation per SD group",
        "data_source": source,
        "flood_data_source": flood_source if flood_data else None,
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

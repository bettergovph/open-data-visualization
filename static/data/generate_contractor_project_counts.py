#!/usr/bin/env python3
"""
Generate Contractor Project Counts JSON
========================================
Creates a JSON file with project counts per contractor for scatter plot analysis.
This script analyzes flood control projects and counts how many projects each contractor has.
"""

import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from flood_client import FloodControlClient

async def generate_contractor_project_counts():
    """Generate contractor project counts for scatter plot analysis"""
    print("🔍 Generating contractor project counts...")
    
    try:
        # Initialize flood client
        client = FloodControlClient()
        
        # Check if MeiliSearch is accessible
        is_healthy = await client.health_check()
        if not is_healthy:
            print("❌ MeiliSearch is not accessible")
            return False
        
        print("✅ MeiliSearch connection established")
        
        # Get all projects
        projects, metadata = await client.search_projects("", limit=10000)
        print(f"📊 Found {len(projects)} projects")
        
        # Count projects per contractor and calculate costs
        contractor_counts = defaultdict(int)
        contractor_costs = defaultdict(float)
        total_projects = 0
        total_cost = 0.0
        
        for project in projects:
            contractor = project.Contractor
            if contractor and contractor.strip():
                contractor_counts[contractor] += 1
                total_projects += 1
                
                # Calculate cost
                if project.ContractCost:
                    try:
                        # Parse cost string (remove ₱, commas, spaces)
                        cost_str = str(project.ContractCost).replace('₱', '').replace(',', '').replace(' ', '')
                        cost = float(cost_str)
                        contractor_costs[contractor] += cost
                        total_cost += cost
                    except (ValueError, TypeError):
                        pass  # Skip invalid cost values
        
        print(f"📈 Analyzed {total_projects} projects from {len(contractor_counts)} contractors")
        print(f"💰 Total contract value: ₱{total_cost:,.2f}")
        
        # Create contractor data with both counts and costs
        contractor_data = []
        for contractor, count in contractor_counts.items():
            cost = contractor_costs.get(contractor, 0.0)
            contractor_data.append({
                'contractor': contractor,
                'project_count': count,
                'total_cost': cost
            })
        
        # Sort by project count (descending) for better visualization
        contractor_data.sort(key=lambda x: x['project_count'], reverse=True)
        
        # Extract arrays for scatter plot
        project_counts = [item['project_count'] for item in contractor_data]
        contractor_names = [item['contractor'] for item in contractor_data]
        contractor_costs_array = [item['total_cost'] for item in contractor_data]
        
        # Calculate basic statistics
        mean = sum(project_counts) / len(project_counts) if project_counts else 0
        variance = sum((count - mean) ** 2 for count in project_counts) / len(project_counts) if project_counts else 0
        standard_deviation = variance ** 0.5
        
        # Count outliers (beyond 3 standard deviations)
        outliers = [count for count in project_counts if abs(count - mean) > 3 * standard_deviation]
        
        # Prepare output data
        output_data = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "total_contractors": len(contractor_counts),
                "total_projects": total_projects,
                "total_cost": round(total_cost, 2),
                "mean_projects_per_contractor": round(mean, 2),
                "standard_deviation": round(standard_deviation, 2),
                "outliers_count": len(outliers),
                "outliers_threshold": round(mean + 3 * standard_deviation, 2)
            },
            "project_counts": project_counts,
            "contractor_names": contractor_names,
            "contractor_costs": contractor_costs_array,
            "contractor_details": [
                {
                    "contractor": item['contractor'],
                    "project_count": item['project_count'],
                    "total_cost": round(item['total_cost'], 2),
                    "z_score": round(abs(item['project_count'] - mean) / standard_deviation, 2) if standard_deviation > 0 else 0
                }
                for item in contractor_data
            ]
        }
        
        # Write to JSON file
        output_file = project_root / "static" / "data" / "contractor_project_counts.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Contractor project counts saved to: {output_file}")
        print(f"📊 Statistics:")
        print(f"   Mean projects per contractor: {mean:.2f}")
        print(f"   Standard deviation: {standard_deviation:.2f}")
        print(f"   Outliers (>3SD): {len(outliers)} contractors")
        print(f"   Max projects: {max(project_counts) if project_counts else 0}")
        print(f"   Min projects: {min(project_counts) if project_counts else 0}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error generating contractor project counts: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(generate_contractor_project_counts())
    sys.exit(0 if success else 1)

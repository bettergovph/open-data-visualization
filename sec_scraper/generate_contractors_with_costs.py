#!/usr/bin/env python3
"""
Generate Contractors with Costs and Suspicion Scores
Creates contractor data with total costs, average costs, and suspicion scores from MeiliSearch
"""

import asyncio
import os
import json
import sys
from datetime import datetime
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flood_client import FloodControlClient

load_dotenv()

async def generate_contractors_with_costs():
    """Generate contractor data with costs and suspicion scores from MeiliSearch"""
    try:
        # Initialize flood client
        client = FloodControlClient()
        
        print("🔍 Fetching all flood control projects from MeiliSearch...")
        
        # Get all projects to calculate costs
        all_projects = []
        offset = 0
        limit = 1000
        
        while True:
            projects, metadata = await client.search_projects(query="", limit=limit, offset=offset)
            if not projects or len(projects) == 0:
                break
            all_projects.extend(projects)
            offset += limit
            print(f"   Fetched {len(all_projects)} projects so far...")
            
            if len(projects) < limit:
                break
        
        print(f"✅ Total projects fetched: {len(all_projects)}")
        
        # Calculate contractor statistics
        contractor_stats = {}
        
        for project in all_projects:
            contractor = project.Contractor
            if not contractor:
                continue
                
            cost = float(project.ContractCost or 0)
            
            if contractor not in contractor_stats:
                contractor_stats[contractor] = {
                    'name': contractor,
                    'projects': 0,
                    'totalCost': 0.0,
                    'avgCostPerProject': 0.0,
                    'suspicionScore': 0,
                    'performance': 'Normal'
                }
            
            contractor_stats[contractor]['projects'] += 1
            contractor_stats[contractor]['totalCost'] += cost
        
        # Calculate statistics for SD calculation
        all_project_counts = [stats['projects'] for stats in contractor_stats.values()]
        all_avg_costs = [stats['totalCost'] / stats['projects'] if stats['projects'] > 0 else 0 for stats in contractor_stats.values()]
        
        # Calculate means and standard deviations
        import statistics
        mean_projects = statistics.mean(all_project_counts)
        mean_costs = statistics.mean(all_avg_costs)
        std_projects = statistics.stdev(all_project_counts) if len(all_project_counts) > 1 else 0
        std_costs = statistics.stdev(all_avg_costs) if len(all_avg_costs) > 1 else 0
        
        print(f"📊 Statistical Analysis:")
        print(f"   Projects - Mean: {mean_projects:.2f}, SD: {std_projects:.2f}")
        print(f"   Costs - Mean: {mean_costs:.2f}, SD: {std_costs:.2f}")
        
        # Calculate average costs and suspicion scores
        for contractor, stats in contractor_stats.items():
            if stats['projects'] > 0:
                stats['avgCostPerProject'] = stats['totalCost'] / stats['projects']
            
            # Calculate suspicion score with SD, projects, and cost factors
            # Use raw numbers (not rounded) and normalize to 0-100 range
            project_count = stats['projects']  # Raw project count
            avg_cost = stats['avgCostPerProject']  # Raw average cost
            
            # Factor 1: Standard Deviation (10 points per SD, capped at 40)
            # Calculate how many SDs away from mean for both projects and costs
            if std_projects > 0:
                project_sd = abs(project_count - mean_projects) / std_projects
            else:
                project_sd = 0
                
            if std_costs > 0:
                cost_sd = abs(avg_cost - mean_costs) / std_costs
            else:
                cost_sd = 0
                
            # Use the higher SD (more suspicious factor)
            max_sd = max(project_sd, cost_sd)
            # Square the SD value and normalize to 40 max
            sd_factor = min(max_sd * max_sd * 10.0, 40.0)  # Square SD, then 10 points per squared SD, capped at 40
            
            # Factor 2: Project count (0.3 points per project, capped at 30)
            # 0.3 points per project, so 100 projects = 30 points
            project_factor = min(project_count * 0.3, 30.0)  # 0.3 points per project, capped at 30
            
            # Factor 3: Average cost per project (0.3 points per million, capped at 30)
            # 0.3 points per million pesos, so 100M = 30 points
            cost_factor = min((avg_cost / 1000000) * 0.3, 30.0)  # 0.3 points per million, capped at 30
            
            # Add all factors together for final suspicion score (0-100 range)
            suspicion_score = sd_factor + project_factor + cost_factor
            
            # Store the suspicion score with decimal values (0-100 range)
            stats['suspicionScore'] = round(suspicion_score, 2)
            
            # Set performance level based on 0-100 scoring system
            if stats['suspicionScore'] >= 70.0:  # High risk threshold
                stats['performance'] = 'High Risk'
            elif stats['suspicionScore'] >= 40.0:  # Medium risk threshold
                stats['performance'] = 'Medium Risk'
            else:
                stats['performance'] = 'Normal'
        
        # Convert to list and sort by project count
        contractors_list = list(contractor_stats.values())
        contractors_list.sort(key=lambda x: x['projects'], reverse=True)
        
        # Generate output data
        output_data = {
            "success": True,
            "contractors": contractors_list,
            "summary": {
                "total_contractors": len(contractors_list),
                "total_projects": sum(c['projects'] for c in contractors_list),
                "total_cost": sum(c['totalCost'] for c in contractors_list),
                "high_risk_contractors": len([c for c in contractors_list if c['suspicionScore'] >= 70]),
                "medium_risk_contractors": len([c for c in contractors_list if 40 <= c['suspicionScore'] < 70]),
                "normal_contractors": len([c for c in contractors_list if c['suspicionScore'] < 40])
            },
            "generated_at": datetime.now().isoformat(),
            "description": "Contractor data with costs and suspicion scores from MeiliSearch",
            "cache_version": "1.0"
        }
        
        # Save to file
        output_file = "static/data/contractors_with_costs.json"
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)
        
        print(f"✅ Generated contractor data with costs and suspicion scores")
        print(f"   📊 Total contractors: {len(contractors_list)}")
        print(f"   📊 Total projects: {output_data['summary']['total_projects']}")
        print(f"   📊 Total cost: ₱{output_data['summary']['total_cost']:,.2f}")
        print(f"   ⚠️  High risk contractors: {output_data['summary']['high_risk_contractors']}")
        print(f"   ⚠️  Medium risk contractors: {output_data['summary']['medium_risk_contractors']}")
        print(f"   ✅ Normal contractors: {output_data['summary']['normal_contractors']}")
        print(f"   💾 Saved to: {output_file}")
        
        return output_data
        
    except Exception as e:
        print(f"❌ Error generating contractor data: {e}")
        return None

async def main():
    """Main function"""
    print("🚀 Starting contractor cost and suspicion score generation...")
    result = await generate_contractors_with_costs()
    
    if result:
        print("🎉 Contractor data generation completed successfully!")
        return 0
    else:
        print("❌ Contractor data generation failed!")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)

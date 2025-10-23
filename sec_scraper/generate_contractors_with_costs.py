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
        
        # Calculate average costs and suspicion scores
        for contractor, stats in contractor_stats.items():
            if stats['projects'] > 0:
                stats['avgCostPerProject'] = stats['totalCost'] / stats['projects']
            
            # Calculate suspicion score using 50-50 multiplier approach
            # Use raw numbers (not rounded) and normalize to 0-100 range
            project_count = stats['projects']  # Raw project count
            avg_cost = stats['avgCostPerProject']  # Raw average cost
            
            # 50-50 multiplier: equal weight for both factors
            # Factor 1: Project count (normalized to 0-50 range)
            # Assume max reasonable project count is 200, normalize to 0-50
            project_factor = min(project_count / 4.0, 50.0)  # project_count/4, capped at 50
            
            # Factor 2: Average cost per project (normalized to 0-50 range)
            # Scale cost to reasonable range (divide by 1M to get millions, then normalize)
            # Assume max reasonable cost is 100M per project, normalize to 0-50
            cost_factor = min((avg_cost / 1000000) / 2.0, 50.0)  # (avg_cost/1M)/2, capped at 50
            
            # Add both factors together for final suspicion score (0-100 range)
            suspicion_score = project_factor + cost_factor
            
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

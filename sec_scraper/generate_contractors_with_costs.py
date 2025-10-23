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
            
            # Calculate suspicion score based on project count and average cost per project
            # Score range: 0-100
            project_count = stats['projects']
            avg_cost = stats['avgCostPerProject']
            
            suspicion_score = 0
            
            # Factor 1: Number of projects (more projects = higher suspicion)
            # Scale: 0-50 points based on project count
            if project_count >= 100:
                suspicion_score += 50  # Maximum for project count
            elif project_count >= 80:
                suspicion_score += 40
            elif project_count >= 60:
                suspicion_score += 35
            elif project_count >= 40:
                suspicion_score += 30
            elif project_count >= 20:
                suspicion_score += 20
            elif project_count >= 10:
                suspicion_score += 10
            # 0-9 projects = 0 points
            
            # Factor 2: Average cost per project (higher average = higher suspicion)
            # Scale: 0-50 points based on average cost
            if avg_cost >= 100000000:  # 100M+ per project
                suspicion_score += 50  # Maximum for average cost
            elif avg_cost >= 50000000:  # 50M+ per project
                suspicion_score += 40
            elif avg_cost >= 20000000:  # 20M+ per project
                suspicion_score += 35
            elif avg_cost >= 10000000:  # 10M+ per project
                suspicion_score += 30
            elif avg_cost >= 5000000:  # 5M+ per project
                suspicion_score += 20
            elif avg_cost >= 1000000:  # 1M+ per project
                suspicion_score += 10
            # Less than 1M per project = 0 points
            
            # Cap suspicion score at 100
            stats['suspicionScore'] = min(suspicion_score, 100)
            
            # Set performance level
            if stats['suspicionScore'] >= 70:
                stats['performance'] = 'High Risk'
            elif stats['suspicionScore'] >= 40:
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

#!/usr/bin/env python3
"""
Generate Flood Control Data with Joint Ventures
Creates flood control data with joint venture detection and partner extraction
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

def is_joint_venture(name: str) -> bool:
    """Check if contractor name represents a joint venture
    
    ONLY check for / (forward slash) as JV indicator
    Do NOT use & or AND as they are part of company names
    """
    if not name:
        return False
    
    # ONLY use / as JV indicator
    return '/' in name

def split_joint_venture(name: str) -> tuple:
    """Split joint venture name into two partners"""
    if not is_joint_venture(name):
        return None, None
    
    # Split by / and clean up
    parts = name.split('/')
    if len(parts) >= 2:
        partner1 = parts[0].strip()
        partner2 = parts[1].strip()
        return partner1, partner2
    
    return None, None

async def generate_flood_control_with_jv():
    """Generate flood control data with joint venture detection"""
    try:
        # Initialize flood client
        client = FloodControlClient()
        
        print("🔍 Fetching all flood control projects from MeiliSearch...")
        
        # Get all projects
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
        
        # Process projects and detect joint ventures
        processed_projects = []
        jv_count = 0
        
        for project in all_projects:
            # Convert to dictionary for JSON serialization
            project_dict = {
                "GlobalID": project.GlobalID,
                "ProjectDescription": project.ProjectDescription,
                "InfraYear": project.InfraYear,
                "Region": project.Region,
                "Province": project.Province,
                "Municipality": project.Municipality,
                "TypeofWork": project.TypeofWork,
                "Contractor": project.Contractor,
                "ContractCost": project.ContractCost,
                "DistrictEngineeringOffice": project.DistrictEngineeringOffice,
                "LegislativeDistrict": project.LegislativeDistrict,
                "ContractID": project.ContractID,
                "ProjectID": project.ProjectID,
                "Latitude": project.Latitude,
                "Longitude": project.Longitude,
                "is_joint_venture": False,
                "jv_partner1": None,
                "jv_partner2": None
            }
            
            # Check if this is a joint venture
            if is_joint_venture(project.Contractor):
                project_dict["is_joint_venture"] = True
                partner1, partner2 = split_joint_venture(project.Contractor)
                project_dict["jv_partner1"] = partner1
                project_dict["jv_partner2"] = partner2
                jv_count += 1
            
            processed_projects.append(project_dict)
        
        # Generate output data
        output_data = {
            "projects": processed_projects,
            "summary": {
                "total_projects": len(processed_projects),
                "joint_ventures": jv_count,
                "regular_contractors": len(processed_projects) - jv_count,
                "generated_at": datetime.now().isoformat()
            }
        }
        
        # Save to file
        output_file = "static/data/flood_control_data_with_jv.json"
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)
        
        print(f"✅ Generated flood control data with joint venture detection")
        print(f"   📊 Total projects: {len(processed_projects)}")
        print(f"   🤝 Joint ventures: {jv_count}")
        print(f"   🏢 Regular contractors: {len(processed_projects) - jv_count}")
        print(f"   💾 Saved to: {output_file}")
        
        return output_data
        
    except Exception as e:
        print(f"❌ Error generating flood control data with JV: {e}")
        return None

async def main():
    """Main function"""
    print("🚀 Starting flood control data with joint venture generation...")
    result = await generate_flood_control_with_jv()
    
    if result:
        print("🎉 Flood control data with JV generation completed successfully!")
        return 0
    else:
        print("❌ Flood control data with JV generation failed!")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)

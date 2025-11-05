#!/usr/bin/env python3
"""
Ad-hoc script to find all projects in Quezon 2nd District
"""

import asyncio
import os
from dotenv import load_dotenv
from flood_client import FloodControlClient

# Load environment variables
load_dotenv()

async def find_quezon_2nd_district_projects():
    """Find all projects in Quezon 2nd District"""
    
    # Quezon 2nd District municipalities
    municipalities = ["Lucena", "Candelaria", "Dolores", "San Antonio", "Sariaya", "Tiaong"]
    
    client = FloodControlClient()
    
    # Check health
    is_healthy = await client.health_check()
    if not is_healthy:
        print("❌ MeiliSearch connection failed!")
        return
    
    print("✅ Connected to MeiliSearch")
    print(f"\n🔍 Searching for projects in Quezon 2nd District municipalities: {municipalities}\n")
    
    all_projects = []
    
    # Search for each municipality
    for mun in municipalities:
        print(f"Searching for '{mun}'...")
        
        # Search without filters first
        projects, metadata = await client.search_projects(
            query=mun,
            filters=None,
            limit=500,
            offset=0
        )
        
        print(f"  Found {len(projects)} projects mentioning '{mun}'")
        
        # Filter to only projects that also mention "Quezon"
        filtered = []
        for proj in projects:
            proj_name = (proj.ProjectDescription or '').upper()
            proj_province = (proj.Province or '').upper()
            proj_municipality = (proj.Municipality or '').upper()
            combined_text = f'{proj_name} {proj_province} {proj_municipality}'
            
            # Check if municipality is mentioned
            mun_mentioned = mun.upper() in combined_text
            # Check if Quezon is mentioned (not Quezon City)
            quezon_mentioned = 'QUEZON' in combined_text and 'QUEZON CITY' not in combined_text
            
            if mun_mentioned and quezon_mentioned:
                filtered.append(proj)
        
        print(f"  ✅ {len(filtered)} projects match (municipality + Quezon mentioned)")
        
        # Add to all_projects, avoiding duplicates
        for proj in filtered:
            if not any(p.GlobalID == proj.GlobalID for p in all_projects if hasattr(p, 'GlobalID')):
                all_projects.append(proj)
    
    print(f"\n📊 TOTAL UNIQUE PROJECTS: {len(all_projects)}")
    
    # Show sample projects
    print("\n" + "="*80)
    print("SAMPLE PROJECTS (first 10):")
    print("="*80)
    
    for i, proj in enumerate(all_projects[:10], 1):
        print(f"\n{i}. {proj.ProjectDescription or 'N/A'}")
        print(f"   Province: {proj.Province or 'N/A'}")
        print(f"   Municipality: {proj.Municipality or 'N/A'}")
        print(f"   Contractor: {proj.Contractor or 'N/A'}")
        print(f"   Amount: {proj.ContractCost or 'N/A'}")
        print(f"   Year: {proj.InfraYear or 'N/A'}")
        print(f"   GlobalID: {proj.GlobalID if hasattr(proj, 'GlobalID') else 'N/A'}")
    
    if len(all_projects) > 10:
        print(f"\n... and {len(all_projects) - 10} more projects")
    
    # Also try searching by "Quezon" directly
    print("\n" + "="*80)
    print("SEARCHING BY 'QUEZON' DIRECTLY:")
    print("="*80)
    
    projects2, metadata2 = await client.search_projects(
        query="Quezon",
        filters='Province = "QUEZON"',
        limit=1000,
        offset=0
    )
    
    print(f"Found {len(projects2)} projects with Province = 'QUEZON'")
    
    # Filter to 2nd District municipalities
    filtered2 = []
    for proj in projects2:
        proj_name = (proj.ProjectDescription or '').upper()
        proj_municipality = (proj.Municipality or '').upper()
        combined = f'{proj_name} {proj_municipality}'
        
        # Check if any 2nd district municipality is mentioned
        for mun in municipalities:
            if mun.upper() in combined:
                filtered2.append(proj)
                break
    
    print(f"✅ {len(filtered2)} projects match 2nd District municipalities")
    
    print("\n" + "="*80)
    print("SAMPLE FROM QUEZON PROVINCE SEARCH (first 10):")
    print("="*80)
    
    for i, proj in enumerate(filtered2[:10], 1):
        print(f"\n{i}. {proj.ProjectDescription or 'N/A'}")
        print(f"   Province: {proj.Province or 'N/A'}")
        print(f"   Municipality: {proj.Municipality or 'N/A'}")

if __name__ == "__main__":
    asyncio.run(find_quezon_2nd_district_projects())


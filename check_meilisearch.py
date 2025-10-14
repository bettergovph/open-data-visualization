"""
Quick script to check MeiliSearch flood control data and compare with CSV
"""
import asyncio
import csv
from flood_client import FloodControlClient
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    print("🔍 Checking MeiliSearch flood control data...")
    print("=" * 80)
    
    # Initialize client
    try:
        client = FloodControlClient()
        print(f"✅ Connected to: {client.base_url}")
        print(f"   Index: {client.index_name}")
        print()
    except Exception as e:
        print(f"❌ Failed to initialize client: {e}")
        return
    
    # Health check
    print("🏥 Health Check...")
    is_healthy = await client.health_check()
    if not is_healthy:
        print("❌ MeiliSearch is not healthy or index doesn't exist!")
        return
    print("✅ MeiliSearch is healthy")
    print()
    
    # Get statistics from MeiliSearch
    print("📊 Getting MeiliSearch statistics...")
    stats = await client.get_statistics()
    print(f"   Total Projects: {stats.totalProjects:,}")
    print(f"   Total Cost: ₱{stats.totalCost:,.2f}")
    print(f"   Unique Contractors: {stats.uniqueContractors:,}")
    print(f"   Regions: {len(stats.regions)}")
    print(f"   Years: {sorted(stats.years.keys())}")
    print()
    
    # Check CSV file
    print("📄 Checking CSV file...")
    csv_file = "/home/joebert/open-data-visualization/database/contracts_export_flood_control_data.csv"
    
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            csv_rows = list(reader)
            csv_count = len(csv_rows)
            
        print(f"   CSV rows (excluding header): {csv_count:,}")
        print(f"   CSV columns: {list(csv_rows[0].keys()) if csv_rows else 'N/A'}")
        print()
        
        # Show first few CSV rows
        print("📋 First 3 rows from CSV:")
        for i, row in enumerate(csv_rows[:3], 1):
            print(f"\n   Row {i}:")
            print(f"      Contract No: {row.get('contract_no', 'N/A')}")
            print(f"      Awardee: {row.get('awardee_name', 'N/A')}")
            print(f"      Organization: {row.get('organization_name', 'N/A')}")
            print(f"      Amount: {row.get('contract_amount', 'N/A')}")
            print(f"      Date: {row.get('award_date', 'N/A')}")
            print(f"      Area: {row.get('area_of_delivery', 'N/A')}")
        
        print()
        
    except Exception as e:
        print(f"❌ Failed to read CSV: {e}")
        csv_count = 0
    
    # Get sample from MeiliSearch
    print("📋 First 3 projects from MeiliSearch:")
    projects, metadata = await client.search_projects("", limit=3)
    for i, project in enumerate(projects, 1):
        print(f"\n   Project {i}:")
        print(f"      GlobalID: {project.GlobalID}")
        print(f"      Description: {project.ProjectDescription[:80] if project.ProjectDescription else 'N/A'}...")
        print(f"      Contractor: {project.Contractor}")
        print(f"      Cost: {project.ContractCost}")
        print(f"      Year: {project.InfraYear}")
        print(f"      Region: {project.Region}")
        print(f"      Province: {project.Province}")
    
    print()
    print("=" * 80)
    print("📊 COMPARISON SUMMARY:")
    print(f"   CSV File:       {csv_count:,} rows")
    print(f"   MeiliSearch:    {stats.totalProjects:,} documents")
    print(f"   Difference:     {abs(csv_count - stats.totalProjects):,} {'(CSV has more)' if csv_count > stats.totalProjects else '(MeiliSearch has more)' if stats.totalProjects > csv_count else '(MATCH!)'}")
    print()
    
    # Note about data structure differences
    print("⚠️  NOTE: The CSV appears to be from PhilGEPS contracts data,")
    print("   while MeiliSearch contains DPWH Flood Control Infrastructure data.")
    print("   These are DIFFERENT datasets with different structures!")
    print()
    print("   CSV fields: reference_id, contract_no, award_title, awardee_name, etc.")
    print("   MeiliSearch fields: GlobalID, ProjectDescription, InfraYear, etc.")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())


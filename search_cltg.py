#!/usr/bin/env python3
import asyncio
import asyncpg
import os

async def search_cltg():
    """Search for CLTG contractor across all three databases"""
    
    # Flood database
    print("\n" + "="*80)
    print("FLOOD CONTROL DATABASE")
    print("="*80)
    try:
        flood_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database='flood'
        )
        
        # Get CLTG projects from flood
        flood_results = await flood_conn.fetch("""
            SELECT COUNT(*) as project_count, 
                   SUM("ContractCost") as total_value,
                   AVG("ContractCost") as avg_value,
                   MIN("ContractCost") as min_value,
                   MAX("ContractCost") as max_value
            FROM flood_control 
            WHERE "Contractor" ILIKE '%CLTG%'
        """)
        
        if flood_results:
            row = flood_results[0]
            print(f"Project Count: {row['project_count']:,}")
            print(f"Total Value: ₱{row['total_value']:,.2f}" if row['total_value'] else "Total Value: ₱0.00")
            print(f"Average Value: ₱{row['avg_value']:,.2f}" if row['avg_value'] else "Average Value: ₱0.00")
            print(f"Min Value: ₱{row['min_value']:,.2f}" if row['min_value'] else "Min Value: ₱0.00")
            print(f"Max Value: ₱{row['max_value']:,.2f}" if row['max_value'] else "Max Value: ₱0.00")
        
        # Get specific projects
        flood_projects = await flood_conn.fetch("""
            SELECT "ProjectDescription", "Contractor", "ContractCost", "InfraYear", "Region"
            FROM flood_control 
            WHERE "Contractor" ILIKE '%CLTG%'
            ORDER BY "ContractCost" DESC
        """)
        
        print(f"\nTop {min(10, len(flood_projects))} Projects:")
        for i, proj in enumerate(flood_projects[:10], 1):
            print(f"{i}. ₱{proj['ContractCost']:,.2f} - {proj['ProjectDescription'][:80]}")
            print(f"   Year: {proj['InfraYear']}, Region: {proj['Region']}")
        
        await flood_conn.close()
    except Exception as e:
        print(f"Error querying flood database: {e}")
    
    # DIME database
    print("\n" + "="*80)
    print("DIME DATABASE")
    print("="*80)
    try:
        dime_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database='dime'
        )
        
        # Get CLTG projects from DIME
        dime_results = await dime_conn.fetch("""
            SELECT COUNT(*) as project_count, 
                   SUM(total_amount) as total_value,
                   AVG(total_amount) as avg_value,
                   MIN(total_amount) as min_value,
                   MAX(total_amount) as max_value
            FROM dime_projects 
            WHERE contractor ILIKE '%CLTG%'
        """)
        
        if dime_results:
            row = dime_results[0]
            print(f"Project Count: {row['project_count']:,}")
            print(f"Total Value: ₱{row['total_value']:,.2f}" if row['total_value'] else "Total Value: ₱0.00")
            print(f"Average Value: ₱{row['avg_value']:,.2f}" if row['avg_value'] else "Average Value: ₱0.00")
            print(f"Min Value: ₱{row['min_value']:,.2f}" if row['min_value'] else "Min Value: ₱0.00")
            print(f"Max Value: ₱{row['max_value']:,.2f}" if row['max_value'] else "Max Value: ₱0.00")
        
        # Get specific projects
        dime_projects = await dime_conn.fetch("""
            SELECT project_title, contractor, total_amount, region, province
            FROM dime_projects 
            WHERE contractor ILIKE '%CLTG%'
            ORDER BY total_amount DESC
        """)
        
        print(f"\nTop {min(10, len(dime_projects))} Projects:")
        for i, proj in enumerate(dime_projects[:10], 1):
            print(f"{i}. ₱{proj['total_amount']:,.2f} - {proj['project_title'][:80]}")
            print(f"   Region: {proj['region']}, Province: {proj['province']}")
        
        await dime_conn.close()
    except Exception as e:
        print(f"Error querying DIME database: {e}")
    
    # PhilGEPS database
    print("\n" + "="*80)
    print("PHILGEPS DATABASE")
    print("="*80)
    try:
        philgeps_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database='philgeps'
        )
        
        # Get CLTG projects from PhilGEPS
        philgeps_results = await philgeps_conn.fetch("""
            SELECT COUNT(*) as project_count, 
                   SUM(contract_amount) as total_value,
                   AVG(contract_amount) as avg_value,
                   MIN(contract_amount) as min_value,
                   MAX(contract_amount) as max_value
            FROM philgeps_awards 
            WHERE awardee ILIKE '%CLTG%'
        """)
        
        if philgeps_results:
            row = philgeps_results[0]
            print(f"Project Count: {row['project_count']:,}")
            print(f"Total Value: ₱{row['total_value']:,.2f}" if row['total_value'] else "Total Value: ₱0.00")
            print(f"Average Value: ₱{row['avg_value']:,.2f}" if row['avg_value'] else "Average Value: ₱0.00")
            print(f"Min Value: ₱{row['min_value']:,.2f}" if row['min_value'] else "Min Value: ₱0.00")
            print(f"Max Value: ₱{row['max_value']:,.2f}" if row['max_value'] else "Max Value: ₱0.00")
        
        # Get specific projects
        philgeps_projects = await philgeps_conn.fetch("""
            SELECT reference_number, description, awardee, contract_amount, procurement_mode, procuring_entity
            FROM philgeps_awards 
            WHERE awardee ILIKE '%CLTG%'
            ORDER BY contract_amount DESC
            LIMIT 10
        """)
        
        print(f"\nTop {len(philgeps_projects)} Projects:")
        for i, proj in enumerate(philgeps_projects, 1):
            print(f"{i}. ₱{proj['contract_amount']:,.2f} - {proj['description'][:80]}")
            print(f"   Entity: {proj['procuring_entity']}")
        
        await philgeps_conn.close()
    except Exception as e:
        print(f"Error querying PhilGEPS database: {e}")
    
    # Grand Total
    print("\n" + "="*80)
    print("GRAND TOTAL ACROSS ALL DATABASES")
    print("="*80)
    
    # Calculate totals
    try:
        flood_total = flood_results[0]['total_value'] if flood_results and flood_results[0]['total_value'] else 0
        flood_count = flood_results[0]['project_count'] if flood_results else 0
    except:
        flood_total = 0
        flood_count = 0
    
    try:
        dime_total = dime_results[0]['total_value'] if dime_results and dime_results[0]['total_value'] else 0
        dime_count = dime_results[0]['project_count'] if dime_results else 0
    except:
        dime_total = 0
        dime_count = 0
    
    try:
        philgeps_total = philgeps_results[0]['total_value'] if philgeps_results and philgeps_results[0]['total_value'] else 0
        philgeps_count = philgeps_results[0]['project_count'] if philgeps_results else 0
    except:
        philgeps_total = 0
        philgeps_count = 0
    
    grand_total = flood_total + dime_total + philgeps_total
    grand_count = flood_count + dime_count + philgeps_count
    
    print(f"Total Projects: {grand_count:,}")
    print(f"Total Value: ₱{grand_total:,.2f}")
    print(f"\nBreakdown:")
    print(f"  Flood Control: {flood_count:,} projects, ₱{flood_total:,.2f}")
    print(f"  DIME: {dime_count:,} projects, ₱{dime_total:,.2f}")
    print(f"  PhilGEPS: {philgeps_count:,} projects, ₱{philgeps_total:,.2f}")

if __name__ == "__main__":
    asyncio.run(search_cltg())


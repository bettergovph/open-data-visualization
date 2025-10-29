#!/usr/bin/env python3
"""
Generate budget regions data for multiple years (2020-2025)
Creates a JSON file with budget data by region over time for stacked area chart
"""

import json
import os
import sys
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# Add the project root to the path so we can import budget client
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

try:
    from budget_postgres_client import get_db_connection
except ImportError:
    print("❌ Could not import budget_postgres_client. Make sure budget_postgres_client.py exists.")
    sys.exit(1)

async def generate_budget_regions_json():
    """Generate budget regions data for multiple years"""
    print("🚀 Starting budget regions data generation...")
    
    # Load environment variables
    load_dotenv()
    
    # Years to analyze
    years = [2020, 2021, 2022, 2023, 2024, 2025]
    
    # Store data for each year
    yearly_data = {}
    all_regions = set()
    
    print(f"📊 Analyzing budget data for years: {years}")
    
    # Get database connection
    conn = None
    try:
        conn = await get_db_connection()
        
        for year in years:
            print(f"🔍 Processing year {year}...")
            try:
                # Query budget data by region for this year from year-specific table
                table_name = f"budget_{year}"
                query = f"""
                SELECT 
                    uacs_reg_id,
                    SUM(amt) as total_amount
                FROM {table_name}
                WHERE uacs_reg_id IS NOT NULL
                GROUP BY uacs_reg_id
                ORDER BY total_amount DESC
                """
                
                rows = await conn.fetch(query)
                
                if not rows:
                    print(f"⚠️ No data found for year {year}")
                    yearly_data[year] = []
                    continue
                
                # Convert to list format
                regions_list = []
                for row in rows:
                    region_id = row['uacs_reg_id'] or 'Unknown'
                    total_amount = float(row['total_amount']) if row['total_amount'] else 0
                    
                    regions_list.append({
                        'uacs_reg_id': region_id,
                        'total_amount': total_amount,
                        'region_name': f'Region {region_id}'
                    })
                    
                    all_regions.add(region_id)
                
                yearly_data[year] = regions_list
                print(f"✅ Year {year}: {len(regions_list)} regions, total budget: ₱{sum(r['total_amount'] for r in regions_list):,.0f}")
                
            except Exception as e:
                print(f"❌ Error processing year {year}: {e}")
                yearly_data[year] = []
    
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False
    finally:
        if conn:
            await conn.close()
    
    # Create the final data structure
    output_data = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "years_analyzed": years,
            "total_regions": len(all_regions),
            "description": "Budget data by region over multiple years for stacked area chart visualization"
        },
        "yearly_data": yearly_data,
        "regions_summary": {}
    }
    
    # Create regions summary (all regions across all years)
    for region_id in sorted(all_regions, key=str):
        region_data = {
            "region_id": region_id,
            "region_name": f"Region {region_id}",
            "years_data": {}
        }
        
        for year in years:
            year_data = yearly_data.get(year, [])
            region_amount = 0
            for region in year_data:
                if region['uacs_reg_id'] == region_id:
                    region_amount = region['total_amount']
                    break
            
            region_data["years_data"][str(year)] = {
                "amount": region_amount,
                "amount_billions": round(region_amount * 1000 / 1000000000, 2)
            }
        
        output_data["regions_summary"][region_id] = region_data
    
    # Save to JSON file
    output_file = os.path.join(os.path.dirname(__file__), 'budget_regions.json')
    
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Budget regions data saved to: {output_file}")
        
        # Print summary
        total_budget_all_years = 0
        for year in years:
            year_total = sum(r['total_amount'] for r in yearly_data.get(year, []))
            total_budget_all_years += year_total
            print(f"📊 Year {year}: ₱{year_total:,.0f} total budget across {len(yearly_data.get(year, []))} regions")
        
        print(f"📈 Total budget across all years: ₱{total_budget_all_years:,.0f}")
        print(f"🗺️ Unique regions found: {len(all_regions)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error saving JSON file: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(generate_budget_regions_json())
    if success:
        print("🎉 Budget regions data generation completed successfully!")
    else:
        print("💥 Budget regions data generation failed!")
        sys.exit(1)

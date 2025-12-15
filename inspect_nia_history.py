
import asyncio
import os
import sys
import json

# Add the project directory to the python path
sys.path.append(os.getcwd())

from visualization import budget_roads_cost_analysis_api

async def check_nia_history():
    years = ['2020', '2021', '2022', '2023', '2024', '2025', '2026']
    
    print(f"{'Year':<6} | {'NIA Projects':<12} | {'Total Amount (P)':<20}")
    print("-" * 45)
    
    for year in years:
        try:
            response = await budget_roads_cost_analysis_api(year)
            # Handle JSONResponse object
            if hasattr(response, 'body'):
                data = json.loads(response.body)
            else:
                data = response
                
            if not data.get('success'):
                error_msg = data.get('error', 'Unknown error')
                print(f"{year:<6} | {'Error':<12} | {error_msg:<20}")
                continue
                
            nia_data = data.get('nia', {})
            projects = nia_data.get('projects', [])
            total_amount = sum(p.get('amount', 0) for p in projects)
            
            print(f"{year:<6} | {len(projects):<12} | {total_amount:,.2f}")
            
            if year == '2024':
                 all_items = data.get('roads', {}).get('projects', []) + \
                             data.get('bridges', {}).get('projects', []) + \
                             data.get('traffic_signs', {}).get('projects', []) + \
                             data.get('nia', {}).get('projects', []) + \
                             data.get('multi_purpose_buildings', {}).get('projects', []) + \
                             data.get('rockfall_netting', {}).get('projects', []) + \
                             data.get('schools', {}).get('projects', [])
                 
                 irrigation_count = 0
                 print(f"\nScanning all {len(all_items)} projects in 2024 for 'irrigation' keyword...")
                 for p in all_items:
                     name = p.get('project_name', '') or p.get('name', '')
                     if 'irrigation' in name.lower():
                         irrigation_count += 1
                         if irrigation_count <= 3:
                             print(f"  Found: {name} (Category: Unknown)")
                 print(f"Total 'irrigation' matches in 2024: {irrigation_count}\n")
            
        except Exception as e:
            print(f"{year:<6} | {'Exception':<12} | {str(e)}")

if __name__ == "__main__":
    asyncio.run(check_nia_history())

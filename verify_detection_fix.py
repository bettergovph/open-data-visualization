
import asyncio
import os
import sys
import json

# Add the project directory to the python path
sys.path.append(os.getcwd())

from visualization import budget_roads_cost_analysis_api

async def verify_fix():
    print("Verifying 2024 detection...")
    
    # Call the API function directly
    # Note: It returns a FastAPI Response object, need to parse body
    response = await budget_roads_cost_analysis_api("2023")
    
    if response.status_code != 200:
        print(f"API Error: {response.status_code}")
        return

    data = json.loads(response.body)
    
    # Check NIA
    nia_data = data.get('nia', {})
    nia_projects = nia_data.get('projects', [])
    print(f"NIA Projects found: {len(nia_projects)}")
    if len(nia_projects) > 0:
        print("Sample NIA projects:")
        for p in nia_projects[:5]:
            print(f" - {p.get('name')}")
            
    # Check Rockfall
    rockfall_data = data.get('rockfall_netting', {})
    rockfall_projects = rockfall_data.get('projects', [])
    print(f"Rockfall Projects found: {len(rockfall_projects)}")
    if len(rockfall_projects) > 0:
        print("Sample Rockfall projects:")
        for p in rockfall_projects[:5]:
            print(f" - {p.get('name')}")

if __name__ == "__main__":
    asyncio.run(verify_fix())

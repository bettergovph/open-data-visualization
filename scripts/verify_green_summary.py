
import asyncio
import json
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock FastAPI setup to test the endpoint function directly
from visualization import integrated_projects_api

async def verify_api():
    print("Testing /api/integrated/projects?green=true...")
    
    # Call the API function directly
    # Note: We need to mock the response or handle the JSONResponse object
    response = await integrated_projects_api(
        page=1, 
        limit=5, 
        project_name=None, 
        contractor=None, 
        source=None, 
        green=True
    )
    
    # Extract data from JSONResponse
    import json
    body = response.body.decode('utf-8')
    data = json.loads(body)
    
    if not data.get('success'):
        print("❌ API returned failure:", data.get('error'))
        return
        
    print(f"✅ API Success")
    print(f"Total Projects: {data.get('total')}")
    print(f"Total Amount: ₱{data.get('total_amount'):,.2f}")
    print(f"Total Districts: {data.get('total_districts')}")
    
    projects = data.get('projects', [])
    print(f"Returned {len(projects)} projects in page 1")
    
    if projects:
        print("\nSample Project 1:")
        print(json.dumps(projects[0], indent=2))
        
        # Verify source is correct
        if projects[0].get('source') == 'Annex A-5 (2026)':
            print("\n✅ Correct Source Detected")
        else:
            print(f"\n❌ Incorrect Source: {projects[0].get('source')}")

    # Check if we have stats
    if 'total_amount' in data and 'total_districts' in data:
         print("\n✅ Dashboard Stats Present")
    else:
         print("\n❌ Dashboard Stats MISSING")

if __name__ == "__main__":
    asyncio.run(verify_api())

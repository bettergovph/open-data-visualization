import sys
import asyncio
import os

# Add current directory to path
sys.path.append('/home/joebert/open-data-visualization')

from visualization import get_contract_splitting

async def test_endpoint():
    print("Testing get_contract_splitting...")
    try:
        response = await get_contract_splitting()
        import json
        data = json.loads(response.body)
        
        if data['success']:
            print("SUCCESS: Endpoint returned success=True")
            clusters = data.get('clusters', [])
            print(f"Found {len(clusters)} clusters.")
            if len(clusters) > 0:
                print("First cluster sample:")
                print(clusters[0])
            else:
                print("WARNING: No clusters returned.")
        else:
            print(f"FAILED: {data.get('error')}")
            
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test_endpoint())

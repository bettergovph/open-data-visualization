
import requests
import json

def test_api():
    contract_id = "20O00045"
    url = f"https://api.transparency.dpwh.gov.ph/projects/{contract_id}/images?limit=2000&includeCoordinates=true"
    
    print(f"Testing API: {url}")
    
    try:
        # Mimic browser headers just in case
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Referer': 'https://transparency.dpwh.gov.ph/'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("Success! JSON Response snippet:")
            print(json.dumps(data, indent=2)[:500]) # First 500 chars
            
            # Check for image urls
            if isinstance(data, list) and len(data) > 0:
                print(f"Found {len(data)} images.")
                print(f"Sample Image URL: {data[0].get('url')}")
            elif isinstance(data, dict):
                 # Check if structure is different
                 print("Response is a dict.")
        else:
            print("Failed to retrieve data.")
            print(response.text[:500])
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_api()

from fastapi.testclient import TestClient
import sys
# Add parent dir to path
sys.path.insert(0, '/home/joebert/open-data-visualization')
from visualization import app

client = TestClient(app)

def test_endpoint():
    print("Testing /api/budget/condition-analysis...")
    response = client.get("/api/budget/condition-analysis")
    
    if response.status_code == 200:
        data = response.json()
        print("Success:", data.get('success'))
        print("Low Priority Count:", len(data.get('low_priority_projects', [])))
        print("No Data Count:", len(data.get('no_data_projects', [])))
        
        # Sample items
        if data.get('low_priority_projects'):
            print("\nSample Low Priority:", data['low_priority_projects'][0])
        if data.get('no_data_projects'):
            print("\nSample No Data:", data['no_data_projects'][0])
    else:
        print("Failed:", response.status_code, response.text)

if __name__ == "__main__":
    test_endpoint()

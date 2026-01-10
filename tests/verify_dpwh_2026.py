
import sys
import os
# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from visualization import app

client = TestClient(app)

def test_dpwh_projects():
    print("Testing /api/dpwh2026/projects...")
    response = client.get("/api/dpwh2026/projects")
    
    if response.status_code != 200:
        print(f"FAILED: Status Code {response.status_code}")
        print(response.json())
        return False
        
    data = response.json()
    items = data.get("data", [])
    total = data.get("total", 0)
    
    print(f"Total Items: {total}")
    print(f"Items on page 1: {len(items)}")
    
    if not items:
        print("FAILED: No items returned")
        return False
        
    # Inspect first item
    first = items[0]
    print("First Item Sample:")
    print(first)
    
    required_fields = ["project_name", "amount", "region", "district", "program"]
    missing = [f for f in required_fields if f not in first]
    
    if missing:
        print(f"FAILED: Missing fields {missing}")
        return False
        
    print("SUCCESS: /api/dpwh2026/projects looks good.")
    
    print("\nTesting Search 'Davao'...")
    response_search = client.get("/api/dpwh2026/projects?search=Davao")
    data_search = response_search.json()
    items_search = data_search.get("data", [])
    print(f"Items found for 'Davao': {len(items_search)}")
    if len(items_search) > 0:
        print("First Match:", items_search[0])
        # Verify region or district likely contains Davao
        first = items_search[0]
        r = (first.get('region') or '').lower()
        d = (first.get('district') or '').lower()
        p = (first.get('project_name') or '').lower()
        if 'davao' in r or 'davao' in d or 'davao' in p:
            print("SUCCESS: Search returned relevant results.")
        else:
            print("WARNING: 'Davao' not found in fields of first result (might be in hidden columns or fuzzy match?)")
    
    print("\nTesting /api/dpwh2026/hierarchy...")
    response_hier = client.get("/api/dpwh2026/hierarchy")
    if response_hier.status_code != 200:
        print(f"FAILED: Hierarchy Status Code {response_hier.status_code}")
        return False
        
    data_hier = response_hier.json()
    # Expecting {"data": [...], "format": "tree"}
    if "data" not in data_hier:
         print("FAILED: Hierarchy response missing 'data'")
         return False
         
    print(f"Hierarchy Data Type: {type(data_hier['data'])}")
    if isinstance(data_hier['data'], list):
         print(f"Hierarchy Items: {len(data_hier['data'])}")
    elif isinstance(data_hier['data'], dict):
         print(f"Hierarchy Root Keys: {list(data_hier['data'].keys())}")
         
         print(f"Hierarchy Root Keys: {list(data_hier['data'].keys())}")
         
    print("SUCCESS: /api/dpwh2026/hierarchy looks good.")
    
    print("\nTesting /api/dpwh2026/stats...")
    response_stats = client.get("/api/dpwh2026/stats")
    if response_stats.status_code != 200:
        print(f"FAILED: Stats Status Code {response_stats.status_code}")
        print(response_stats.json())
        return False
        
    data_stats = response_stats.json()
    if not data_stats.get('success'):
         print("FAILED: Stats success flag is False")
         print(data_stats)
         return False
         
    print(f"Total Parsed: {data_stats.get('total_parsed')}")
    stats_map = data_stats.get('stats', {})
    for cat in ['national_roads', 'secondary_roads', 'flood_control', 'public_buildings']:
        if cat in stats_map and stats_map[cat]:
            s = stats_map[cat]
            if 'outlier_count' not in s:
                 print(f"FAILED: Missing 'outlier_count' in {cat}")
                 return False
            print(f"  {cat}: Count={s['count']}, Outliers={s['outlier_count']} ({s['outlier_count']/s['count']*100:.1f}%)")
        else:
            print(f"  {cat}: No data or None")
            
    print("SUCCESS: /api/dpwh2026/stats looks good and includes anomalies.")
    
    # Test Outlier Drilldown
    print("\nTesting /api/dpwh2026/stats/outliers?category=national_roads...")
    response_outs = client.get("/api/dpwh2026/stats/outliers?category=national_roads")
    if response_outs.status_code != 200:
        print(f"FAILED: Outliers Status Code {response_outs.status_code}")
        return False
        
    data_outs = response_outs.json()
    if not data_outs.get('success'):
         print("FAILED: Outliers success flag is False")
         return False
         
    outliers = data_outs.get('outliers', [])
    print(f"Fetched {len(outliers)} outliers. Threshold: {data_outs.get('threshold'):,.2f}")
    if outliers:
        top = outliers[0]
        print(f"Top Outlier: {top['name'][:50]}... CostMetric={top['cost_metric']:,.2f}")

    # Test Repeated Projects
    print("\nTesting /api/dpwh2026/repeated...")
    response_rep = client.get("/api/dpwh2026/repeated")
    if response_rep.status_code != 200:
         print(f"FAILED: Repeated Status Code {response_rep.status_code}")
         return False
    data_rep = response_rep.json()
    if not data_rep.get('success'):
         print(f"FAILED: Repeated success flag is False: {data_rep.get('error')}")
         return False
         
    groups = data_rep.get('groups', [])
    print(f"Found {len(groups)} repeated project names.")
    if groups:
        top_g = groups[0]
        print(f"Top Repeated: '{top_g['name']}' (x{top_g['count']}) - Total: {top_g['total_amount']:,.2f}")

    # Test Master Red Flags
    print("\nTesting /api/dpwh2026/red-flags/all...")
    response_all = client.get("/api/dpwh2026/red-flags/all")
    if response_all.status_code != 200:
         print(f"FAILED: Red Flags All Status Code {response_all.status_code}")
         return False
    data_all = response_all.json()
    if not data_all.get('success'):
         print(f"FAILED: Red Flags All success flag is False: {data_all.get('error')}")
         return False
    
    count = data_all.get('count', 0)
    print(f"Found {count} combined red flags.")
    return True

if __name__ == "__main__":
    try:
        if test_dpwh_projects():
            sys.exit(0)
        else:
            sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

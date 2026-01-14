import json
from pathlib import Path

# Path determined from generate_condition_risks_cache.py analysis
RISK_PATH_PRIMARY = Path('/home/joebert/open-data-visualization/static/data/condition_risks_v2.json')
RISK_PATH_FALLBACK = Path('/home/joebert/open-data-visualization/static/data/condition_risks.json')

def show_examples():
    if RISK_PATH_PRIMARY.exists():
        risk_file = RISK_PATH_PRIMARY
    elif RISK_PATH_FALLBACK.exists():
        print(f"Primary not found, using fallback: {RISK_PATH_FALLBACK}")
        risk_file = RISK_PATH_FALLBACK
    else:
        print("No risk files found.")
        return

    print(f"Loading data from {risk_file}")
    with open(risk_file, 'r') as f:
        data = json.load(f)

    print("\n--- 5 Examples: NO DATA (High Risk) ---")
    # Projects where we matched the road, but found no condition data for that segment
    no_data = data.get('no_data_projects', [])
    for i, p in enumerate(no_data[:5]):
        print(f"{i+1}. {p['project_name']}")
        print(f"   Region: {p['region']}")
        print(f"   Matched Road: {p['road_name']} (ID: {p['road_id']})")
        print(f"   Amount: {p['amount']:,.2f}")
        print("-" * 40)

    print("\n--- 5 Examples: NO MATCH (High Risk) ---")
    # Projects where we couldn't match the road name OR chainage
    no_match = data.get('no_match_projects', [])
    for i, p in enumerate(no_match[:5]):
        print(f"{i+1}. {p['project_name']}")
        print(f"   Region: {p['region']}")
        print(f"   Reason matches failed: {p.get('remark', 'Unknown')}")
        print(f"   Amount: {p['amount']:,.2f}")
        print("-" * 40)
        
    # Also check matching stats
    stats = data.get('stats', {})
    print("\n--- Stats ---")
    print(f"Matches Found: {stats.get('matches_found')}")
    print(f"No Data: {stats.get('no_data_count')}")
    print(f"No Match: {stats.get('no_match_count')}")


if __name__ == "__main__":
    show_examples()

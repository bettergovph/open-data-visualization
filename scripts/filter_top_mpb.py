
import json
import os

INPUT_JSON = "repeated_targets.json" # Still use the full extraction as source (Wait, I overwrote it with sample 10. I need to re-extract first.)
MATRIX_JSON = "static/data/integrated_matrix.json"

def main():
    # 1. Re-extract all repeated projects to ensure we have the full pool
    print("Loading full matrix...")
    with open(MATRIX_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    ranking = data.get('ranking', [])
    candidates = []

    print(f"Scanning {len(ranking)} districts/keys...")

    for entry in ranking:
        projects = entry.get('projects', [])
        for p in projects:
            hist_match = p.get('historical_match')
            links = p.get('transparency_links', [])
            name = p.get('name', '').upper()
            amount = p.get('amount', 0)
            
            # Criteria: 
            # 1. Repeated (Historical Match exists)
            # 2. Transparency Links exist
            # 3. Multi-Purpose Building (MPB)
            if hist_match and links:
                if "MULTI-PURPOSE" in name or "MULTI PURPOSE" in name or "MPB" in name:
                    candidates.append({
                        'id': p['id'],
                        'name': p['name'],
                        'amount': amount,
                        'historical_match': hist_match,
                        'transparency_links': links
                    })
    
    print(f"Found {len(candidates)} Repeated MPB candidates.")
    
    # 2. Sort by Amount (Descending)
    candidates.sort(key=lambda x: x['amount'], reverse=True)
    
    # 3. Take Top 100
    top_10 = candidates[:100]
    
    print("Top 10 Highest Priced MPBs:")
    for i, p in enumerate(top_10, 1):
        print(f"{i}. {p['name']} - P{p['amount']:,.2f}")
        
    # 4. Save
    with open("repeated_mpb_targets.json", "w") as f:
        json.dump(top_10, f, indent=2)
    
    # Also update the main generation input for the report script
    with open("repeated_targets.json", "w") as f:
        json.dump(top_10, f, indent=2)

if __name__ == "__main__":
    main()

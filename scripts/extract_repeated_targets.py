
import json
import os

OUTPUT_JSON = "static/data/integrated_matrix.json"

def main():
    if not os.path.exists(OUTPUT_JSON):
        print("Waiting for integrated_matrix.json...")
        return

    with open(OUTPUT_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    ranking = data.get('ranking', [])
    targets = []
    
    print(f"Scanning {len(ranking)} districts/keys...")

    for entry in ranking:
        projects = entry.get('projects', [])
        for p in projects:
            # Criteria: Repeated (historical match) OR likely repeated (user mentioned Red/Repeated)
            # and MUST have transparency links
            links = p.get('transparency_links', [])
            hist_match = p.get('historical_match')
            flag_reason = p.get('flag_reason')
            
            # The User said: "collate all the repeated projects ... put the 2026 project name ... historical contracts"
            # So we target items with `historical_match` driven by the "Repeated" tab.
            
            if hist_match and links:
                targets.append({
                    'id': p['id'],
                    'name': p['name'],
                    'historical_match': hist_match,
                    'transparency_links': links
                })
                
    print(f"Found {len(targets)} repeated projects with transparency links.")
    
    # Save targets for the reporter
    with open("repeated_targets.json", "w") as f:
        json.dump(targets, f, indent=2)

if __name__ == "__main__":
    main()

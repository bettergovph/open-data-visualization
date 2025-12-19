
import json
import os

TOP_100_FILE = "top_100_mpb_targets.json"
OUTPUT_FILE = "screenshot_targets.json"

def main():
    if not os.path.exists(TOP_100_FILE):
        print(f"Error: {TOP_100_FILE} not found.")
        return

    with open(TOP_100_FILE, 'r') as f:
        projects = json.load(f)

    # Extract unique matched contracts
    unique_contracts = {}
    for proj in projects:
        if "matches" in proj:
            for match in proj["matches"]:
                c_id = match["contract_id"]
                if c_id not in unique_contracts:
                    unique_contracts[c_id] = {
                        "contract_id": c_id,
                        "name": match["name"],
                        "amount": match["amount"],
                        "url_portal": f"https://transparency.dpwh.gov.ph/?project={c_id}"
                    }

    targets = list(unique_contracts.values())
    
    # Sort by amount desc just to have an order
    targets.sort(key=lambda x: x["amount"], reverse=True)

    print(f"Found {len(targets)} unique transparency contracts matched from the Top 100 projects.")

    with open(OUTPUT_FILE, 'w') as f:
        json.dump(targets, f, indent=2)
    
    print(f"Saved targets to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()

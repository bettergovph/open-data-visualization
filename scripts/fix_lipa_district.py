import json

DISTRICTS_FILE = "static/data/districts.json"

def fix_lipa():
    with open(DISTRICTS_FILE, 'r') as f:
        data = json.load(f)
    
    batangas = data['districts'].get('Batangas')
    if not batangas:
        print("Error: Batangas not found")
        return

    # Check existence of 6th District Rep
    reps = batangas.get('representatives', {})
    rep_6th = reps.get('6th District')
    print(f"Current 6th District Rep: {rep_6th}")
    
    if not rep_6th or "Ryan Recto" not in rep_6th:
        print("Warning: 6th District rep might be missing or incorrect. Updates from sync script should have set it.")
        # We can enforce it if needed, but let's trust the sync or just print warning.
        # Actually, let's enforce it to be safe.
        reps['6th District'] = "Ryan Recto"
        batangas['representatives'] = reps
        print("Enforced Ryan Recto for 6th District.")

    # Update Municipality Mapping
    munis = batangas.get('municipalities', {})
    current_lipa = munis.get('Lipa City')
    print(f"Current Lipa City District: {current_lipa}")
    
    if current_lipa != "6th District":
        munis['Lipa City'] = "6th District"
        print("Updated Lipa City to 6th District.")
        batangas['municipalities'] = munis
        
        with open(DISTRICTS_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        print("Saved districts.json")
    else:
        print("Lipa City is already 6th District.")

if __name__ == "__main__":
    fix_lipa()

import json
import re

try:
    with open('static/data/dynasty-projects-config.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    targets = ["Ernix", "Dionisio"]
    found = False
    
    print("Searching for Ernix Dionisio in config...")
    
    # Check if target_congressmen key exists
    congressmen_list = data.get('target_congressmen', [])
    
    for cm in congressmen_list:
        name = cm.get('display_name', '')
        full_name = cm.get('full_name', '')
        
        # Check matching
        match = any(t.lower() in name.lower() or t.lower() in full_name.lower() for t in targets)
        
        if match:
            found = True
            print(f"\n✅ FOUND: {name}")
            print(f"   ID: {cm.get('id')}")
            print(f"   Province: {cm.get('province')}")
            print(f"   District: {cm.get('district_number')}")
            print(f"   First Name Pattern: {cm.get('first_name_pattern')}")
            print(f"   Last Name Pattern: {cm.get('last_name_pattern')}")
            
            fam = cm.get('family_connections', {})
            contractors = fam.get('contractors', [])
            print(f"   Explicit Contractors ({len(contractors)}):")
            for c in contractors:
                print(f"     - {c}")
                
            # Check for generic patterns
            if cm.get('last_name_pattern') == "DIONISIO":
                print("\n⚠️  WARNING: Last name pattern is just 'DIONISIO'. This might match 'San Dionisio' if logic is loose!")

    if not found:
        print("❌ Ernix Dionisio NOT found in config.")

except Exception as e:
    print(f"Error: {e}")

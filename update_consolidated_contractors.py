import json

def update_consolidated_config():
    # Load unique contractors from DB
    try:
        with open('unique_contractors.json', 'r', encoding='utf-8') as f:
            unique_contractors = json.load(f)
    except FileNotFoundError:
        print("❌ unique_contractors.json not found. Run extract_all_contractors.py first.")
        return

    # Load congressmen data
    try:
        with open('static/data/congressmen_consolidated.json', 'r', encoding='utf-8') as f:
            congressmen = json.load(f)
    except FileNotFoundError:
        print("❌ congressmen_consolidated.json not found.")
        return

    print(f"Loaded {len(unique_contractors)} unique contractors and {len(congressmen)} congressmen.")

    updated_count = 0
    
    for cm in congressmen:
        # keywords to search for
        keywords = set()
        
        # Collect keywords from linked_contractors
        linked = cm.get('linked_contractors', [])
        for l in linked:
            if l and len(l) > 3: # Avoid short generic keywords
                keywords.add(l)
                
        # Also check family_connections
        family = cm.get('family_connections', {})
        family_contractors = family.get('contractors', [])
        for fc in family_contractors:
            if fc and len(fc) > 3:
                keywords.add(fc)
        
        # Special case for Elizaldy Co (ID 17) to ensure he gets his keywords
        if cm.get('id') == 17:
             keywords.add("SUNWEST")
             keywords.add("FS CO")
             keywords.add("HI-TONE")

        if not keywords:
            # Ensure 'contractors' key exists even if empty
            if 'contractors' not in cm:
                cm['contractors'] = []
            continue

        # Find exact matches in DB list
        exact_matches = set()
        for k in keywords:
            k_upper = k.upper().strip()
            for db_c in unique_contractors:
                db_c_upper = db_c.upper()
                # Check if keyword is part of the DB contractor string
                # We need to be careful not to match generic words if keyword is generic
                # But here keywords are specific contractor names e.g. "SUNWEST"
                if k_upper in db_c_upper:
                    exact_matches.add(db_c)
        
        # Update the congressman record
        # We put this in a new top-level 'contractors' key which the script uses
        existing_contractors = set(cm.get('contractors', []))
        existing_contractors.update(exact_matches)
        
        # Start fresh for 'contractors' to ensure we only have exact DB strings (plus maybe original keywords if desired, but strict matching implies only DB strings work)
        # Actually, let's keep exact matches primarily.
        cm['contractors'] = sorted(list(existing_contractors))
        
        if exact_matches:
            # print(f"Updated {cm.get('display_name')} (ID {cm.get('id')}): Added {len(exact_matches)} contractors.")
            updated_count += 1

    # Save updated file
    with open('static/data/congressmen_consolidated.json', 'w', encoding='utf-8') as f:
        json.dump(congressmen, f, indent=2, ensure_ascii=False)
        
    print(f"✅ Updated {updated_count} congressmen configurations.")

if __name__ == "__main__":
    update_consolidated_config()

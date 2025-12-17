import json
import re
from collections import defaultdict

# Mock the COMMON_TOKENS from the class
COMMON_TOKENS = {
    'INC', 'INCORPORATED', 'CORP', 'CORPORATION', 'CO', 'COMPANY', 'LTD', 'LIMITED',
    'AND', 'THE', 'OF', 'SA', 'NG', 'NI', 'BY', 'FOR', 'TO', 'AT', 'ON', 'IN',
    'CONSTRUCTION', 'BUILDERS', 'DEVELOPMENT', 'DEVELOPERS', 'ENTERPRISES', 
    'SUPPLY', 'SUPPLIES', 'TRADING', 'GENERAL', 'MERCHANDISING', 'SERVICES',
    'ENGINEERING', 'ARCHITECTURAL', 'WORKS', 'GROUP', 'SOLUTIONS', 'SYSTEMS',
    'VENTURES', '&', 'JR', 'SR', 'III', 'II', 'IV',
    'ASSOCIATES', 'PARTNERS', 'MANAGEMENT', 'HOLDINGS',
    'INVESTMENTS', 'PROPERTIES', 'REALTY', 'ESTATE', 'PROJECTS', 'SOLUTIONS', 'CONSULTING',
    'DISTRIBUTORS', 'MANUFACTURING', 'INDUSTRIES', 'PRODUCTS', 'EQUIPMENT', 'MATERIALS',
    'CONTRACTOR', 'GENERIC', 'GEN'
}

def build_lookup():
    with open('static/data/congressmen_consolidated.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    elizaldy = next((c for c in data if c['id'] == 17), None)
    if not elizaldy:
        print("Elizaldy not found!")
        return

    contractor_lookup = defaultdict(list)
    inverted_index = defaultdict(set)
    
    print(f"Processing Elizaldy (ID 17)...")
    
    contractors = elizaldy.get('contractors', [])
    contractor_patterns = elizaldy.get('contractor_patterns', [])
    
    print(f"Contractors: {json.dumps(contractors, indent=2)}")
    print(f"Patterns: {json.dumps(contractor_patterns, indent=2)}")

    # Simulate _build_lookup_dictionaries logic
    for contractor in contractors:
        if contractor:
            contractor_upper = contractor.upper().strip()
            contractor_lookup[contractor_upper].append("Elizaldy")
            
            normalized = re.sub(r'[^A-Z0-9]+', ' ', contractor_upper).strip()
            if normalized != contractor_upper:
                contractor_lookup[normalized].append("Elizaldy")

    # Inverted Index Logic
    for key in contractor_lookup.keys():
        normalized = ''.join([c if c.isalnum() else ' ' for c in key.upper()])
        tokens = normalized.split()
        
        for token in tokens:
            if len(token) >= 2 and token not in COMMON_TOKENS:
                inverted_index[token].add(key)
            else:
                 print(f"   [Ignored Token]: {token} (In common: {token in COMMON_TOKENS})")

    # Check results
    print("\n--- Inverted Index Tokens for Elizaldy ---")
    for token, keys in inverted_index.items():
        print(f"Token: '{token}' -> Keys: {list(keys)}")

    # Check for suspicious tokens
    suspicious = ['CONSTRUCTION', 'BUILDERS', 'SUPPLY', 'CO']
    for s in suspicious:
        if s in inverted_index:
            print(f"🚨 ALERT: '{s}' found in formatted index! This causes overmatching.")
        else:
             print(f"✅ '{s}' correctly excluded.")

if __name__ == "__main__":
    build_lookup()

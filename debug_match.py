import json
from pathlib import Path

# Load consolidated data
with open('static/data/congressmen_consolidated.json', 'r') as f:
    congressmen = json.load(f)

elizaldy = next((c for c in congressmen if c['id'] == 17), None)
print("Elizaldy Linked Contractors:", elizaldy['linked_contractors'])

# Check cache logic simulation
contractor = "SHALJOMAR CONSTRUCTION & SUPPLY"
print(f"\nTesting contractor: {contractor}")

# Load contractor lookup if possible (simulated, since it's built in memory)
# But I can check if 'SHALJOMAR' shares tokens with 'SUNWEST' etc.
# 'CONSTRUCTION' is the common token.
print(f"Has 'CONSTRUCTION'? {'CONSTRUCTION' in contractor}")

# Check known common tokens
common_tokens = {'CONSTRUCTION', 'SUPPLY', 'AND', '&', 'INC', 'CORP', 'CORPORATION', 'BUILDERS', 'DEVELOPMENT', 'TRADING', 'ENTERPRISES', 'ENGINEERING', 'SERVICES'}
tokens = set(contractor.replace('&', ' ').split())
filtered = {t for t in tokens if t.upper() not in common_tokens and len(t) >= 3}
print(f"Filtered tokens: {filtered}")

# The issue might be that `_build_contractor_lookup` or `_build_lookup_dictionaries` 
# is still indexing "CONSTRUCTION" for Elizaldy.

#!/usr/bin/env python3
"""
Debug script to understand why contractor matching isn't working
for Elizaldy Co and Edwin Gardiola.
"""

import json
import re
import pandas as pd
from pathlib import Path
from collections import defaultdict

PARQUET_DIR = Path(__file__).parent.parent / 'data' / 'parquet'
CONFIG_FILE = Path(__file__).parent.parent / 'static' / 'data' / 'dynasty-projects-config.json'
CLASSIFIED_PARQUET = PARQUET_DIR / 'integrated_projects_classified.parquet'

# Known contractor patterns to search for
ELIZALDY_PATTERNS = ['SUNWEST', 'FS CO', 'FS CO BUILDERS', 'HI-TONE']
GARDIOLA_PATTERNS = ['NEWINGTON', 'LOUREL', 'S-ANG', 'SANG']

def main():
    print("=" * 80)
    print("DEBUG: Contractor Matching for Elizaldy Co and Edwin Gardiola")
    print("=" * 80)
    
    # Load config
    print("\n1. Loading config...")
    with open(CONFIG_FILE) as f:
        config = json.load(f)
    
    # Find Elizaldy Co and Gardiola in config
    elizaldy_config = None
    gardiola_config = None
    
    for cm in config.get('target_congressmen', []):
        if 'ELIZALDY' in (cm.get('first_name_pattern') or '').upper():
            elizaldy_config = cm
        if 'GARDIOLA' in (cm.get('last_name_pattern') or '').upper():
            gardiola_config = cm
    
    print(f"\n2. Config loaded:")
    if elizaldy_config:
        print(f"   Elizaldy Co: {elizaldy_config.get('display_name')}")
        family_contractors = elizaldy_config.get('family_connections', {}).get('contractors', [])
        print(f"   Family contractors: {len(family_contractors)}")
        for c in family_contractors[:5]:
            print(f"      - {c[:60]}...")
    else:
        print("   ❌ Elizaldy Co NOT FOUND in config!")
    
    if gardiola_config:
        print(f"\n   Gardiola: {gardiola_config.get('display_name')}")
        family_contractors = gardiola_config.get('family_connections', {}).get('contractors', [])
        print(f"   Family contractors: {len(family_contractors)}")
        for c in family_contractors[:5]:
            print(f"      - {c[:60]}...")
    else:
        print("   ❌ Gardiola NOT FOUND in config!")
    
    # Simulate building contractor_lookup like the cache generator does
    print("\n3. Simulating contractor_lookup build...")
    
    def _expand_patterns(name: str) -> list:
        base_upper = name.upper().strip()
        patterns = {base_upper}
        patterns.add(re.sub(r'\([^)]*\)', '', base_upper).strip())
        for part in re.split(r'[\\/]', base_upper):
            part = part.strip()
            if len(part) >= 2:
                patterns.add(part)
        words = re.split(r'[^A-Z0-9]+', base_upper)
        for word in words:
            word = word.strip()
            if len(word) >= 2:
                patterns.add(word)
        return [p for p in patterns if p and len(p) >= 2]
    
    # Build lookup for Elizaldy
    elizaldy_lookup_keys = set()
    if elizaldy_config:
        for c in elizaldy_config.get('family_connections', {}).get('contractors', []):
            # Full name
            elizaldy_lookup_keys.add(c.upper().strip())
            # Normalized
            normalized = re.sub(r'[^A-Z0-9]+', ' ', c.upper()).strip()
            elizaldy_lookup_keys.add(normalized)
            # Patterns
            for p in _expand_patterns(c):
                elizaldy_lookup_keys.add(p.upper())
    
    print(f"\n   Elizaldy lookup keys: {len(elizaldy_lookup_keys)}")
    # Check if key patterns are present
    for pattern in ELIZALDY_PATTERNS:
        found = pattern.upper() in elizaldy_lookup_keys
        print(f"      '{pattern}' in lookup: {'✅' if found else '❌'}")
    
    # Build lookup for Gardiola
    gardiola_lookup_keys = set()
    if gardiola_config:
        for c in gardiola_config.get('family_connections', {}).get('contractors', []):
            gardiola_lookup_keys.add(c.upper().strip())
            normalized = re.sub(r'[^A-Z0-9]+', ' ', c.upper()).strip()
            gardiola_lookup_keys.add(normalized)
            for p in _expand_patterns(c):
                gardiola_lookup_keys.add(p.upper())
    
    print(f"\n   Gardiola lookup keys: {len(gardiola_lookup_keys)}")
    for pattern in GARDIOLA_PATTERNS:
        found = pattern.upper() in gardiola_lookup_keys
        print(f"      '{pattern}' in lookup: {'✅' if found else '❌'}")
    
    # Load projects and check contractor names
    print("\n4. Checking project contractor names...")
    if not CLASSIFIED_PARQUET.exists():
        print(f"   ❌ {CLASSIFIED_PARQUET} not found!")
        return
    
    df = pd.read_parquet(CLASSIFIED_PARQUET)
    print(f"   Loaded {len(df)} projects")
    
    # Find projects with matching contractors
    elizaldy_projects = []
    gardiola_projects = []
    
    for _, row in df.iterrows():
        contractor = str(row.get('contractor', '')).upper().strip()
        if not contractor or contractor == 'N/A':
            continue
        
        # Check for Elizaldy patterns
        for pattern in ELIZALDY_PATTERNS:
            if pattern.upper() in contractor:
                elizaldy_projects.append({
                    'contractor': row.get('contractor'),
                    'contractor_congressman': row.get('contractor_congressman'),
                    'district_congressman': row.get('district_congressman'),
                })
                break
        
        # Check for Gardiola patterns
        for pattern in GARDIOLA_PATTERNS:
            if pattern.upper() in contractor:
                gardiola_projects.append({
                    'contractor': row.get('contractor'),
                    'contractor_congressman': row.get('contractor_congressman'),
                    'district_congressman': row.get('district_congressman'),
                })
                break
    
    print(f"\n5. Found projects with target contractors:")
    print(f"   Elizaldy-related: {len(elizaldy_projects)}")
    print(f"   Gardiola-related: {len(gardiola_projects)}")
    
    # Check how many are assigned
    elizaldy_assigned = sum(1 for p in elizaldy_projects if p.get('contractor_congressman') and 'CO' in str(p.get('contractor_congressman', '')).upper())
    gardiola_assigned = sum(1 for p in gardiola_projects if p.get('contractor_congressman') and 'GARDIOLA' in str(p.get('contractor_congressman', '')).upper())
    
    print(f"\n6. Assignment status:")
    print(f"   Elizaldy projects assigned to him: {elizaldy_assigned} / {len(elizaldy_projects)}")
    print(f"   Gardiola projects assigned to him: {gardiola_assigned} / {len(gardiola_projects)}")
    
    # Sample unassigned projects
    print("\n7. Sample UNASSIGNED Elizaldy-related projects:")
    unassigned_elizaldy = [p for p in elizaldy_projects if not p.get('contractor_congressman') or 'CO' not in str(p.get('contractor_congressman', '')).upper()]
    for p in unassigned_elizaldy[:10]:
        print(f"   Contractor: {p['contractor']}")
        print(f"   Contractor CM: {p.get('contractor_congressman', 'None')}")
        print(f"   District CM: {p.get('district_congressman', 'None')}")
        print()
    
    print("\n8. Simulating matching for sample project...")
    if unassigned_elizaldy:
        sample = unassigned_elizaldy[0]
        sample_contractor = str(sample['contractor']).upper().strip()
        sample_normalized = re.sub(r'[^A-Z0-9]+', ' ', sample_contractor).strip()
        
        print(f"   Sample contractor: {sample_contractor}")
        print(f"   Normalized: {sample_normalized}")
        
        # Check exact match
        exact_match = sample_contractor in elizaldy_lookup_keys or sample_normalized in elizaldy_lookup_keys
        print(f"   Exact match in lookup: {'✅' if exact_match else '❌'}")
        
        # Check token overlap
        sample_tokens = set(re.split(r'[^A-Z0-9]+', sample_normalized))
        sample_tokens = {t for t in sample_tokens if len(t) >= 2}
        print(f"   Sample tokens: {sample_tokens}")
        
        # Check against each lookup key
        print(f"\n   Checking against lookup keys with 'SUNWEST':")
        sunwest_keys = [k for k in elizaldy_lookup_keys if 'SUNWEST' in k]
        for key in sunwest_keys[:5]:
            print(f"      Key: {key[:60]}...")
            key_tokens = set(re.split(r'[^A-Z0-9]+', key))
            key_tokens = {t for t in key_tokens if len(t) >= 2}
            common = sample_tokens.intersection(key_tokens)
            print(f"      Key tokens: {key_tokens}")
            print(f"      Common: {common}")
            print()

if __name__ == '__main__':
    main()










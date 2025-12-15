
import sys
import json
from pathlib import Path
from collections import defaultdict
import re

# Mocking necessary parts of the main script
class MockGenerator:
    def __init__(self):
        self.COMMON_TOKENS = {
            'CONSTRUCTION', 'INC', 'CORP', 'INCORPORATED', 'CORPORATION', 'AND', 'THE', 'OF', 'COMPANY', 
            'CO', 'LTD', 'LIMITED', 'TRADING', 'ENTERPRISES', 'SUPPLY', 'SERVICES', 'BUILDERS', 'DEVELOPMENT', 
            'ENGINEERING', 'FORMERLY', 'GENERAL', 'FOR', 'GROUP', 'SYSTEMS', 'TECHNOLOGIES'
        }
        
    def _name_key(self, first, last):
        return ((first or '').strip().upper(), (last or '').strip().upper())
        
    def _apply_district_corrections(self, data):
        pass

    def _build_lookup_dictionaries(self, congressmen_data, districts_data):
        district_lookup = defaultdict(list)
        contractor_lookup = defaultdict(list)
        contractor_inverted_index = defaultdict(set)
        
        self._apply_district_corrections(congressmen_data)
        
        for congressman_name, cm_data in congressmen_data.items():
            contractors = cm_data.get('contractors', [])
            contractor_patterns = cm_data.get('contractor_patterns', [])
            
            for contractor in contractors:
                if contractor:
                    contractor_upper = contractor.upper().strip()
                    contractor_lookup[contractor_upper].append((congressman_name, cm_data))
                    normalized = re.sub(r'[^A-Z0-9]+', ' ', contractor_upper).strip()
                    if normalized != contractor_upper:
                        contractor_lookup[normalized].append((congressman_name, cm_data))
            
            for pattern in contractor_patterns:
                if pattern:
                    pattern_upper = pattern.upper().strip()
                    contractor_lookup[pattern_upper].append((congressman_name, cm_data))
                    normalized = re.sub(r'[^A-Z0-9]+', ' ', pattern_upper).strip()
                    if normalized != pattern_upper:
                        contractor_lookup[normalized].append((congressman_name, cm_data))

        # Build Inverted Index
        for key in contractor_lookup.keys():
            normalized = ''.join([c if c.isalnum() else ' ' for c in key.upper()])
            tokens = normalized.split()
            for token in tokens:
                if len(token) >= 3 and token not in self.COMMON_TOKENS:
                    contractor_inverted_index[token].add(key)
                    
        return district_lookup, contractor_lookup, contractor_inverted_index

def test_contractor_flow():
    print("🧪 Testing Contractor Loading Flow...")
    
    # 1. Load Config
    config_path = Path('static/data/dynasty-projects-config.json')
    if not config_path.exists():
        print("❌ Config not found")
        return
        
    with open(config_path, 'r', encoding='utf-8') as f:
        config_data = json.load(f)
        
    # Find Elizaldy Co
    target = next((c for c in config_data['target_congressmen'] if 'ELIZALDY' in c['first_name_pattern']), None)
    if not target:
        print("❌ Elizaldy Co not found in config")
        return
        
    print(f"✅ Found Target: {target['display_name']}")
    print(f"   Hardcoded Contractors: {target.get('family_connections', {}).get('contractors', [])}")
    
    # 2. Simulate congressmen_data population (Simplified)
    # We assume 'get_congressmen_data' works, but let's emulate what it produces for Elizaldy Co
    # specifically merging hardcoded contractors.
    
    cm_data = {
        'company_name': target['display_name'],
        'provinces': ['Ako Bicol Party-list'],
        'contractors': target.get('family_connections', {}).get('contractors', []),
        'contractor_patterns': []
    }
    
    congressmen_data = {target['display_name']: cm_data}
    
    # 3. Build Lookups
    gen = MockGenerator()
    _, contractor_lookup, contractor_index = gen._build_lookup_dictionaries(congressmen_data, {})
    
    print(f"\n📊 Contractor Lookup Keys: {len(contractor_lookup)}")
    print(f"📊 Inverted Index Tokens: {len(contractor_index)}")
    
    # Check FS CO
    test_key = "FS CO BUILDERS AND SUPPLY"
    if test_key in contractor_lookup:
        print(f"✅ Found '{test_key}' in lookup")
    else:
        print(f"❌ '{test_key}' NOT in lookup")

    # Check SUNWEST
    sunwest_key = "SUNWEST, INC. (FORMERLY: SUNWEST CONSTRUCTION & DEVELOPMENT CORPORATION)"
    if sunwest_key in contractor_lookup:
        print(f"✅ Found '{sunwest_key}' in lookup")
    else:
        print(f"❌ '{sunwest_key}' NOT in lookup")
        
    # Check Inverted Index
    tokens_to_check = ["BUILDERS", "SUNWEST"]
    for token in tokens_to_check:
        if token in contractor_index:
            print(f"✅ Token '{token}' found in index. Mapped to {len(contractor_index[token])} keys.")
        else:
            print(f"❌ Token '{token}' NOT in index")
        
    # 4. Simulate Match
    print("\n🔍 Simulating Match...")
    project_texts = [
        "CONSTRUCTION OF ROAD BY FS CO BUILDERS AND SUPPLY",
        "REPAIR OF SCHOOL BY SUNWEST INC"
    ]
    
    for project_text in project_texts:
        print(f"   Testing: {project_text}")
        text_upper = project_text.upper()
        tokens = ''.join([c if c.isalnum() else ' ' for c in text_upper]).split()
        candidates = set()
        for t in tokens:
            if t in contractor_index:
                candidates.update(contractor_index[t])
                
        print(f"      Candidates found: {len(candidates)}")
        
        matches = []
        for cand in candidates:
            # Simple substring match
            if cand in text_upper:
                matches.append(cand)
                
        if matches:
            print(f"      ✅ MATCHED: {matches}")
        else:
            print("      ❌ NO MATCH found")

if __name__ == "__main__":
    test_contractor_flow()

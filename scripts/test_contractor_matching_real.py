
import sys
import pandas as pd
from pathlib import Path
import re
from collections import defaultdict

# Mock the Generator class for contractor matching
class MockContractorMatcher:
    def __init__(self):
        self.contractor_lookup = {}
        self.contractor_inverted_index = defaultdict(set)
        self.common_tokens = {'INC', 'CORP', 'CORPORATION', 'CO', 'LTD', 'CONSTRUCTION', 'BUILDERS', 'TRADING', 'ENTERPRISES', 'SUPPLY', 'AND', '&', 'THE', 'OF', 'GROUP', 'DEVELOPMENT', 'SERVICES', 'ENGINEERING', 'CONST'}

    def _tokenize_contractor(self, name):
        if not name:
            return set()
        # Allow 2-letter tokens if not in common list (Logic from main script)
        tokens = set()
        parts = re.split(r'[^A-Z0-9]', name.upper())
        for part in parts:
            if not part:
                continue
            if len(part) > 2 or (len(part) == 2 and part not in self.common_tokens):
                tokens.add(part)
        return tokens

    def load_dynasty_data(self):
        print("🔧 Loading Dynasty Data...")
        dynasty_path = Path('static/data/parquet/political_dynasties.parquet')
        contractors_path = Path('static/data/parquet/politician_contractors.parquet')
        
        if not dynasty_path.exists():
            print(f"❌ Missing: {dynasty_path}")
            return False
            
        df_dynasty = pd.read_parquet(dynasty_path)
        print(f"   Loaded {len(df_dynasty)} dynasty records")
        
        # Load contractors and join
        contractors_map = defaultdict(list)
        if contractors_path.exists():
            df_contractors = pd.read_parquet(contractors_path)
            print(f"   Loaded {len(df_contractors)} contractor links")
            
            # Join via politician_id
            if 'politician_id' in df_contractors.columns and 'contractor_name' in df_contractors.columns:
                for _, row in df_contractors.iterrows():
                    pid = row['politician_id']
                    company = row['contractor_name']
                    if company:
                        contractors_map[pid].append(company)
            else:
                print("⚠️ Unexpected columns in politician_contractors.parquet")
                print(f"   Columns: {df_contractors.columns}")
            
            # DEBUG: Print sample keys from map
            print(f"   DEBUG: Sample contractor map keys (politician_ids): {list(contractors_map.keys())[:5]}")
        else:
            print(f"⚠️ Missing: {contractors_path} - No contractors will be indexed")
        
        # Build lookup
        count = 0
        
        # DEBUG: Print sample dynasty keys
        print(f"   DEBUG: Inspecting dynasty keys...")
        
        for i, row in df_dynasty.iterrows():
            pid = row.get('id') # Dynasty ID
            
            if i < 5:
                print(f"      Dynasty ID: {pid}")
            
            # Get contractors from map (using ID) + any existing in row
            contractors = list(row.get('contractors', [])) if 'contractors' in row else []
            contractors.extend(contractors_map.get(pid, []))
            
            if not contractors:
                continue
                
            cm_key = f"{row.get('first_name', '')} {row.get('last_name', '')} ({row['province']})"
            
            # Simple indexing simulation
            for contractor in contractors:
                c_name_norm = str(contractor).upper().strip()
                tokens = self._tokenize_contractor(c_name_norm)
                for token in tokens:
                    self.contractor_inverted_index[token].add(cm_key)
                count += 1
                
        print(f"✅ Indexed {count} contractors")
        return True

    def match_contractor(self, contractor_name):
        if not contractor_name:
            return None
            
        tokens = self._tokenize_contractor(str(contractor_name).upper())
        if not tokens:
            return None
            
        # Check for matches
        candidates = defaultdict(int)
        for token in tokens:
            if token in self.contractor_inverted_index:
                for cm in self.contractor_inverted_index[token]:
                    candidates[cm] += 1
        
        # Find best candidate (simplified score)
        best_cm = None
        max_score = 0
        
        for cm, score in candidates.items():
            if score > max_score:
                max_score = score
                best_cm = cm
                
        return best_cm if max_score > 0 else None

def test_contractor_matching():
    # 1. Initialize
    matcher = MockContractorMatcher()
    if not matcher.load_dynasty_data():
        return
        
    # 2. Load DIME Projects
    print("\n🔧 Loading DIME Projects...")
    dime_path = Path('static/data/parquet/dime_projects.parquet')
    if not dime_path.exists():
        print(f"❌ Missing: {dime_path}")
        return
        
    df = pd.read_parquet(dime_path)
    print(f"   Loaded {len(df)} projects")
    
    # 3. Test Matching
    matches_found = 0
    tested = 0
    limit = 1000  # Test first 1000 projects
    
    print(f"\n🧪 Testing first {limit} projects...")
    
    for _, row in df.iterrows():
        contractor = row.get('contractor_name')
        if not contractor:
            continue
            
        tested += 1
        match = matcher.match_contractor(contractor)
        
        if match:
            matches_found += 1
            if matches_found <= 5:
                print(f"   ✅ MATCH: '{contractor}' -> {match}")
                
        if tested >= limit:
            break
            
    print(f"\n📊 Summary:")
    print(f"   Tested: {tested}")
    print(f"   Matches: {matches_found}")
    
    if matches_found > 0:
        print("✅ SUCCESS: Contractor matching is working with real data.")
    else:
        print("❌ FAILURE: No contractor matches found (this is suspicious given 1000 samples).")

if __name__ == "__main__":
    test_contractor_matching()

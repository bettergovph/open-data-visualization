
import duckdb
import re
import sys
from pathlib import Path

# Mock Worker Logic (Simplified for testing)
LOCATION_ENTRIES = []

def normalize_for_match_worker(text):
    if not text: return ""
    import unicodedata
    text = str(text)
    try: text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
    except: pass
    text = text.lower().strip()
    text = text.replace("city of ", "").replace("municipality of ", "")
    return text.strip()

def word_boundary_match(needle, haystack):
    # Copy of the LATEST logic I just pushed
    if not needle or len(needle) < 3: return False
    suffixes = [
        'road', 'rd', 'st', 'street', 'ave', 'avenue', 'blvd', 'boulevard', 
        'hwy', 'highway', 'dr', 'drive', 'ln', 'lane', 'expy', 'expressway',
        'ext', 'extension', 'bypass', 'diversion', 'circumferential', 'causeway',
        'bridge', 'flyover', 'viaduct', 'underpass', 'overpass', 'north road' # Added specific one for testing if general suffix fails? No, "North Road" is composed.
    ]
    # "North Road": "North" is a word. "Road" is a suffix.
    # Needle "Manila". Haystack "Manila North Road".
    # "Manila" + "North" + "Road".
    # Intervening words: "North" (1 word).
    # Suffix: "Road".
    # Should be caught by: (?:\s+[\w\.\-]+){0,3}\s+road
    
    suffix_pattern = r'(?:' + '|'.join(suffixes) + r')'
    exclusion_pattern = r'\b' + re.escape(needle) + r'\b(?:\s+[\w\.\-]+){0,3}\s+' + suffix_pattern + r'\b'
    if re.search(exclusion_pattern, haystack, re.IGNORECASE):
        # print(f"  -> Excluded '{needle}' in '{haystack}'")
        return False
    pattern = r'\b' + re.escape(needle) + r'\b'
    return bool(re.search(pattern, haystack, re.IGNORECASE))

def load_locations():
    path = Path('static/data/unified_locations.parquet')
    if not path.exists(): return False
    con = duckdb.connect()
    rows = con.execute("SELECT province, municipality, barangay, district, congressman FROM read_parquet(?) WHERE congressman IS NOT NULL AND congressman != 'TBD' AND congressman != 'Unknown'", [str(path)]).fetchall()
    
    entries = []
    for r in rows:
        entries.append({
            'prov': r[0], 'muni': r[1], 'brgy': r[2], 'dist': r[3], 'cong': r[4],
            'prov_norm': normalize_for_match_worker(r[0]),
            'muni_norm': normalize_for_match_worker(r[1]),
            'brgy_norm': normalize_for_match_worker(r[2])
        })
    return entries

def find_best_location_match_mock(project_name, project_province, entries, strict_province=False):
    name_norm = normalize_for_match_worker(project_name)
    prov_norm = normalize_for_match_worker(project_province) if project_province else ""
    
    best_match = None
    best_score = 0
    
    for entry in entries:
        # STRICT FILTERING LOGIC TO TEST
        if strict_province and prov_norm:
            # Check if entry province matches requested province
            e_prov = entry['prov_norm']
            # Simple containment check:
            # If "Ilocos Norte" (req) vs "Metro Manila" (entry) -> No match
            # If "Ilocos Norte" (req) vs "Ilocos Norte" (entry) -> Match
            
            # Logic: Is prov_norm present in entry['prov_norm'] OR vice versa?
            if prov_norm not in e_prov and e_prov not in prov_norm:
                continue
        
        score = 0
        match_length_bonus = 0
        
        # Muni Match
        if entry['muni_norm'] and len(entry['muni_norm']) > 3:
            if word_boundary_match(entry['muni_norm'], name_norm):
                score += 35
                match_length_bonus += len(entry['muni_norm']) * 2
                
        # Total
        total_score = score * 100 + match_length_bonus
        if total_score > best_score:
            best_score = total_score
            best_match = entry
            
    return best_match, best_score

def run_tests():
    global LOCATION_ENTRIES
    print("Loading locations...")
    entries = load_locations()
    if not entries: 
        print("Failed to load locations")
        return

    print(f"Loaded {len(entries)} locations.")
    
    # CASE: Manila North Road in Ilocos Norte
    # "Manila" matches "Manila City" (Muni).
    # Suffix exclusion should prevent it normally.
    # But strict province filtering makes it bulletproof.
    
    p_name = "Improvement of Manila North Road"
    p_prov = "Ilocos Norte"
    
    print(f"\nTest 1: '{p_name}' in '{p_prov}'")
    
    # 1. No Strict Filter (Current Worker Sim)
    match, score = find_best_location_match_mock(p_name, p_prov, entries, strict_province=False)
    if match:
        print(f"  [Loose Filter] Matched: {match['muni']}, {match['prov']} (Score: {score})")
        if "Manila" in match['muni'] and "Metro Manila" in match['prov']:
            print("  -> FAIL: Wrongly matched matches Manila City despite wrong province.")
    else:
        print(f"  [Loose Filter] No Match (Score: {score})")

    # 2. Strict Filter
    match, score = find_best_location_match_mock(p_name, p_prov, entries, strict_province=True)
    if match:
        print(f"  [Strict Filter] Matched: {match['muni']}, {match['prov']} (Score: {score})")
        if match['prov_norm'] == normalize_for_match_worker(p_prov):
             print("  -> PASS: Matched inside Ilocos Norte.")
    else:
        print(f"  [Strict Filter] No Match (Score: {score})")

    # 3. Text Inference Test
    print(f"\nTest 2 (Inference): '{p_name} {p_prov}' (No explicit province arg)")
    
    combined_text = f"{p_name} {p_prov}"
    # Mocking the new logic:
    detected = set()
    if "ilocos norte" in combined_text.lower():
        detected.add("ilocos norte")
    
    # Run with mock detection
    print(f"  [Mock Detected Provs]: {detected}")
    
    best_match = None
    best_score = 0
    for entry in entries:
        # Consistency Check
        if detected:
            e_prov = entry['prov_norm']
            match_found = False
            for dp in detected:
                prov_norm_dp = normalize_for_match_worker(dp)
                if prov_norm_dp in e_prov or e_prov in prov_norm_dp:
                    match_found = True
                    break
            if not match_found:
                 continue
                 
        # Scoring
        if entry['muni_norm'] and len(entry['muni_norm']) > 3:
             if word_boundary_match(entry['muni_norm'], normalize_for_match_worker(combined_text)):
                 best_match = entry
                 best_score = 100
                 
    if best_match:
        print(f"  [Inference Result] Matched: {best_match['muni']}, {best_match['prov']}")
        if "Manila" in best_match['muni'] and "Metro Manila" in best_match['prov']:
             print("  -> FAIL: Still matching Manila City.")
        else:
             print("  -> PASS: Correctly filtered out Manila City.")
    else:
        print("  [Inference Result] No Match (Matches filtered out). PASS.")

if __name__ == "__main__":
    run_tests()

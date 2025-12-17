
import duckdb
import re
import sys
from pathlib import Path

# Paths
UNIFIED_LOCATIONS_PARQUET = Path('static/data/unified_locations.parquet')

def normalize_for_match_worker(text):
    if not text:
        return ""
    import unicodedata
    text = str(text)
    try:
        text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
    except:
        pass
    text = text.lower().strip()
    text = text.replace("city of ", "").replace("municipality of ", "")
    return text.strip()

def word_boundary_match(needle, haystack):
    if not needle or len(needle) < 3:
        return False
        
    # Generalized Road Suffixes
    suffixes = [
        'road', 'rd', 'st', 'street', 'ave', 'avenue', 'blvd', 'boulevard', 
        'hwy', 'highway', 'dr', 'drive', 'ln', 'lane', 'expy', 'expressway',
        'ext', 'extension', 'bypass', 'diversion', 'circumferential', 'causeway',
        'bridge', 'flyover', 'viaduct', 'underpass', 'overpass'
    ]
    # Create pattern: \bSUFFIX\b
    suffix_pattern = r'(?:' + '|'.join(suffixes) + r')'
    
    # 1. Lookahead Check: Needle followed by up to 3 words then a road suffix
    # e.g. "Isidro" in "Isidro Ungab Road"
    # (?:\s+[\w\.\-]+){0,3} matches 0 to 3 intervening words (allowing dots/dashes)
    exclusion_pattern = r'\b' + re.escape(needle) + r'\b(?:\s+[\w\.\-]+){0,3}\s+' + suffix_pattern + r'\b'
    
    if re.search(exclusion_pattern, haystack, re.IGNORECASE):
        # Found needle as part of a road phrase
        # print(f"DEBUG: Excluded '{needle}' in '{haystack}' due to road suffix")
        return False 

    # Normal match check
    pattern = r'\b' + re.escape(needle) + r'\b'
    return bool(re.search(pattern, haystack, re.IGNORECASE))

def check_names(names):
    if not UNIFIED_LOCATIONS_PARQUET.exists():
        print(f"Error: {UNIFIED_LOCATIONS_PARQUET} not found.")
        return

    con = duckdb.connect()
    print(f"Checking locations for names: {names}")
    
    for name in names:
        # Check if any location contains this name
        print(f"\n--- Searching for '{name}' ---")
        parts = name.lower().split()
        for part in parts:
             if len(part) <= 3: continue
             
             print(f"Checking token: '{part}'")
             query = f"""
                SELECT province, municipality, barangay, district, congressman 
                FROM read_parquet('{UNIFIED_LOCATIONS_PARQUET}') 
                WHERE 
                    LOWER(province) LIKE '%{part}%' OR 
                    LOWER(municipality) LIKE '%{part}%' OR 
                    LOWER(barangay) LIKE '%{part}%'
             """
             rows = con.execute(query).fetchall()
             if rows:
                 print(f"Found matches for '{part}'")
             else:
                 print(f"No location matches found for token '{part}'")

    con.close()

def test_matching_logic():
    print("\n--- Testing IMPROVED Logic ---")
    
    test_cases = [
        ("san pedro", "concreting of san pedro road", False),
        ("san pedro", "concreting of san pedro st.", False),
        ("san pedro", "concreting of san pedro", True),
        ("dionisio", "ernix dionisio road", False),
        # Crucial Test Case: Needle is "isidro" (loc) in "Isidro Ungab Road"
        # "Isidro" is NOT followed immediately by "Road", but by "Ungab Road".
        ("isidro", "concreting of isidro ungab road", False),
        ("ungab", "isidro ungab st", False), 
        ("ungab", "improvement of isidro ungab st section", False), # "ungab" followed by "st"
        ("sema", "bai sandra sema blvd", False),
        # Distant suffix
        ("macapagal", "pres. diosdado macapagal highway", False),
        ("macapagal", "pres. diosdado p. macapagal highway", False), # "p." "macapagal" "highway" -> 0 words between
        
        ("quezon", "quezon ave", False),
        ("quezon", "quezon city", True),
        ("rizal", "j.p. rizal st.", False),
        ("rizal", "rizal province", True),
        
        # False Negatives check
        ("davao city", "projects in davao city", True),
        ("davao", "davao city expressway", True), # "Davao" is excluded because "City Expressway" uses it.
    ]
    
    for needle, haystack, expected in test_cases:
        needle_norm = normalize_for_match_worker(needle)
        haystack_norm = normalize_for_match_worker(haystack)
        result = word_boundary_match(needle_norm, haystack_norm)
        status = "PASSED" if result == expected else "FAILED"
        print(f"Needle: '{needle}', Haystack: '{haystack}' -> Result: {result} (Expected: {expected}) [{status}]")

if __name__ == "__main__":
    # check_names(["Isidro Ungab"]) # Skip querying for speed in this test
    test_matching_logic()

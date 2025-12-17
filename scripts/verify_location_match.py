
import sys
import os
import re

# Add scripts directory to path to allow importing the module
sys.path.append(os.path.join(os.path.dirname(__file__), 'scripts'))
import generate_dynasty_projects_cache_duckdb as gen

# Mock Location Data
# 1. Province QUEZON, Muni LUCENA, Brgy BARANGAY 1.
# 2. Province NUEVA ECIJA, Muni SAN JOSE, Brgy ABAR 1ST.
# 3. Province MANILA, Muni MANILA, Brgy SAN JOSE. (Ambiguous Brgy name)
mock_entries = [
    {'prov': 'QUEZON', 'muni': 'LUCENA CITY', 'brgy': 'BARANGAY 1', 'dist': 'DIST 1', 'cong': 'CONG A'},
    {'prov': 'NUEVA ECIJA', 'muni': 'SAN JOSE CITY', 'brgy': 'ABAR 1ST', 'dist': 'DIST 2', 'cong': 'CONG B'},
    {'prov': 'METRO MANILA', 'muni': 'MANILA', 'brgy': 'SAN JOSE', 'dist': 'DIST 3', 'cong': 'CONG C'},
]

# Inject mock state
gen.WORKER_STATE = {
    'location_entries': mock_entries,
    # normalize requires unicodedata, imported inside function or available
}

def test_match(text, expected_prov, expected_muni):
    print(f"Testing: '{text}'")
    match = gen.find_best_location_match_worker(text)
    if match:
        prov, muni, brgy, dist, cong = match
        print(f"  Result: Prov={prov}, Muni={muni}, Brgy={brgy}")
        if prov == expected_prov and muni == expected_muni:
            print("  ✅ PASS")
        else:
            print(f"  ❌ FAIL. Expected {expected_prov}/{expected_muni}")
    else:
        if expected_prov is None:
            print("  ✅ PASS (No match expected)")
        else:
            print("  ❌ FAIL. No match found.")

if __name__ == "__main__":
    print("--- Verifying Road Name Exclusion ---")
    # 1. "Quezon Ave" -> Should NOT match Quezon Province
    test_match("Construction of road in Quezon Ave", None, None)

    print("\n--- Verifying Province Context ---")
    # 2. "Quezon Province" -> Should match Quezon Province
    test_match("Project in Quezon Province for irrigation", "QUEZON", "LUCENA CITY") 

    print("\n--- Verifying Hierarchy (Municipality + Province vs Barangay alone) ---")
    # 3. "San Jose, Nueva Ecija" -> Should match Entry 2 (Muni San Jose, Prov NE)
    # Muni(35) + Prov(10) = 45. vs Brgy(40). Wins.
    test_match("School building in San Jose, Nueva Ecija", "NUEVA ECIJA", "SAN JOSE CITY")

    print("\n--- Verifying Hierarchy (Barangay Only) ---")
    # 4. "San Jose" -> Should match Entry 3 (Brgy San Jose)
    # Entry 2: Muni(35). Entry 3: Brgy(40).
    # Brgy > Muni. So Entry 3.
    test_match("Repair in San Jose", "METRO MANILA", "MANILA")


import sys
import os
import asyncio
import json
from pathlib import Path
import re

# Add script directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from generate_dynasty_projects_cache_duckdb import DynastyProjectsCacheGeneratorDuckDB

async def run_debug():
    print("Initializing Generator...")
    generator = DynastyProjectsCacheGeneratorDuckDB()
    
    print("Loading Config...")
    # This will load from DuckDB if available
    config_data, districts_data = await generator.load_config()
    
    print("Building Lookup Dictionaries...")
    congressmen_data = await generator.get_congressmen_data(None, config_data, districts_data, True)
    district_lookup, contractor_lookup, contractor_inverted_index = generator._build_lookup_dictionaries(congressmen_data, districts_data)
    
    print(f"Loaded {len(congressmen_data)} congressmen")
    # Check for Herrera
    herrera_found = False
    for name in congressmen_data:
        if 'HERRERA' in name.upper():
            print(f"Found Herrera: {name}")
            print(f"Contractors: {congressmen_data[name].get('contractors')}")
            herrera_found = True
    if not herrera_found:
        print("❌ Bernadette Herrera NOT found in congressmen_data")
    print(f"Loaded {len(contractor_lookup)} contractor keys")
    
    # Debug district_lookup for Davao
    print("\n--- Debugging Davao Lookup ---")
    davao_keys = [k for k in district_lookup.keys() if 'DAVAO' in k[0]]
    print(f"Found {len(davao_keys)} Davao keys")
    
    print("Checking specific keys:")
    keys_to_check = [
        ('DAVAO CITY', 'DAVAO CITY'),
        ('DAVAO CITY', ''),
        ('DAVAO DEL SUR', 'DAVAO CITY'),
        ('DAVAO DEL SUR', '')
    ]
    for k in keys_to_check:
        candidates = district_lookup.get(k, [])
        print(f"Key {k}: {len(candidates)} candidates")
        for c in candidates:
            print(f"  - {c[0]} ({c[1].get('district', 'No District')})")
    
    # Test Cases
    test_cases = [
        # 1. Bernadette Herrera (Party List) - Contractor Match
        {
            "name": "Bernadette Herrera (Contractor Match)",
            "project_text": "Construction of Multi-Purpose Building",
            "province": "QUEZON CITY",
            "municipality": "QUEZON CITY",
            "contractor": "OCTAGON CONCRETE SOLUTIONS INC", # Real contractor
            "year": 2024,
            "expected_match": "HERRERA"
        },
        # 2. Davao City - No District (Should be Paolo Duterte / 1st District)
        {
            "name": "Davao City (No District)",
            "project_text": "Concreting of Road in Davao City",
            "province": "DAVAO DEL SUR",
            "municipality": "DAVAO CITY",
            "contractor": "GENERIC CONTRACTOR",
            "year": 2024,
            "expected_match": "PAOLO"
        },
        # 3. Davao City - Matina (Should be Paolo Duterte / 1st District)
        {
            "name": "Davao City (Matina)",
            "project_text": "Repair of School in Matina, Davao City",
            "province": "DAVAO DEL SUR",
            "municipality": "DAVAO CITY",
            "contractor": "GENERIC CONTRACTOR",
            "year": 2024,
            "expected_match": "PAOLO"
        },
        # 4. Jose Manuel Alba (Region X) - Correct Region
        {
            "name": "Jose Manuel Alba (Region X Match)",
            "project_text": "Farm to Market Road in Bukidnon",
            "province": "BUKIDNON",
            "municipality": "MANOLO FORTICH",
            "contractor": "GENERIC CONTRACTOR",
            "year": 2024,
            "expected_match": "ALBA"
        },
        # 5. Jose Manuel Alba (Region X) - Incorrect Region (Cebu)
        {
            "name": "Jose Manuel Alba (Wrong Region - Cebu)",
            "project_text": "Road Widening in Cebu City",
            "province": "CEBU",
            "municipality": "CEBU CITY",
            "contractor": "GENERIC CONTRACTOR",
            "year": 2024,
            "expected_match": None # Should NOT match Alba
        }
    ]
    
    print("\nRunning Test Cases...")
    for case in test_cases:
        print(f"\n--- Test: {case['name']} ---")
        
        match, match_type, score, dist_cm, cont_cm = generator._match_project_unified(
            project_text=case['project_text'],
            province=case['province'],
            municipality_barangay=case['municipality'],
            contractor=case['contractor'],
            year=case['year'],
            congressmen_data=congressmen_data,
            district_lookup=district_lookup,
            contractor_lookup=contractor_lookup,
            contractor_inverted_index=contractor_inverted_index
        )
        
        print(f"Result: {match} (Type: {match_type}, Score: {score})")
        
        expected = case['expected_match']
        if expected:
            if match and expected.upper() in match.upper():
                print("✅ PASS")
            else:
                print(f"❌ FAIL (Expected {expected}, got {match})")
        else:
            if match is None or (match and "ALBA" not in match.upper()): # Specific check for Alba negative test
                 print("✅ PASS")
            else:
                 print(f"❌ FAIL (Expected None/Not Alba, got {match})")

if __name__ == "__main__":
    asyncio.run(run_debug())

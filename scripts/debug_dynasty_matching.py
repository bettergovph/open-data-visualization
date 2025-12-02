
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
    """
    Test script for dynasty matching logic.
    Run this after making changes to generate_dynasty_projects_cache_duckdb.py
    to ensure existing correct matches are not broken.
    """
    print("Initializing Generator...")
    generator = DynastyProjectsCacheGeneratorDuckDB()
    
    print("Loading Config...")
    config_data, districts_data = await generator.load_config()
    
    print("Building Lookup Dictionaries...")
    congressmen_data = await generator.get_congressmen_data(None, config_data, districts_data, True)
    district_lookup, contractor_lookup, contractor_inverted_index = generator._build_lookup_dictionaries(congressmen_data, districts_data)
    
    print(f"Loaded {len(congressmen_data)} congressmen")
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
        # Original test cases
        {
            "name": "Bernadette Herrera (Contractor Match)",
            "project_text": "Construction of Multi-Purpose Building",
            "province": "QUEZON CITY",
            "municipality": "QUEZON CITY",
            "contractor": "OCTAGON CONCRETE SOLUTIONS INC",
            "year": 2024,
            "expected_match": "HERRERA"
        },
        {
            "name": "Davao City (No District)",
            "project_text": "Concreting of Road in Davao City",
            "province": "DAVAO DEL SUR",
            "municipality": "DAVAO CITY",
            "contractor": "GENERIC CONTRACTOR",
            "year": 2024,
            "expected_match": "PAOLO"
        },
        {
            "name": "Davao City (Matina)",
            "project_text": "Repair of School in Matina, Davao City",
            "province": "DAVAO DEL SUR",
            "municipality": "DAVAO CITY",
            "contractor": "GENERIC CONTRACTOR",
            "year": 2024,
            "expected_match": "PAOLO"
        },
        {
            "name": "Jose Manuel Alba (Region X Match)",
            "project_text": "Farm to Market Road in Bukidnon",
            "province": "BUKIDNON",
            "municipality": "MANOLO FORTICH",
            "contractor": "GENERIC CONTRACTOR",
            "year": 2024,
            "expected_match": "ALBA"
        },
        {
            "name": "Jose Manuel Alba (Wrong Region - Cebu)",
            "project_text": "Construction of Road in Cebu City",
            "province": "CEBU",
            "municipality": "CEBU CITY",
            "contractor": "GENERIC CONTRACTOR",
            "year": 2023,
            "expected_match": None  # Should NOT match Alba
        },
        # New test cases requested by user
        # Note: David Suarez and Evelina Escudero only have "St Matthew Gen Contractor Development Corp"
        # which is shared by 269 congressmen, so contractor matching is non-deterministic.
        # We test district matching instead, which is deterministic.
        {
            "name": "David Suarez (District Match)",
            "project_text": "Road Concreting in Quezon 2nd District",
            "province": "QUEZON",
            "municipality": "LUCENA CITY",
            "contractor": "GENERIC CONTRACTOR",
            "year": 2023,
            "expected_match": "SUAREZ"
        },
        {
            "name": "Evelina Escudero (District Match)",
            "project_text": "School Building in Sorsogon 1st District",
            "province": "SORSOGON",
            "municipality": "SORSOGON CITY",
            "contractor": "GENERIC CONTRACTOR",
            "year": 2023,
            "expected_match": "ESCUDERO"
        },
        {
            "name": "Sandro Marcos (District Match)",
            "project_text": "Ilocos Norte 1st District Project",
            "province": "ILOCOS NORTE",
            "municipality": "LAOAG CITY",
            "contractor": "GENERIC CONTRACTOR",
            "year": 2023,
            "expected_match": "MARCOS"
        },
        {
            "name": "Martin Romualdez (District Match)",
            "project_text": "Leyte 1st District Project",
            "province": "LEYTE",
            "municipality": "TACLOBAN CITY",
            "contractor": "GENERIC CONTRACTOR",
            "year": 2023,
            "expected_match": "ROMUALDEZ"
        },
        {
            "name": "Martin Romualdez (Contractor Match - Ferdstar)",
            "project_text": "Construction by Ferdstar",
            "province": "METRO MANILA",
            "municipality": "MANILA",
            "contractor": "FERDSTAR BUILDERS CONTRACTORS",
            "year": 2023,
            "expected_match": "ROMUALDEZ"
        },
        {
            "name": "Edwin Gardiola (Contractor Match)",
            "project_text": "Construction by C.T. Leoncio",
            "province": "METRO MANILA",
            "municipality": "MANILA",
            "contractor": "C.T. LEONCIO CONSTRUCTION & TRADING",
            "year": 2023,
            "expected_match": "GARDIOLA"
        }
    ]
    
    print("\nRunning Test Cases...")
    passed = 0
    failed = 0
    
    for case in test_cases:
        print(f"\n--- Test: {case['name']} ---")
        
        match, match_type, score, dist_cm, cont_cm, cont_cm_2 = generator._match_project_unified(
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
                passed += 1
            else:
                print(f"❌ FAIL (Expected {expected}, got {match})")
                failed += 1
        else:
            # Negative test cases
            if match is None or (match and "ALBA" not in match.upper()):
                print("✅ PASS")
                passed += 1
            else:
                print(f"❌ FAIL (Expected None/Not Alba, got {match})")
                failed += 1
    
    print(f"\n{'='*50}")
    print(f"Test Summary: {passed} passed, {failed} failed")
    print(f"{'='*50}")

if __name__ == "__main__":
    asyncio.run(run_debug())

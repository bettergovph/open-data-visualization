
import asyncio
import sys
import json
from pathlib import Path
from pprint import pprint

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from generate_dynasty_projects_cache_duckdb import DynastyProjectsCacheGeneratorDuckDB, POLITICAL_DYNASTIES_PARQUET

# Test Cases
TEST_CASES = [
    # 1. Clear District Match (Unified DB should catch this)
    {
        "id": "T1",
        "description": "Simple District Match",
        "project_name": "Concreting of Road, Brgy. Batasan Hills",
        "location": "Quezon City",
        "contractor": "Generic Builders",
        "expected_type": "district",
    },
    # 2. Contractor Match (Known Contractor)
    # Using 'SUNWEST' which we saw in debug script maps to Elizaldy Co
    {
        "id": "T2",
        "description": "Strong Contractor Match",
        "project_name": "Generic Road Project",
        "location": "Nationwide",
        "contractor": "SUNWEST CONSTRUCTION AND DEVELOPMENT CORP.",
        "expected_type": "contractor",
        "expected_contractor_cm": "Elizaldy Salcedo Co"
    },
    # 3. Joint Venture (2 Contractors)
    {
        "id": "T3",
        "description": "Joint Venture Contractor",
        "project_name": "Big Project",
        "location": "Manila",
        "contractor": "SUNWEST CONSTRUCTION / TRIPLE A BUILDERS", 
        # Triple A maps to Wilfredo S. Caminero (from debug output)
        "expected_type": "contractor", # Or district, depending on priorities
    },
    # 4. Party List Case (Should prioritize Contractor)
    # Need a known party list contractor. Elizaldy Co is Ako Bicol (Partylist).
    {
        "id": "T4",
        "description": "Party List Priority",
        "project_name": "Project in Specific District",
        "location": "Albay, Legazpi City", # This is Elizaldy Co's home province but he is Party List
        "contractor": "SUNWEST CONSTRUCTION",
        "expect_priority": "contractor" 
    },
    # 5. Ambiguous Location (Should use Enriched Data)
    {
        "id": "T5",
        "description": "Enrichment Test",
        "project_name": "Construction of Multi-Purpose Building",
        "location": "Brgy. 105, Tondo, Manila",
        "contractor": None
    },
    # 6. Cross-District: Project in District A, Contractor of Cong B (Checking Prioritization)
    # Using 'TRIPLE A' (Wilfredo S. Caminero, Cebu 2nd) in 'Albay' (Salceda)
    {
        "id": "T6",
        "description": "Cross-District Conflict",
        "project_name": "Road in Albay",
        "location": "Albay, Legazpi City",
        "contractor": "TRIPLE A BUILDERS", # Wilfredo Caminero
        "expected_final_cm": "Wilfredo S. Caminero" # We MIGHT expect this if we want to track dynasty contractors
    },
    # 7. Same-District: Project in District A, Contractor of Cong A
    # Using 'TRIPLE A' (Wilfredo S. Caminero, Cebu 2nd) in 'Cebu'
    {
        "id": "T7",
        "description": "Same-District Contractor",
        "project_name": "Road in Cebu",
        "location": "Cebu, Argao", # Argao is in Cebu 2nd District
        "contractor": "TRIPLE A BUILDERS", # Wilfredo Caminero
        "expected_final_cm": "Wilfredo S. Caminero"
    }
]

async def run_tests():
    print("Initializing Generator...")
    generator = DynastyProjectsCacheGeneratorDuckDB()
    
    print("Loading Config/Data...")
    # Load real data to ensure we test actual lookup state
    config_data, districts_data = await generator.load_config()
    congressmen_data = await generator.get_congressmen_data(
        generator.duckdb_conn, config_data, districts_data, POLITICAL_DYNASTIES_PARQUET.exists()
    )
    
    print("Building Lookups...")
    district_lookup, contractor_lookup, contractor_inverted_index = generator._build_lookup_dictionaries(
        congressmen_data, districts_data
    )
    
    print(f"\n✅ Initialization Complete.")
    print(f"Contractor Lookup Entries: {len(contractor_lookup)}")
    
    print("\n🔎 Running Test Cases:\n")
    
    for case in TEST_CASES:
        print(f"--- Test Case {case['id']}: {case['description']} ---")
        print(f"Input: Location='{case['location']}', Contractor='{case['contractor']}'")
        
        # Run classification
        # We Mock project_data minimal fields
        project_data = {
            "project_name": case['project_name'], 
            "project_description": case['project_name'],
            "location": case['location'],
            "contractor": case['contractor']
        }
        
        # Extract location parts (simplified for test)
        # In real script, _extract_location_from_text does this
        # doing a quick pass here or manually defining args
        prov = ""
        mun_brgy = ""
        if "Quezon City" in case['location']:
            prov = "QUEZON CITY"
        elif "Manila" in case['location']:
            prov = "MANILA"
            mun_brgy = "TONDO"
        elif "Albay" in case['location']:
            prov = "ALBAY"
            mun_brgy = "LEGAZPI CITY"
            
        result = generator._match_project_unified(
            project_text=case['location'],
            province=prov,
            municipality_barangay=mun_brgy,
            contractor=case['contractor'],
            year=2024,
            congressmen_data=congressmen_data,
            district_lookup=district_lookup,
            contractor_lookup=contractor_lookup,
            contractor_inverted_index=contractor_inverted_index,
            project_data=project_data
        )
        
        final_congressman, match_type, match_score, district_cm, contractor_cm, contractor_cm_2 = result
        
        print(f"Result:")
        print(f"  Match Type: {match_type}")
        print(f"  Final CM:   {final_congressman}")
        print(f"  District CM: {district_cm}")
        print(f"  Contractor CM 1: {contractor_cm}")
        print(f"  Contractor CM 2: {contractor_cm_2}")
        
        # Validations
        if 'expected_type' in case:
            if match_type == case['expected_type']:
                print("  ✅ Match Type OK")
            else:
                print(f"  ❌ Match Type Mismatch (Expected {case['expected_type']})")
                
        if 'expected_contractor_cm' in case:
            if contractor_cm == case['expected_contractor_cm']:
                print("  ✅ Contractor CM OK")
            else:
                 print(f"  ❌ Contractor CM Mismatch (Expected {case['expected_contractor_cm']})")
        print("\n")

if __name__ == "__main__":
    asyncio.run(run_tests())

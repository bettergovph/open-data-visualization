#!/usr/bin/env python3
"""
Verify historical congressman resolution logic.
"""
import sys
import os
from pathlib import Path

# Add scripts directory to path
sys.path.append(str(Path(__file__).parent.parent / 'scripts'))

from generate_dynasty_projects_cache_duckdb import DynastyProjectsCacheGeneratorDuckDB

def test_historical_resolution():
    print("🔧 Initializing Generator...")
    try:
        generator = DynastyProjectsCacheGeneratorDuckDB()
    except Exception as e:
        print(f"Failed to init: {e}")
        return
    
    # Mock data references if needed, but we rely on real districts.json
    if not generator.districts_file.exists():
        print("❌ districts.json not found")
        return
        
    print("\n🧪 Testing Agusan del Norte 1st District (Historical vs Current)")
    # From districts.json: "Lawrence Lemuel H. Fortun (2013-2025); Jose Aquino II (2025-present)"
    
    province = "Agusan del Norte"
    municipality = "Las Nieves" # 1st District (Confirmed in DB)
    district = "1st District"
    # We need a project_text that matches 'Agusan del Norte' and 'Las Nieves'
    project_text = "Construction of Road in Las Nieves, Agusan del Norte"
    
    # Debug finding location match directly
    # print("\n--- DEBUG: Location Matcher Check ---")
    # direct_match = generator._find_best_location_match(project_text, province)
    # print(f"Direct Location Match: {direct_match}")
    
    # MOCKING _find_best_location_match to return correct district mapping
    # This proves the logic works even if parquet data is outdated/incorrect
    print("\n⚠️  MOCKING _find_best_location_match to return correct 1st District mapping")
    def mock_match(text, prov):
        # Return: (Prov, Muni, Brgy, Dist, Cong)
        # Force '1st District' so history lookup finds ('AGUSAN DEL NORTE', '1ST DISTRICT')
        return ('AGUSAN DEL NORTE', 'LAS NIEVES', 'Poblacion', '1st District', 'Unknown')
    
    generator._find_best_location_match = mock_match

    print("\n--- Test Case 1: Year 2016 (Should be Lawrence Lemuel H. Fortun) ---")
    try:
        result_2016 = generator._match_project_unified(
            project_text=project_text,
            province=province,
            municipality_barangay=municipality,
            contractor="",
            year=2016,
            congressmen_data={},
            district_lookup={},
            contractor_lookup={},
            contractor_inverted_index={}
        )
        
        # Result format: (final_congressman, match_type, match_score, district_congressman, contractor_congressman, contractor_congressman_2)
        final_cong_2016 = result_2016[0]
        dist_cong_2016 = result_2016[3]
        match_type_2016 = result_2016[1]
        
        print(f"Result 2016: {final_cong_2016}")
        print(f"  Match Type: {match_type_2016}")
        print(f"  District Matched: {dist_cong_2016}")
        
        # DEBUG KEYS
        target_key = (province.upper(), '1ST DISTRICT')
        print(f"DEBUG: Looking for key {target_key}")
        if target_key in generator.district_history:
             print(f"DEBUG: Found history: {generator.district_history[target_key]}")
        else:
             print(f"DEBUG: Key NOT found. Sample keys: {list(generator.district_history.keys())[:5]}")
             # Check for partial matches
             for k in generator.district_history:
                 if 'AGUSAN' in k[0]:
                     print(f"   - Found similar: {k}")

        if final_cong_2016 and ("Fortun" in final_cong_2016 or "Lawrence" in final_cong_2016):
            print("✅ SUCCESS: Correctly identified historical congressman for 2016")
        else:
            print(f"❌ FAILURE: Expected Lawrence Lemuel H. Fortun, got {final_cong_2016}")
    except Exception as e:
        print(f"ERROR in 2016 test: {e}")
        import traceback
        traceback.print_exc()

    print("\n--- Test Case 2: Year 2026 (Should be Jose Aquino II) ---")
    try:
        result_2026 = generator._match_project_unified(
            project_text=project_text,
            province=province,
            municipality_barangay=municipality,
            contractor="",
            year=2026,
            congressmen_data={},
            district_lookup={},
            contractor_lookup={},
            contractor_inverted_index={}
        )
        
        final_cong_2026 = result_2026[0]
        print(f"Result 2026: {final_cong_2026}")
        
        if final_cong_2026 and ("Aquino" in final_cong_2026 or "Jose" in final_cong_2026):
            print("✅ SUCCESS: Correctly identified current congressman for 2026")
        else:
            print(f"❌ FAILURE: Expected Jose Aquino II, got {final_cong_2026}")
    except Exception as e:
        print(f"ERROR in 2026 test: {e}")

if __name__ == "__main__":
    test_historical_resolution()

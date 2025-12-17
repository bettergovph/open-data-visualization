
import sys
import os
from pathlib import Path

# Add scripts folder to path
sys.path.append(str(Path(__file__).parent.parent))
from scripts.generate_dynasty_projects_cache_duckdb import init_worker, find_best_location_match_worker, normalize_for_match_worker

def test_worker_logic():
    print("Testing worker logic...")
    
    # Mock data as DICTS because worker code uses .get()
    mock_locations = [
        {'prov': 'ILOCOS NORTE', 'muni': 'Laoag City', 'brgy': 'Brgy 1', 'dist': '1st District', 'cong': 'Sandro Marcos', 'prov_norm': 'ilocos norte', 'muni_norm': 'laoag city', 'brgy_norm': 'brgy 1'},
        {'prov': 'METRO MANILA', 'muni': 'Manila City', 'brgy': 'Tondo', 'dist': '1st District', 'cong': 'Ernix Dionisio', 'prov_norm': 'metro manila', 'muni_norm': 'manila city', 'brgy_norm': 'tondo'},
        {'prov': 'DAVAO CITY', 'muni': 'Davao City', 'brgy': 'Poblacion', 'dist': '1st District', 'cong': 'Paolo Duterte', 'prov_norm': 'davao city', 'muni_norm': 'davao city', 'brgy_norm': 'poblacion'},
        {'prov': 'METRO MANILA', 'muni': 'Navotas City', 'brgy': 'Bagumbayan', 'dist': 'Lone District', 'cong': 'Toby Tiangco', 'prov_norm': 'metro manila', 'muni_norm': 'navotas city', 'brgy_norm': 'bagumbayan'}
    ]
    
    shared_data = {
        'location_entries': mock_locations,
        'unique_provinces': ['ILOCOS NORTE', 'METRO MANILA', 'DAVAO CITY'],
        'contractor_lookup': {},
        'contractor_inverted_index': {},
    }
    
    print("Running init_worker...")
    try:
        init_worker(shared_data)
        print("init_worker passed.")
    except Exception as e:
        print(f"init_worker FAILED: {e}")
        import traceback
        traceback.print_exc()
        return

    print("Testing find_best_location_match_worker...")
    
    test_cases = [
        # Should FAIL (1 level: Manila City matched, but Province not matched/provided)
        ("Improvement of Manila North Road", None),
        
        # Should PASS (2 levels: Ilocos Norte check)
        ("Improvement of Manila North Road", "Ilocos Norte"),

        # Should PASS (2 levels: Davao City Muni + Prov)
        ("Concreting of Road in Davao City", "Davao City"),
        
        # Should PASS (2 levels: Laoag City + Ilocos Norte)
        ("Construction of School in Laoag City, Ilocos Norte", None),
        
        # Should FAIL (1 level: Laoag City alone)
        ("Construction of School in Laoag City", None),
        
        # Should PASS (2 levels: Brgy 1 + Laoag City)
        ("Repair of Brgy 1, Laoag City", None),
        
        # LONE DISTRICT EXCEPTION TEST
        # Should PASS if logic is fixed (Navotas City is Lone District)
        # Currently expected to FAIL (Level 1)
        ("Construction of Navotas City Hall", None)
    ]
    
    for name, prov in test_cases:
        print(f"  Matching: '{name}' (Prov: {prov})")
        try:
            res = find_best_location_match_worker(name, prov)
            if res:
                print(f"  -> Match Found: {res[0]}, {res[1]}, {res[2]}")
            else:
                print(f"  -> No Match")
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_worker_logic()

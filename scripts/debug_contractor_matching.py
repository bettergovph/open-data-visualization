
import asyncio
import sys
from pathlib import Path
import json

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent))

from generate_dynasty_projects_cache_duckdb import DynastyProjectsCacheGeneratorDuckDB, POLITICAL_DYNASTIES_PARQUET

async def debug_contractor_logic():
    print("Initializing Generator...")
    generator = DynastyProjectsCacheGeneratorDuckDB()
    
    print("Loading Config...")
    config_data, districts_data = await generator.load_config()
    
    print("Loading Congressmen Data...")
    # Assume political_dynasties_available=True for now, or check file existence
    has_dynasty_parquet = POLITICAL_DYNASTIES_PARQUET.exists()
    print(f"Dynasty Parquet exists: {has_dynasty_parquet}")
    
    # We need a connection for get_congressmen_data if it uses it
    # generator.duckdb_conn is already init in __init__
    
    congressmen_data = await generator.get_congressmen_data(
        generator.duckdb_conn, config_data, districts_data, has_dynasty_parquet
    )
    
    print(f"Loaded {len(congressmen_data)} congressmen.")
    
    print("Building Lookup Dictionaries...")
    district_lookup, contractor_lookup, contractor_inverted_index = generator._build_lookup_dictionaries(
        congressmen_data, districts_data
    )
    
    print(f"District Lookup Size: {len(district_lookup)}")
    print(f"Contractor Lookup Size: {len(contractor_lookup)}")
    print(f"Contractor Inverted Index Size: {len(contractor_inverted_index)}")
    
    # Inspect a few entries
    if contractor_lookup:
        print("\nSample Contractor Lookup Keys:")
        for k in list(contractor_lookup.keys())[:5]:
            print(f"  '{k}': {contractor_lookup[k][0][0]}") # Print first cong name
            
    # Test Matching
    test_contractors = [
        "SUNWEST", 
        "SUNWEST CONSTRUCTION",
        "TRIPLE A",
        "MACROPRIME",
        "UNKNOWN CONTRACTOR X"
    ]
    
    print("\nTesting Matcher:")
    for cont in test_contractors:
        match = generator._find_congressman_by_contractor(
            cont, contractor_lookup, contractor_inverted_index, congressmen_data
        )
        print(f"  '{cont}' -> {match}")

if __name__ == "__main__":
    asyncio.run(debug_contractor_logic())

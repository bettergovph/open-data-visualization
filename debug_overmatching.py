
import sys
import json
import duckdb
from pathlib import Path
import os

# Add script directory to path
sys.path.insert(0, str(Path(__file__).parent / "scripts"))

# Import the generator
from generate_dynasty_projects_cache_duckdb import DynastyProjectsCacheGeneratorDuckDB

# Target Congressmen
TARGETS = [
    "Elizaldy Salcedo Co",
    "Bernadette Herrera",
    "Eddie Villanueva"
]

import asyncio

async def debug_investigation():
    print("🔍 initializing Generator...")
    generator = DynastyProjectsCacheGeneratorDuckDB()
    generator.location_matcher.load()
    
    # Load config and data
    config_data, districts_data = await generator.load_config()
    political_dynasties_available = Path("static/data/political_dynasties.parquet").exists() # check logic from script
    if not political_dynasties_available:
        # try default path
        political_dynasties_available = Path("data/political_dynasties.parquet").exists()
        
    congressmen_data = await generator.get_congressmen_data(
        None, 
        config_data,
        districts_data,
        True # Force availability or check
    )
    
    print("🔧 Building lookup dictionaries...")
    lookup_ret = generator._build_lookup_dictionaries(congressmen_data, districts_data)
    
    if len(lookup_ret) == 3:
        generator.district_lookup, generator.contractor_lookup, generator.contractor_inverted_index = lookup_ret
    else:
        generator.district_lookup, generator.contractor_lookup = lookup_ret
        # Simplified inverted index build if needed, or just rely on lookup
    
    # 1. Check Contractor Lookup for targets
    print("\n🔍 Inspecting Contractor Lookup:")
    found_contractors = {}
    for contractor, matches in generator.contractor_lookup.items():
        for cm_name, score in matches:
            for target in TARGETS:
                # Basic fuzzy check
                if target.upper() in cm_name.upper() or cm_name.upper() in target.upper():
                    if target not in found_contractors:
                        found_contractors[target] = []
                    found_contractors[target].append(contractor)
    
    for target in TARGETS:
        contractors = found_contractors.get(target, [])
        print(f"   👤 {target}: {len(contractors)} link(s)")
        for c in contractors[:10]:
            print(f"      - {c}")
        if len(contractors) > 10:
            print(f"      - ... ({len(contractors) - 10} more)")

    # 2. Inspect District Lookup for targets
    print("\n🔍 Inspecting District Lookup:")
    # (This structure is complex: (prov, city) -> list of (name, match_type))
    # We'll just scan it.
    found_districts = {}
    for location, reps in generator.district_lookup.items():
        prov, city = location
        for rep_name, meta in reps:
            for target in TARGETS:
                 if target.upper() in rep_name.upper() or rep_name.upper() in target.upper():
                    if target not in found_districts:
                        found_districts[target] = []
                    found_districts[target].append(location)

    for target in TARGETS:
        districts = found_districts.get(target, [])
        print(f"   👤 {target}: {len(districts)} location(s)")
        for d in districts[:5]:
            print(f"      - {d}")

if __name__ == "__main__":
    asyncio.run(debug_investigation())

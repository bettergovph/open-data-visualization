import asyncio
import sys
from pathlib import Path
from collections import defaultdict
import duckdb

# Add scripts directory to path to import the class
sys.path.append(str(Path.cwd() / 'scripts'))
try:
    from generate_dynasty_projects_cache_duckdb import DynastyProjectsCacheGeneratorDuckDB
except ImportError:
    # Fallback if running from root
    sys.path.append('scripts')
    from generate_dynasty_projects_cache_duckdb import DynastyProjectsCacheGeneratorDuckDB

async def test_contractor_loading():
    print("🧪 Testing Contractor Loading Logic...")
    
    generator = DynastyProjectsCacheGeneratorDuckDB()
    
    # Mock connections/config
    dynasty_conn = duckdb.connect() # InMemory
    config_data = {'target_congressmen': [{'name': 'Elizaldy Salcedo Co', 'aliases': ['Zaldy Co']}]}
    districts_data = {}
    
    # We need to test get_congressmen_data specifically
    # It requires parquet files to be present in data/parquet
    # We assume they exist based on previous checks
    
    print("   Calling get_congressmen_data...")
    try:
        congressmen_data = await generator.get_congressmen_data(
            dynasty_conn, 
            config_data, 
            districts_data, 
            political_dynasties_available=True
        )
        
        # Check if Zaldy Co has contractors
        found_zaldy = False
        contractor_count = 0
        
        for name, data in congressmen_data.items():
            if 'ZALDY' in name.upper() or 'ELIZALDY' in name.upper():
                found_zaldy = True
                contractors = data.get('contractors', [])
                contractor_count = len(contractors)
                print(f"   👤 Found Congressman: {name}")
                print(f"   🏗️  Contractors linked: {len(contractors)}")
                if contractors:
                    print(f"   📝 Sample contractors: {contractors[:3]}")
                break
        
        if not found_zaldy:
            print("   ❌ Zaldy Co not found in processed congressmen data")
        elif contractor_count == 0:
            print("   ❌ Zaldy Co found but has 0 contractors. JOIN logic might have failed.")
        else:
            print("   ✅ Contractor loading successful!")
            
    except Exception as e:
        print(f"   ❌ Error during execution: {e}")
        import traceback
        traceback.print_exc()

async def test_dime_fallback_logic():
    print("\n🧪 Testing DIME Fallback Logic...")
    # This logic is inside generate_cache -> loop over sources.
    # It's hard to unit test the method directly without running the whole thing.
    # But we can verify that we can load the DIME parquet file and it has data.
    
    generator = DynastyProjectsCacheGeneratorDuckDB()
    dime_path = Path('data/parquet/dime_projects.parquet')
    
    if dime_path.exists():
        try:
            print(f"   📂 Loading {dime_path}...")
            projects = generator.load_projects_from_parquet(dime_path, source_name='DIME')
            print(f"   ✅ Loaded {len(projects)} DIME projects.")
            
            # Check if source is set correctly
            sample = projects[0]
            if sample.get('source') == 'DIME' or sample.get('_source') == 'DIME':
                 print(f"   ✅ Source field correctly set to 'DIME'")
            else:
                 print(f"   ⚠️ Source field verification failed. Sample source: {sample.get('source')}")
                 
        except Exception as e:
            print(f"   ❌ Failed to load DIME parquet: {e}")
    else:
        print("   ❌ dime_projects.parquet not found")

async def main():
    await test_contractor_loading()
    await test_dime_fallback_logic()

if __name__ == "__main__":
    asyncio.run(main())

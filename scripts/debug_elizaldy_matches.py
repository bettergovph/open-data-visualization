import duckdb
from pathlib import Path
import json
import re

DATA_DIR = Path("data")
PARQUET_DIR = DATA_DIR / "parquet"
CONFIG_FILE = Path("static/data/dynasty-projects-config.json")

def normalize_name(name):
    if not name: return ""
    return re.sub(r'[^A-Z0-9]', '', name.upper())

def debug_elizaldy():
    print("🔬 Debugging Elizaldy Co matches...")
    
    # 1. Check Config
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
            
        elizaldy = next((c for c in config['target_congressmen'] if c['id'] == 17), None)
        if not elizaldy:
            print("❌ Elizaldy Co not found in config!")
            return
            
        print(f"✅ Found Elizaldy Co in config: {elizaldy['display_name']}")
        print(f"   First Pattern: {elizaldy['first_name_pattern']}")
        print(f"   Last Pattern: {elizaldy['last_name_pattern']}")
        print(f"   Explicit Contractors: {elizaldy.get('family_connections', {}).get('contractors', [])}")
    else:
        print(f"❌ Config file not found at {CONFIG_FILE}")
        return

    # 2. Check Parquet Matches
    conn = duckdb.connect()
    
    files_to_check = [
        "contractor_dynasty_matches.parquet",
        "politician_contractors.parquet"
    ]
    
    for filename in files_to_check:
        filepath = PARQUET_DIR / filename
        if not filepath.exists():
            print(f"⚠️ {filename} not found.")
            # Try absolute path based on CWD
            filepath = Path.cwd() / "data" / "parquet" / filename
            if not filepath.exists():
                print(f"⚠️ {filename} really not found at {filepath}")
                continue
            
        print(f"\n📂 Checking {filename}...")
        try:
            # Get columns
            cols_info = conn.execute(f"DESCRIBE SELECT * FROM '{filepath}'").fetchall()
            cols = [c[0] for c in cols_info]
            print(f"   Columns: {cols}")
            
            # Find relevant name columns
            name_cols = [c for c in cols if 'name' in c.lower() or 'congressman' in c.lower() or 'politician' in c.lower()]
            company_cols = [c for c in cols if 'company' in c.lower() or 'contractor' in c.lower()]
            
            print(f"   Name Cols: {name_cols}")
            print(f"   Company Cols: {company_cols}")
            
            if not name_cols or not company_cols:
                print("   ⚠️ Cannot identify necessary columns.")
                continue
                
            # Check for matches to ELIZALDY and CO
            for name_col in name_cols:
                query = f"""
                    SELECT * FROM '{filepath}' 
                    WHERE UPPER({name_col}) LIKE '%ELIZALDY%' 
                """
                rows = conn.execute(query).fetchall()
                if rows:
                    print(f"   Found {len(rows)} rows matching 'ELIZALDY' in {name_col}:")
                    for row in rows:
                        row_dict = dict(zip(cols, row))
                        print(f"     - {row_dict[name_col]} -> {row_dict.get(company_cols[0], 'Unknown Company')}")
                        
        except Exception as e:
            print(f"   Error processing {filename}: {e}")
            import traceback
            traceback.print_exc()
            
    conn.close()

if __name__ == "__main__":
    debug_elizaldy()

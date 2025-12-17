import duckdb
from pathlib import Path

# Paths assumption based on previous context
DATA_DIR = Path("data/parquet")
PC_FILE = DATA_DIR / "politician_contractors.parquet"
PD_FILE = DATA_DIR / "political_dynasties.parquet"

def debug_joined():
    print(f"Checking files:\n  {PC_FILE}\n  {PD_FILE}")
    # Use absolute paths to be safe if run from wrong dir
    base = Path.cwd()
    pc_path = base / PC_FILE
    pd_path = base / PD_FILE
    
    if not pc_path.exists():
        print(f"❌ {pc_path} missing.")
        return
    if not pd_path.exists():
        print(f"❌ {pd_path} missing.")
        return

    conn = duckdb.connect()
    
    # Query matching logic similar to get_congressmen_data
    # We look for ELIZALDY and CO
    
    query = f"""
        SELECT 
            pd.id,
            pd.first_name, 
            pd.last_name, 
            pc.contractor_name, 
            pc.source,
            pc.match_confidence
        FROM '{pc_path}' pc
        JOIN '{pd_path}' pd ON pc.politician_id = pd.id
        WHERE 
            (UPPER(pd.first_name) LIKE '%ELIZALDY%' OR UPPER(pd.last_name) LIKE '%CO')
    """
    # Note: "LIKE '%CO'" matches "ELIZALDY CO", "ZALDY CO", "JOSE CO", etc.
    # Logic in script: _name_key uses EXACT first/last pattern match from config if available.
    # Config: first="ELIZALDY", last="CO".
    # _name_key = ("ELIZALDY", "CO").
    # Lookup in contractor_lookup uses this key.
    # contractor_lookup is built from rows where:
    # key = _name_key(row_dict['dynasty_first_name'], row_dict['dynasty_last_name'])
    
    # So we want distinct First/Last pairs from the JOIN that match "ELIZALDY" and "CO".
    
    print("\n🔍 Executing Query for ANY 'ELIZALDY' or 'CO'...")
    try:
        results = conn.execute(query).fetchall()
        print(f"Found {len(results)} raw matches.")
        
        print("\n--- Filtering for Exact Config Match (ELIZALDY + CO) ---")
        filtered = []
        for r in results:
            first = (r[1] or '').strip().upper()
            last = (r[2] or '').strip().upper()
            if "ELIZALDY" in first and "CO" == last: # Strict on Last
                filtered.append(r)
            elif "ELIZALDY" in first and "CO" in last: # Loose on Last
                 pass # processed above?
        
        # Actually let's just print them all if count is low, or summarize
        seen_contractors = set()
        for r in results:
            first = (r[1] or '').strip().upper()
            last = (r[2] or '').strip().upper()
            
            # Simulate _name_key check
            # Config: ELIZALDY, CO
            if first == "ELIZALDY" and last == "CO":
                print(f"  [EXACT MATCH] {r[1]} {r[2]} -> {r[3]} (Src: {r[4]})")
                seen_contractors.add(r[3])
            elif "ELIZALDY" in first and "CO" in last:
                print(f"  [LOOSE MATCH] {r[1]} {r[2]} -> {r[3]} (Src: {r[4]})")
            else:
                # noise
                pass

        if "SHALJOMAR CONSTRUCTION & SUPPLY" in seen_contractors:
            print("\n❌ SHALJOMAR found in EXACT MATCHES!")
        else:
            print("\n✅ SHALJOMAR NOT found in exact matches.")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        
    conn.close()

if __name__ == "__main__":
    debug_joined()

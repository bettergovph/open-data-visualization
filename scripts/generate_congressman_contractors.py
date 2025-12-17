import duckdb
from pathlib import Path
import json
import re

# Paths
DATA_DIR = Path("data")
PARQUET_DIR = DATA_DIR / "parquet"
CONFIG_FILE = Path("static/data/dynasty-projects-config.json")
OUTPUT_FILE = Path("static/data/congressmen_consolidated.json")

# Parquet Files
PC_FILE = PARQUET_DIR / "politician_contractors.parquet"
PD_FILE = PARQUET_DIR / "political_dynasties.parquet"

def normalize_name_key(first, last):
    f = (first or '').strip().upper()
    l = (last or '').strip().upper()
    return (f, l)

def main():
    print("🚀 Generating Consolidated Congressman Data (Single Source of Truth)...")
    
    # 1. Load Config
    if not CONFIG_FILE.exists():
        print(f"❌ Config file missing: {CONFIG_FILE}")
        return
        
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
        
    target_congressmen = config.get('target_congressmen', [])
    print(f"Loaded {len(target_congressmen)} congressmen from config.")
    
    # 2. Connect to DB
    conn = duckdb.connect()
    
    # 3. Load DB Matches
    db_matches_by_id = {}
    db_matches_by_name = {} # Key: (first, last)
    
    if PC_FILE.exists() and PD_FILE.exists():
        print("📊 Loading matches from Parquet DB...")
        
        # Query: Join on ID
        query = f"""
            SELECT 
                pd.id,
                pd.first_name, 
                pd.last_name, 
                pc.contractor_name, 
                pc.source,
                pc.match_confidence
            FROM '{PC_FILE}' pc
            JOIN '{PD_FILE}' pd ON pc.politician_id = pd.id
            WHERE pc.contractor_name IS NOT NULL
        """
        try:
            rows = conn.execute(query).fetchall()
            print(f"   Found {len(rows)} verified matches in DB.")
            
            for r in rows:
                pid = r[0]
                first = r[1]
                last = r[2]
                contractor = r[3]
                source = r[4]
                conf = r[5]
                
                # Normalize contractor name slightly? No, keep raw.
                
                # By ID
                if pid not in db_matches_by_id:
                    db_matches_by_id[pid] = []
                db_matches_by_id[pid].append(contractor)
                
                # By Name
                key = normalize_name_key(first, last)
                if key not in db_matches_by_name:
                    db_matches_by_name[key] = []
                db_matches_by_name[key].append(contractor)
                
        except Exception as e:
            print(f"⚠️ Error querying DB: {e}")
    else:
        print("⚠️ Parquet files missing. Skipping DB matches.")

    # 4. Build Result List
    results = []
    
    for cm in target_congressmen:
        # Start with a copy of the original config entry
        result_entry = cm.copy()
        
        cm_id = cm.get('id')
        first_pat = cm.get('first_name_pattern')
        last_pat = cm.get('last_name_pattern')
        
        # Explicit from Config
        config_contractors = cm.get('family_connections', {}).get('contractors', [])
        
        # From DB
        db_contractors = []
        
        # Match by ID
        if cm_id in db_matches_by_id:
            db_contractors.extend(db_matches_by_id[cm_id])
            
        # Match by Name Pattern
        name_key = normalize_name_key(first_pat, last_pat)
        if name_key in db_matches_by_name:
            db_contractors.extend(db_matches_by_name[name_key])
        
        # Combine all unique names
        all_unique = set()
        for c in config_contractors:
            all_unique.add(c)
        for c in db_contractors:
            all_unique.add(c)
            
        # Update the 'contractors' field in the result
        # We put it at root level for easy access, or nested?
        # Let's put it as 'explicit_contractors' to be clear, 
        # or just 'linked_contractors'.
        result_entry['linked_contractors'] = sorted(list(all_unique))
        
        # Remove the nested family_connections if redundant?
        # User says "attribute is what is there district and what are there contractor links".
        # Keeping original config structure is safer, but adding this new field.
        
        results.append(result_entry)
        
        # Debug print for Elizaldy
        if cm_id == 17:
            print(f"👤 {cm.get('display_name')}: Found {len(all_unique)} contractors.")
            print(f"   Config: {len(config_contractors)} | DB: {len(db_contractors)}")
            for c in sorted(list(all_unique)):
                print(f"     - {c}")

    # 5. Save JSON
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(results, f, indent=2)
        
    print(f"✅ Saved consolidated data to {OUTPUT_FILE}")
    conn.close()

if __name__ == "__main__":
    main()

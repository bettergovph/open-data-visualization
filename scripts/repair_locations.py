import pandas as pd
import json
import os
import re

def repair_locations():
    parquet_path = "static/data/unified_locations.parquet"
    json_path = "static/data/districts.json"
    
    if not os.path.exists(parquet_path):
        print(f"Error: {parquet_path} not found.")
        return

    print(f"Loading {parquet_path}...")
    df = pd.read_parquet(parquet_path)
    
    print(f"Loading {json_path}...")
    with open(json_path, 'r') as f:
        d_data = json.load(f)
        districts_map = d_data.get('districts', {})

    # Load Auxiliary Data for Marikina
    marikina_json_path = "static/data/districts_generated.json"
    marikina_map = {}
    if os.path.exists(marikina_json_path):
        print(f"Loading {marikina_json_path} for Marikina data...")
        with open(marikina_json_path, 'r') as f:
            mData = json.load(f)
            # Path: NCR 2nd Dist -> City Of Marikina -> barangays
            ncr_key = "National Capital Region - Second District"
            city_key = "City Of Marikina"
            
            if ncr_key in mData and city_key in mData[ncr_key]:
                city_data = mData[ncr_key][city_key]
                if "barangays" in city_data:
                    generated_map = city_data["barangays"]
                    for bName, dName in generated_map.items():
                        if dName not in marikina_map: marikina_map[dName] = []
                        marikina_map[dName].append(bName)
            else:
                 print(f"Warning: Could not find {ncr_key} -> {city_key} in generated json.")
    
    # Load Auxiliary Data for Davao del Sur
    wiki_json_path = "static/data/districts.json.wiki-backup"
    davao_sur_map = {}
    if os.path.exists(wiki_json_path):
        print(f"Loading {wiki_json_path} for Davao del Sur data...")
        with open(wiki_json_path, 'r') as f:
            wData = json.load(f)
            # Path: districts -> Davao del Sur -> municipalities
            if "districts" in wData and "Davao del Sur" in wData["districts"]:
                ds_data = wData["districts"]["Davao del Sur"]
                if "municipalities" in ds_data:
                    d_munis = ds_data["municipalities"]
                    for mName, dName in d_munis.items():
                        if dName not in davao_sur_map: davao_sur_map[dName] = []
                        davao_sur_map[dName].append(mName)
            else:
                print("Warning: Could not find districts -> Davao del Sur in wiki backup.")

    # Helper: Normalize for fuzzy match
    def normalize(name):
        if not isinstance(name, str): return ""
        name = name.lower()
        name = name.replace("saint ", "st. ").replace("santo ", "sto. ")
        name = name.replace("u.p.", "up").replace("u. p.", "up")
        name = name.replace(" proper", "")
        return name.strip()

    # Helper to lookup district by barangay (Generalized)
    def lookup_district(city_key, barangay_name, custom_map=None):
        # Use custom map if provided (format: { "1st District": [list of names] })
        target_map = None
        
        if custom_map:
            target_map = custom_map
        elif city_key in districts_map and 'barangays' in districts_map[city_key]:
            target_map = districts_map[city_key]['barangays']
        
        if not target_map: return None
        
        b_norm = normalize(barangay_name)
        
        for dist, items in target_map.items():
            for item in items:
                # Exact normalized match
                if normalize(item) == b_norm:
                    return dist
                # Contains match
                if normalize(item) in b_norm and len(item) > 4: 
                    return dist
        return None

    # Caloocan Special Logic
    def get_caloocan_district(brgy_str):
        # Extract number from "Barangay 123"
        match = re.search(r'(\d+)', str(brgy_str))
        if not match: return None
        num = int(match.group(1))
        
        # 1st District: 1-4, 77-85, 132-177
        if (1 <= num <= 4) or (77 <= num <= 85) or (132 <= num <= 177):
            return "1st District"
        # 2nd District: 5-76, 86-131
        elif (5 <= num <= 76) or (86 <= num <= 131):
            return "2nd District"
        # 3rd District: 178-188
        elif (178 <= num <= 188):
            return "3rd District"
        
        return None

    # Helper function to apply fixes
    def apply_city_fix(prov_name_match, city_key, method="lookup", custom_map=None, target_col='barangay'):
        print(f"Fixing {prov_name_match} ({method})...")
        mask = df['province'].str.contains(prov_name_match, case=False, na=False)
        rows = df[mask]
        print(f"  Found {len(rows)} rows.")
        
        updates = 0
        for idx, row in rows.iterrows():
            target_val = row.get(target_col)
            if not target_val or target_val == "Unknown": continue
            
            new_dist = None
            if method == "caloocan":
                new_dist = get_caloocan_district(target_val)
            else:
                new_dist = lookup_district(city_key, str(target_val), custom_map=custom_map)
            
            if new_dist:
                df.at[idx, 'district'] = new_dist
                updates += 1
                
        print(f"  Updated {updates} rows.")

    # 1. QC Fix (Improved Fuzzy)
    apply_city_fix("Quezon City", "Quezon City")

    # 2. Caloocan Fix (Numeric Ranges)
    apply_city_fix("Caloocan", None, method="caloocan")

    # 3. Marikina Fix - Uses external map from districts_generated.json
    apply_city_fix("Marikina", None, custom_map=marikina_map)

    # 4. Cebu City Fix
    apply_city_fix("City of Cebu", "Cebu City") 

    # 5. Davao City Fix
    apply_city_fix("City of Davao", "Davao City")
    
    # 6. Agusan del Norte (Butuan Merge)
    print("Fixing Agusan del Norte (Merging Butuan)...")
    butuan_mask = df['province'].str.contains("Butuan", case=False, na=False)
    print(f"  Found {butuan_mask.sum()} Butuan rows.")
    df.loc[butuan_mask, 'province'] = "AGUSAN DEL NORTE"
    df.loc[butuan_mask, 'district'] = "1st District"
    
    # 7. Quezon (Lucena Merge)
    print("Fixing Quezon (Merging Lucena)...")
    lucena_mask = df['province'].str.contains("Lucena", case=False, na=False)
    print(f"  Found {lucena_mask.sum()} Lucena rows.")
    df.loc[lucena_mask, 'province'] = "QUEZON"
    df.loc[lucena_mask, 'district'] = "2nd District"

    # 8. Davao del Sur (Uses external map from districts.json.wiki-backup)
    # Note: Davao del Sur entries are likely municipalities, so we check 'municipality' column?
    # Or is it 'province'="Davao del Sur" and 'municipality'="Digos"?
    # The parquet usually has 'municipality' column.
    apply_city_fix("Davao del Sur", None, custom_map=davao_sur_map, target_col='municipality')
    
    # Digos Check (Merge into Davao del Sur if separate)
    digos_mask = df['province'].str.contains("Digos", case=False, na=False)
    if digos_mask.sum() > 0:
        print(f"  Found {digos_mask.sum()} Digos rows. Merging to Davao del Sur.")
        df.loc[digos_mask, 'province'] = "DAVAO DEL SUR"
        # Digos is Capital -> likely 1st District? Or use map?
        # Map says Digos City is 2nd District in the snippet I saw!
        # "Digos City": "2nd District"
        # Let's trust the map if we can, or hardcode.
        df.loc[digos_mask, 'district'] = "2nd District" 


    print("Saving repaired parquet...")
    df.to_parquet(parquet_path)
    print("Success.")

if __name__ == "__main__":
    repair_locations()

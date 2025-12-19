#!/usr/bin/env python3
"""
Build Unified Location Database (2019 Admin + 2025 DILG + 2025 Comelec)

Outputs:
- static/data/unified_locations.duckdb
- static/data/unified_locations.parquet

Schema:
- region (str)
- province (str)
- municipality (str)
- barangay (str)
- district (str) - e.g. "1st District", "Lone District"
- congressman (str) - Mapped from district
"""

import json
import os
import re
import glob
import pandas as pd
import duckdb
from pathlib import Path
from tqdm import tqdm

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
ADMIN_JSON = BASE_DIR.parent / "philippine-regions-provinces-cities-municipalities-barangays" / "philippine_provinces_cities_municipalities_and_barangays_2019v2.json"
DILG_DIR = BASE_DIR / "data" / "dilg"
COMELEC_DIR = BASE_DIR.parent / "ph-elections2025" / "data"
OUTPUT_DB = BASE_DIR / "static" / "data" / "unified_locations.duckdb"
OUTPUT_PARQUET = BASE_DIR / "static" / "data" / "unified_locations.parquet"
CONGRESSMAN_RANKING = BASE_DIR / "static" / "data" / "congressman-ranking.json"

def load_admin_hierarchy():
    """Load the base valid structure"""
    print(f"Loading Admin Hierarchy from {ADMIN_JSON}...")
    with open(ADMIN_JSON, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_dilg_barangays():
    """Load authoritative Barangay list from DILG Excel files"""
    # Note: Assuming converted to JSON or reading XLSX directly. 
    # For now, let's look for the excel files as seen in the ls output.
    excel_files = glob.glob(str(DILG_DIR / "official-list_*.xlsx"))
    print(f"Found {len(excel_files)} DILG Excel files.")
    
    all_barangays = []
    
    for f in tqdm(excel_files, desc="Reading DILG Data"):
        try:
            # Load specific columns to save memory
            # Usually strict format: Region, Province, City/Mun, Barangay
            df = pd.read_excel(f, dtype=str)
            # Normalize column names
            df.columns = [c.strip().upper() for c in df.columns]
            
            # Identify columns (heuristic)
            region_col = next((c for c in df.columns if 'REGION' in c), None)
            prov_col = next((c for c in df.columns if 'PROVINCE' in c), None)
            mun_col = next((c for c in df.columns if 'CITY' in c or 'MUNICIPALITY' in c), None)
            brgy_col = next((c for c in df.columns if 'BARANGAY' in c), None)
            
            if region_col and prov_col and mun_col and brgy_col:
                subset = df[[region_col, prov_col, mun_col, brgy_col]].rename(columns={
                    region_col: 'region',
                    prov_col: 'province',
                    mun_col: 'municipality',
                    brgy_col: 'barangay'
                })
                all_barangays.append(subset)
        except Exception as e:
            print(f"Error reading {f}: {e}")

    if not all_barangays:
        return pd.DataFrame()
        
    full_df = pd.concat(all_barangays, ignore_index=True)
    return full_df.drop_duplicates()


DISTRICTS_JSON = BASE_DIR / "static" / "data" / "districts.json"

def load_districts_json():
    print(f"Loading Districts DB from {DISTRICTS_JSON}...")
    if not DISTRICTS_JSON.exists():
        print("Error: districts.json not found.")
        return {}
    with open(DISTRICTS_JSON, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    districts = data.get('districts', {})
    
    # Load Manual BARMM Overrides (Highest Priority for structure/reps)
    overrides_path = BASE_DIR / "static" / "data" / "barmm_overrides.json"
    if overrides_path.exists():
        print(f"Loading Overrides from {overrides_path}...")
        with open(overrides_path, 'r', encoding='utf-8') as f:
            overrides = json.load(f)
            districts.update(overrides)

    # Load Generated Districts from Election CSVs (High Priority for District Assignment)
    # This fills in "municipalities" map
    generated_path = BASE_DIR / "static" / "data" / "districts_generated.json"
    if generated_path.exists():
        print(f"Loading Generated Districts from {generated_path}...")
        with open(generated_path, 'r', encoding='utf-8') as f:
            gen_data = json.load(f)
            
            # Merge into main districts dict
            for prov, municipalities in gen_data.items():
                # Normalize prov key lookup
                target_prov_key = None
                
                # Try direct
                if prov in districts:
                    target_prov_key = prov
                else:
                    # Try case-insensitive
                    prov_norm = normalize_location_name(prov)
                    for k in districts.keys():
                        if normalize_location_name(k) == prov_norm:
                            target_prov_key = k
                            break
                            
                # If province exists in districts.json (or overrides), update its muni map
                if target_prov_key:
                    if 'municipalities' not in districts[target_prov_key]:
                        districts[target_prov_key]['municipalities'] = {}
                    
                    # Update each municipality
                    for muni, dist in municipalities.items():
                        # We trust the generated one for the district name
                        districts[target_prov_key]['municipalities'][muni] = dist
                else:
                    # Province not in districts.json? 
                    # We could add it, but we might miss 'representatives' block then.
                    # For now just log it or add partial entry?
                    pass

    return districts

def normalize_location_name(name):
    if name is None or pd.isna(name): return ""
    name = str(name).upper().strip()
    name = name.replace("CITY OF ", "").replace(" CITY", "")
    name = name.replace("(CAPITAL)", "").strip()
    name = name.replace("(WESTERN SAMAR)", "").strip()
    return name
def get_congressman_from_districts(districts_data, province, district):
    if not province or not district: return "TBD"
    
    prov_data = districts_data.get(province)
    
    # Priority 1: Case-Insensitive Match (Better than aggressive normalization)
    if not prov_data:
        province_lower = str(province).lower().strip()
        for k, v in districts_data.items():
            if k.lower().strip() == province_lower:
                prov_data = v
                break
    
    # Priority 2: Normalized lookup (Aggressive stripping of "City", "Province", etc.)
    if not prov_data:
        # scan keys
        norm_prov = normalize_location_name(province)
        for k, v in districts_data.items():
            if normalize_location_name(k) == norm_prov:
                prov_data = v
                break
    
    if not prov_data: return "TBD"
    
    # Representatives dict
    reps = prov_data.get('representatives', {})
    
    # Clean district string to match keys (e.g. "1st District")
    # Our input might be "1st District", output is Name
    
    rep_name = reps.get(district)
    
    if not rep_name:
        # Try fuzzy match or variations?
        # Usually keys are "1st District", "Lone District", "At-large District"
        pass
        
    return rep_name or "TBD"

def get_district_from_json(districts_data, province, municipality, barangay=None):
    return get_district_from_json_with_key(districts_data, province, municipality, barangay)[0]

def get_district_from_json_with_key(districts_data, province, municipality, barangay=None):
    """
    Resolve district using districts.json plus fallbacks, returning:
      (district_name, resolved_top_level_key)

    The resolved_top_level_key is the key in districts.json that provided the match.
    This is needed for cases where the input 'province' is not a districts.json key
    (e.g., NCR rows, HUC handling, or combined entries like Taguig–Pateros).
    """
    resolved_key = None

    def _ret(val: str):
        return val, resolved_key

    # 1. Lookup Province
    prov_data = districts_data.get(province)
    if prov_data:
        resolved_key = province
    
    # Priority 1: Case-Insensitive Match
    if not prov_data:
        province_lower = str(province).lower().strip()
        for k, v in districts_data.items():
            if k.lower().strip() == province_lower:
                prov_data = v
                resolved_key = k
                break
                
    # Priority 2: Normalized lookup
    if not prov_data:
        # Try normalized
        norm_prov = normalize_location_name(province)
        found = False
        for k, v in districts_data.items():
            if normalize_location_name(k) == norm_prov:
                prov_data = v
                resolved_key = k
                found = True
                break
        
        # IF NOT FOUND: Do NOT return "Unknown" yet. 
        # It might be an HUC listed as a province.
        if not found:
             prov_data = None 
             resolved_key = None
    
    # NEW: Check if Municipality exists as a top-level key (for HUCs like Quezon City, Manila in NCR)
    if not prov_data:
        # Check if municipality is a top-level key
        # Try direct, case-insensitive, normalized
        if municipality in districts_data:
             prov_data = districts_data[municipality]
             resolved_key = municipality
        else:
             mun_lower = str(municipality).lower().strip()
             for k, v in districts_data.items():
                 if k.lower().strip() == mun_lower:
                     prov_data = v
                     resolved_key = k
                     break
        
        if not prov_data:
             norm_mun_key = normalize_location_name(municipality)
             for k, v in districts_data.items():
                 if normalize_location_name(k) == norm_mun_key:
                     prov_data = v
                     resolved_key = k
                     break 

    # NEW: Global municipality scan (handles combined keys like Taguig–Pateros)
    # If we still don't have a province/city entry, find any top-level key whose
    # municipalities map contains this municipality.
    if not prov_data:
        target_mun_norm = normalize_location_name(municipality)
        for k, v in districts_data.items():
            munis = v.get('municipalities', {}) if isinstance(v, dict) else {}
            for mk in munis.keys():
                if normalize_location_name(mk) == target_mun_norm:
                    prov_data = v
                    resolved_key = k
                    break
            if prov_data:
                break
             
    # 2. Lookup Municipality
    district_info = None
    if prov_data:
        # Municipalities dict maps Muni Name -> District
        munis = prov_data.get('municipalities', {})
        district_info = munis.get(municipality)
        
        if not district_info:
            # Try normalized muni name
            norm_mun = normalize_location_name(municipality)
            found_key = None
            
            # Priority 1: Exact normalized match
            for k in munis.keys():
                if normalize_location_name(k) == norm_mun:
                    found_key = k
                    break
            
            # Priority 2: Fuzzy/Substring match (e.g. Asuncion vs Asuncion (Saug))
            if not found_key:
                # Clean generic words? Or just check inclusion
                for k in munis.keys():
                    k_norm = normalize_location_name(k)
                    if k_norm in norm_mun or norm_mun in k_norm:
                        # Only accept if length is significant
                        if len(k_norm) > 3 and len(norm_mun) > 3:
                            found_key = k
                            break
            
            if found_key:
                district_info = munis[found_key]

    # Handle Dictionary Result (Mixed District) or String
    if isinstance(district_info, dict):
        # It's a mixed city/muni
        # Check if we have barangay info
        if barangay and 'barangays' in district_info:
            brgy_map = district_info['barangays']
            # Direct match
            res = brgy_map.get(barangay)
            if not res:
                # Normalized barangay match
                target_brgy_norm = normalize_location_name(barangay)
                for k, v in brgy_map.items():
                    if normalize_location_name(k) == target_brgy_norm:
                        res = v
                        break
            
            if res:
                return _ret(res)
            
        # Fallback if barangay not found in mixed map
        return _ret("Unknown") # Or "Mixed"?
            
    if district_info:
        return _ret(district_info)
        

    # 3.5. Check for specific Barangay mappings (Classic districts.json style)
    # Structure: "barangays": { "1st District": ["Brgy A", "Brgy B"], ... }
    # MOVED UP: Run this BEFORE HUC Fallback to prioritize local province/city data
    if prov_data:
        brgy_map = prov_data.get('barangays')
        if brgy_map and barangay:
            norm_brgy = normalize_location_name(barangay)
            for dist_name, brgy_list in brgy_map.items():
                for b in brgy_list:
                    if normalize_location_name(b) in norm_brgy: # "Barangay 76" vs "76"
                        return _ret(dist_name)

    # 4. HUC Fallback: DILG sometimes lists HUC (highly urbanized city) as the Province
    # e.g. Province="CITY OF DAVAO", Municipality="CITY OF DAVAO"
    # But we have it under Province="Davao Del Sur", Municipality="City Of Davao"
    # If we failed to find the 'province' at the top level, or found it but it had no info.
    
    # Only try this if we haven't found a valid district yet
    if not district_info or district_info == "Unknown":
        # Check if the 'province' argument itself is actually a municipality in our DB
        # scan all provinces
        target_huc_norm = normalize_location_name(province)
        
        for prov_key, p_data in districts_data.items():
            p_munis = p_data.get('municipalities', {})
            
            # Check if this province has a municipality matching our input 'province'
            # e.g. does Davao Del Sur have "City Of Davao"?
            
            found_huc_key = None
            for m_key in p_munis.keys():
                if normalize_location_name(m_key) == target_huc_norm:
                    found_huc_key = m_key
                    break
            
            # If match found, this is our data
            if found_huc_key:
                huc_data = p_munis[found_huc_key]
                resolved_key = prov_key
                
                # Now resolve district within this HUC data
                # If it's a dict (mixed), check barangay
                if isinstance(huc_data, dict):
                     if barangay and 'barangays' in huc_data:
                        # Reuse the barangay lookup logic
                        brgy_map = huc_data['barangays']
                        target_brgy_norm = normalize_location_name(barangay)
                        for k, v in brgy_map.items():
                             if normalize_location_name(k) == target_brgy_norm:
                                 return _ret(v)
                                 
                elif huc_data:
                    # Single district city
                    return _ret(huc_data)
                    
                # If we matched the city but failed to match barangay, 
                # we should probably return "Unknown" here but stop searching other provinces
                # unless generic name? "City of Davao" is specific.
                break
                    
    # 6. Fallback: If province has only one district ("Lone District" or "At-large")
    if prov_data:
        all_dists = prov_data.get('all_districts', [])
        if len(all_dists) == 1:
            return _ret(all_dists[0])
        
    return _ret("Unknown")

def main():
    # 1. Load DILG Data (Master Barangay List)
    df = load_dilg_barangays()
    if df.empty:
        print("Failed to load DILG data. Exiting.")
        return
    
    
    # NCR region aliases:
    # Add common textual variants so matching can treat "Metro Manila" as a region-level hint
    # (and avoid confusing it with "Manila" the city).
    try:
        region_norm = df['region'].astype(str).str.upper().str.strip()
        ncr_mask = region_norm.eq('NCR')
        if ncr_mask.any():
            aliases = ['METRO MANILA', 'NATIONAL CAPITAL REGION']
            frames = [df]
            for alias in aliases:
                extra = df.loc[ncr_mask].copy()
                extra['region'] = alias
                frames.append(extra)
            df = pd.concat(frames, ignore_index=True).drop_duplicates()
    except Exception:
        pass

    # 2. Load Districts JSON
    districts_data = load_districts_json()
    
    # DEBUG: Check Tatalon in loaded data
    qc_data = districts_data.get("Quezon City", {})
    qc_brgys = qc_data.get("barangays", {})
    qc_munis = qc_data.get("municipalities", {})
    print(f"DEBUG: QC Municipalities keys: {list(qc_munis.keys())}")
    if "Quezon City" in qc_munis:
         print(f"  FOUND 'Quezon City' in entries: {qc_munis['Quezon City']}")
    print("DEBUG: Loaded QC Barangays for Tatalon:")
    for d, b_list in qc_brgys.items():
        if "Tatalon" in b_list:
            print(f"  FOUND Tatalon in {d}")
    
    # 3. Apply District Mapping
    print("Assigning Districts via districts.json...")
    
    def apply_location_logic(row):
        prov = row['province']
        mun = row['municipality']
        brgy = row.get('barangay')
        
        dist, prov_key = get_district_from_json_with_key(districts_data, prov, mun, brgy)
        cong = get_congressman_from_districts(districts_data, prov_key or prov, dist)
        
        # Strip name to just the name part usually (format: "Name (Year-Year)")
        if cong and cong != "TBD":
             cong = cong.split('(')[0].strip()
             
        if brgy and "Tatalon" in str(brgy):
            print(f"DEBUG TATALON: Prov='{prov}', Mun='{mun}' -> Dist='{dist}', Cong='{cong}'")
            if dist == "3rd District":
                # Print why it chose 3rd? Hard to trace return value, but let's see inputs.
                pass

        return pd.Series([dist, cong])

    df[['district', 'congressman']] = df.apply(apply_location_logic, axis=1)
    
    # 5. Save to DuckDB
    print(f"Saving to {OUTPUT_DB}...")
    conn = duckdb.connect(str(OUTPUT_DB))
    conn.execute("CREATE OR REPLACE TABLE locations AS SELECT * FROM df")
    conn.close()
    
    # 6. Save to Parquet (for easy loading in other scripts)
    print(f"Saving to {OUTPUT_PARQUET}...")
    df.to_parquet(OUTPUT_PARQUET)
    
    print("Done!")


if __name__ == "__main__":
    main()


import os
import csv
import json
import glob
from pathlib import Path
from collections import defaultdict
import re

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
ELECTIONS_DATA_DIR = BASE_DIR.parent / "ph-elections2025" / "data"
OUTPUT_JSON = BASE_DIR / "static" / "data" / "districts_generated.json"

def extract_district(csv_path):
    """
    Reads a CSV and searches for 'MEMBER, HOUSE OF REPRESENTATIVES' or similar.
    Returns the district string if found, e.g. '1st District', 'Lone District'.
    """
    try:
        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            # We don't strictly need a CSV reader if we just grep lines, but let's be safe
            # The format is: Precinct, Context, Level, Contest, Candidate, Votes, Percent
            # We want the 'Contest' column (index 4 usually, but let's just search the line)
            
            content = f.read()
            
            # Look for Congress/House contests
            # Patterns:
            # "MEMBER, HOUSE OF REPRESENTATIVES - <DISTRICT>"
            # "MEMBER, HOUSE OF REPRESENTATIVES - <PROVINCE> - <DISTRICT>"
            # For BARMM, sometimes they might differ slightly, but usually standard.
            
            # Regex to capture the district part
            # Examples: 
            # "MEMBER, HOUSE OF REPRESENTATIVES - FIRST DISTRICT"
            # "MEMBER, HOUSE OF REPRESENTATIVES - LONE DISTRICT"
            # "MEMBER, HOUSE OF REPRESENTATIVES of MAGUINDANAO DEL NORTE - LONE LEGDIST"
            
            # Iterate lines to find the contest
            # We want to capture the specific district text
            
            # Revised Regex to be more inclusive
            matches = re.search(r"MEMBER, HOUSE OF REPRESENTATIVES.*?- ([A-Z0-9 ]+(?:DISTRICT|LEGDIST))", content, re.IGNORECASE)
            if matches:
                dist_raw = matches.group(1).strip()
                return normalize_district(dist_raw)
                
            # Fallback: Check for Sangguniang Bayan ... Lone District?
            # Sometimes used for validating it's a lone district area (e.g. some cities)
            if "LONE DIST" in content:
                # But be careful, SB is local. Congressman is national.
                # Only use if we can't find House contest?
                # Actually, some CSVs might be missing House contest if uncontested? Unlikely for election returns.
                pass
                
    except Exception as e:
        print(f"Error reading {csv_path}: {e}")
    
    return None

def normalize_district(raw):
    """
    Converts 'FIRST DISTRICT' -> '1st District'
    'LONE DISTRICT' -> 'Lone District'
    'LONE LEGDIST' -> 'Lone District'
    """
    raw = raw.upper().strip()
    
    if "LONE" in raw: return "Lone District"
    if "AT-LARGE" in raw: return "At-large District"
    
    # Remove LEGDIST / DISTRICT to clean up if needed, but the ordinals logic works
    raw = raw.replace("LEGDIST", "DISTRICT")
    
    # Ordinal mapping
    ordinals = {
        "FIRST": "1st", "SECOND": "2nd", "THIRD": "3rd", "FOURTH": "4th", 
        "FIFTH": "5th", "SIXTH": "6th", "SEVENTH": "7th", "EIGHTH": "8th"
    }
    
    for k, v in ordinals.items():
        if k in raw:
            return f"{v} District"
            
    # Try parsing numbers directly "1ST", "2ND"
    match = re.search(r"(\d+)(ST|ND|RD|TH)", raw)
    if match:
        return f"{match.group(1)}{match.group(2).lower()} District"
        
    return raw.title() # Fallback "Taguig-Pateros District" -> Title Case

def main():
    if not ELECTIONS_DATA_DIR.exists():
        print(f"Error: {ELECTIONS_DATA_DIR} does not exist.")
        return

    print(f"Scanning {ELECTIONS_DATA_DIR}...")
    
    # Structure: PROVINCE / MUNICIPALITY / BARANGAY / CSV
    # We want to map Province -> Municipality -> District
    
    mapping = defaultdict(dict)
    
    # Get all provinces
    provinces = [p for p in ELECTIONS_DATA_DIR.iterdir() if p.is_dir()]
    
    print(f"Found {len(provinces)} provinces.")
    
    for prov_dir in provinces:
        prov_name_clean = prov_dir.name.replace('_', ' ').title()
        
        # Get municipalities
        munis = [m for m in prov_dir.iterdir() if m.is_dir()]
        
        for muni_dir in munis:
            muni_name_clean = muni_dir.name.replace('_', ' ').title()
            
            # Get Barangays
            brgys = [b for b in muni_dir.iterdir() if b.is_dir()]
            
            # Store barangay-level districts
            muni_districts = {}
            
            for brgy_dir in brgys:
                brgy_name_clean = brgy_dir.name.replace('_', ' ').title()
                
                # Check CSV in this barangay
                csv_files = list(brgy_dir.glob("*.csv"))
                if csv_files:
                    # Just check one file per barangay
                    dist = extract_district(csv_files[0])
                    if dist:
                        muni_districts[brgy_name_clean] = dist
            
            if not muni_districts:
                continue

            # Check if all barangays are in the same district
            distinct_dists = set(muni_districts.values())
            
            if len(distinct_dists) == 1:
                # Single district for the whole municipality
                mapping[prov_name_clean][muni_name_clean] = list(distinct_dists)[0]
            else:
                # Mixed districts (e.g. Davao City)
                # We store a dict: { "mixed": True, "barangays": { "Brgy": "Dist" } }
                # Or just match the structure used in build script?
                # Build script usually expects "municipalities": { "Muni": "Dist" } 
                # OR "barangays": { "1st Dist": [List of Brgys] }
                # Let's verify what build_unified expects. 
                # It loads this json.
                # If we output a DICT here for the municipality, we must handle it in build script.
                mapping[prov_name_clean][muni_name_clean] = {
                    "is_mixed": True,
                    "barangays": muni_districts
                }

    print(f"Saving to {OUTPUT_JSON}...")
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        # Convert defaultdict to regular dict for clean JSON
        json.dump({k: dict(v) for k, v in mapping.items()}, f, indent=2, sort_keys=True)
        
    print("Done.")

if __name__ == "__main__":
    main()

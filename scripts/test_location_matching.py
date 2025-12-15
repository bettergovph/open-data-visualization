import duckdb
import re
from pathlib import Path
from collections import defaultdict

def load_location_db(con):
    print("Loading Location DB...")
    con.execute("CREATE OR REPLACE TABLE unified_locations AS SELECT * FROM read_parquet('static/data/unified_locations.parquet')")
    df = con.execute("SELECT region, province, municipality, district, congressman FROM unified_locations").fetch_df()
    
    lookup = defaultdict(lambda: defaultdict(dict))
    muni_counts = defaultdict(set)
    muni_info_map = {}
    
    province_defaults = {}
    prov_districts = defaultdict(set)
    prov_congressmen = defaultdict(set)
    
    for _, row in df.iterrows():
        reg = str(row['region']).upper().strip()
        prov = str(row['province']).upper().strip()
        mun = str(row['municipality']).upper().strip()
        dist = str(row['district'])
        cong = str(row['congressman'])
        
        prov_districts[prov].add(dist)
        prov_congressmen[prov].add(cong)
        
        def norm(name):
            t = name.upper().replace("(CAPITAL)", "").replace("(CAPITAL)", "").replace("(Capital)", "").strip()
            if t.startswith("CITY OF "):
                t = t[8:].strip() + " CITY"
            return t

        mun_norm = norm(mun)
        
        data = {
            'province': prov,
            'municipality': mun,
            'district': dist,
            'congressman': cong
        }
        
        lookup[prov][mun] = data
        lookup[prov][mun_norm] = data
        
        muni_counts[mun].add(prov)
        muni_counts[mun_norm].add(prov)
        
        if mun not in muni_info_map: muni_info_map[mun] = data
        if mun_norm not in muni_info_map: muni_info_map[mun_norm] = data
        
    unique_muni_lookup = {}
    for m, provinces in muni_counts.items():
        if len(provinces) == 1:
            unique_muni_lookup[m] = muni_info_map[m]

    for p, dists in prov_districts.items():
        if len(dists) == 1:
            province_defaults[p] = {
                'province': p,
                'municipality': 'Province-wide',
                'district': list(dists)[0],
                'congressman': list(prov_congressmen[p])[0]
            }
        else:
             province_defaults[p] = {
                'province': p,
                'municipality': 'Province-wide',
                'district': 'Multiple Districts',
                'congressman': 'Multiple'
            }

    return {'hierarchy': lookup, 'unique': unique_muni_lookup, 'province_defaults': province_defaults}

def enrich(text, lookup_data):
    text = text.upper()
    def normalize_search_text(t):
        t = t.replace("(CAPITAL)", "").replace("(CAPITAL)", "").replace("(Capital)", "").strip()
        if t.startswith("CITY OF "):
            t = t[8:].strip() + " CITY"
        return t
    text_norm = normalize_search_text(text)
    
    hierarchy = lookup_data['hierarchy']
    unique_lookup = lookup_data['unique']
    found_info = None
    
    # Strategy 1 (Unique First)
    if not found_info:
        # Sort keys by length descending to ensure "BACOLOD CITY" matches before "BACOLOD"
        sorted_keys = sorted(unique_lookup.keys(), key=len, reverse=True)
        for mun_key in sorted_keys:
            info = unique_lookup[mun_key]
            if len(mun_key) < 4: continue
            # Enforce boundaries for BOTH mun_key (raw match) and pattern (norm match)
            # Check Norm
            pattern_norm = r'\b' + re.escape(mun_key) + r'\b'
            if re.search(pattern_norm, text_norm):
                print(f"   [Match Strategy 1] Found Unique (Norm): {mun_key} -> {info['province']}")
                found_info = info
                break
            # Check Raw (if key is different)
            # Actually mun_key is the key in lookup. It could be raw or norm. 
            # If mun_key is "BACOLOD CITY", text_norm won't match (because text_norm has CITY stripped? No, text_norm is normalized).
            # Loop runs over keys. keys include "BACOLOD CITY" and "BACOLOD".
            
            # If key is "BACOLOD CITY" (Raw): 
            # regex(BACOLOD CITY) in text_norm? text_norm="... BACOLOD ...". No match.
            # So we must ALSO check raw text.
            pattern_raw = r'\b' + re.escape(mun_key) + r'\b'
            if re.search(pattern_raw, text):
                print(f"   [Match Strategy 1] Found Unique (Raw): {mun_key} -> {info['province']}")
                found_info = info
                break
                
    # Strategy 2 (Province First)
    matched_province = None
    if not found_info:
        for prov in hierarchy.keys():
            if prov in text:
                matched_province = prov
                for mun_key, info in hierarchy[prov].items():
                    if len(mun_key) < 4: continue
                    # Check Norm
                    pattern_norm = r'\b' + re.escape(mun_key) + r'\b'
                    if re.search(pattern_norm, text_norm):
                        print(f"   [Match Strategy 2] Found inside {prov} (Norm): {mun_key}")
                        found_info = info
                        break
                    # Check Raw
                    pattern_raw = r'\b' + re.escape(mun_key) + r'\b'
                    if re.search(pattern_raw, text):
                        print(f"   [Match Strategy 2] Found inside {prov} (Raw): {mun_key}")
                        found_info = info
                        break
                if found_info: break
    
    if not found_info and matched_province:
         print(f"   [Match Strategy 2.5] Fallback to Province: {matched_province}")
         found_info = lookup_data['province_defaults'].get(matched_province)
         
    return found_info

con = duckdb.connect()
lookup_data = load_location_db(con)

test_cases = [
    "Construction of Road in Bacolod City",
    "Project in Bacolod",
    "Improvement of Quezon City Road",
    "Project in Quezon Province",
    "Lanao del Norte Interior Circum. Rd"
]

print("\nRunning Tests...")
for t in test_cases:
    print(f"\nText: '{t}'")
    res = enrich(t, lookup_data)
    if res:
        print(f"RESULT: {res['municipality']}, {res['province']} | Cong: {res['congressman']}")
    else:
        print("RESULT: Unknown")

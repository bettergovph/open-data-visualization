
import json
import pandas as pd
import os
import duckdb
from pathlib import Path
from collections import defaultdict
from datetime import datetime
import multiprocessing
import unicodedata
import re
import time
import math

DATA_DIR = "static/data"

# --- Globals for Worker Processes ---
g_resurrected_map = None
g_flagged_map = None
g_congressman_lookup = None
g_city_lookup = None
g_location_entries = None
g_transparency_index = None
g_transparency_projects = None
g_STOPWORDS = None

def normalize_for_match(text):
    if not text: return ""
    try:
        text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
        text = text.lower()
        # Remove punctuation (keep words separated)
        text = re.sub(r'[^\w\s]', ' ', text)
        text = text.strip()
        text = text.replace("city of ", "").replace("municipality of ", "")
    except:
        return ""
    return text

def extract_barangay(text):
    if not text: return None
    try:
        t = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII').lower()
        patterns = [r"brgy\.?\s+([a-z0-9][a-z0-9\s\-']{1,40})", r"barangay\s+([a-z0-9][a-z0-9\s\-']{1,40})"]
        for pat in patterns:
            m = re.search(pat, t)
            if m:
                candidate = m.group(1).strip()
                candidate = re.split(r'[;,|]', candidate)[0].strip()
                return candidate if candidate else None
    except:
        pass
    return None

def find_best_location_match(project_name, project_province=None):
    if not project_name: return None
    
    # Access shared location entries
    location_entries = g_location_entries
    if not location_entries: return None

    name_norm = normalize_for_match(project_name)
    name_lower = project_name.lower()
    prov_norm = normalize_for_match(project_province) if project_province else ""

    # Disambiguation patterns
    disambiguation_patterns = [
        (r'davao\s+de\s+oro', 'DAVAO DE ORO'),
        (r'davao\s+del\s+sur', 'DAVAO DEL SUR'),
        (r'davao\s+del\s+norte', 'DAVAO DEL NORTE'),
        (r'davao\s+oriental', 'DAVAO ORIENTAL'),
        (r'davao\s+occidental', 'DAVAO OCCIDENTAL'),
        (r'cebu\s+city', 'CEBU CITY'),
        (r'cagayan\s+de\s+oro', 'CITY OF CAGAYAN DE ORO'),
        (r'quezon\s+city', 'QUEZON CITY'),
        (r'zamboanga\s+del\s+norte', 'ZAMBOANGA DEL NORTE'),
        (r'zamboanga\s+del\s+sur', 'ZAMBOANGA DEL SUR'),
        (r'zamboanga\s+sibugay', 'ZAMBOANGA SIBUGAY'),
    ]

    for pattern, target_prov in disambiguation_patterns:
        if re.search(pattern, name_lower):
            for entry in location_entries:
                prov, muni, brgy, dist, cong = entry
                if target_prov.lower() in prov.lower():
                    muni_norm = normalize_for_match(muni)
                    brgy_norm = normalize_for_match(brgy)
                    if muni_norm and len(muni_norm) > 3 and muni_norm in name_norm:
                        return entry
                    if brgy_norm and len(brgy_norm) > 3 and brgy_norm in name_norm:
                        return entry

    best_match = None
    best_score = 0

    def word_boundary_match(needle, haystack):
        if not needle or len(needle) < 3: return False
        try:
            pattern = r'\b' + re.escape(needle) + r'\b'
            return bool(re.search(pattern, haystack))
        except:
            return False

    for entry in location_entries:
        prov, muni, brgy, dist, cong = entry
        score = 0
        match_length_bonus = 0

        prov_entry = normalize_for_match(prov)
        muni_entry = normalize_for_match(muni)
        brgy_entry = normalize_for_match(brgy)

        if prov_entry and len(prov_entry) > 3:
            if word_boundary_match(prov_entry, name_norm):
                score += 3
                match_length_bonus += len(prov_entry)
            elif prov_norm and prov_entry == prov_norm:
                score += 2

        if muni_entry and len(muni_entry) > 3:
            if word_boundary_match(muni_entry, name_norm):
                score += 4
                match_length_bonus += len(muni_entry) * 2

        if brgy_entry and len(brgy_entry) > 3:
            if word_boundary_match(brgy_entry, name_norm):
                score += 2
                match_length_bonus += len(brgy_entry)

        total_score = score * 100 + match_length_bonus

        if total_score > best_score:
            best_score = total_score
            best_match = entry

    return best_match if best_score >= 200 else None

def process_chunk(pids):
    results = []
    
    # Access globals
    res_map = g_resurrected_map
    flag_map = g_flagged_map
    cong_lookup = g_congressman_lookup
    city_lookup = g_city_lookup
    trans_index = g_transparency_index
    trans_projs = g_transparency_projects
    stopwords = g_STOPWORDS
    
    for pid in pids:
        # Get data
        res_match = res_map.get(pid)
        flagged_item = flag_map.get(pid)
        
        # Base Data
        if res_match:
            item_2026 = res_match.get('year_2026', {})
            name = item_2026.get('name')
            amount = item_2026.get('amount', 0)
            district = item_2026.get('district')
            congressman = item_2026.get('congressman')
            province = item_2026.get('province')
            historical_match = res_match.get('historical', {}).get('description')
        else:
            name = flagged_item.get('name')
            amount = flagged_item.get('amount', 0)
            district = flagged_item.get('district')
            congressman = flagged_item.get('congressman')
            province = flagged_item.get('province')
            historical_match = None

        # Fill missing
        if flagged_item:
            if not district: district = flagged_item.get('district')
            if not congressman: congressman = flagged_item.get('congressman')
            if not province: province = flagged_item.get('province')
            if not name: name = flagged_item.get('name')

        # Skip SIPAG aggregates
        if name and "SUSTAINABLE INFRASTRUCTURE PROJECTS ALLEVIATING GAPS (SIPAG) - MULTI-PURPOSE BUILDINGS/FACILITIES TO SUPPORT SOCIAL SERVICES" in name:
            continue

        flag_reason = flagged_item.get('flag_reason') if flagged_item else None
        subcategory = flagged_item.get('subcategory') if flagged_item else None

        district = district or "Unknown"
        congressman = congressman or "Unknown"
        province = province or "Unknown"

        # --- Transparency Matching ---
        transparency_links = []
        if name:
             name_norm = normalize_for_match(name)
             name_tokens = set([t for t in name_norm.split() if len(t) > 2 and t not in stopwords])
             
             if len(name_tokens) >= 2:
                 candidate_counts = {}
                 for token in name_tokens:
                     if token in trans_index:
                         for idx in trans_index[token]:
                             candidate_counts[idx] = candidate_counts.get(idx, 0) + 1

                 for idx, count in candidate_counts.items():
                     matched = False
                     if count >= 3:
                         matched = True
                     elif len(name_tokens) > 0 and count >= len(name_tokens) * 0.8:
                         matched = True
                         
                     if matched:
                         t_proj = trans_projs[idx]
                         transparency_links.append({
                             'id': t_proj['id'],
                             'amount': t_proj['amount'],
                             'name': t_proj['name']
                         })
                         if len(transparency_links) >= 10:
                             break

        # --- Location Matching ---
        if name:
            best_match = find_best_location_match(name, province)
            if best_match:
                prov_match, muni_match, brgy_match, dist_match, cong_match = best_match
                congressman = cong_match
                district = dist_match
                province = prov_match

        # --- Fallbacks ---
        if congressman in ["Unknown", "TBA", "TBD"] and (province, district) in cong_lookup:
            congressman = cong_lookup[(province, district)]

        if congressman in ["Unknown", "TBA", "TBD"] and province and province != "Unknown":
            prov_clean = province.replace("CITY OF ", "").replace("City of ", "").strip()
            if prov_clean.upper() in city_lookup:
                congressman = city_lookup[prov_clean.upper()]
                if district == "Unknown": district = "Lone District"
            elif province.upper() in city_lookup:
                congressman = city_lookup[province.upper()]
                if district == "Unknown": district = "Lone District"

        # --- Corrections ---
        if "Las Pinas" in str(district) or "Villar, Camille" in str(congressman) or "Camille Villar" in str(congressman):
             congressman = "Senator Camille Villar"
             if district == "Unknown": district = "Las Piñas City"
        if "Ralph Recto" in str(congressman):
            congressman = "Ryan Christian Recto"

        # Key
        if province and province != "Unknown":
            key = f"{congressman} ({district}, {province})"
        else:
            key = f"{congressman} ({district})"
        
        # Barangay Alignment check
        brgy_2026 = extract_barangay(name) or extract_barangay(item_2026.get('description', '') if res_match else '')
        brgy_hist = extract_barangay(res_match.get('historical', {}).get('description', '') if res_match else '')
        if brgy_2026 or brgy_hist:
            if not (brgy_2026 and brgy_hist and brgy_2026 == brgy_hist):
                historical_match = None

        project_info = {
            'id': pid,
            'name': name,
            'amount': amount,
            'transparency_links': transparency_links,
            'historical_match': historical_match,
            'flag_reason': flag_reason,
            'subcategory': subcategory,
            'key': key,
            'congressman': congressman,
            'district': district,
            'province': province
        }
        results.append(project_info)

    return results

def init_worker_process(
    res_map, flag_map, cong_lookup, cit_lookup, 
    loc_entries, trans_idx, trans_projs, stops
):
    global g_resurrected_map, g_flagged_map, g_congressman_lookup, g_city_lookup
    global g_location_entries, g_transparency_index, g_transparency_projects, g_STOPWORDS
    g_resurrected_map = res_map
    g_flagged_map = flag_map
    g_congressman_lookup = cong_lookup
    g_city_lookup = cit_lookup
    g_location_entries = loc_entries
    g_transparency_index = trans_idx
    g_transparency_projects = trans_projs
    g_STOPWORDS = stops

def generate_integrated_matrix():
    print("="*100)
    print(" INTEGRATED MATRIX GENERATION (2026) - PARALLEL")
    print("="*100)

    # 1. Load Projects
    resurrected_path = Path("static/data/resurrected_projects_dpwh_enriched.json")
    flagged_path = Path("static/data/flagged_amount_projects_2026.json")
    
    with open(resurrected_path, 'r', encoding='utf-8') as f:
        res_data = json.load(f)
        res_matches = res_data.get('matches', [])
    with open(flagged_path, 'r', encoding='utf-8') as f:
        flagged_list = json.load(f)

    # Map Projects
    resurrected_map = {str(m.get('year_2026', {}).get('id')): m for m in res_matches if m.get('year_2026', {}).get('id')}
    flagged_map = {str(p.get('id')): p for p in flagged_list if p.get('id')}
    all_pids = list(set(flagged_map.keys()) | set(resurrected_map.keys()))
    
    print(f"Projects to Process: {len(all_pids)}")

    # 2. Load Districts
    districts_file = os.path.join(DATA_DIR, "districts.json")
    congressman_lookup = {}
    city_lookup = {}
    with open(districts_file, "r") as f:
        d_data = json.load(f)
        for prov, info in d_data['districts'].items():
            reps = info.get('representatives', {})
            for dist, rep in reps.items():
                if rep: congressman_lookup[(prov, dist)] = rep
            muni_map = info.get('municipalities', {})
            for muni, dist in muni_map.items():
                if reps.get(dist): city_lookup[muni.lower()] = reps.get(dist)

    # 3. Load Locations
    location_entries = []
    unified_locations_path = os.path.join(DATA_DIR, "unified_locations.parquet")
    con = duckdb.connect()
    con.execute(f"CREATE TABLE ul AS SELECT * FROM read_parquet('{unified_locations_path}')")
    result = con.execute("SELECT province, municipality, barangay, district, congressman FROM ul WHERE congressman IS NOT NULL AND congressman != 'TBD' AND congressman != 'Unknown'").fetchall()
    for row in result:
        prov, muni, brgy, dist, cong = row
        if cong: location_entries.append((prov, muni, brgy, dist, cong))
    con.close()
    print(f"Location Entries: {len(location_entries)}")

    # 4. Load Transparency
    transparency_projects = []
    transparency_parquet_path = os.path.join(DATA_DIR, "parquet/transparency_projects.parquet")
    STOPWORDS = {
        "construction", "completion", "rehabilitation", "improvement", "repair", "maintenance", 
        "upgrading", "widening", "concreting", "asphalt", "overlay", "reblocking", 
        "school", "classroom", "infra", "infrastructure",
        "project", "program", "phase", "package", "contract", "id", "no", "of", "the", "in", 
        "and", "to", "with", "at", "city", "province", "municipality", "barangay", "district",
        "st.", "ave.", "rd.", "ext.", "brgy", "poblacion", "water", "system", "flood", "control"
    }
    
    # Load and Tokenize
    print("Loading Transparency Data...")
    con = duckdb.connect()
    t_rows = con.execute(f"SELECT contract_id, project_name, amount FROM read_parquet('{transparency_parquet_path}') WHERE project_name IS NOT NULL").fetchall()
    con.close()
    
    print("Tokenizing Transparency Data...")
    for row in t_rows:
        cid, pname, pamount = row
        if not pname: continue
        norm = normalize_for_match(pname)
        tokens = set([t for t in norm.split() if len(t) > 2 and t not in STOPWORDS])
        transparency_projects.append({
            'id': cid, 'name': pname, 'amount': pamount, 'tokens': tokens
        })
    
    # Index
    print("Indexing Transparency Data...")
    transparency_index = {}
    token_counts = {}
    for idx, item in enumerate(transparency_projects):
        for token in item['tokens']:
            token_counts[token] = token_counts.get(token, 0) + 1
            if token not in transparency_index:
                transparency_index[token] = []
            transparency_index[token].append(idx)
            
    # Prune
    threshold = len(transparency_projects) * 0.05
    pruned = 0
    
    # Tokens to NEVER prune (Essential for MPB matching)
    KEEP_TOKENS = {"multi-purpose", "multipurpose", "building"}

    for token, count in token_counts.items():
        if count > threshold:
            if token in KEEP_TOKENS:
                continue
            if token in transparency_index: 
                del transparency_index[token]
                pruned += 1
    print(f"Indexed {len(transparency_projects)} items. Pruned {pruned} frequent tokens.")

    # 5. Parallel Execution
    cpu_count = os.cpu_count() or 4
    print(f"Processing with {cpu_count} workers...")
    
    chunk_size = math.ceil(len(all_pids) / cpu_count / 4) # 4 chunks per core for better load balancing
    chunks = [all_pids[i:i + chunk_size] for i in range(0, len(all_pids), chunk_size)]
    
    pool = multiprocessing.Pool(
        processes=cpu_count,
        initializer=init_worker_process,
        initargs=(
            resurrected_map, flagged_map, congressman_lookup, city_lookup,
            location_entries, transparency_index, transparency_projects, STOPWORDS
        )
    )
    
    total_chunks = len(chunks)
    processed_count = 0
    
    # Aggregators
    district_stats = defaultdict(lambda: {
        'congressman': 'Unknown', 'district': 'Unknown', 'province': 'Unknown',
        'project_count': 0, 'total_amount': 0.0, 'projects': []
    })
    
    results_flat = []
    
    print("Batch Processing...")
    for batch_result in pool.imap_unordered(process_chunk, chunks):
        results_flat.extend(batch_result)
        processed_count += 1
        print(f"   Processed Batch {processed_count}/{total_chunks}...", end='\r')
    
    pool.close()
    pool.join()
    print("\nProcessing Complete. Aggregating...")

    # 6. Aggregate
    High_priority_projects = []
        
    for p in results_flat:
        key = p.pop('key')
        cong = p.pop('congressman')
        dist = p.pop('district')
        prov = p.pop('province')
        
        amount = p['amount']
        
        # Update Stats
        district_stats[key]['congressman'] = cong
        district_stats[key]['district'] = dist
        district_stats[key]['province'] = prov
        district_stats[key]['project_count'] += 1
        district_stats[key]['total_amount'] += amount
        district_stats[key]['projects'].append(p)
        
        High_priority_projects.append(p)

    # 7. Ranking (Broad)
    ranking_list = []
    for key, stats in district_stats.items():
        ranking_list.append(stats)
    ranking_list.sort(key=lambda x: (x['project_count'], x['total_amount']), reverse=True)

    # 8. Strict Ranking (Subset)
    # Filter projects where historical_match AND flag_reason are present
    ranking_list_strict = []
    
    strict_count = 0
    strict_amount = 0.0

    for entry in ranking_list:
        # Deep copy to avoid mutating the broad list
        entry_strict = entry.copy()
        strict_projs = [p for p in entry['projects'] if p.get('historical_match') and p.get('flag_reason')]
        
        if strict_projs:
            entry_strict['projects'] = strict_projs
            entry_strict['project_count'] = len(strict_projs)
            entry_strict['total_amount'] = sum(p['amount'] for p in strict_projs)
            ranking_list_strict.append(entry_strict)
            
            strict_count += len(strict_projs)
            strict_amount += entry_strict['total_amount']

    ranking_list_strict.sort(key=lambda x: (x['project_count'], x['total_amount']), reverse=True)

    # Output Broad
    output_data = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "total_high_priority_projects": len(High_priority_projects),
            "total_amount_involved": sum(p['total_amount'] for p in ranking_list),
            "total_districts_affected": len(ranking_list)
        },
        "ranking": ranking_list
    }
    
    output_path = Path("static/data/integrated_matrix.json")
    print(f"💾 Saving Broad Matrix to {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    # Output Strict
    output_data_strict = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "total_high_priority_projects": strict_count,
            "total_amount_involved": strict_amount,
            "total_districts_affected": len(ranking_list_strict)
        },
        "ranking": ranking_list_strict
    }
    
    output_path_strict = Path("static/data/integrated_matrix_strict.json")
    print(f"💾 Saving Strict Matrix to {output_path_strict}...")
    with open(output_path_strict, 'w', encoding='utf-8') as f:
        json.dump(output_data_strict, f, indent=2, ensure_ascii=False)
        
    print("✅ Done.")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    generate_integrated_matrix()

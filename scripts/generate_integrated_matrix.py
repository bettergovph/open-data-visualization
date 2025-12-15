import json
import pandas as pd
import os
import duckdb
from pathlib import Path
from collections import defaultdict
from datetime import datetime

DATA_DIR = "static/data"

def generate_integrated_matrix():
    print("="*100)
    print(" INTEGRATED MATRIX GENERATION (2026)")
    print(" Combining Resurrected Projects + Flagged Amount Projects")
    print("="*100)

    # 1. Load Data
    # UPDATED: Use the Enriched Unrevised file
    resurrected_path = Path("static/data/resurrected_projects_dpwh_enriched.json")
    flagged_path = Path("static/data/flagged_amount_projects_2026.json")
    
    if not resurrected_path.exists():
        print(f"❌ Resurrected projects file not found: {resurrected_path}")
        return
    if not flagged_path.exists():
        print(f"❌ Flagged projects file not found: {flagged_path}")
        return

    print("Loading datasets...")
    with open(resurrected_path, 'r', encoding='utf-8') as f:
        resurrected_data = json.load(f)
        resurrected_matches = resurrected_data.get('matches', [])
    
    with open(flagged_path, 'r', encoding='utf-8') as f:
        flagged_list = json.load(f)
    
    print(f"   Loaded {len(resurrected_matches)} resurrected matches.")
    print(f"   Loaded {len(flagged_list)} flagged amount projects.")
    
    # 2. Index Flagged Projects by ID
    flagged_map = {str(p.get('id')): p for p in flagged_list if p.get('id')}
    print(f"   Indexed {len(flagged_map)} unique flagged projects by ID.")
    
    # 3. Find Union (Resurrected OR Flagged)
    high_priority_projects = []
    
    # Aggregators
    district_stats = defaultdict(lambda: {
        'congressman': 'Unknown',
        'district': 'Unknown',
        'province': 'Unknown',
        'project_count': 0,
        'total_amount': 0.0,
        'projects': []
    })
    
    # Create a unified set of all Project IDs
    resurrected_map = {str(m.get('year_2026', {}).get('id')): m for m in resurrected_matches if m.get('year_2026', {}).get('id')}
    all_pids = set(flagged_map.keys()) | set(resurrected_map.keys())
    
    print(f"   Processing {len(all_pids)} unique projects (Union)...")

    # --- Load District/Congressman Mapping (Source of Truth) ---
    districts_file = os.path.join(DATA_DIR, "districts.json")
    congressman_lookup = {}
    municipality_lookup = {}  # municipality -> (province, district, congressman)
    city_lookup = {}  # city_name -> congressman
    
    if os.path.exists(districts_file):
        try:
            with open(districts_file, "r") as f:
                d_data = json.load(f)
                if 'districts' in d_data:
                    for prov_key, info in d_data['districts'].items():
                        reps = info.get('representatives', {})
                        # Map (province, district) -> representative
                        for dist_key, rep_name in reps.items():
                            if rep_name:
                                congressman_lookup[(prov_key, dist_key)] = rep_name
                        # Map municipalities/cities to representative via district
                        muni_map = info.get('municipalities', {})
                        for muni_name, dist_key in muni_map.items():
                            rep_name = reps.get(dist_key)
                            if rep_name:
                                city_lookup[muni_name.lower()] = rep_name
                                    
            print(f"✅ Loaded {len(congressman_lookup)} verified 2025/2026 District Mappings.")
            print(f"✅ Loaded {len(city_lookup)} city lookups.")
        except Exception as e:
            print(f"⚠️ Failed to load districts.json: {e}")
    
    # --- Load FULL location hierarchy from unified_locations.parquet ---
    # Each entry has: province, municipality, barangay, district, congressman
    # For matching, we'll score entries by how many components match the project text
    unified_locations_path = os.path.join(DATA_DIR, "unified_locations.parquet")
    location_entries = []  # List of (province, municipality, barangay, district, congressman)
    
    if os.path.exists(unified_locations_path):
        try:
            import unicodedata
            con = duckdb.connect()
            con.execute(f"CREATE TABLE ul AS SELECT * FROM read_parquet('{unified_locations_path}')")
            result = con.execute("SELECT province, municipality, barangay, district, congressman FROM ul WHERE congressman IS NOT NULL AND congressman != 'TBD' AND congressman != 'Unknown'").fetchall()
            for row in result:
                prov, muni, brgy, dist, cong = row
                if cong:
                    location_entries.append((prov, muni, brgy, dist, cong))
            con.close()
            print(f"✅ Loaded {len(location_entries)} location entries from unified_locations.parquet")
        except Exception as e:
            print(f"⚠️ Failed to load unified_locations.parquet: {e}")
    
    def normalize_for_match(text):
        """Normalize text for matching - lowercase, ASCII, clean.
        IMPORTANT: Keep 'city' keyword for proper disambiguation (e.g., 'cebu city' vs 'cebu province')"""
        if not text:
            return ""
        import unicodedata
        text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
        # Don't remove 'city' - we need it for disambiguation
        # Just normalize 'city of X' to 'X city' for consistency
        text = text.lower().strip()
        text = text.replace("city of ", "").replace("municipality of ", "")
        return text
    
    def find_best_location_match(project_name, project_province=None):
        """Find the location entry with the most matching components.
        Uses word-boundary matching and prefers longer/more specific matches."""
        if not project_name:
            return None

        import re
        name_norm = normalize_for_match(project_name)
        name_lower = project_name.lower()
        prov_norm = normalize_for_match(project_province) if project_province else ""

        # --- DISAMBIGUATION: Check for multi-word province names FIRST ---
        disambiguation_patterns = [
            (r'davao\s+de\s+oro', 'DAVAO DE ORO'),
            (r'davao\s+del\s+sur', 'DAVAO DEL SUR'),
            (r'davao\s+del\s+norte', 'DAVAO DEL NORTE'),
            (r'davao\s+oriental', 'DAVAO ORIENTAL'),
            (r'davao\s+occidental', 'DAVAO OCCIDENTAL'),
            (r'cebu\s+city', 'CEBU CITY'),  # Cebu City vs Cebu Province
            (r'cagayan\s+de\s+oro', 'CITY OF CAGAYAN DE ORO'),
            (r'quezon\s+city', 'QUEZON CITY'),  # QC vs Quezon Province
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
            """Check if needle appears as whole word(s) in haystack, not as substring of longer word"""
            if not needle or len(needle) < 3:
                return False
            pattern = r'\b' + re.escape(needle) + r'\b'
            return bool(re.search(pattern, haystack))

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

    def extract_barangay(text):
        """Extract a normalized barangay token if explicitly mentioned (e.g., 'Brgy. X' or 'Barangay Y')."""
        if not text:
            return None
        import re, unicodedata
        t = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII').lower()
        patterns = [
            r"brgy\.?\s+([a-z0-9][a-z0-9\s\-']{1,40})",
            r"barangay\s+([a-z0-9][a-z0-9\s\-']{1,40})",
        ]
        for pat in patterns:
            m = re.search(pat, t)
            if m:
                candidate = m.group(1).strip()
                candidate = re.split(r'[;,|]', candidate)[0].strip()
                return candidate if candidate else None
        return None

    for pid in all_pids:
        # Get data from both sources if available
        res_match = resurrected_map.get(pid)
        flagged_item = flagged_map.get(pid)
        
        # Base Data (Prefer Resurrected 2026 info, fall back to Flagged)
        if res_match:
            item_2026 = res_match.get('year_2026', {})
            name = item_2026.get('name')
            amount = item_2026.get('amount', 0)
            district = item_2026.get('district')
            congressman = item_2026.get('congressman')
            province = item_2026.get('province')
            historical_match = res_match.get('historical', {}).get('description')
        else:
            # Only in Flagged
            name = flagged_item.get('name')
            amount = flagged_item.get('amount', 0)
            district = flagged_item.get('district')
            congressman = flagged_item.get('congressman')
            province = flagged_item.get('province')
            historical_match = None

        # Fills from the other source if missing
        if flagged_item:
            if not district: district = flagged_item.get('district')
            if not congressman: congressman = flagged_item.get('congressman')
            if not province: province = flagged_item.get('province')
            if not name: name = flagged_item.get('name')

        # --- EXCLUSION: Skip Aggregate Projects ---
        # Exclude specific aggregate lines that are not real projects
        if name and "SUSTAINABLE INFRASTRUCTURE PROJECTS ALLEVIATING GAPS (SIPAG) - MULTI-PURPOSE BUILDINGS/FACILITIES TO SUPPORT SOCIAL SERVICES" in name:
            continue

        flag_reason = flagged_item.get('flag_reason') if flagged_item else None
        subcategory = flagged_item.get('subcategory') if flagged_item else None

        # Defaults - source data provides initial values but will be overridden by hierarchy
        district = district or "Unknown"
        congressman = congressman or "Unknown"
        province = province or "Unknown"

        # --- PRIMARY: Use hierarchical location matching to DETECT correct congressman/district ---
        # The project name contains location info (barangay, municipality, province)
        # Use the location hierarchy to find the correct district and congressman
        if name:
            best_match = find_best_location_match(name, province)
            if best_match:
                prov_match, muni_match, brgy_match, dist_match, cong_match = best_match
                # Use the hierarchy match - this is the source of truth
                congressman = cong_match
                district = dist_match
                province = prov_match

        # --- FALLBACK 1: If no hierarchy match, try congressman_lookup with province+district ---
        if congressman in ["Unknown", "TBA", "TBD"] and (province, district) in congressman_lookup:
            congressman = congressman_lookup[(province, district)]

        # --- FALLBACK 2: Try city_lookup for cities with congressmen ---
        if congressman in ["Unknown", "TBA", "TBD"] and province and province != "Unknown":
            prov_clean = province.replace("CITY OF ", "").replace("City of ", "").strip()
            if prov_clean.upper() in city_lookup:
                congressman = city_lookup[prov_clean.upper()]
                if district == "Unknown":
                    district = "Lone District"
            elif province.upper() in city_lookup:
                congressman = city_lookup[province.upper()]
                if district == "Unknown":
                    district = "Lone District"

        # --- Data Corrections ---
        # Fix Camille Villar (Las Pinas) -> Senator
        if "Las Pinas" in str(district) or "Villar, Camille" in str(congressman) or "Camille Villar" in str(congressman):
             congressman = "Senator Camille Villar"
             if district == "Unknown": district = "Las Piñas City"

        # Fix Ralph Recto -> Ryan Recto (Batangas 6th District)
        if "Ralph Recto" in str(congressman):
            congressman = "Ryan Christian Recto"

        # Normalize District Key
        if province and province != "Unknown":
            key = f"{congressman} ({district}, {province})"
        else:
            key = f"{congressman} ({district})"
        
        # Stats
        district_stats[key]['congressman'] = congressman
        district_stats[key]['district'] = district
        district_stats[key]['province'] = province
        district_stats[key]['project_count'] += 1
        district_stats[key]['total_amount'] += amount
        
        # Store project info
        # Enforce barangay alignment when explicitly mentioned to avoid mismatches across barangays
        brgy_2026 = extract_barangay(name) or extract_barangay(item_2026.get('description', '') if res_match else '')
        brgy_hist = extract_barangay(res_match.get('historical', {}).get('description', '') if res_match else '')
        if brgy_2026 or brgy_hist:
            if not (brgy_2026 and brgy_hist and brgy_2026 == brgy_hist):
                historical_match = None  # drop match if barangay is specified and doesn't align

        project_info = {
            'id': pid,
            'name': name,
            'amount': amount,
            'historical_match': historical_match,
            'flag_reason': flag_reason,
            'subcategory': subcategory
        }
        district_stats[key]['projects'].append(project_info)
        high_priority_projects.append(project_info)
            
    print(f"\n✅ Generated Matrix with {len(high_priority_projects)} High Priority Projects (Union).")
    
    # 4. Rank and Export
    ranking_list = []
    for key, stats in district_stats.items():
        ranking_list.append(stats)
        
    # Sort by Count (Desc), then Total Amount (Desc)
    ranking_list.sort(key=lambda x: (x['project_count'], x['total_amount']), reverse=True)
    
    output_data = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "total_high_priority_projects": len(high_priority_projects),
            "total_amount_involved": sum(p['total_amount'] for p in ranking_list),
            "total_districts_affected": len(ranking_list)
        },
        "ranking": ranking_list
    }
    
    output_path = Path("static/data/integrated_matrix.json")
    print(f"\n💾 Saving Integrated Matrix to {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
        
    print("✅ Matrix Generation Complete.")

if __name__ == "__main__":
    generate_integrated_matrix()

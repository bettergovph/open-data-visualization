#!/usr/bin/env python3
"""
Enrich Resurrected Projects with Contractor Data (DuckDB/Parquet Version)
Adds contractor information from multiple sources:
- DIME database (from Parquet)
- Flood projects (from Parquet)
- PhilGEPS contracts (from Parquet)
- Transparency projects (from Parquet)
- Infrawatch (microsite) projects (from Parquet)

optimized for "in-memory" operation using DuckDB and Parquet.
"""

import json
import duckdb
import pandas as pd
import re
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher

class ContractorEnricherDuckDB:
    def __init__(self):
        # In-memory DuckDB for budget lookups
        self.con = duckdb.connect(database=':memory:')
        self.parquet_data = {}
        self.contractor_cache = {}
        
        # Load all sources
        self._load_parquet_sources()
        
    def _load_parquet_sources(self):
        """Load parquet files into memory for fast searching"""
        print("📦 Loading parquet data sources into memory...")
        
        sources = {
            'flood': {
                'path': "data/parquet/flood_projects.parquet",
                'cols': ['project_description', 'contractor_name', 'contract_id', 'contract_year', 'project_year']
            },
            'philgeps': {
                'path': "data/parquet/philgeps_contracts.parquet",
                'cols': ['project_name', 'project_description', 'philgeps_award_title', 
                         'contractor_name', 'philgeps_awardee_name', 'contract_id', 
                         'philgeps_contract_no', 'philgeps_reference_id',
                         'contract_year', 'project_year']
            },
            'transparency': {
                'path': "data/parquet/transparency_projects.parquet",
                'cols': ['project_description', 'description', 'contractor_name', 
                         'contractor_name_2', 'contractor_name_3', 'contractor_name_4',
                         'contract_id', 'year']
            },
            'infrawatch': {
                'path': "data/parquet/infrawatch_projects.parquet",
                'cols': ['project_description', 'contractor_name', 'contract_id',
                         'contract_year', 'project_year']
            },
            'dime': {
                'path': "data/parquet/dime_projects.parquet",
                'cols': ['project_name', 'project_description', 'contractor_name', 'global_id', 'project_year'] 
            }
        }
        
        for name, config in sources.items():
            path = Path(config['path'])
            try:
                if path.exists():
                    print(f"   Loading {name} from {path}...")
                    # Use DuckDB to read and convert to Pandas for efficient existing python logic usage
                    # Or just use pandas read_parquet directly
                    df = pd.read_parquet(path)
                    
                    # Filter matching columns
                    available_cols = [c for c in config['cols'] if c in df.columns]
                    self.parquet_data[name] = df[available_cols].copy()
                    
                    # Ensure text columns are string
                    text_cols = [c for c in available_cols if 'name' in c or 'description' in c or 'title' in c]
                    for c in text_cols:
                         self.parquet_data[name][c] = self.parquet_data[name][c].astype(str)

                    print(f"      ✅ Loaded {len(df):,} items")
                else:
                    print(f"      ⚠️  {path} not found")
                    self.parquet_data[name] = None
            except Exception as e:
                print(f"      ❌ Error loading {name}: {e}")
                self.parquet_data[name] = None

        # Also register budget files in DuckDB for source info lookup
        print("\n   Registering budget files in DuckDB...")
        try:
            # Explicitly load only historical budget files (2020-2025) to avoid schema mismatch with 2026 AMENDMENTS
            # The 2026 file has different columns (no department_desc etc) which breaks the union
            self.con.execute("""
                CREATE OR REPLACE TABLE budget_historical AS 
                SELECT * FROM read_parquet([
                    'data/parquet/budget_2020.parquet',
                    'data/parquet/budget_2021.parquet',
                    'data/parquet/budget_2022.parquet',
                    'data/parquet/budget_2023.parquet',
                    'data/parquet/budget_2024.parquet',
                    'data/parquet/budget_2025.parquet'
                ], union_by_name=True)
            """)
            count = self.con.sql("SELECT COUNT(*) FROM budget_historical").fetchone()[0]
            print(f"      ✅ Registered {count:,} budget items in DuckDB")
        except Exception as e:
            print(f"      ❌ Error registering budget files: {e}")

    def _normalize_text(self, text: str) -> str:
        if not text or pd.isna(text) or str(text).lower() == 'nan':
            return ""
        text = str(text).lower().strip()
        text = re.sub(r'\s+', ' ', text)
        return text

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        if not text1 or not text2: return 0.0
        return SequenceMatcher(None, text1.lower().strip(), text2.lower().strip()).ratio()

    def _extract_year_from_contract_id(self, contract_id: str) -> Optional[int]:
        if not contract_id or pd.isna(contract_id): return None
        s = str(contract_id).strip()
        if len(s) >= 2 and s[:2].isdigit():
            val = int(s[:2])
            return 2000 + val if val < 50 else 1900 + val
        return None

    def _search_dataframe(self, source: str, search_text: str, year: Optional[int] = None) -> Optional[Dict]:
        """Generic search for Pandas DataFrames using keyword pre-filtering"""
        if source not in self.parquet_data or self.parquet_data[source] is None:
            return None
            
        df = self.parquet_data[source]
        search_normalized = self._normalize_text(search_text)
        if not search_normalized: return None
        
        words = search_normalized.split()
        key_words = [w for w in words if len(w) > 4]
        if len(key_words) < 2: key_words = words[:5]
        
        # Regex pattern for at least one keyword (lax filter)
        # For performance, maybe stricter? The original used this.
        # Let's try to match at least 2 keywords if possible for filtering
        pattern_words = key_words[:5]
        pattern = '|'.join([re.escape(w) for w in pattern_words])
        
        # Identify columns to search
        search_cols = []
        if source == 'flood': search_cols = ['project_description']
        elif source == 'philgeps': search_cols = ['project_name', 'project_description', 'philgeps_award_title']
        elif source == 'dime': search_cols = ['project_name', 'project_description']
        elif source == 'infrawatch': search_cols = ['project_description']
        elif source == 'transparency': search_cols = ['project_description', 'description']
        
        # Check available cols
        search_cols = [c for c in search_cols if c in df.columns]
        if not search_cols: return None
        
        # 1. Broad Filter (Vectorized regex)
        mask = pd.Series(False, index=df.index)
        for col in search_cols:
            mask |= df[col].astype(str).str.lower().str.contains(pattern, na=False, regex=True)
        
        matches = df[mask]
        
        # 2. Year Filter
        if year is not None and not matches.empty:
            year_col = 'contract_year' if 'contract_year' in matches.columns else ('project_year' if 'project_year' in matches.columns else ('year' if 'year' in matches.columns else None))
            
            keep_mask = pd.Series(False, index=matches.index)
            
            if year_col:
                vals = pd.to_numeric(matches[year_col], errors='coerce')
                keep_mask |= (vals == year)
            
            # Check contract_id implied year?
            contract_id_col = 'contract_id' if 'contract_id' in matches.columns else ('philgeps_contract_no' if 'philgeps_contract_no' in matches.columns else None)
            
            if contract_id_col:
                 # Only check if year match failed/missing
                 # Simplified: parse all
                 years_implied = matches[contract_id_col].apply(self._extract_year_from_contract_id)
                 keep_mask |= (years_implied == year)
            
            matches = matches[keep_mask]
            
        if matches.empty:
            return None
            
        # 3. Fuzzy Ranking (Top 100 max to avoid slowness)
        if len(matches) > 100:
            matches = matches.head(100)
            
        best_score = 0
        best_result = None
        
        for idx, row in matches.iterrows():
            # Find best match text in row
            row_text = ""
            for col in search_cols:
                val = str(row.get(col, ""))
                if self._calculate_similarity(search_normalized, val) > self._calculate_similarity(search_normalized, row_text):
                     row_text = val
            
            score = self._calculate_similarity(search_normalized, row_text)
            
            if score > best_score and score > 0.6: # Min threshold
                # Extract contractor
                contractor = None
                # Check specific contractor columns
                c_cols = ['contractor_name', 'contractor_name_2', 'philgeps_awardee_name']
                for c_col in c_cols:
                    if c_col in row and row[c_col] and str(row[c_col]).strip() not in ['None', 'nan', 'No Data Available', '']:
                         contractor = str(row[c_col]).strip()
                         break
                
                if contractor:
                    best_score = score
                    # Extract ID
                    cid = None
                    id_cols = ['contract_id', 'philgeps_contract_no', 'philgeps_reference_id', 'global_id']
                    for i_col in id_cols:
                         if i_col in row and row[i_col]:
                              cid = str(row[i_col])
                              break
                              
                    best_result = {
                        'contractor': contractor,
                        'contract_id': cid,
                        'similarity': score,
                        'matched_text': row_text
                    }
                    
        return best_result

    def get_contractor_for_project(self, project_name: str, project_description: str = None, year: Optional[int] = None) -> Optional[Dict]:
        cache_key = f"{project_name}|{year}".lower()
        if cache_key in self.contractor_cache:
            return self.contractor_cache[cache_key]
        
        search_text = f"{project_name} {project_description or ''}".strip()
        
        sources = ['transparency', 'infrawatch', 'philgeps', 'dime', 'flood']
        all_matches = []
        
        for source in sources:
            res = self._search_dataframe(source, search_text, year)
            if res:
                all_matches.append({'source': source, 'result': res})
        
        if not all_matches:
            self.contractor_cache[cache_key] = None
            return None
            
        # Sort by similarity
        all_matches.sort(key=lambda x: x['result']['similarity'], reverse=True)
        best = all_matches[0]['result']
        
        self.contractor_cache[cache_key] = best
        return best

    def _resolve_source_file(self, source_file: str, year: int) -> str:
        if not source_file: return ""
        # Simplified resolution logic
        name = Path(source_file).name
        # Try generic logic
        return name # Just return basename for display

    def _enrich_historical_source_info_duckdb(self, historical: Dict):
        """Lookup source row/col info from Budget Parquet files"""
        if not historical.get('id') or not historical.get('year'):
            return

        hist_id = historical['id']
        year = historical['year']
        
        # Extract numeric year
        if isinstance(year, str):
             m = re.search(r'(\d{4})', year)
             year = int(m.group(1)) if m else 0
             
        try:
             # Look for cols. `source_row` might not exist in all years?
             # But we verified export script puts them there if available.
             # We querying the unified `budget_historical` view/table.
             # We should filter by year first to be safe if IDs overlap (though IDs are usually unique UUIDs?)
             # Actually ID column is often text in Postgres.
             
             query = f"""
                 SELECT source_file, source_row, source_col, sourceline
                 FROM budget_historical
                 WHERE id = '{hist_id}'
                 LIMIT 1
             """
             res = self.con.sql(query).fetchone()
             
             if res:
                  # res is tuple: (source_file, source_row, source_col, sourceline)
                  sf, sr, sc, sl = res
                  
                  if sf: historical['source_file'] = sf
                  
                  # Logic for row
                  row_val = sl if sl is not None else (sr if sr is not None else None)
                  if row_val: historical['source_row'] = row_val
                  if sc: historical['source_col'] = sc
        except Exception as e:
             pass

    def enrich_json(self, json_path: Path):
        # 0. Load District Map (Baking Logic)
        print("   Loading District Map for enrichment...")
        districts_file = Path("static/data/districts.json")
        congressman_lookup = {}
        city_district_lookup = {}
        
        alias_map = {
            "TAGUIG": "Taguig–Pateros",
            "TAGUIG CITY": "Taguig–Pateros",
            "NCR": "Metro Manila",
            "METRO MANILA": "Metro Manila",
        }
        
        # Helper
        def get_district_key(p_name):
            if not p_name: return None
            norm = p_name.upper().strip()
            if norm in alias_map: return alias_map[norm]
            for k in d_data.get('districts', {}).keys():
                 if k.upper() == norm: return k
                 if k.upper() == norm + " CITY": return k
                 if k.upper().replace(" CITY", "") == norm: return k
            return None

        if districts_file.exists():
            try:
                with open(districts_file, "r") as f:
                    d_data = json.load(f)
                    if 'districts' in d_data:
                        for prov_key, info in d_data['districts'].items():
                            # Load Reps
                            if 'representatives' in info and isinstance(info['representatives'], dict):
                                for dist_name, rep_raw in info['representatives'].items():
                                    lower_raw = rep_raw.lower()
                                    if "present" in lower_raw or "2025" in lower_raw or "2026" in lower_raw:
                                        rep_clean = rep_raw.split('(')[0].strip()
                                        congressman_lookup[(prov_key, dist_name)] = rep_clean
                                        # Also handle "District 1" vs "1st District" normalization?
                                        # My baking logic handles 1st->District 1 if needed?
                                        # Actually districts.json uses "1st District". Project uses "Lone District" or "District 1".
                                        # We normalize project side.
                            
                            # Load Municipalities defaults
                            for city, default_dist in info.get('municipalities', {}).items():
                                 city_district_lookup[(prov_key, city.upper())] = default_dist
                                 
                print(f"   ✅ Loaded {len(congressman_lookup)} Verified District Mappings.")
            except Exception as e:
                print(f"   ⚠️ Failed to load districts.json: {e}")
                d_data = {} # Safety

        # 1. Load Data
        print(f"\n📊 Enriching {json_path}...")
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"❌ Failed to load source file: {e}")
            return
            
        matches = data.get('matches', [])
        print(f"   Processing {len(matches)} matches...")
        
        stats = defaultdict(int)
        
        # Pre-group
        by_project = defaultdict(list)
        for m in matches:
             if m.get('year_2026', {}).get('id'):
                  by_project[m['year_2026']['id']].append(m)
                  
        processed = 0
        total_groups = len(by_project)
        print(f"   Processing {total_groups} unique projects...")
        
        for pid, group in by_project.items():
            # A. ENRICH CONGRESSMAN
            first_m = group[0]
            y26 = first_m.get('year_2026', {})
            
            prov = y26.get('province', '').strip()
            city = y26.get('city', '').strip()
            dist = y26.get('district', '').strip()
            
            final_rep = None
            target_key = get_district_key(prov)
            
            # Special NCR handling
            if (not target_key or target_key == "Metro Manila") and city:
                 city_key = get_district_key(city)
                 if city_key: target_key = city_key
            
            # 1. Exact Match via District
            if target_key and dist:
                 # Normalize dist: "District 1" -> "1st District", "Lone" -> "Lone District"
                 d_norm = dist.title() 
                 if d_norm == "District 1": d_norm = "1st District"
                 elif d_norm == "District 2": d_norm = "2nd District"
                 elif d_norm == "District 3": d_norm = "3rd District"
                 elif d_norm == "District 4": d_norm = "4th District"
                 elif "Lone" in d_norm: d_norm = "Lone District"
                 
                 if (target_key, d_norm) in congressman_lookup:
                      final_rep = congressman_lookup[(target_key, d_norm)]
            
            # 2. City Lookup Fallback
            if not final_rep and target_key and city:
                 # Try finding default district for this city
                 # e.g. Taguig City -> 2nd District
                 def_dist = city_district_lookup.get((target_key, city.upper()))
                 if def_dist and (target_key, def_dist) in congressman_lookup:
                      final_rep = congressman_lookup[(target_key, def_dist)]
            
            # 3. Hardcoded Taguig/Hagonoy Fix
            if not final_rep and "TAGUIG" in prov.upper() and ("HAGONOY" in str(y26).upper() or "HAGONOY" in str(first_m.get('match_context','')).upper()):
                 # Force Taguig Rep.
                 # Usually Taguig-Pateros 2nd District?
                 # Or just use ANY rep from Taguig if desperate?
                 # Let's use the one mapped to 'Taguig City' which is 2nd District.
                 # If target_key is Taguig-Pateros, and we have 2nd District rep.
                 if target_key and (target_key, "2nd District") in congressman_lookup:
                       final_rep = congressman_lookup[(target_key, "2nd District")]

            if final_rep:
                 for m in group:
                      m['year_2026']['congressman'] = final_rep
                 stats['congressman_baked'] += 1
            else:
                 stats['failures'] += 1

            # B. CONTRACTORS
            for m in group:
                  hist = m.get('historical', {})
                  if not hist: continue
                  
                  # self._enrich_historical_source_info_duckdb(hist)
                  
                  desc = hist.get('description', '')
                  yr = hist.get('year')
                  if isinstance(yr, str):
                       match_yr = re.search(r'(\d{4})', yr)
                       yr_int = int(match_yr.group(1)) if match_yr else None
                  else:
                       yr_int = int(yr) if yr else None
                       
                  res = self.get_contractor_for_project(desc, desc, yr_int)
                  
                  if res and res.get('contractor'):
                       hist['contractor'] = res['contractor']
                       if res.get('contract_id'): hist['contract_id'] = res['contract_id']
                       stats['enriched'] += 1
                  else:
                       stats['not_found'] += 1
                       
            processed += 1
            if processed % 500 == 0:
                  print(f"      Processed {processed}/{total_groups} projects... (Enriched: {stats['enriched']}, Baked: {stats['congressman_baked']})")
                  
        data['metadata']['enrichment_info'] = {
             "enriched_at": datetime.now().isoformat(),
             "source": str(json_path),
             "stats": dict(stats)
        }
        
        out_path = Path("static/data/resurrected_projects_dpwh_enriched.json")
        with open(out_path, 'w', encoding='utf-8') as f:
             json.dump(data, f, indent=2, ensure_ascii=False)
             
        print(f"\n✅ Done. Saved to {out_path}")
        print(f"   Stats: {dict(stats)}")

if __name__ == "__main__":
    enricher = ContractorEnricherDuckDB()
    enricher.enrich_json(Path("static/data/resurrected_projects_dpwh.json"))

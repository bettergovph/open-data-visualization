
import duckdb
import pandas as pd
from pathlib import Path
from collections import defaultdict

class LocationEnricher:
    def __init__(self, db_path="static/data/unified_locations.parquet"):
        self.db_path = Path(db_path)
        self.lookup = None
        self.loaded = False

    def load_db(self):
        """Load unified location database for enrichment"""
        print(f"Loading Unified Location Database from {self.db_path}...")
        if not self.db_path.exists():
            print(f"⚠️  Unified Location DB not found at {self.db_path}. Skipping enrichment.")
            return False
            
        con = duckdb.connect(database=':memory:')
        con.execute(f"CREATE OR REPLACE TABLE unified_locations AS SELECT * FROM read_parquet('{self.db_path}')")
        
        # Build optimized lookups
        df = con.execute("SELECT region, province, municipality, district, congressman FROM unified_locations").fetch_df()
        con.close()
        
        # 1. Multi-level Lookup: Region -> Province -> Municipality -> Info
        self.lookup = defaultdict(lambda: defaultdict(dict))
        
        # 2. Unique Municipality Lookup: Municipality -> Info (if unique across PH)
        muni_counts = defaultdict(set) # Muni -> Set of Provinces
        muni_info_map = {} # Muni -> {prov, district, cong}
        
        for _, row in df.iterrows():
            prov = str(row['province']).upper().strip()
            mun = str(row['municipality']).upper().strip()
            
            # Normalize Municipality for Lookup (remove CITY OF / CITY)
            def norm(name):
                return name.replace("CITY OF ", "").replace(" CITY", "").strip()

            mun_norm = norm(mun)
            
            data = {
                'province': prov,
                'municipality': mun,
                'district': row['district'],
                'congressman': row['congressman']
            }
            
            # Populate Hierarchy Lookup
            self.lookup[prov][mun] = data
            self.lookup[prov][mun_norm] = data
            
            # Populate Unique Muni Tracker
            muni_counts[mun].add(prov)
            muni_counts[mun_norm].add(prov)
            
            # Store info candidates
            if mun not in muni_info_map: muni_info_map[mun] = data
            if mun_norm not in muni_info_map: muni_info_map[mun_norm] = data
            
        # Finalize Unique Lookup
        self.unique_lookup = {}
        for m, provinces in muni_counts.items():
            if len(provinces) == 1:
                self.unique_lookup[m] = muni_info_map[m]
                
        print(f"✅ Location DB loaded. Indexed {len(df)} locations.")
        print(f"✅ Found {len(self.unique_lookup)} unique municipalities/cities.")
        self.loaded = True
        return True

    def enrich_project(self, project):
        """Enrich a single project with District/Congressman info"""
        if not self.loaded: return project
        
        # Extract text to search
        text = (str(project.get('name', '')) + " " + 
                str(project.get('description', '')) + " " + 
                str(project.get('location', ''))).upper()
        
        # Helper to normalize for matching
        def normalize_search_text(t):
            return t.replace("CITY OF ", "").replace(" CITY", "")
            
        text_norm = normalize_search_text(text)
        
        found_info = None
        
        # Strategy 1: Find Province first, then Municipality
        for prov in self.lookup.keys():
            if prov in text:
                for mun_key, info in self.lookup[prov].items():
                    if len(mun_key) < 4: continue
                    if mun_key in text or mun_key in text_norm:
                        found_info = info
                        break
                if found_info: break
                
        # Strategy 2: If no province found, checking strictly Unique Municipalities
        if not found_info:
            import re
            for mun_key, info in self.unique_lookup.items():
                if len(mun_key) < 4: continue
                # Exact word boundary match
                pattern = r'\b' + re.escape(mun_key) + r'\b'
                if re.search(pattern, text_norm):
                    found_info = info
                    break
        
        if found_info:
            project['province'] = found_info['province']
            project['municipality'] = found_info['municipality']
            project['district'] = found_info.get('district', 'Unknown')
            project['congressman'] = found_info.get('congressman', 'Unknown')
        
        return project

    def enrich_list(self, projects):
        """Enrich a list of projects in-place"""
        if not self.loaded: 
            if not self.load_db():
                return projects
        
        enriched_count = 0
        for p in projects:
            old_cong = p.get('congressman')
            self.enrich_project(p)
            if p.get('congressman') and p.get('congressman') != 'Unknown' and p.get('congressman') != old_cong:
                enriched_count += 1
                
        print(f"Enriched {enriched_count} projects with location info.")
        return projects

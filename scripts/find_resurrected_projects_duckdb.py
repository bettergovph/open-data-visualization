#!/usr/bin/env python3
"""
Find Resurrected Projects (DuckDB Version)
Identifies projects in 2026 that also existed in 2025 or earlier years.

This version uses DuckDB to load data from Parquet files into memory, 
minimizing disk I/O and creating a unified historical dataset.

It then applies the same detailed matching logic (revised_name priority, chainage, etc.)
as the refined Python script.
"""

import duckdb
import json
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from difflib import SequenceMatcher
from typing import List, Dict, Any, Tuple

# Re-use the logic class structure but adapted for DuckDB input
class ResurrectedProjectFinderDuckDB:
    def __init__(self):
        # In-memory DuckDB connection
        self.con = duckdb.connect(database=':memory:')
        
    def normalize_name(self, name: str) -> str:
        """Normalize project name for strict comparison"""
        if not name or not isinstance(name, str):
            return ""
        
        name = name.upper()
        
        name = re.sub(r'\bGOP\b', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\bLOAN\s+PROCEEDS\b', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\bLOAN\s+PROCEED\b', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\bPROCEEDS\b', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\bLOAN\b', '', name, flags=re.IGNORECASE)
        
        name = re.sub(r'^(CONSTRUCTION OF|CONCRETING OF|REPAIR/|REHABILITATION AND|REHABILITATION OF)\s+', '', name)
        name = re.sub(r'\s+(FMR|PHASE\s+[IVXLCDM]+|PHASE\s+\d+)$', '', name)
        
        name = ' '.join(name.split())
        
        stop_words = {'THE', 'OF', 'AND', 'IN', 'TO', 'FOR', 'A', 'AN'}
        words = [w for w in name.split() if w not in stop_words and len(w) > 2]
        name = ' '.join(words)
        
        return name.strip()

    def is_generic_name(self, name: str) -> bool:
        """Check if name is too generic"""
        if not name:
            return True
        
        name_upper = name.upper().strip()
        name_clean = re.sub(r'^[a-z0-9]+\.\s*', '', name_upper, flags=re.IGNORECASE)
        
        generic_patterns = [
            r'^NATIONAL CAPITAL REGION$',
            r'^REGION\s+\d+$',
            r'^[A-Z]\s*\.\s*NATIONAL CAPITAL REGION$',
            r'^\d+\s*\.\s*NATIONAL CAPITAL REGION$',
            r'^[A-Z]\s*\.\s*REGION',
            r'^\d+\s*\.\s*REGION',
        ]
        
        for pattern in generic_patterns:
            if re.match(pattern, name_clean):
                return True
        
        words = name_clean.split()
        if len(words) <= 2:
            return True
            
        return False

    def extract_chainage_range(self, name: str) -> tuple:
        """Extract chainage range from project name"""
        if not isinstance(name, str):
            return None
            
        # Pattern 1: K format
        pattern_k = r'K(\d+)\s*\+\s*\(?(-?\d+)\)?\s*-\s*K(\d+)\s*\+\s*\(?(-?\d+)\)?'
        match = re.search(pattern_k, name, re.IGNORECASE)
        if match:
            return (int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4)))
        
        # Pattern 2: Chainage format
        pattern_chainage = r'Chainage\s+(\d+)\s*-\s*Chainage\s+(\d+)'
        match = re.search(pattern_chainage, name, re.IGNORECASE)
        if match:
            start_total = int(match.group(1))
            end_total = int(match.group(2))
            return (start_total // 1000, start_total % 1000, end_total // 1000, end_total % 1000)
        
        return None

    def chainage_ranges_overlap(self, range1: tuple, range2: tuple) -> bool:
        if not range1 or not range2:
            return False
        
        def to_meters(km, m):
            return km * 1000 + m
        
        start1 = to_meters(range1[0], range1[1])
        end1 = to_meters(range1[2], range1[3])
        start2 = to_meters(range2[0], range2[1])
        end2 = to_meters(range2[2], range2[3])
        
        if start1 > end1: start1, end1 = end1, start1
        if start2 > end2: start2, end2 = end2, start2
        
        return start1 < end2 and start2 < end1

    def _extract_year_for_calculation(self, year_value):
        if isinstance(year_value, (int, float)):
            return int(year_value)
        elif isinstance(year_value, str):
            year_match = re.search(r'(\d{4})', str(year_value))
            if year_match:
                return int(year_match.group(1))
        return 0

    def load_data_duckdb(self, source_filter: str = "Annex A-5"):
        """
        Load data from Parquet files using DuckDB.
        """
        print(f"\n{'='*100}")
        print(f" PHASE 1: LOADING DATA WITH DUCKDB")
        print(f"{'='*100}")
        
        # 1. Load 2026 Amendments
        print("🦆 Loading 2026 data form Parquet...")
        self.con.execute(f"""
            CREATE OR REPLACE TABLE budget_2026 AS 
            SELECT * FROM read_parquet('data/parquet/budget_2026_amendments.parquet')
            WHERE source_sheet = '{source_filter}'
        """)
        
        count_2026 = self.con.execute("SELECT COUNT(*) FROM budget_2026").fetchone()[0]
        print(f"   Loaded {count_2026} items for 2026 ({source_filter})")
        
        # 2. Load Historical Data (2020-2025)
        print("\n🦆 Loading Historical Data (2020-2025) from Parquet...")
        
        dept_filter = "DEPARTMENT OF PUBLIC WORKS AND HIGHWAYS" if source_filter == "Annex A-5" else ""
        
        self.con.execute(f"""
            CREATE OR REPLACE TABLE historical AS
            SELECT 
                * REPLACE (amount * 1000 AS amount)
            FROM read_parquet([
                'data/parquet/budget_2025.parquet',
                'data/parquet/budget_2024.parquet',
                'data/parquet/budget_2023.parquet',
                'data/parquet/budget_2022.parquet',
                'data/parquet/budget_2021.parquet',
                'data/parquet/budget_2020.parquet'
            ], union_by_name=True)
            WHERE 
                (amount * 1000) > 0 
                AND upper(department_desc) LIKE '%{dept_filter}%'
        """)
        
        count_hist = self.con.execute("SELECT COUNT(*) FROM historical").fetchone()[0]
        print(f"   Loaded {count_hist} historical items")
        
        # Materialize to Python objects for processing
        # We fetch as dictionary to match the previous structure
        print("\n📥 Materializing data to Python objects...")
        
        # 2026 Data
        year_2026_items = self.con.execute("SELECT * FROM budget_2026").fetch_df().to_dict('records')
        
        # Historical Data
        historical_data = self.con.execute("SELECT * FROM historical").fetch_df().to_dict('records')
        
        print(f"   ✅ Materialized {len(year_2026_items)} 2026 items and {len(historical_data)} historical items")
        
        return year_2026_items, historical_data

    def process_data(self, year_2026_items, historical_data, name_similarity_threshold=0.95, min_amount=100000):
        """
        Phase 2: Process data in memory with INCREMENTAL SAVING.
        """
        print(f"\n{'='*100}")
        print(f" PHASE 2: IN-MEMORY PROCESSING (INCREMENTAL)")
        print(f"{'='*100}")
        
        # Check for existing progress to resume
        progress_file = Path("static/data/resurrected_progress.jsonl")
        processed_ids = set()
        existing_matches = []
        
        if progress_file.exists():
            print(f"   🔄 Found progress file, loading processed items...")
            try:
                with open(progress_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if not line.strip(): continue
                        record = json.loads(line)
                        if 'processed_id' in record:
                            processed_ids.add(record['processed_id'])
                        elif 'match' in record:
                            existing_matches.append(record['match'])
                print(f"   resume: Skipped {len(processed_ids)} already processed items.")
                print(f"   resume: Loaded {len(existing_matches)} existing matches.")
            except Exception as e:
                print(f"   ⚠️  Error loading progress file: {e}. Starting fresh.")
                processed_ids = set()
                existing_matches = []

        print(f"   Name similarity threshold: {name_similarity_threshold:.0%} (strict)")
        print(f"   Minimum amount: ₱{min_amount:,.0f}")
        
        # Pre-normalize historical names and create word index
        print(f"\n   Pre-normalizing historical names and creating index...")
        normalized_historical = []
        word_index = defaultdict(list)
        
        for idx, item in enumerate(historical_data):
            amount = abs(item['amount'])
            if amount < min_amount:
                continue
            name = item.get('description', '')
            normalized_name = self.normalize_name(name)
            
            if not normalized_name:
                continue
            
            normalized_historical.append({
                'item': item,
                'normalized_name': normalized_name,
                'original_name': name,
                'amount': amount
            })
            
            words = set([w for w in normalized_name.split() if len(w) > 3])
            for word in words:
                word_index[word].append(idx)
        
        print(f"   Pre-normalized {len(normalized_historical)} historical items above minimum amount")
        print(f"   Created word index with {len(word_index)} unique words")
        
        # Compare each 2026 item with historical items
        matches = list(existing_matches) # Start with existing
        total_comparisons = 0
        processed = len(processed_ids)
        items_to_process = [item for item in year_2026_items if str(item.get('id')) not in processed_ids]
        
        print(f"\n   Starting matching process for {len(items_to_process)} remaining items...")
        
        # Open progress file in append mode
        with open(progress_file, 'a', encoding='utf-8') as progress_f:
            for item_2026 in items_to_process:
                item_id = str(item_2026.get('id'))
                amount_2026 = abs(item_2026.get('amount', 0)) 
                
                # Default: processed record (will be written at end of loop)
                processed_record = {'processed_id': item_id}
                
                if amount_2026 >= min_amount:
                    # Revised Name Logic
                    revised_name = (item_2026.get('revised_name') or '').strip()
                    name_2026 = revised_name or item_2026.get('name', '') or item_2026.get('description', '')
                    using_revised = bool(revised_name)
                    
                    if not self.is_generic_name(name_2026):
                        normalized_name_2026 = self.normalize_name(name_2026)
                        if normalized_name_2026:
                            chainage_2026 = self.extract_chainage_range(name_2026)
                            words_2026 = set([w for w in normalized_name_2026.split() if len(w) > 3])
                            
                            candidate_indices = set()
                            for word in words_2026:
                                if word in word_index:
                                    candidate_indices.update(word_index[word])
                            
                            item_matches = []
                            
                            for idx in candidate_indices:
                                if idx >= len(normalized_historical): continue
                                norm_historical = normalized_historical[idx]
                                
                                if self.is_generic_name(norm_historical['original_name']): continue
                                
                                total_comparisons += 1
                                name_sim = SequenceMatcher(None, normalized_name_2026, norm_historical['normalized_name']).ratio()
                                
                                if name_sim < name_similarity_threshold: continue
                                
                                chainage_penalty = 0.0
                                if chainage_2026:
                                    chainage_historical = self.extract_chainage_range(norm_historical['original_name'])
                                    if chainage_historical:
                                        if not self.chainage_ranges_overlap(chainage_2026, chainage_historical):
                                            if name_sim < 0.98: continue
                                            else: chainage_penalty = 0.20
                                    else:
                                        if name_sim < 0.90: continue
                                        chainage_penalty = 0.15
                                
                                item_historical = norm_historical['item']
                                historical_year = self._extract_year_for_calculation(item_historical.get('year', 2025)) or 2025
                                years_old = 2026 - historical_year
                                time_penalty = min(0.50, years_old * 0.10)
                                
                                adjusted_sim = name_sim * (1.0 - chainage_penalty) * (1.0 - time_penalty)
                                
                                item_matches.append({
                                    'historical': norm_historical,
                                    'name_sim': name_sim,
                                    'adjusted_sim': adjusted_sim,
                                    'time_penalty': time_penalty,
                                    'chainage_penalty': chainage_penalty,
                                    'historical_year': historical_year
                                })
                            
                            item_matches.sort(key=lambda x: x['adjusted_sim'], reverse=True)
                            
                            matches_by_year = {}
                            for match in item_matches:
                                year = match['historical_year']
                                if year not in matches_by_year or match['adjusted_sim'] > matches_by_year[year]['adjusted_sim']:
                                    matches_by_year[year] = match
                            
                            # Construct Match Object
                            for match in matches_by_year.values():
                                item_historical = match['historical']['item']
                                
                                new_match = {
                                    'source_sheet': "Annex A-5",
                                    'year_2026': {
                                        'id': item_2026.get('id'),
                                        'name': item_2026.get('name', ''),
                                        'revised_name': item_2026.get('revised_name'),
                                        'matched_using': 'revised_name' if using_revised else 'name',
                                        'description': item_2026.get('description', ''),
                                        'amount': amount_2026,
                                        'region': None,
                                        'contractor': item_2026.get('contractor')
                                    },
                                    'historical': {
                                        'id': item_historical['id'],
                                        'description': item_historical['description'],
                                        'amount': item_historical['amount'],
                                        'year': item_historical['year'],
                                        'region_id': item_historical['region_id'],
                                        'department_desc': item_historical['department_desc'],
                                        'agency_desc': item_historical['agency_desc'],
                                        'source_file': item_historical['source_file'],
                                    },
                                    'similarity': {
                                        'name': match['name_sim'],
                                        'adjusted': match['adjusted_sim'],
                                        'time_penalty': match['time_penalty'],
                                        'chainage_penalty': match['chainage_penalty']
                                    },
                                    'years_apart': self._extract_year_for_calculation(item_historical['year'])
                                }
                                matches.append(new_match)
                                # Write MATCH to progress file
                                progress_f.write(json.dumps({'match': new_match}) + "\n")
                                
                # Mark as processed in progress file (flush periodically?)
                progress_f.write(json.dumps(processed_record) + "\n")
                if processed % 50 == 0:
                    progress_f.flush()
                
                processed += 1
                if processed % 500 == 0:
                    print(f"   Processed {processed}/{len(year_2026_items)} items...")
        
        print(f"\n   Compared {total_comparisons:,} pairs")
        print(f"   Found {len(matches)} resurrected projects")
        return matches

    def save_results(self, matches):
        print(f"\n{'='*100}")
        print(f" PHASE 3: SAVING RESULTS")
        print(f"{'='*100}")
        
        output_path = Path("static/data/resurrected_projects_dpwh_revised.json")
        output_data = {
            "metadata": {
                "total_matches": len(matches),
                "source_filter": "Annex A-5 (DPWH)",
                "generated_at": datetime.now().isoformat(),
                "status": "completed (duckdb + incremental)",
                "description": "Resurrected projects matched using revised_name (DuckDB + Parquet)"
            },
            "matches": matches
        }
        
        print(f"💾 Writing to {output_path}...")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"✅ Results saved successfully.")
        
        # Cleanup progress file
        progress_file = Path("static/data/resurrected_progress.jsonl")
        if progress_file.exists():
             progress_file.unlink()
             print("   Deleted temporary progress file.")

if __name__ == "__main__":
    print("=" * 100)
    print(" RESURRECTED PROJECTS DETECTION - DUCKDB VERSION")
    print(" Powered by DuckDB + Parquet")
    print("=" * 100)
    
    finder = ResurrectedProjectFinderDuckDB()
    
    # 1. Load
    year_2026, historical = finder.load_data_duckdb(source_filter="Annex A-5")
    
    # 2. Process
    matches = finder.process_data(
        year_2026, 
        historical,
        name_similarity_threshold=0.92,
        min_amount=100000
    )
    
    # 3. Save
    finder.save_results(matches)
    
    print("\n✅ DONE.")

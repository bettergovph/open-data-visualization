#!/usr/bin/env python3
"""
Find Resurrected Projects (Revised Names Version)
Identifies projects in 2026 that also existed in 2025 or earlier years.

This version uses `revised_name` field for matching, falling back to `name` if revised_name is blank.
This allows comparing how the matching differs when using revised (cleaned) names.

The output is saved to resurrected_projects_dpwh_revised.json for the #resu2 tab.

Usage:
    python3 scripts/find_resurrected_projects_revised.py
"""

import json
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import errors as psycopg2_errors
from pathlib import Path
from typing import Dict, List, Any
from difflib import SequenceMatcher
from collections import defaultdict
import re
from datetime import datetime


class ResurrectedProjectFinderRevised:
    def __init__(self):
        self.db_config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'budget_analysis',
            'user': 'budget_admin',
            'password': 'wuQ5gBYCKkZiOGb61chLcByMu'
        }
        self.year_2026_data = {}
        self.year_2025_data = []
        self.year_2024_data = []
        self.year_2023_data = []
        self.matches = []
        
    def extract_chainage_range(self, name: str) -> tuple:
        """Extract chainage range from project name
        Supports two formats:
        1. Kxxxx + aaa - Kyyyy + bbb (e.g., K0001 + 001 - K0002 + 999)
        2. Chainage XXXX - Chainage YYYY (e.g., Chainage 3500 - Chainage 7000)
        Handles both positive and negative meters: K0001 + (-927) or K0001 + 927
        Returns: (start_km, start_m, end_km, end_m) or None if not found
        For Chainage format, treats the number as total meters (km*1000 + m)
        """
        # Pattern 1: K format
        pattern_k = r'K(\d+)\s*\+\s*\(?(-?\d+)\)?\s*-\s*K(\d+)\s*\+\s*\(?(-?\d+)\)?'
        match = re.search(pattern_k, name, re.IGNORECASE)
        if match:
            start_km = int(match.group(1))
            start_m = int(match.group(2))
            end_km = int(match.group(3))
            end_m = int(match.group(4))
            return (start_km, start_m, end_km, end_m)
        
        # Pattern 2: Chainage format
        pattern_chainage = r'Chainage\s+(\d+)\s*-\s*Chainage\s+(\d+)'
        match = re.search(pattern_chainage, name, re.IGNORECASE)
        if match:
            start_total = int(match.group(1))
            end_total = int(match.group(2))
            start_km = start_total // 1000
            start_m = start_total % 1000
            end_km = end_total // 1000
            end_m = end_total % 1000
            return (start_km, start_m, end_km, end_m)
        
        return None
    
    def chainage_ranges_overlap(self, range1: tuple, range2: tuple) -> bool:
        """Check if two chainage ranges overlap"""
        if not range1 or not range2:
            return False
        
        def to_meters(km, m):
            return km * 1000 + m
        
        start1 = to_meters(range1[0], range1[1])
        end1 = to_meters(range1[2], range1[3])
        start2 = to_meters(range2[0], range2[1])
        end2 = to_meters(range2[2], range2[3])
        
        if start1 > end1:
            start1, end1 = end1, start1
        if start2 > end2:
            start2, end2 = end2, start2
        
        overlaps = start1 < end2 and start2 < end1
        return overlaps
    
    def is_generic_name(self, name: str) -> bool:
        """Check if name is too generic (like headers or categories)"""
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
        
        if name_clean in ['NATIONAL CAPITAL REGION', 'NCR']:
            return True
        
        return False
    
    def normalize_name(self, name: str) -> str:
        """Normalize project name for strict comparison"""
        if not name:
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
    
    def similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between two names"""
        norm1 = self.normalize_name(name1)
        norm2 = self.normalize_name(name2)
        
        if not norm1 or not norm2:
            return 0.0
        
        return SequenceMatcher(None, norm1, norm2).ratio()
    
    def load_2026_data(self, source_filter: str):
        """Load 2026 data from JSON file"""
        json_path = Path("static/data/budget_amendments_2026.json")
        
        if not json_path.exists():
            raise FileNotFoundError(f"JSON file not found: {json_path}")
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        all_items = data.get('line_items', []) + data.get('projects', [])
        line_items = [
            item for item in all_items
            if item.get('source_sheet') == source_filter
        ]
        
        return line_items
    
    def _extract_year_for_calculation(self, year_value):
        """Extract numeric year from year value"""
        if isinstance(year_value, (int, float)):
            return int(year_value)
        elif isinstance(year_value, str):
            year_match = re.search(r'(\d{4})', str(year_value))
            if year_match:
                return int(year_match.group(1))
        return 0
    
    def load_historical_data(self, year: int, source_filter: str = None, amounts_in_thousands: bool = True):
        """Load historical budget data from PostgreSQL database"""
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = %s
        """, (f'budget_{year}',))
        
        available_columns = {row['column_name'] for row in cursor.fetchall()}
        
        required_columns = {'id', 'amt', 'dsc', 'uacs_dpt_dsc', 'uacs_reg_id', 'uacs_agy_dsc', 'year', 'source_file'}
        
        missing_columns = required_columns - available_columns
        if missing_columns:
            print(f"   ⚠️  Table budget_{year} missing required columns: {missing_columns}")
            cursor.close()
            conn.close()
            return []
        
        if source_filter == "Annex A-1":
            dept_filter = "DEPARTMENT OF BUDGET AND MANAGEMENT"
        elif source_filter == "Annex A-4":
            dept_filter = "DEPARTMENT OF AGRICULTURE"
        elif source_filter == "Annex A-5":
            dept_filter = "DEPARTMENT OF PUBLIC WORKS AND HIGHWAYS"
        else:
            dept_filter = None
        
        if dept_filter:
            query = f"""
                SELECT 
                    id,
                    amt,
                    dsc,
                    uacs_dpt_dsc,
                    uacs_reg_id,
                    uacs_agy_dsc,
                    year,
                    source_file
                FROM budget_{year}
                WHERE upper(uacs_dpt_dsc) LIKE %s
                AND amt > 0
            """
            cursor.execute(query, (f'%{dept_filter}%',))
        else:
            query = f"""
                SELECT 
                    id,
                    amt,
                    dsc,
                    uacs_dpt_dsc,
                    uacs_reg_id,
                    uacs_agy_dsc,
                    year,
                    source_file
                FROM budget_{year}
                WHERE amt > 0
            """
            cursor.execute(query)
        
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        amount_multiplier = 1000 if amounts_in_thousands else 1
        
        data = []
        for row in rows:
            data.append({
                'id': row['id'],
                'amount': float(row['amt']) * amount_multiplier,
                'description': row['dsc'] or '',
                'department_desc': row['uacs_dpt_dsc'] or '',
                'region_id': row['uacs_reg_id'],
                'agency_desc': row['uacs_agy_dsc'] or '',
                'year': row['year'] or year,
                'source_file': row['source_file'] or ''
            })
        
        return data
    
    def load_all_data(self, source_filter: str, amounts_in_thousands: bool = True):
        """
        Phase 1: Load ALL data into memory.
        Reads JSON file and queries Database.
        """
        print(f"\n{'='*100}")
        print(f" PHASE 1: LOADING DATA INTO MEMORY")
        print(f"{'='*100}")

        # 1. Load 2026 data from JSON
        print(f"\n📁 Loading 2026 data from {source_filter}...")
        year_2026_items = self.load_2026_data(source_filter)
        print(f"   Found {len(year_2026_items)} items from {source_filter}")
        
        items_with_revised = sum(1 for item in year_2026_items if item.get('revised_name'))
        print(f"   Items with revised_name: {items_with_revised}")
        print(f"   Items without revised_name (will use name): {len(year_2026_items) - items_with_revised}")

        # 2. Load historical data from DB
        historical_data = []
        years_to_check = list(range(2025, 2019, -1))
        
        print(f"\n🔌 Connecting to database...")
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            for year in years_to_check:
                print(f"   Querying {year} budget data...")
                try:
                    # Check columns first
                    cursor.execute(f"""
                        SELECT column_name 
                        FROM information_schema.columns 
                        WHERE table_name = 'budget_{year}'
                    """)
                    available_columns = {row['column_name'] for row in cursor.fetchall()}
                    
                    required_columns = {'id', 'amt', 'dsc', 'uacs_dpt_dsc', 'uacs_reg_id', 'uacs_agy_dsc', 'year', 'source_file'}
                    missing_columns = required_columns - available_columns
                    
                    if missing_columns:
                        print(f"     ⚠️  Table budget_{year} missing columns: {missing_columns}")
                        continue

                    # Build Query
                    if source_filter == "Annex A-5":
                        dept_filter = "DEPARTMENT OF PUBLIC WORKS AND HIGHWAYS"
                        query = f"""
                            SELECT id, amt, dsc, uacs_dpt_dsc, uacs_reg_id, uacs_agy_dsc, year, source_file
                            FROM budget_{year}
                            WHERE upper(uacs_dpt_dsc) LIKE %s AND amt > 0
                        """
                        cursor.execute(query, (f'%{dept_filter}%',))
                    else:
                        # Default fallback
                        query = f"""
                            SELECT id, amt, dsc, uacs_dpt_dsc, uacs_reg_id, uacs_agy_dsc, year, source_file
                            FROM budget_{year}
                            WHERE amt > 0
                        """
                        cursor.execute(query)
                    
                    rows = cursor.fetchall()
                    
                    # Process rows in memory immediately
                    amount_multiplier = 1000 if amounts_in_thousands else 1
                    for row in rows:
                        historical_data.append({
                            'id': row['id'],
                            'amount': float(row['amt']) * amount_multiplier,
                            'description': row['dsc'] or '',
                            'department_desc': row['uacs_dpt_dsc'] or '',
                            'region_id': row['uacs_reg_id'],
                            'agency_desc': row['uacs_agy_dsc'] or '',
                            'year': row['year'] or year,
                            'source_file': row['source_file'] or ''
                        })
                    
                    print(f"     Loaded {len(rows)} items from {year}")

                except psycopg2_errors.UndefinedTable:
                    print(f"     Table budget_{year} does not exist, skipping")
                    conn.rollback()
                except Exception as e:
                    print(f"     Error loading {year}: {e}")
                    conn.rollback()
            
            cursor.close()
            conn.close()
            print(f"🔌 Database connection closed.")
            
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            return [], []

        print(f"\n✅ DATA LOADING COMPLETE")
        print(f"   2026 Items: {len(year_2026_items)}")
        print(f"   Historical Items: {len(historical_data)}")
        
        return year_2026_items, historical_data

    def process_data(self, year_2026_items, historical_data, name_similarity_threshold=0.95, min_amount=100000):
        """
        Phase 2: Process data in memory.
        Performs normalization, indexing, and matching.
        """
        print(f"\n{'='*100}")
        print(f" PHASE 2: IN-MEMORY PROCESSING")
        print(f"{'='*100}")
        
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
        matches = []
        total_comparisons = 0
        processed = 0
        
        print(f"\n   Starting matching process...")
        
        for item_2026 in year_2026_items:
            amount_2026 = abs(item_2026.get('final_amount', 0) or item_2026.get('original_amount', 0))
            if amount_2026 < min_amount:
                continue
            
            # KEY CHANGE: Use revised_name if available, otherwise fall back to name
            revised_name = (item_2026.get('revised_name') or '').strip()
            name_2026 = revised_name or item_2026.get('name', '') or item_2026.get('description', '')
            
            # Track which name we're using for debugging
            using_revised = bool(revised_name)
            
            # Skip generic names
            if self.is_generic_name(name_2026):
                continue
            
            normalized_name_2026 = self.normalize_name(name_2026)
            
            if not normalized_name_2026:
                continue
            
            chainage_2026 = self.extract_chainage_range(name_2026)
            
            words_2026 = set([w for w in normalized_name_2026.split() if len(w) > 3])
            
            candidate_indices = set()
            for word in words_2026:
                if word in word_index:
                    candidate_indices.update(word_index[word])
            
            item_matches = []
            
            for idx in candidate_indices:
                if idx >= len(normalized_historical):
                    continue
                    
                norm_historical = normalized_historical[idx]
                if not norm_historical['normalized_name']:
                    continue
                
                if self.is_generic_name(norm_historical['original_name']):
                    continue
                
                total_comparisons += 1
                
                name_sim = SequenceMatcher(None, normalized_name_2026, norm_historical['normalized_name']).ratio()
                
                if name_sim < name_similarity_threshold:
                    continue
                
                chainage_penalty = 0.0
                if chainage_2026:
                    chainage_historical = self.extract_chainage_range(norm_historical['original_name'])
                    if chainage_historical:
                        if not self.chainage_ranges_overlap(chainage_2026, chainage_historical):
                            if name_sim < 0.98:
                                continue
                            else:
                                chainage_penalty = 0.20
                    else:
                        if name_sim < 0.90:
                            continue
                        chainage_penalty = 0.15
                
                item_historical = norm_historical['item']
                historical_year_raw = item_historical.get('year', 2025)
                historical_year = self._extract_year_for_calculation(historical_year_raw)
                if historical_year == 0:
                    historical_year = 2025
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
            
            contractor = (
                item_2026.get('contractor') or 
                (item_2026.get('contractors', [None])[0] if isinstance(item_2026.get('contractors'), list) else None)
            )
            
            for match in matches_by_year.values():
                item_historical = match['historical']['item']
                amount_historical = match['historical']['amount']
                
                new_match = {
                    'source_sheet': "Annex A-5", # Assuming fixed for now based on usage
                    'year_2026': {
                        'id': item_2026.get('id'),
                        'name': item_2026.get('name', ''),  # Original name
                        'revised_name': item_2026.get('revised_name'),  # Revised name
                        'matched_using': 'revised_name' if using_revised else 'name',  # Track which was used
                        'description': item_2026.get('description', ''),
                        'amount': amount_2026,
                        'region': item_2026.get('location', {}).get('region') if isinstance(item_2026.get('location'), dict) else None,
                        'source_row': item_2026.get('source_row'),
                        'source_col': item_2026.get('source_col_b') or item_2026.get('source_col_c'),
                        'contractor': contractor
                    },
                    'historical': {
                        'id': item_historical['id'],
                        'description': item_historical['description'],
                        'amount': amount_historical,
                        'year': item_historical['year'],
                        'region_id': item_historical['region_id'],
                        'department_desc': item_historical['department_desc'],
                        'agency_desc': item_historical['agency_desc'],
                        'source_file': item_historical['source_file'],
                        'contractor': None
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
            
            processed += 1
            if processed % 1000 == 0: # Reduced logging frequency
                print(f"   Processed {processed}/{len(year_2026_items)} items...")
        
        print(f"\n   Compared {total_comparisons:,} pairs")
        print(f"   Found {len(matches)} resurrected projects")
        
        return matches

    def save_results(self, matches):
        """
        Phase 3: Save results to disk.
        """
        print(f"\n{'='*100}")
        print(f" PHASE 3: SAVING RESULTS")
        print(f"{'='*100}")
        
        output_path = Path("static/data/resurrected_projects_dpwh_revised.json")
        output_data = {
            "metadata": {
                "total_matches": len(matches),
                "source_filter": "Annex A-5 (DPWH)",
                "name_similarity_threshold": 0.92,
                "min_amount": 100000,
                "search_years": list(range(2020, 2026)),
                "generated_at": datetime.now().isoformat(),
                "status": "completed",
                "description": "Resurrected projects matched using revised_name (with fallback to name)"
            },
            "matches": matches
        }
        
        print(f"💾 Writing to {output_path}...")
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"✅ Results saved successfully.")


if __name__ == "__main__":
    print("=" * 100)
    print(" RESURRECTED PROJECTS DETECTION - REVISED NAMES VERSION")
    print(" Finding DPWH projects in 2026 that existed in 2025 or earlier years")
    print(" Using revised_name field (with fallback to name if blank)")
    print(" OPTIMIZED: All operations performed in memory")
    print("=" * 100)
    
    finder = ResurrectedProjectFinderRevised()
    
    # 1. Load
    year_2026_items, historical_data = finder.load_all_data(
        source_filter="Annex A-5",
        amounts_in_thousands=True
    )
    
    if not year_2026_items or not historical_data:
        print("❌ Data loading failed or empty. Exiting.")
        exit(1)

    # 2. Process
    all_matches = finder.process_data(
        year_2026_items, 
        historical_data,
        name_similarity_threshold=0.92,
        min_amount=100000
    )
    
    # 3. Save
    finder.save_results(all_matches)
    
    # Summary
    print("\n" + "=" * 100)
    print(" SUMMARY")
    print("=" * 100)
    
    print(f"\n📊 Total Resurrected Projects: {len(all_matches)}")
    
    # Count by matched_using
    revised_matches = sum(1 for m in all_matches if m['year_2026'].get('matched_using') == 'revised_name')
    name_matches = sum(1 for m in all_matches if m['year_2026'].get('matched_using') == 'name')
    print(f"\n   Matched using revised_name: {revised_matches}")
    print(f"   Matched using name (fallback): {name_matches}")
    
    # Group by historical year
    by_year = defaultdict(list)
    for match in all_matches:
        by_year[match['historical']['year']].append(match)
    
    print(f"\n   By Historical Year:")
    for year in sorted(by_year.keys(), reverse=True):
        matches = by_year[year]
        total_amount_2026 = sum(m['year_2026']['amount'] for m in matches)
        print(f"   - {year}: {len(matches)} projects (₱{total_amount_2026:,.0f})")
    
    # Total amounts
    total_amount_2026 = sum(m['year_2026']['amount'] for m in all_matches)
    total_amount_historical = sum(m['historical']['amount'] for m in all_matches)
    
    print(f"\n   Total Amount (2026): ₱{total_amount_2026:,.0f}")
    print(f"   Total Amount (Historical): ₱{total_amount_historical:,.0f}")


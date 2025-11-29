#!/usr/bin/env python3
"""
Find Resurrected Projects
Identifies projects in 2026 that also existed in 2025 or earlier years (strict name matching).

Usage:
    python3 scripts/find_resurrected_projects.py
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


class ResurrectedProjectFinder:
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
        # Pattern 1: K format: K followed by digits, +, optional parentheses, optional minus, digits, -, K, digits, +, optional parentheses, optional minus, digits
        pattern_k = r'K(\d+)\s*\+\s*\(?(-?\d+)\)?\s*-\s*K(\d+)\s*\+\s*\(?(-?\d+)\)?'
        match = re.search(pattern_k, name, re.IGNORECASE)
        if match:
            start_km = int(match.group(1))
            start_m = int(match.group(2))  # Can be negative
            end_km = int(match.group(3))
            end_m = int(match.group(4))  # Can be negative
            return (start_km, start_m, end_km, end_m)
        
        # Pattern 2: Chainage format: Chainage followed by number, -, Chainage, number
        pattern_chainage = r'Chainage\s+(\d+)\s*-\s*Chainage\s+(\d+)'
        match = re.search(pattern_chainage, name, re.IGNORECASE)
        if match:
            start_total = int(match.group(1))
            end_total = int(match.group(2))
            # Convert total meters to (km, m) format
            start_km = start_total // 1000
            start_m = start_total % 1000
            end_km = end_total // 1000
            end_m = end_total % 1000
            return (start_km, start_m, end_km, end_m)
        
        return None
    
    def chainage_ranges_overlap(self, range1: tuple, range2: tuple) -> bool:
        """Check if two chainage ranges overlap
        Each range is (start_km, start_m, end_km, end_m)
        Ranges must be on the same kilometer section to overlap
        """
        if not range1 or not range2:
            return False
        
        # If start and end are on different kilometers, check if the ranges span overlapping kilometers
        # For example: K0001+500-K0002+500 overlaps with K0001+800-K0002+200
        
        # Convert to total meters for easier comparison (handles negative meters)
        def to_meters(km, m):
            return km * 1000 + m
        
        start1 = to_meters(range1[0], range1[1])
        end1 = to_meters(range1[2], range1[3])
        start2 = to_meters(range2[0], range2[1])
        end2 = to_meters(range2[2], range2[3])
        
        # Ensure start <= end for both ranges
        if start1 > end1:
            start1, end1 = end1, start1
        if start2 > end2:
            start2, end2 = end2, start2
        
        # Check for overlap: ranges overlap if they share any common section
        # Note: Adjacent segments (one ends exactly where the other begins) are NOT considered matches
        # as they are different projects, even if on the same road
        # For overlap: start1 < end2 and start2 < end1 (strict inequality to exclude adjacency)
        overlaps = start1 < end2 and start2 < end1
        return overlaps
    
    def is_generic_name(self, name: str) -> bool:
        """Check if name is too generic (like headers or categories)"""
        if not name:
            return True
        
        name_upper = name.upper().strip()
        
        # Remove leading numbers/letters and periods (like "a.", "1.", "7.")
        name_clean = re.sub(r'^[a-z0-9]+\.\s*', '', name_upper, flags=re.IGNORECASE)
        
        # Generic patterns that shouldn't match
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
        
        # If name is too short or only contains generic words
        words = name_clean.split()
        if len(words) <= 2:
            return True
        
        # If it's just a region name without project details
        if name_clean in ['NATIONAL CAPITAL REGION', 'NCR']:
            return True
        
        return False
    
    def normalize_name(self, name: str) -> str:
        """Normalize project name for strict comparison"""
        if not name:
            return ""
        
        # Convert to uppercase
        name = name.upper()
        
        # Remove funding source indicators
        name = re.sub(r'\bGOP\b', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\bLOAN\s+PROCEEDS\b', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\bLOAN\s+PROCEED\b', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\bPROCEEDS\b', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\bLOAN\b', '', name, flags=re.IGNORECASE)
        
        # Remove common prefixes/suffixes
        name = re.sub(r'^(CONSTRUCTION OF|CONCRETING OF|REPAIR/|REHABILITATION AND|REHABILITATION OF)\s+', '', name)
        name = re.sub(r'\s+(FMR|PHASE\s+[IVXLCDM]+|PHASE\s+\d+)$', '', name)
        
        # Remove extra whitespace
        name = ' '.join(name.split())
        
        # Remove common words that don't add meaning
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
        
        # Filter to specified source sheet
        all_items = data.get('line_items', []) + data.get('projects', [])
        line_items = [
            item for item in all_items
            if item.get('source_sheet') == source_filter
        ]
        
        return line_items
    
    def load_historical_data(self, year: int, source_filter: str = None, amounts_in_thousands: bool = True):
        """Load historical budget data from PostgreSQL database
        
        Args:
            year: Budget year
            source_filter: Source sheet filter
            amounts_in_thousands: If True, multiply amounts by 1000 (budget amounts are stored in thousands)
        """
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Determine department filter based on source
        if source_filter == "Annex A-1":
            dept_filter = "(uacs_dpt_dsc ILIKE '%AGRICULTURE%' OR dsc ILIKE '%farm%market%' OR dsc ILIKE '%FMR%')"
        elif source_filter == "Annex A-4":
            dept_filter = "(uacs_dpt_dsc ILIKE '%NIA%' OR dsc ILIKE '%NIA%' OR uacs_dpt_dsc ILIKE '%IRRIGATION%')"
        elif source_filter == "Annex A-5":
            dept_filter = "(uacs_dpt_dsc ILIKE '%PUBLIC WORKS%' OR uacs_dpt_dsc ILIKE '%DPWH%' OR dsc ILIKE '%DPWH%')"
        else:
            dept_filter = "(uacs_dpt_dsc ILIKE '%AGRICULTURE%' OR dsc ILIKE '%farm%market%' OR dsc ILIKE '%FMR%' OR uacs_dpt_dsc ILIKE '%PUBLIC WORKS%' OR uacs_dpt_dsc ILIKE '%DPWH%' OR dsc ILIKE '%DPWH%' OR uacs_dpt_dsc ILIKE '%NIA%' OR dsc ILIKE '%NIA%' OR uacs_dpt_dsc ILIKE '%IRRIGATION%')"
        
        # For amounts in thousands, minimum is 100 (which equals 100,000 in real pesos)
        min_amt = 100 if amounts_in_thousands else 100000
        
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
            WHERE year = {year}
            AND amt >= {min_amt}
            AND {dept_filter}
            ORDER BY amt DESC, dsc
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        # Convert to list of dicts
        historical_data = []
        for row in rows:
            amt = float(row['amt']) if row['amt'] else 0.0
            # Convert from thousands to real pesos if needed
            if amounts_in_thousands:
                amt = amt * 1000
            
            historical_data.append({
                'id': row['id'],
                'amount': amt,
                'description': row['dsc'] or '',
                'department_desc': row['uacs_dpt_dsc'],
                'region_id': row['uacs_reg_id'],
                'agency_desc': row['uacs_agy_dsc'],
                'year': row['year'],
                'source_file': row['source_file']
            })
        
        cursor.close()
        conn.close()
        
        return historical_data
    
    def find_resurrected_projects(self, 
                                   source_filter: str,
                                   name_similarity_threshold: float = 0.95,  # Very strict: 95%
                                   min_amount: float = 100000,
                                   max_items: int = None,  # Limit processing for large datasets
                                   amounts_in_thousands: bool = True):  # Budget amounts are in thousands
        """
        Find projects in 2026 that match projects from 2025 or earlier (strict name matching)
        
        Args:
            source_filter: Source sheet to filter (Annex A-1, A-4, or A-5)
            name_similarity_threshold: Minimum name similarity (0-1), default 0.95 (very strict)
            min_amount: Minimum amount to consider
        """
        print(f"\n{'='*100}")
        print(f" FINDING RESURRECTED PROJECTS: {source_filter}")
        print(f"{'='*100}")
        
        # Load 2026 data
        print(f"\n📁 Loading 2026 data from {source_filter}...")
        year_2026_items = self.load_2026_data(source_filter)
        print(f"   Found {len(year_2026_items)} items from {source_filter}")
        
        # Limit items if specified (for large datasets like Annex A-5)
        if max_items and len(year_2026_items) > max_items:
            print(f"   Limiting to first {max_items} items for faster processing")
            year_2026_items = year_2026_items[:max_items]
        
        # Load historical data (2025, 2024, 2023, ..., 2016) - filtered by source
        # Search all available years
        historical_data = []
        years_to_check = list(range(2025, 2015, -1))  # 2025 down to 2016
        
        for year in years_to_check:
            print(f"\n💾 Loading {year} budget data...")
            try:
                year_data = self.load_historical_data(year, source_filter, amounts_in_thousands=amounts_in_thousands)
                print(f"   Found {len(year_data)} relevant items from {year}")
                if year_data:
                    historical_data.extend(year_data)
            except psycopg2_errors.UndefinedTable as e:
                print(f"   Table budget_{year} does not exist, continuing to next year")
                continue  # Continue to next year
            except Exception as e:
                error_msg = str(e)
                if "does not exist" in error_msg.lower() or "relation" in error_msg.lower():
                    print(f"   Table budget_{year} does not exist, continuing to next year")
                    continue
                else:
                    print(f"   ⚠️  Error loading {year} data: {e}")
                    continue
        
        print(f"\n   Total historical items: {len(historical_data)}")
        print(f"   Name similarity threshold: {name_similarity_threshold:.0%} (strict)")
        print(f"   Minimum amount: ₱{min_amount:,.0f}")
        
        # Pre-normalize historical names and create word index for faster lookup
        print(f"\n   Pre-normalizing historical names and creating index...")
        normalized_historical = []
        word_index = defaultdict(list)  # Map word -> list of item indices
        
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
            
            # Index by significant words
            words = set([w for w in normalized_name.split() if len(w) > 3])
            for word in words:
                word_index[word].append(idx)
        
        print(f"   Pre-normalized {len(normalized_historical)} historical items above minimum amount")
        print(f"   Created word index with {len(word_index)} unique words")
        
        # Compare each 2026 item with historical items
        matches = []
        total_comparisons = 0
        processed = 0
        
        for item_2026 in year_2026_items:
            amount_2026 = abs(item_2026.get('final_amount', 0) or item_2026.get('original_amount', 0))
            if amount_2026 < min_amount:
                continue
            
            # Prioritize 'name' field as it has specific project names, fallback to 'description'
            name_2026 = item_2026.get('name', '') or item_2026.get('description', '')
            
            # Skip generic names (headers, categories)
            if self.is_generic_name(name_2026):
                continue
            
            normalized_name_2026 = self.normalize_name(name_2026)
            
            if not normalized_name_2026:
                continue
            
            # Extract chainage range if present
            chainage_2026 = self.extract_chainage_range(name_2026)
            
            # Extract significant words from 2026 name
            words_2026 = set([w for w in normalized_name_2026.split() if len(w) > 3])
            
            # Find candidate matches using word index
            candidate_indices = set()
            for word in words_2026:
                if word in word_index:
                    candidate_indices.update(word_index[word])
            
            # Find matches in candidate items only
            # Save ALL matches that meet the threshold, not just the best one
            # This allows us to see matches from all years
            item_matches = []  # Store all valid matches for this 2026 item
            
            for idx in candidate_indices:
                if idx >= len(normalized_historical):
                    continue
                    
                norm_historical = normalized_historical[idx]
                if not norm_historical['normalized_name']:
                    continue
                
                # Skip generic historical names
                if self.is_generic_name(norm_historical['original_name']):
                    continue
                
                total_comparisons += 1
                
                # Calculate name similarity
                name_sim = SequenceMatcher(None, normalized_name_2026, norm_historical['normalized_name']).ratio()
                
                # First check: name similarity must meet threshold BEFORE penalties
                if name_sim < name_similarity_threshold:
                    continue  # Skip if base similarity is too low
                
                # If 2026 item has chainage, check for overlap with historical
                chainage_penalty = 0.0
                if chainage_2026:
                    chainage_historical = self.extract_chainage_range(norm_historical['original_name'])
                    if chainage_historical:
                        # Both have chainage - check for overlap
                        if not self.chainage_ranges_overlap(chainage_2026, chainage_historical):
                            # Different sections - require 98%+ similarity
                            if name_sim < 0.98:
                                continue  # Skip - different chainage sections with low similarity
                            else:
                                # Even with high similarity, penalize for different sections
                                chainage_penalty = 0.20  # 20% penalty for different chainage sections
                    else:
                        # 2026 has chainage but historical doesn't - be more strict
                        # This could be a different section, so require higher similarity
                        if name_sim < 0.90:  # Require 90%+ if historical lacks chainage info
                            continue
                        chainage_penalty = 0.15  # 15% penalty for missing chainage in historical
                
                # Apply time-based penalty: 10% per year (roads require maintenance)
                item_historical = norm_historical['item']
                historical_year = item_historical.get('year', 2025)
                years_old = 2026 - historical_year
                time_penalty = min(0.50, years_old * 0.10)  # Max 50% penalty (5+ years)
                
                # Apply penalties to similarity score (for ranking/display only)
                adjusted_sim = name_sim * (1.0 - chainage_penalty) * (1.0 - time_penalty)
                
                # Save this match (name similarity already meets threshold)
                item_matches.append({
                    'historical': norm_historical,
                    'name_sim': name_sim,
                    'adjusted_sim': adjusted_sim,
                    'time_penalty': time_penalty,
                    'chainage_penalty': chainage_penalty,
                    'historical_year': historical_year
                })
            
            # Sort matches by adjusted similarity (best first) and save all that meet threshold
            # But limit to one match per historical year to avoid duplicates
            item_matches.sort(key=lambda x: x['adjusted_sim'], reverse=True)
            
            # Group by year and take best from each year
            matches_by_year = {}
            for match in item_matches:
                year = match['historical_year']
                if year not in matches_by_year or match['adjusted_sim'] > matches_by_year[year]['adjusted_sim']:
                    matches_by_year[year] = match
            
            # Save all matches (one per year)
            for match in matches_by_year.values():
                item_historical = match['historical']['item']
                amount_historical = match['historical']['amount']
                
                matches.append({
                    'source_sheet': source_filter,
                    'year_2026': {
                        'id': item_2026.get('id'),
                        'name': name_2026,
                        'description': item_2026.get('description', ''),
                        'amount': amount_2026,
                        'region': item_2026.get('location', {}).get('region') if isinstance(item_2026.get('location'), dict) else None,
                        'source_row': item_2026.get('source_row'),
                        'source_col': item_2026.get('source_col_b') or item_2026.get('source_col_c')
                    },
                    'historical': {
                        'id': item_historical['id'],
                        'description': item_historical['description'],
                        'amount': amount_historical,
                        'year': item_historical['year'],
                        'region_id': item_historical['region_id'],
                        'department_desc': item_historical['department_desc'],
                        'agency_desc': item_historical['agency_desc'],
                        'source_file': item_historical['source_file']
                    },
                    'similarity': {
                        'name': match['name_sim'],  # Original similarity
                        'adjusted': match['adjusted_sim'],  # After penalties
                        'time_penalty': match['time_penalty'],
                        'chainage_penalty': match['chainage_penalty']
                    },
                    'years_apart': 2026 - item_historical['year']
                })
            
            processed += 1
            if processed % 100 == 0:
                print(f"   Processed {processed}/{len(year_2026_items)} 2026 items, found {len(matches)} matches so far...")
                # Save intermediate results every 100 items
                if matches:
                    try:
                        output_path = Path("static/data/resurrected_projects_dpwh.json")
                        output_data = {
                            "metadata": {
                                "total_matches": len(matches),
                                "source_filter": source_filter,
                                "name_similarity_threshold": name_similarity_threshold,
                                "min_amount": min_amount,
                                "search_years": list(range(2016, 2026)),
                                "generated_at": datetime.now().isoformat(),
                                "status": "in_progress",
                                "processed_items": processed,
                                "total_items": len(year_2026_items)
                            },
                            "matches": matches
                        }
                        with open(output_path, 'w', encoding='utf-8') as f:
                            json.dump(output_data, f, indent=2, ensure_ascii=False)
                    except Exception as e:
                        print(f"   ⚠️  Could not save intermediate results: {e}")
        
        print(f"\n   Compared {total_comparisons:,} pairs")
        print(f"   Found {len(matches)} resurrected projects")
        
        return matches


if __name__ == "__main__":
    print("=" * 100)
    print(" RESURRECTED PROJECTS DETECTION - DPWH ONLY")
    print(" Finding DPWH projects in 2026 that existed in 2025 or earlier years")
    print(" Using strict name matching (92% similarity threshold)")
    print(" Processing ALL DPWH items")
    print("=" * 100)
    
    finder = ResurrectedProjectFinder()
    
    # Process only Annex A-5 (DPWH) - ALL items
    print("\n" + "="*100)
    print(" PROCESSING ANNEX A-5 (DPWH) - ALL ITEMS")
    print("="*100)
    all_matches = finder.find_resurrected_projects(
        source_filter="Annex A-5",
        name_similarity_threshold=0.92,  # 92% for stricter name matching
        min_amount=100000,
        max_items=None,  # Process ALL items (no limit)
        amounts_in_thousands=True  # Budget amounts are stored in thousands
    )
    
    # Save results to JSON
    output_path = Path("static/data/resurrected_projects_dpwh.json")
    output_data = {
        "metadata": {
            "total_matches": len(all_matches),
            "source_filter": "Annex A-5 (DPWH)",
            "name_similarity_threshold": 0.92,
            "min_amount": 100000,
            "search_years": list(range(2016, 2026)),
            "generated_at": datetime.now().isoformat(),
            "status": "completed"
        },
        "matches": all_matches
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Results saved to: {output_path}")
    
    # Print Summary
    print("\n" + "=" * 100)
    print(" SUMMARY")
    print("=" * 100)
    
    print(f"\n📊 Total Resurrected Projects: {len(all_matches)}")
    
    # Group by source
    by_source = defaultdict(list)
    for match in all_matches:
        by_source[match['source_sheet']].append(match)
    
    print(f"\n   By Source:")
    for source, matches in by_source.items():
        total_amount_2026 = sum(m['year_2026']['amount'] for m in matches)
        print(f"   - {source}: {len(matches)} projects (₱{total_amount_2026:,.0f})")
    
    # Group by historical year
    by_year = defaultdict(list)
    for match in all_matches:
        by_year[match['historical']['year']].append(match)
    
    print(f"\n   By Historical Year:")
    for year in sorted(by_year.keys(), reverse=True):
        matches = by_year[year]
        total_amount_2026 = sum(m['year_2026']['amount'] for m in matches)
        print(f"   - {year}: {len(matches)} projects (₱{total_amount_2026:,.0f})")
    
    # Group by years apart
    by_years_apart = defaultdict(list)
    for match in all_matches:
        by_years_apart[match['years_apart']].append(match)
    
    print(f"\n   By Years Since Last Appearance:")
    for years_apart in sorted(by_years_apart.keys()):
        matches = by_years_apart[years_apart]
        total_amount_2026 = sum(m['year_2026']['amount'] for m in matches)
        print(f"   - {years_apart} year(s) ago: {len(matches)} projects (₱{total_amount_2026:,.0f})")
    
    # Total amounts
    total_amount_2026 = sum(m['year_2026']['amount'] for m in all_matches)
    total_amount_historical = sum(m['historical']['amount'] for m in all_matches)
    
    print(f"\n   Total Amount (2026): ₱{total_amount_2026:,.0f}")
    print(f"   Total Amount (Historical): ₱{total_amount_historical:,.0f}")
    
    # Top matches by similarity
    if all_matches:
        print(f"\n🔝 Top 20 Resurrected Projects (by name similarity):")
        sorted_matches = sorted(all_matches, key=lambda x: x['similarity']['name'], reverse=True)[:20]
        for i, match in enumerate(sorted_matches, 1):
            name_2026 = match['year_2026']['name'][:70]
            year_historical = match['historical']['year']
            years_apart = match['years_apart']
            similarity = match['similarity']['name']
            amount_2026 = match['year_2026']['amount']
            amount_historical = match['historical']['amount']
            
            print(f"\n   {i}. {name_2026}...")
            print(f"      Found in {year_historical} ({years_apart} year(s) ago) | Similarity: {similarity:.1%}")
            print(f"      2026: ₱{amount_2026:,.0f} | {year_historical}: ₱{amount_historical:,.0f}")


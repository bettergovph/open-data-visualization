#!/usr/bin/env python3
"""
Compare 2026 Senate Committee Report vs 2025 Budget
Identifies copied line items between years with stricter matching criteria.

Usage:
    python3 scripts/compare_2026_vs_2025.py
"""

import json
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
from typing import Dict, List, Any, Tuple
from difflib import SequenceMatcher
from collections import defaultdict
import re
from datetime import datetime


class YearComparison:
    def __init__(self):
        self.db_config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'budget_analysis',
            'user': 'budget_admin',
            'password': 'wuQ5gBYCKkZiOGb61chLcByMu'
        }
        self.year_2026_data = None
        self.year_2025_data = []
        self.matches = []
        
    def normalize_name(self, name: str) -> str:
        """Normalize project/line item name for comparison (stricter version)"""
        if not name:
            return ""
        
        # Convert to uppercase
        name = name.upper()
        
        # Remove funding source indicators (GOP, Loan proceeds, etc.)
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
    
    def amount_similarity(self, amount1: float, amount2: float) -> float:
        """Calculate similarity between two amounts (0-1 scale)"""
        if amount1 == 0 and amount2 == 0:
            return 1.0
        if amount1 == 0 or amount2 == 0:
            return 0.0
        
        # Calculate percentage difference
        diff = abs(amount1 - amount2)
        avg = (abs(amount1) + abs(amount2)) / 2
        if avg == 0:
            return 1.0
        
        # Similarity is inverse of percentage difference
        pct_diff = diff / avg
        similarity = max(0.0, 1.0 - pct_diff)
        
        return similarity
    
    def load_2026_data(self, source_filter: str = "Annex A-1"):
        """Load 2026 data from JSON file"""
        json_path = Path("static/data/budget_amendments_2026.json")
        
        if not json_path.exists():
            raise FileNotFoundError(f"JSON file not found: {json_path}")
        
        print(f"\n📁 Loading 2026 data from {json_path}...")
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Filter to only specified source sheet
        all_items = data.get('line_items', []) + data.get('projects', [])
        line_items = [
            item for item in all_items
            if item.get('source_sheet') == source_filter
        ]
        
        print(f"   Found {len(line_items)} items from {source_filter}")
        self.year_2026_data = line_items
        return line_items
    
    def load_2025_data(self, source_filter: str = "Annex A-1"):
        """Load 2025 data from PostgreSQL database"""
        print(f"\n💾 Loading 2025 data from database...")
        
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Query 2025 budget data
        # Note: budget_2025 table uses different column names
        if source_filter == "Annex A-1":
            # Farm to Market Roads - Department of Agriculture
            dept_filter = "uacs_dpt_dsc ILIKE '%AGRICULTURE%' OR dsc ILIKE '%farm%market%' OR dsc ILIKE '%FMR%'"
        elif source_filter == "Annex A-5":
            # DPWH projects
            dept_filter = "uacs_dpt_dsc ILIKE '%PUBLIC WORKS%' OR uacs_dpt_dsc ILIKE '%DPWH%' OR dsc ILIKE '%DPWH%'"
        else:
            dept_filter = "1=1"  # No filter
        
        query = f"""
            SELECT 
                id,
                amt,
                dsc,
                uacs_dpt_dsc,
                uacs_reg_id,
                uacs_agy_dsc,
                fundcd,
                uacs_fundsubcat_dsc,
                uacs_exp_cd,
                uacs_exp_dsc,
                source_file
            FROM budget_2025
            WHERE year = 2025
            AND amt > 0
            AND ({dept_filter})
            ORDER BY amt DESC, dsc
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        # Convert to list of dicts
        self.year_2025_data = []
        for row in rows:
            self.year_2025_data.append({
                'id': row['id'],
                'amount': float(row['amt']) if row['amt'] else 0.0,
                'description': row['dsc'] or '',
                'department_desc': row['uacs_dpt_dsc'],
                'region_id': row['uacs_reg_id'],
                'agency_desc': row['uacs_agy_dsc'],
                'fund_code': row['fundcd'],
                'fund_desc': row['uacs_fundsubcat_dsc'],
                'exp_code': row['uacs_exp_cd'],
                'exp_desc': row['uacs_exp_dsc'],
                'source_file': row['source_file']
            })
        
        cursor.close()
        conn.close()
        
        print(f"   Found {len(self.year_2025_data)} items from 2025 budget")
        return self.year_2025_data
    
    def find_cross_year_duplicates(self,
                                    name_similarity_threshold: float = 0.90,  # Stricter: 90%
                                    amount_similarity_threshold: float = None,  # Ignore amount - focus on name only
                                    min_amount: float = 100000,
                                    source_filter: str = "Annex A-1"):
        """
        Find items that appear in both 2026 and 2025 with name matching only.
        Also checks if 2026 projects are aggregations of multiple 2025 line items.
        
        Args:
            name_similarity_threshold: Minimum name similarity (0-1), default 0.90 (stricter)
            amount_similarity_threshold: Ignored - focusing on name matching only
            min_amount: Minimum amount to consider
            source_filter: Source sheet to filter (Annex A-1 or Annex A-5)
        """
        if not self.year_2026_data:
            self.load_2026_data(source_filter)
        if not self.year_2025_data:
            self.load_2025_data(source_filter)
        
        print(f"\n🔍 Finding cross-year duplicates (name matching only)...")
        print(f"   2026 items: {len(self.year_2026_data)}")
        print(f"   2025 items: {len(self.year_2025_data)}")
        print(f"   Name similarity threshold: {name_similarity_threshold:.0%}")
        print(f"   Amount matching: DISABLED (focusing on name only)")
        print(f"   Checking for aggregations: ENABLED")
        print(f"   Minimum amount: ₱{min_amount:,.0f}")
        
        matches = []
        total_comparisons = 0
        
        # Pre-normalize all 2025 names for faster comparison
        print(f"   Pre-normalizing 2025 names...")
        normalized_2025 = []
        for item_2025 in self.year_2025_data:
            amount_2025 = abs(item_2025['amount'])
            if amount_2025 < min_amount:
                continue
            name_2025 = item_2025.get('description', '')
            normalized_2025.append({
                'item': item_2025,
                'normalized_name': self.normalize_name(name_2025),
                'original_name': name_2025,
                'amount': amount_2025
            })
        
        print(f"   Pre-normalized {len(normalized_2025)} 2025 items above minimum amount")
        
        # Compare each 2026 item with 2025 items
        processed = 0
        for item_2026 in self.year_2026_data:
            amount_2026 = abs(item_2026.get('final_amount', 0) or item_2026.get('original_amount', 0))
            if amount_2026 < min_amount:
                continue
            
            name_2026 = item_2026.get('description', '') or item_2026.get('name', '')
            region_2026 = None
            if item_2026.get('location') and isinstance(item_2026.get('location'), dict):
                region_2026 = item_2026.get('location', {}).get('region')
            
            # Pre-normalize 2026 name once
            normalized_name_2026 = self.normalize_name(name_2026)
            if not normalized_name_2026:
                continue
            
            # Extract significant words from 2026 name (words longer than 3 chars)
            words_2026 = set([w for w in normalized_name_2026.split() if len(w) > 3])
            
            # Find ALL 2025 items that match by name (ignore amount)
            name_matches = []
            for norm_2025 in normalized_2025:
                if not norm_2025['normalized_name']:
                    continue
                
                # Quick filter: check if they share at least one significant word
                words_2025 = set([w for w in norm_2025['normalized_name'].split() if len(w) > 3])
                if not words_2026.intersection(words_2025):
                    continue  # Skip if no common words
                
                total_comparisons += 1
                
                # Calculate name similarity using pre-normalized names
                name_sim = SequenceMatcher(None, normalized_name_2026, norm_2025['normalized_name']).ratio()
                
                if name_sim >= name_similarity_threshold:
                    name_matches.append({
                        'item': norm_2025['item'],
                        'name_similarity': name_sim,
                        'amount': norm_2025['amount']
                    })
            
            # Progress reporting
            processed += 1
            if processed % 100 == 0:
                print(f"   Processed {processed}/{len(self.year_2026_data)} 2026 items, found {len(matches)} matches so far...")
            
            if not name_matches:
                continue
            
            # Sort by name similarity (best first) and limit to top matches for performance
            name_matches.sort(key=lambda x: x['name_similarity'], reverse=True)
            # Limit to top 50 matches to avoid processing too many aggregations
            if len(name_matches) > 50:
                name_matches = name_matches[:50]
            
            # Check if it's a single match or aggregation
            if len(name_matches) == 1:
                # Single match
                match_2025 = name_matches[0]
                item_2025 = match_2025['item']
                amount_2025 = match_2025['amount']
                amount_sim = self.amount_similarity(amount_2026, amount_2025)
                
                matches.append({
                    'match_type': 'single',
                    'year_2026': {
                        'id': item_2026.get('id'),
                        'name': name_2026,
                        'description': item_2026.get('description', ''),
                        'amount': amount_2026,
                        'region': region_2026,
                        'source_sheet': item_2026.get('source_sheet'),
                        'source_row': item_2026.get('source_row'),
                        'source_col': item_2026.get('source_col_b') or item_2026.get('source_col_c')
                    },
                    'year_2025': {
                        'id': item_2025['id'],
                        'description': item_2025['description'],
                        'amount': amount_2025,
                        'region_id': item_2025['region_id'],
                        'department_desc': item_2025['department_desc'],
                        'agency_desc': item_2025['agency_desc'],
                        'source_file': item_2025['source_file']
                    },
                    'similarity': {
                        'name': match_2025['name_similarity'],
                        'amount': amount_sim,
                        'combined_score': match_2025['name_similarity']  # Name only
                    },
                    'amount_difference': abs(amount_2026 - amount_2025),
                    'amount_difference_pct': (abs(amount_2026 - amount_2025) / min(amount_2026, amount_2025) * 100) if min(amount_2026, amount_2025) > 0 else 0
                })
            else:
                # Multiple matches - could be aggregation
                # Try to find combination that matches amount
                total_2025_amount = sum(m['amount'] for m in name_matches)
                amount_sim_total = self.amount_similarity(amount_2026, total_2025_amount)
                
                # Check if sum of all matches is close to 2026 amount
                # Or if best single match is close
                best_single = name_matches[0]
                amount_sim_single = self.amount_similarity(amount_2026, best_single['amount'])
                
                # Use aggregation if total is closer than single, otherwise use best single
                if amount_sim_total > amount_sim_single and amount_sim_total >= 0.80:  # 80% threshold for aggregation
                    # Aggregation match
                    matches.append({
                        'match_type': 'aggregation',
                        'year_2026': {
                            'id': item_2026.get('id'),
                            'name': name_2026,
                            'description': item_2026.get('description', ''),
                            'amount': amount_2026,
                            'region': region_2026,
                            'source_sheet': item_2026.get('source_sheet'),
                            'source_row': item_2026.get('source_row'),
                            'source_col': item_2026.get('source_col_b') or item_2026.get('source_col_c')
                        },
                        'year_2025_items': [
                            {
                                'id': m['item']['id'],
                                'description': m['item']['description'],
                                'amount': m['amount'],
                                'name_similarity': m['name_similarity'],
                                'region_id': m['item']['region_id'],
                                'department_desc': m['item']['department_desc'],
                                'agency_desc': m['item']['agency_desc'],
                                'source_file': m['item']['source_file']
                            }
                            for m in name_matches
                        ],
                        'year_2025_total': {
                            'total_amount': total_2025_amount,
                            'item_count': len(name_matches),
                            'avg_name_similarity': sum(m['name_similarity'] for m in name_matches) / len(name_matches)
                        },
                        'similarity': {
                            'name': sum(m['name_similarity'] for m in name_matches) / len(name_matches),
                            'amount': amount_sim_total,
                            'combined_score': (sum(m['name_similarity'] for m in name_matches) / len(name_matches) * 0.7 + amount_sim_total * 0.3)
                        },
                        'amount_difference': abs(amount_2026 - total_2025_amount),
                        'amount_difference_pct': (abs(amount_2026 - total_2025_amount) / min(amount_2026, total_2025_amount) * 100) if min(amount_2026, total_2025_amount) > 0 else 0
                    })
                else:
                    # Use best single match
                    match_2025 = best_single
                    item_2025 = match_2025['item']
                    amount_2025 = match_2025['amount']
                    amount_sim = self.amount_similarity(amount_2026, amount_2025)
                    
                    matches.append({
                        'match_type': 'single',
                        'year_2026': {
                            'id': item_2026.get('id'),
                            'name': name_2026,
                            'description': item_2026.get('description', ''),
                            'amount': amount_2026,
                            'region': region_2026,
                            'source_sheet': item_2026.get('source_sheet'),
                            'source_row': item_2026.get('source_row'),
                            'source_col': item_2026.get('source_col_b') or item_2026.get('source_col_c')
                        },
                        'year_2025': {
                            'id': item_2025['id'],
                            'description': item_2025['description'],
                            'amount': amount_2025,
                            'region_id': item_2025['region_id'],
                            'department_desc': item_2025['department_desc'],
                            'agency_desc': item_2025['agency_desc'],
                            'source_file': item_2025['source_file']
                        },
                        'similarity': {
                            'name': match_2025['name_similarity'],
                            'amount': amount_sim,
                            'combined_score': match_2025['name_similarity']
                        },
                        'amount_difference': abs(amount_2026 - amount_2025),
                        'amount_difference_pct': (abs(amount_2026 - amount_2025) / min(amount_2026, amount_2025) * 100) if min(amount_2026, amount_2025) > 0 else 0,
                        'note': f'Found {len(name_matches)} name matches, using best single match'
                    })
        
        print(f"   Compared {total_comparisons:,} pairs")
        print(f"   Found {len(matches)} cross-year matches")
        single_matches = sum(1 for m in matches if m.get('match_type') == 'single')
        aggregation_matches = sum(1 for m in matches if m.get('match_type') == 'aggregation')
        print(f"   - Single matches: {single_matches}")
        print(f"   - Aggregation matches: {aggregation_matches}")
        
        self.matches = matches
        return matches
    
    def save_results(self, output_path: str = "static/data/cross_year_duplicates_2026_vs_2025.json", min_amount: float = 100000):
        """Save cross-year duplicate detection results to JSON"""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Group matches by source sheet
        matches_by_source = defaultdict(list)
        for match in self.matches:
            source = match['year_2026'].get('source_sheet', 'Unknown')
            matches_by_source[source].append(match)
        
        # Calculate summary statistics (handle both single and aggregation matches)
        total_amount_2026 = 0
        total_amount_2025 = 0
        single_count = 0
        aggregation_count = 0
        
        for m in self.matches:
            total_amount_2026 += m['year_2026']['amount']
            if m.get('match_type') == 'aggregation':
                total_amount_2025 += m['year_2025_total']['total_amount']
                aggregation_count += 1
            else:
                total_amount_2025 += m['year_2025']['amount']
                single_count += 1
        
        # Calculate data characteristics for analysis
        if self.year_2026_data:
            amounts_2026 = [abs(item.get('final_amount', 0) or item.get('original_amount', 0)) for item in self.year_2026_data]
            amounts_2026 = [a for a in amounts_2026 if a >= min_amount]
            if amounts_2026:
                min_2026 = min(amounts_2026)
                max_2026 = max(amounts_2026)
                avg_2026 = sum(amounts_2026) / len(amounts_2026)
            else:
                min_2026 = max_2026 = avg_2026 = 0
        else:
            min_2026 = max_2026 = avg_2026 = 0
        
        if self.year_2025_data:
            amounts_2025 = [abs(item['amount']) for item in self.year_2025_data if abs(item['amount']) >= min_amount]
            if amounts_2025:
                min_2025 = min(amounts_2025)
                max_2025 = max(amounts_2025)
                avg_2025 = sum(amounts_2025) / len(amounts_2025)
            else:
                min_2025 = max_2025 = avg_2025 = 0
        else:
            min_2025 = max_2025 = avg_2025 = 0
        
        results = {
            'metadata': {
                'comparison_date': datetime.now().isoformat(),
                'year_2026_source': 'Senate Committee Report 2026',
                'year_2025_source': 'GAA 2025 Budget Database',
                'total_matches': len(self.matches),
                'total_amount_2026': total_amount_2026,
                'total_amount_2025': total_amount_2025,
                'matches_by_source': {k: len(v) for k, v in matches_by_source.items()},
                'data_characteristics': {
                    'year_2026': {
                        'total_items': len(self.year_2026_data) if self.year_2026_data else 0,
                        'items_above_min': len(amounts_2026) if self.year_2026_data else 0,
                        'min_amount': min_2026,
                        'max_amount': max_2026,
                        'avg_amount': avg_2026
                    },
                    'year_2025': {
                        'total_items': len(self.year_2025_data) if self.year_2025_data else 0,
                        'items_above_min': len(amounts_2025) if self.year_2025_data else 0,
                        'min_amount': min_2025,
                        'max_amount': max_2025,
                        'avg_amount': avg_2025
                    }
                },
                'matching_criteria': {
                    'name_similarity_threshold': 0.90,
                    'amount_similarity_threshold': 'DISABLED (name matching only)',
                    'aggregation_detection': 'ENABLED',
                    'min_amount': min_amount
                }
            },
            'summary': {
                'total_copied_items': len(self.matches),
                'single_matches': single_count,
                'aggregation_matches': aggregation_count,
                'total_copied_amount_2026': total_amount_2026,
                'total_copied_amount_2025': total_amount_2025,
                'average_name_similarity': sum(m['similarity']['name'] for m in self.matches) / len(self.matches) if self.matches else 0,
                'average_amount_similarity': sum(m['similarity'].get('amount', 0) for m in self.matches) / len(self.matches) if self.matches else 0,
                'exact_amount_matches': sum(1 for m in self.matches if m.get('amount_difference', 0) == 0),
                'high_confidence_matches': sum(1 for m in self.matches if m['similarity']['combined_score'] >= 0.95)
            },
            'matches': sorted(self.matches, key=lambda x: x['similarity']['combined_score'], reverse=True)
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Saved cross-year duplicate detection results to: {output_file}")
        return output_file


if __name__ == "__main__":
    print("=" * 100)
    print(" CROSS-YEAR DUPLICATE DETECTION: 2026 vs 2025")
    print("=" * 100)
    
    # Process Annex A-1 (Farm to Market Roads)
    print("\n" + "=" * 100)
    print(" PROCESSING ANNEX A-1 (FARM TO MARKET ROADS)")
    print("=" * 100)
    
    comparator_a1 = YearComparison()
    comparator_a1.load_2026_data("Annex A-1")
    comparator_a1.load_2025_data("Annex A-1")
    matches_a1 = comparator_a1.find_cross_year_duplicates(
        name_similarity_threshold=0.90,  # Stricter: 90%
        amount_similarity_threshold=None,  # Ignored - name matching only
        min_amount=100000,
        source_filter="Annex A-1"
    )
    
    # Process Annex A-5 (DPWH Projects)
    print("\n" + "=" * 100)
    print(" PROCESSING ANNEX A-5 (DPWH PROJECTS)")
    print("=" * 100)
    
    comparator_a5 = YearComparison()
    comparator_a5.load_2026_data("Annex A-5")
    comparator_a5.load_2025_data("Annex A-5")
    matches_a5 = comparator_a5.find_cross_year_duplicates(
        name_similarity_threshold=0.90,  # Stricter: 90%
        amount_similarity_threshold=None,  # Ignored - name matching only
        min_amount=100000,
        source_filter="Annex A-5"
    )
    
    # Combine results
    all_matches = matches_a1 + matches_a5
    comparator_a1.matches = all_matches
    
    # Save combined results
    output_file = comparator_a1.save_results("static/data/cross_year_duplicates_2026_vs_2025.json", min_amount=100000)
    
    # Print summary
    print(f"\n📊 SUMMARY:")
    print(f"   Total cross-year matches: {len(all_matches)}")
    print(f"   Annex A-1 matches: {len(matches_a1)}")
    print(f"   Annex A-5 matches: {len(matches_a5)}")
    
    single_matches = [m for m in all_matches if m.get('match_type') == 'single']
    aggregation_matches = [m for m in all_matches if m.get('match_type') == 'aggregation']
    
    print(f"   Single matches: {len(single_matches)}")
    print(f"   Aggregation matches: {len(aggregation_matches)}")
    
    if all_matches:
        # Calculate totals (handle both single and aggregation matches)
        total_2026 = 0
        total_2025 = 0
        for m in all_matches:
            total_2026 += m['year_2026']['amount']
            if m.get('match_type') == 'aggregation':
                total_2025 += m['year_2025_total']['total_amount']
            else:
                total_2025 += m['year_2025']['amount']
        
        avg_name_sim = sum(m['similarity']['name'] for m in all_matches) / len(all_matches)
        exact_matches = sum(1 for m in all_matches if m.get('amount_difference', 0) == 0)
        
        print(f"   Total amount (2026): ₱{total_2026:,.0f}")
        print(f"   Total amount (2025): ₱{total_2025:,.0f}")
        print(f"   Average name similarity: {avg_name_sim:.1%}")
        print(f"   Exact amount matches: {exact_matches}")
        
        print(f"\n🔝 Top 10 Cross-Year Matches:")
        sorted_matches = sorted(all_matches, key=lambda x: x['similarity']['combined_score'], reverse=True)[:10]
        for i, match in enumerate(sorted_matches, 1):
            name_2026 = match['year_2026']['name'][:60]
            amount_2026 = match['year_2026']['amount']
            match_type = match.get('match_type', 'single')
            score = match['similarity']['combined_score']
            
            if match_type == 'aggregation':
                amount_2025 = match['year_2025_total']['total_amount']
                item_count = match['year_2025_total']['item_count']
                print(f"\n   {i}. {name_2026}... [AGGREGATION]")
                print(f"      2026: ₱{amount_2026:,.0f} | 2025: ₱{amount_2025:,.0f} ({item_count} items) | Score: {score:.1%}")
            else:
                amount_2025 = match['year_2025']['amount']
                print(f"\n   {i}. {name_2026}...")
                print(f"      2026: ₱{amount_2026:,.0f} | 2025: ₱{amount_2025:,.0f} | Score: {score:.1%}")


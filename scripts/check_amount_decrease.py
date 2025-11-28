#!/usr/bin/env python3
"""
Check Annex A-5 Projects with 31.3417% Decrease
Analyzes projects that have been decreased by exactly 31.3417% between years.

Usage:
    python3 scripts/check_amount_decrease.py
"""

import json
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
from typing import Dict, List, Any
from difflib import SequenceMatcher
from collections import defaultdict
import re
from datetime import datetime


class AmountDecreaseAnalyzer:
    def __init__(self):
        self.db_config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'budget_analysis',
            'user': 'budget_admin',
            'password': 'wuQ5gBYCKkZiOGb61chLcByMu'
        }
        self.target_decrease = 0.031906333333333  # 3.1906333333333%
        self.tolerance = 0.00001  # Very small tolerance for exact match
        
    def normalize_name(self, name: str) -> str:
        """Normalize project name for comparison"""
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
    
    def load_2026_annex_a5(self):
        """Load Annex A-5 data from 2026 JSON"""
        json_path = Path("static/data/budget_amendments_2026.json")
        
        if not json_path.exists():
            raise FileNotFoundError(f"JSON file not found: {json_path}")
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Filter to Annex A-5
        all_items = data.get('line_items', []) + data.get('projects', [])
        annex_a5_items = [
            item for item in all_items
            if item.get('source_sheet') == 'Annex A-5'
        ]
        
        return annex_a5_items
    
    def load_2025_dpwh_data(self, amounts_in_thousands: bool = True):
        """Load 2025 DPWH data from PostgreSQL"""
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
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
            FROM budget_2025
            WHERE year = 2025
            AND amt >= {min_amt}
            AND (uacs_dpt_dsc ILIKE '%PUBLIC WORKS%' OR uacs_dpt_dsc ILIKE '%DPWH%' OR dsc ILIKE '%DPWH%')
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
    
    def find_decreased_projects(self):
        """
        Find Annex A-5 projects that decreased by exactly 3.1906333333333%
        Check decrease from Column O (GAB/original) to Column S (Final) within same project
        """
        print("=" * 100)
        print(" ANALYZING ANNEX A-5 PROJECTS WITH 3.1906333333333% DECREASE")
        print(" Checking decrease from Column O (GAB) to Column S (Final) within same project")
        print("=" * 100)
        
        # Load 2026 Annex A-5 data
        print("\n📁 Loading 2026 Annex A-5 data...")
        year_2026_items = self.load_2026_annex_a5()
        print(f"   Found {len(year_2026_items)} items from Annex A-5")
        
        # Find projects with 3.1906333333333% decrease from O to S
        matches = []
        processed = 0
        output_path = Path("static/data/annex_a5_decreased_31pct.json")
        
        # Create initial output file
        initial_data = {
            "metadata": {
                "total_matches": 0,
                "target_decrease_percentage": 3.1906333333333,
                "target_decrease_decimal": 0.031906333333333,
                "comparison": "Column O (GAB) to Column S (Final) within same project",
                "generated_at": datetime.now().isoformat(),
                "status": "processing",
                "processed_items": 0,
                "total_items": len(year_2026_items)
            },
            "matches": []
        }
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(initial_data, f, indent=2, ensure_ascii=False)
        
        print(f"   Created output file: {output_path}")
        
        for item in year_2026_items:
            # Column O = original_amount (GAB)
            # Column S = final_amount (Final)
            amount_o = abs(item.get('original_amount', 0))
            amount_s = abs(item.get('final_amount', 0))
            
            if amount_o <= 0 or amount_s <= 0:
                processed += 1
                continue
            
            # Calculate actual decrease percentage from O to S
            actual_decrease = (amount_o - amount_s) / amount_o
            
            # Check if it matches target decrease (within tolerance)
            if abs(actual_decrease - self.target_decrease) <= self.tolerance:
                matches.append({
                    'project': {
                        'id': item.get('id'),
                        'name': item.get('name', '') or item.get('description', ''),
                        'description': item.get('description', ''),
                        'column_o_amount': amount_o,  # GAB (original)
                        'column_s_amount': amount_s,  # Final
                        'region': item.get('location', {}).get('region') if isinstance(item.get('location'), dict) else None,
                        'source_row': item.get('source_row'),
                        'source_sheet': item.get('source_sheet')
                    },
                    'decrease': {
                        'percentage': actual_decrease * 100,
                        'amount': amount_o - amount_s
                    }
                })
            
            processed += 1
            if processed % 500 == 0:
                print(f"   Processed {processed}/{len(year_2026_items)} items, found {len(matches)} matches with 3.1906333333333% decrease...")
                # Save incrementally
                incremental_data = {
                    "metadata": {
                        "total_matches": len(matches),
                        "target_decrease_percentage": 3.1906333333333,
                        "target_decrease_decimal": 0.031906333333333,
                        "comparison": "Column O (GAB) to Column S (Final) within same project",
                        "generated_at": datetime.now().isoformat(),
                        "status": "processing",
                        "processed_items": processed,
                        "total_items": len(year_2026_items)
                    },
                    "matches": matches
                }
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(incremental_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n   Processed {processed} items")
        print(f"   Found {len(matches)} projects with exactly 3.1906333333333% decrease from Column O to Column S")
        
        return matches


if __name__ == "__main__":
    print("=" * 100)
    print(" ANNEX A-5 AMOUNT DECREASE ANALYSIS")
    print(" Finding projects decreased by exactly 3.1906333333333%")
    print("=" * 100)
    
    analyzer = AmountDecreaseAnalyzer()
    
    matches = analyzer.find_decreased_projects()
    
    # Update final status
    output_path = Path("static/data/annex_a5_decreased_31pct.json")
    output_data = {
        "metadata": {
            "total_matches": len(matches),
            "target_decrease_percentage": 3.1906333333333,
            "target_decrease_decimal": 0.031906333333333,
            "comparison": "Column O (GAB) to Column S (Final) within same project",
            "generated_at": datetime.now().isoformat(),
            "status": "completed"
        },
        "matches": matches
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Final results saved to: {output_path}")
    
    # Print Summary
    print("\n" + "=" * 100)
    print(" SUMMARY")
    print("=" * 100)
    
    # Get total count
    total_projects = len(analyzer.load_2026_annex_a5())
    
    print(f"\n📊 Total Projects with 3.1906333333333% Decrease: {len(matches)}")
    print(f"   Out of {total_projects:,} total Annex A-5 projects")
    print(f"   Percentage: {(len(matches) / total_projects * 100):.2f}%")
    
    if matches:
        total_amount_o = sum(m['project']['column_o_amount'] for m in matches)
        total_amount_s = sum(m['project']['column_s_amount'] for m in matches)
        total_decrease = total_amount_o - total_amount_s
        
        print(f"\n   Total Amount (Column O - GAB): ₱{total_amount_o:,.2f}")
        print(f"   Total Amount (Column S - Final): ₱{total_amount_s:,.2f}")
        print(f"   Total Decrease: ₱{total_decrease:,.2f}")
        print(f"   Average Decrease: {sum(m['decrease']['percentage'] for m in matches) / len(matches):.4f}%")
        
        print(f"\n🔝 Top 20 Projects with 3.1906333333333% Decrease:")
        sorted_matches = sorted(matches, key=lambda x: x['project']['column_o_amount'], reverse=True)[:20]
        for i, match in enumerate(sorted_matches, 1):
            name = match['project']['name'][:70]
            amount_o = match['project']['column_o_amount']
            amount_s = match['project']['column_s_amount']
            decrease_pct = match['decrease']['percentage']
            
            print(f"\n   {i}. {name}...")
            print(f"      Column O (GAB): ₱{amount_o:,.2f} | Column S (Final): ₱{amount_s:,.2f} | Decrease: {decrease_pct:.4f}%")
    else:
        print("\n   No projects found with exactly 3.1906333333333% decrease")


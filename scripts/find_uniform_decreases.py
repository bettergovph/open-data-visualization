#!/usr/bin/env python3
"""
Find Uniform Decrease Patterns in Annex A-5
Analyzes all projects to find uniform percentage decreases from Column O to Column S.

Usage:
    python3 scripts/find_uniform_decreases.py
"""

import json
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict
from datetime import datetime


class UniformDecreaseFinder:
    def __init__(self):
        self.tolerance = 0.0001  # 0.01% tolerance for grouping similar percentages
        
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
    
    def round_percentage(self, pct: float) -> float:
        """Round percentage to nearest 0.0001% for grouping"""
        return round(pct * 10000) / 10000
    
    def find_uniform_decreases(self):
        """
        Find all uniform decrease patterns in Annex A-5 projects
        """
        print("=" * 100)
        print(" ANALYZING UNIFORM DECREASE PATTERNS IN ANNEX A-5")
        print(" Checking decrease from Column O (GAB) to Column S (Final)")
        print("=" * 100)
        
        # Load 2026 Annex A-5 data
        print("\n📁 Loading 2026 Annex A-5 data...")
        items = self.load_2026_annex_a5()
        print(f"   Found {len(items)} items from Annex A-5")
        
        # Analyze all projects
        decrease_groups = defaultdict(list)
        no_decrease = 0
        invalid = 0
        processed = 0
        
        output_path = Path("static/data/annex_a5_uniform_decreases.json")
        
        for item in items:
            # Column O = original_amount (GAB)
            # Column S = final_amount (Final)
            amount_o = abs(item.get('original_amount', 0))
            amount_s = abs(item.get('final_amount', 0))
            
            if amount_o <= 0:
                invalid += 1
                processed += 1
                continue
            
            if amount_s <= 0:
                invalid += 1
                processed += 1
                continue
            
            # Calculate decrease percentage
            if amount_s >= amount_o:
                # No decrease or increase
                no_decrease += 1
                processed += 1
                continue
            
            actual_decrease = (amount_o - amount_s) / amount_o
            actual_decrease_pct = actual_decrease * 100
            
            # Round to group similar percentages
            rounded_pct = self.round_percentage(actual_decrease_pct)
            
            decrease_groups[rounded_pct].append({
                'project': {
                    'id': item.get('id'),
                    'name': item.get('name', '') or item.get('description', ''),
                    'description': item.get('description', ''),
                    'column_o_amount': amount_o,
                    'column_s_amount': amount_s,
                    'region': item.get('location', {}).get('region') if isinstance(item.get('location'), dict) else None,
                    'source_row': item.get('source_row'),
                    'source_sheet': item.get('source_sheet')
                },
                'decrease': {
                    'percentage': actual_decrease_pct,
                    'amount': amount_o - amount_s
                }
            })
            
            processed += 1
            if processed % 1000 == 0:
                print(f"   Processed {processed}/{len(items)} items, found {len(decrease_groups)} unique decrease percentages...")
        
        print(f"\n   Processed {processed} items")
        print(f"   Found {len(decrease_groups)} unique decrease percentages")
        print(f"   Projects with no decrease or increase: {no_decrease}")
        print(f"   Invalid projects (zero amounts): {invalid}")
        
        # Sort by count (most frequent first)
        sorted_groups = sorted(
            decrease_groups.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )
        
        # Prepare output
        patterns = []
        for rounded_pct, matches in sorted_groups:
            if len(matches) >= 5:  # Only include patterns with at least 5 matches
                total_o = sum(m['project']['column_o_amount'] for m in matches)
                total_s = sum(m['project']['column_s_amount'] for m in matches)
                avg_pct = sum(m['decrease']['percentage'] for m in matches) / len(matches)
                
                patterns.append({
                    'decrease_percentage': rounded_pct,
                    'average_percentage': avg_pct,
                    'match_count': len(matches),
                    'total_column_o_amount': total_o,
                    'total_column_s_amount': total_s,
                    'total_decrease': total_o - total_s,
                    'matches': matches[:100]  # Limit to first 100 for JSON size
                })
        
        output_data = {
            "metadata": {
                "total_projects": len(items),
                "projects_with_decrease": processed - no_decrease - invalid,
                "projects_no_decrease": no_decrease,
                "invalid_projects": invalid,
                "unique_decrease_percentages": len(decrease_groups),
                "patterns_found": len(patterns),
                "generated_at": datetime.now().isoformat(),
                "status": "completed"
            },
            "patterns": sorted(patterns, key=lambda x: x['match_count'], reverse=True)
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Results saved to: {output_path}")
        
        # Print summary
        print("\n" + "=" * 100)
        print(" SUMMARY - TOP UNIFORM DECREASE PATTERNS")
        print("=" * 100)
        
        print(f"\n📊 Found {len(patterns)} uniform decrease patterns (with 5+ matches):")
        
        for i, pattern in enumerate(patterns[:20], 1):
            print(f"\n   {i}. {pattern['decrease_percentage']:.4f}% decrease ({pattern['average_percentage']:.6f}% average)")
            print(f"      Matches: {pattern['match_count']:,} projects")
            print(f"      Total Column O: ₱{pattern['total_column_o_amount']:,.2f}")
            print(f"      Total Column S: ₱{pattern['total_column_s_amount']:,.2f}")
            print(f"      Total Decrease: ₱{pattern['total_decrease']:,.2f}")
            print(f"      Percentage of total projects: {(pattern['match_count'] / len(items) * 100):.2f}%")
        
        return patterns


if __name__ == "__main__":
    print("=" * 100)
    print(" UNIFORM DECREASE PATTERN ANALYSIS")
    print(" Finding all uniform percentage decreases in Annex A-5")
    print("=" * 100)
    
    finder = UniformDecreaseFinder()
    patterns = finder.find_uniform_decreases()
    
    print(f"\n✅ Analysis complete! Found {len(patterns)} uniform decrease patterns.")



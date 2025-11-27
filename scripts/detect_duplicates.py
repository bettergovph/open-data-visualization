#!/usr/bin/env python3
"""
Detect Duplicate Budget Amendments
Identifies line items with similar names and amounts that may be duplicates.

Usage:
    python3 scripts/detect_duplicates.py
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Tuple
from difflib import SequenceMatcher
from collections import defaultdict
import re

class DuplicateDetector:
    def __init__(self, json_path: str = "static/data/budget_amendments_2026.json"):
        self.json_path = Path(json_path)
        self.data = None
        self.duplicates = []
        
    def load_data(self):
        """Load the budget amendments JSON file"""
        if not self.json_path.exists():
            raise FileNotFoundError(f"JSON file not found: {self.json_path}")
        
        with open(self.json_path, 'r', encoding='utf-8') as f:
            self.data = json.load(f)
        
        print(f"✅ Loaded {len(self.data.get('line_items', []))} line items")
    
    def normalize_name(self, name: str) -> str:
        """Normalize project/line item name for comparison"""
        if not name:
            return ""
        
        # Convert to uppercase
        name = name.upper()
        
        # Remove funding source indicators (GOP, Loan proceeds, etc.) - these are not part of project identity
        # Projects can be: GOP only, Loan proceeds only, or both - but funding source doesn't make them different projects
        name = re.sub(r'\bGOP\b', '', name, flags=re.IGNORECASE)  # Remove standalone GOP
        name = re.sub(r'\bLOAN\s+PROCEEDS\b', '', name, flags=re.IGNORECASE)  # Remove "LOAN PROCEEDS"
        name = re.sub(r'\bLOAN\s+PROCEED\b', '', name, flags=re.IGNORECASE)  # Remove "LOAN PROCEED" (singular)
        name = re.sub(r'\bPROCEEDS\b', '', name, flags=re.IGNORECASE)  # Remove standalone PROCEEDS
        name = re.sub(r'\bLOAN\b', '', name, flags=re.IGNORECASE)  # Remove standalone LOAN
        
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
        # 0% diff = 1.0 similarity, 10% diff = 0.9 similarity, etc.
        pct_diff = diff / avg
        similarity = max(0.0, 1.0 - pct_diff)
        
        return similarity
    
    def detect_duplicates(self, 
                          name_similarity_threshold: float = 0.85,
                          amount_similarity_threshold: float = 0.95,
                          min_amount: float = 100000,
                          source_filter: str = "Annex A-1") -> List[Dict]:
        """
        Detect duplicate line items based on name and amount similarity
        
        Args:
            name_similarity_threshold: Minimum name similarity (0-1)
            amount_similarity_threshold: Minimum amount similarity (0-1)
            min_amount: Minimum amount to consider (filter out very small items)
            source_filter: Only check items from this source sheet (default: "Annex A-1")
        """
        if not self.data:
            self.load_data()
        
        # Filter to only Annex A-1 items (projects)
        all_items = self.data.get('line_items', []) + self.data.get('projects', [])
        line_items = [
            item for item in all_items
            if item.get('source_sheet') == source_filter
        ]
        
        duplicates = []
        processed = set()
        
        print(f"\n🔍 Detecting duplicates from {source_filter}...")
        print(f"   Found {len(line_items)} items from {source_filter}")
        print(f"   Name similarity threshold: {name_similarity_threshold:.0%}")
        print(f"   Amount similarity threshold: {amount_similarity_threshold:.0%}")
        print(f"   Minimum amount: ₱{min_amount:,.0f}")
        
        # For Annex A-5 with exact amount matching, use optimized grouping by amount first
        use_exact_amount = (source_filter == "Annex A-5")
        
        all_groups = []  # Collect all groups from both paths
        total_comparisons = 0
        
        if use_exact_amount:
            # Fast path: Group by exact amount first, then compare names within each amount group
            amount_groups = defaultdict(list)
            for idx, item in enumerate(line_items):
                amount = abs(item.get('final_amount', 0) or item.get('original_amount', 0))
                if amount >= min_amount:
                    amount_groups[amount].append((idx, item))
            
            for exact_amount, items in amount_groups.items():
                if len(items) < 2:
                    continue  # Need at least 2 items with same amount
                
                # Group by region within this amount group
                region_groups = defaultdict(list)
                for idx, item in items:
                    region = None
                    if item.get('location') and isinstance(item.get('location'), dict):
                        region = item.get('location', {}).get('region')
                    region_groups[region].append((idx, item))
                
                # Compare names within each region group
                for region, region_items in region_groups.items():
                    if len(region_items) < 2:
                        continue
                    
                    # Compare all pairs within this region/amount group
                    for i, (idx1, item1) in enumerate(region_items):
                        if idx1 in processed:
                            continue
                        
                        name1 = item1.get('description', '') or item1.get('name', '')
                        group = [item1]
                        group_indices = [idx1]
                        
                        for j, (idx2, item2) in enumerate(region_items[i+1:], start=i+1):
                            if idx2 in processed:
                                continue
                            
                            name2 = item2.get('description', '') or item2.get('name', '')
                            total_comparisons += 1
                            
                            # Only check name similarity (amount is already exact match)
                            name_sim = self.similarity(name1, name2)
                            
                            if name_sim >= name_similarity_threshold:
                                group.append(item2)
                                group_indices.append(idx2)
                                processed.add(idx2)
                        
                        if len(group) > 1:
                            processed.add(idx1)
                            all_groups.append(group)
        else:
            # Original algorithm for approximate amount matching
            dept_groups = defaultdict(list)
            for idx, item in enumerate(line_items):
                dept_id = item.get('department_id', 'UNKNOWN')
                dept_groups[dept_id].append((idx, item))
            
            for dept_id, items in dept_groups.items():
                # Compare all pairs within the same department
                for i, (idx1, item1) in enumerate(items):
                    if idx1 in processed:
                        continue
                    
                    name1 = item1.get('description', '') or item1.get('name', '')
                    amount1 = abs(item1.get('final_amount', 0) or item1.get('original_amount', 0))
                    region1 = None
                    if item1.get('location') and isinstance(item1.get('location'), dict):
                        region1 = item1.get('location', {}).get('region')
                    
                    if amount1 < min_amount:
                        continue
                    
                    group = [item1]
                    group_indices = [idx1]
                    
                    for j, (idx2, item2) in enumerate(items[i+1:], start=i+1):
                        if idx2 in processed:
                            continue
                        
                        name2 = item2.get('description', '') or item2.get('name', '')
                        amount2 = abs(item2.get('final_amount', 0) or item2.get('original_amount', 0))
                        region2 = None
                        if item2.get('location') and isinstance(item2.get('location'), dict):
                            region2 = item2.get('location', {}).get('region')
                        
                        if amount2 < min_amount:
                            continue
                        
                        # IMPORTANT: Only consider duplicates if they're from the same region
                        if region1 and region2 and region1 != region2:
                            continue
                        if (region1 and not region2) or (not region1 and region2):
                            continue
                        
                        total_comparisons += 1
                        
                        # Calculate similarities
                        name_sim = self.similarity(name1, name2)
                        amount_sim = self.amount_similarity(amount1, amount2)
                        amount_match = amount_sim >= amount_similarity_threshold
                        
                        # Check if both thresholds are met
                        if name_sim >= name_similarity_threshold and amount_match:
                            group.append(item2)
                            group_indices.append(idx2)
                            processed.add(idx2)
                    
                    if len(group) > 1:
                        processed.add(idx1)
                        all_groups.append(group)
        
        # Process all groups into duplicate_groups format
        duplicate_groups = []
        for group in all_groups:
                    
                    # Calculate average similarities for the group
                    group_name_sims = []
                    group_amount_sims = []
                    for i in range(len(group)):
                        for j in range(i + 1, len(group)):
                            item_i_name = (group[i].get('description', '') or group[i].get('name', '')).strip()
                            item_j_name = (group[j].get('description', '') or group[j].get('name', '')).strip()
                            item_i_amount = abs(group[i].get('final_amount', 0) or group[i].get('original_amount', 0))
                            item_j_amount = abs(group[j].get('final_amount', 0) or group[j].get('original_amount', 0))
                            
                            group_name_sims.append(self.similarity(item_i_name, item_j_name))
                            group_amount_sims.append(self.amount_similarity(item_i_amount, item_j_amount))
                    
                    avg_name_sim = sum(group_name_sims) / len(group_name_sims) if group_name_sims else 0
                    avg_amount_sim = sum(group_amount_sims) / len(group_amount_sims) if group_amount_sims else 0
                    
                    # Generate remarks explaining why these are duplicates
                    amounts = [abs(item.get('final_amount', 0) or item.get('original_amount', 0)) for item in group]
                    min_amt = min(amounts)
                    max_amt = max(amounts)
                    amount_diff_pct = ((max_amt - min_amt) / min_amt * 100) if min_amt > 0 else 0
                    
                    remarks = []
                    remarks.append(f"Name similarity: {avg_name_sim:.1%} (threshold: {name_similarity_threshold:.0%})")
                    if use_exact_amount:
                        remarks.append("Exact amount match (all items have identical amounts)")
                    else:
                        remarks.append(f"Amount similarity: {avg_amount_sim:.1%} (threshold: {amount_similarity_threshold:.0%})")
                        if amount_diff_pct > 0:
                            remarks.append(f"Amount difference: {amount_diff_pct:.2f}% between items")
                    
                    # Check if names are very similar
                    normalized_names = [self.normalize_name(item.get('description', '') or item.get('name', '')) for item in group]
                    if len(set(normalized_names)) == 1:
                        remarks.append("All items have identical normalized names")
                    elif len(set(normalized_names)) < len(group):
                        remarks.append("Some items have identical normalized names")
                    
                    # Add region information to remarks
                    regions = set()
                    for item in group:
                        if item.get('location') and isinstance(item.get('location'), dict):
                            region = item.get('location', {}).get('region')
                            if region:
                                regions.add(region)
                    if len(regions) == 1:
                        remarks.append(f"All items from same region: {list(regions)[0]}")
                    elif len(regions) > 1:
                        remarks.append(f"Items from {len(regions)} different regions: {', '.join(sorted(regions))}")
                    
                    # Get source Excel file from items (should all be the same for a group)
                    source_excel = None
                    source_sheet = None
                    for item in group:
                        item_source = item.get('source_sheet', '')
                        if item_source:
                            source_sheet = item_source
                            # Map source sheet to Excel file name
                            if item_source == 'Annex A-1':
                                source_excel = 'Annex A-1 DA-Farm-to-Market Roads.xlsx'
                            elif item_source == 'Annex A-2':
                                source_excel = 'Annex A-2 DepEd - Office of the Secretary - Non Implementing Unit Secondary Schools.xlsx'
                            elif item_source == 'Annex A-4':
                                source_excel = 'Annex A-4 BSGC-OEOs-NIA Details of NIA\'s Operations Budget.xlsx'
                            elif item_source == 'Annex A-5':
                                source_excel = 'Annex A-5 Details of DPWH\'s Programs&Projects.xlsx'
                            elif item_source == 'Annex A':
                                source_excel = 'Annex A - Line By Line Amendments.xlsx'
                            break
                    
                    duplicate_groups.append({
                        'group_id': len(duplicate_groups) + 1,
                        'items': group,
                        'name_similarity': avg_name_sim,
                        'amount_similarity': avg_amount_sim,
                        'count': len(group),
                        'total_amount': sum(amounts),
                        'remarks': ' | '.join(remarks),
                        'amount_range': {
                            'min': min_amt,
                            'max': max_amt,
                            'difference': max_amt - min_amt,
                            'difference_pct': amount_diff_pct
                        },
                        'source_sheet': source_sheet,
                        'source_excel': source_excel
                    })
        
        print(f"   Compared {total_comparisons:,} pairs")
        print(f"   Found {len(duplicate_groups)} duplicate groups")
        
        return duplicate_groups
    
    def save_results(self, output_path: str = "static/data/duplicates_2026.json"):
        """Save duplicate detection results to JSON"""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # If no duplicates found, still create file with empty groups
        if not self.duplicates:
            self.duplicates = []
        
        # Get unique source Excel files from all groups
        source_excels = set()
        source_sheets = set()
        for group in self.duplicates:
            if group.get('source_excel'):
                source_excels.add(group['source_excel'])
            if group.get('source_sheet'):
                source_sheets.add(group['source_sheet'])
        
        results = {
            'metadata': {
                'source_file': str(self.json_path),
                'detection_date': str(Path(__file__).stat().st_mtime),
                'total_groups': len(self.duplicates),
                'total_items': sum(g['count'] for g in self.duplicates),
                'source_excel_files': sorted(list(source_excels)),
                'source_sheets': sorted(list(source_sheets))
            },
            'duplicate_groups': self.duplicates
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Saved duplicate detection results to: {output_file}")
        return output_file

if __name__ == "__main__":
    detector = DuplicateDetector()
    duplicates = detector.detect_duplicates(
        name_similarity_threshold=0.85,
        amount_similarity_threshold=0.95,
        min_amount=100000,
        source_filter="Annex A-1"  # Only check Annex A-1 projects
    )
    detector.duplicates = duplicates
    detector.save_results()
    
    # Print summary
    print(f"\n📊 Summary:")
    print(f"   Total duplicate groups: {len(duplicates)}")
    print(f"   Total items in groups: {sum(g['count'] for g in duplicates)}")
    print(f"   Total amount: ₱{sum(g['total_amount'] for g in duplicates):,.0f}")
    
    # Show top 5 groups
    if duplicates:
        print(f"\n🔝 Top 5 Duplicate Groups:")
        sorted_groups = sorted(duplicates, key=lambda x: x['total_amount'], reverse=True)[:5]
        for i, group in enumerate(sorted_groups, 1):
            print(f"\n   {i}. Group #{group['group_id']} ({group['count']} items, ₱{group['total_amount']:,.0f})")
            for item in group['items'][:3]:  # Show first 3 items
                name = item.get('description', '') or item.get('name', '')[:60]
                amount = item.get('final_amount', 0) or item.get('original_amount', 0)
                dept = item.get('department_id', 'UNKNOWN')
                print(f"      - {name}... (₱{amount:,.0f}, {dept})")
            if len(group['items']) > 3:
                print(f"      ... and {len(group['items']) - 3} more")


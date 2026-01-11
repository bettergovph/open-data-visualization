import pandas as pd
import re
import sys
import json
import os
import numpy as np
from scipy.stats import chi2_contingency
from pathlib import Path

# Configuration
DATA_DIR = Path('/home/joebert/open-data-visualization/data/parquet')
OUTPUT_FILE = Path('/home/joebert/open-data-visualization/static/data/condition_risks.json')

REHAB_KEYWORDS = [
    # Rehabilitation / Repair
    'rehabilitation', 'major repair', 'reconstruction', 'asset preservation', 
    'preventive maintenance', 'restoration', 'upgrading', 'improvement',
    # New Construction
    'construction', 'widening', 'concreting', 'asphalting',
    # General Road Keywords
    'road', 'highway', 'bridge', 'drainage', 'pavement', 'overlay'
]

# Canonical Region names for extraction
REGION_NAMES = [
    'National Capital Region', 'Cordillera Administrative Region',
    'Ilocos Region', 'Region I', 'Cagayan Valley', 'Region II',
    'Central Luzon', 'Region III', 'CALABARZON', 'Region IV-A',
    'MIMAROPA', 'Region IV-B', 'Bicol Region', 'Region V',
    'Western Visayas', 'Region VI', 'Central Visayas', 'Region VII',
    'Eastern Visayas', 'Region VIII', 'Zamboanga Peninsula', 'Region IX',
    'Northern Mindanao', 'Region X', 'Davao Region', 'Region XI',
    'SOCCSKSARGEN', 'Region XII', 'Caraga', 'Region XIII',
    'Bangsamoro Autonomous Region', 'BARMM', 'Negros Island Region', 'NIR'
]

def extract_region_from_path(path):
    """Extracts Region name from a hierarchy path string."""
    if not path or pd.isna(path):
        return None
    for reg in REGION_NAMES:
        if reg.lower() in path.lower():
            return reg
    return None

# Helper Functions
def extract_all_chainage_ranges(name: str):
    """Extract all chainage ranges from name"""
    if not name:
        return []

    ranges = []
    seen = set()

    def parse_number(value) -> float:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        cleaned = str(value).replace(',', '')
        try:
            return float(cleaned)
        except ValueError:
            cleaned = re.sub(r'[^\d\.\-]', '', cleaned)
            return float(cleaned) if cleaned else 0.0

    def add_range(start_km, start_m, end_km, end_m):
        key = (
            float(parse_number(start_km)),
            float(parse_number(start_m)),
            float(parse_number(end_km)),
            float(parse_number(end_m))
        )
        if key not in seen:
            ranges.append(key)
            seen.add(key)

    dash = r'[-–—]'
    number = r'\d+(?:[.,]\d+)?'

    pattern_k = rf'K({number})\s*\+\s*\(?(-?{number})\)?\s*{dash}\s*K({number})\s*\+\s*\(?(-?{number})\)?'
    for match in re.finditer(pattern_k, name, re.IGNORECASE):
        add_range(match.group(1), match.group(2), match.group(3), match.group(4))

    return ranges

def to_meters(km, m):
    return km * 1000 + m

def overlaps(start1, end1, start2, end2):
    return max(start1, start2) < min(end1, end2)

def generate_cache():
    print("Loading data...")
    try:
        # Use DPWH 2026 Leaf Nodes as the primary project source (FY 2026)
        dpwh_2026 = pd.read_parquet(DATA_DIR / 'dpwh_2026_leaf_nodes.parquet')
        road_inv = pd.read_parquet(DATA_DIR / 'road_inventory_2025.parquet')
        sect_inv = pd.read_parquet(DATA_DIR / 'road_section_inventory_2025.parquet')
        road_cond = pd.read_parquet(DATA_DIR / 'road_condition_2025.parquet')
    except Exception as e:
        print(f"Error reading parquet files: {e}")
        return

    print(f"Loaded {len(dpwh_2026)} DPWH 2026 leaf nodes.")
    
    # Pre-process DPWH 2026 data: extract Region from path
    # Filter to rows with actual project data (amount > 0)
    dpwh_2026['extracted_region'] = dpwh_2026['path'].apply(extract_region_from_path)
    projects = dpwh_2026[dpwh_2026['amount'].notna() & (dpwh_2026['amount'] > 0)].copy()
    projects = projects.rename(columns={'value': 'project_name'})
    projects['region'] = projects['extracted_region']
    print(f"Filtered to {len(projects)} project rows with amount > 0.")



    # 1. Build Road Lookups
    print("Building road lookups...")
    # Road Name -> Road ID
    road_lookup = {}
    for _, row in road_inv.iterrows():
        name = str(row['Road Name']).lower().strip()
        rid = row['Road ID']
        # Filter out very short or generic names if needed
        if len(name) > 4:
            road_lookup[name] = rid
    
    # Add common highway aliases (many DPWH projects use these names)
    # Map project naming convention -> inventory naming convention
    HIGHWAY_ALIASES = {
        'maharlika highway': ['daang maharlika'],
        'manila north road': ['macarthur hwy', 'manila north', 'north rd'],
        'manila south road': ['south superhighway', 'south rd'],
        'pan-philippine highway': ['daang maharlika', 'pan-philippine'],
    }
    
    # Try to find a road ID for aliases by searching existing names
    for alias, patterns in HIGHWAY_ALIASES.items():
        if alias not in road_lookup:
            # Try to find a matching road in existing lookup
            for existing_name, rid in list(road_lookup.items()):
                for pattern in patterns:
                    if pattern in existing_name:
                        road_lookup[alias] = rid
                        break
    
    print(f"  Road lookup size: {len(road_lookup)}")
    
    # Road ID -> List of Section IDs
    road_to_sections = {}
    for _, row in sect_inv.iterrows():
        rid = row['Road ID']
        sid = row['Road Section ID']
        if rid not in road_to_sections:
            road_to_sections[rid] = []
        road_to_sections[rid].append(sid)
        
    # Section ID -> List of Condition Segments
    section_to_conditions = {}
    
    # Track all Bad/Poor segments to see if they get covered
    # stored as (SectionID, Start, End) -> {usage_count: 0, details: row}
    # Using a unique key for each segment: string "SectionID|Start|End"
    bad_poor_registry = {}
    
    for _, row in road_cond.iterrows():
        sid = row['Road Section ID']
        if sid not in section_to_conditions:
            section_to_conditions[sid] = []
        
        start_m = row['Start (m)']
        end_m = row['End (m)']
        cond = row['VCR']
        
        segment_entry = {
            'start': min(start_m, end_m),
            'end': max(start_m, end_m),
            'condition': cond,
            'original_row': row.to_dict()
        }
        
        # Add ID for tracking
        segment_id = f"{sid}|{segment_entry['start']}|{segment_entry['end']}"
        segment_entry['id'] = segment_id
        
        section_to_conditions[sid].append(segment_entry)
        
        if cond in ['Bad', 'Poor']:
            bad_poor_registry[segment_id] = {
                'covered': False,
                'data': row.to_dict()
            }

    # 2. Filter Rehabilitation Projects
    print("Filtering rehabilitation projects...")
    # Include keywords
    mask = projects['project_name'].str.contains('|'.join(REHAB_KEYWORDS), case=False, na=False)
    # Exclude non-road projects (lighting, buildings, etc.)
    EXCLUDE_KEYWORDS = ['lighting', 'building', 'office', 'warehouse', 'storage', 'water supply', 'waterworks']
    exclude_mask = projects['project_name'].str.contains('|'.join(EXCLUDE_KEYWORDS), case=False, na=False)
    potential_rehabs = projects[mask & ~exclude_mask]
    print(f"Found {len(potential_rehabs)} potential rehabilitation projects.")

    # 3. Analyze Projects
    print("Analyzing projects...")
    
    results = {
        'generated_at': pd.Timestamp.now().isoformat(),
        'low_priority_projects': [], # Good/Fair
        'no_data_projects': [],      # Gamble
        'justified_projects': [],    # Bad/Poor (Good decisions)
        'unaddressed_assets': [],    # Bad/Poor with no project
        'stats': {
            'total_rehabs_scanned': len(potential_rehabs),
            'matches_found': 0,
            'low_priority_count': 0,
            'no_data_count': 0,
            'justified_count': 0,
            'unaddressed_count': 0
        }
    }
    
    # Pre-sort road names by length for safer matching (longest first)
    sorted_road_names = sorted(road_lookup.keys(), key=len, reverse=True)
    
    count = 0 
    for _, row in potential_rehabs.iterrows():
        count += 1
        if count % 1000 == 0:
            print(f"Processed {count} projects...")
            
        name = row['project_name']
        name_lower = name.lower()
        amount = row.get('amount', 0)
        region = row.get('region')
        
        # Only analyze if it has chainage info
        ranges = extract_all_chainage_ranges(name)
        if not ranges:
            continue
            
        # Match Road Name
        matched_road_id = None
        matched_road_name = None
        
        # Optimization: Scan sorted road names
        for r_name in sorted_road_names:
            if r_name in name_lower:
                matched_road_name = r_name
                matched_road_id = road_lookup[r_name]
                break
        
        if matched_road_id:
            results['stats']['matches_found'] += 1
            
            # Check Condition
            sections = road_to_sections.get(matched_road_id, [])
            conditions_found = set()
            has_overlap = False
            
            for (start_km, start_m, end_km, end_m) in ranges:
                p_start = to_meters(start_km, start_m)
                p_end = to_meters(end_km, end_m)
                
                # Check ALL sections for this road
                for sid in sections:
                    conds = section_to_conditions.get(sid, [])
                    for c in conds:
                        if overlaps(p_start, p_end, c['start'], c['end']):
                            val = c['condition']
                            if val: # Ensure not None
                                conditions_found.add(val)
                            has_overlap = True
                            
                            # Mark as covered if tracked
                            if 'id' in c and c['id'] in bad_poor_registry:
                                bad_poor_registry[c['id']]['covered'] = True
            
            # Region is now extracted directly from the path column
            final_region = region if pd.notna(region) and region else 'Unknown'
            
            entry = {
                'id': 'N/A',  # DPWH 2026 hierarchy doesn't have project_id
                'project_name': name,
                'amount': amount,
                'region': final_region,
                'road_name': matched_road_name,
                'road_id': matched_road_id,
                'conditions': list(conditions_found)
            }
            
            if not has_overlap:
                # Flag: No Condition Data (Gamble)
                entry['remark'] = 'High Risk (No Data)'
                results['no_data_projects'].append(entry)
                results['stats']['no_data_count'] += 1
            else:
                 is_bad_poor_present = 'Bad' in conditions_found or 'Poor' in conditions_found
                 is_good_fair_present = 'Good' in conditions_found or 'Fair' in conditions_found
                 
                 if is_good_fair_present and not is_bad_poor_present:
                     # Purely Good/Fair - Highest Risk (Wasteful)
                     entry['remark'] = 'Highest Risk (Redundant)'
                     results['low_priority_projects'].append(entry)
                     results['stats']['low_priority_count'] += 1
                 else:
                     # Contains Bad or Poor - Justified!
                     # We don't display these in the main list (user focused on risks), but we track for stats
                     entry['remark'] = 'Low Risk (Justified)'
                     results['justified_projects'].append(entry)
                     results['stats']['justified_count'] += 1

    # 4. Identify Unaddressed Bad/Poor
    print("Identifying unaddressed assets...")
    for seg_id, info in bad_poor_registry.items():
        if not info['covered']:
            data = info['data']
            results['unaddressed_assets'].append({
                'project_name': '(No Project Assigned)',
                'road_name': f"{data.get('Road Section ID')} ({data.get('District Engineering Office')})",
                'amount': 0,
                'region': data.get('Region'),
                'conditions': [data.get('VCR')],
                'remark': f"Unaddressed {data.get('VCR')} Condition",
                'segment_details': f"{data.get('Start (m)')} - {data.get('End (m)')}"
            })
    
    results['stats']['unaddressed_count'] = len(results['unaddressed_assets'])

    # Create Stats Helper
    def compute_category_stats(items):
        total_amount = 0
        by_region = {}
        
        for item in items:
            amt = item.get('amount', 0) or 0
            reg = item.get('region', 'Unknown')
            if not reg: reg = 'Unknown'
            
            total_amount += amt
            
            if reg not in by_region:
                by_region[reg] = {'count': 0, 'amount': 0}
            by_region[reg]['count'] += 1
            by_region[reg]['amount'] += amt
            
        # All Regions by Count (Expanded to All)
        top_regions = sorted(by_region.items(), key=lambda x: x[1]['count'], reverse=True)
        return {
            'count': len(items),
            'total_amount': total_amount,
            'top_regions': top_regions # List of (Region, {count, amount})
        }

    # Sort results
    results['low_priority_projects'].sort(key=lambda x: x.get('amount', 0) or 0, reverse=True)
    results['no_data_projects'].sort(key=lambda x: x.get('amount', 0) or 0, reverse=True)
    results['unaddressed_assets'].sort(key=lambda x: x.get('road_name', ''), reverse=False)

    # Compute Detailed Stats
    results['stats']['details'] = {
        'low_priority': compute_category_stats(results['low_priority_projects']),
        'no_data': compute_category_stats(results['no_data_projects']),
        'justified': compute_category_stats(results['justified_projects']),
        'unaddressed': compute_category_stats(results['unaddressed_assets'])
    }
    
    # Calculate Totals
    total_rehab_amount = (
        results['stats']['details']['low_priority']['total_amount'] +
        results['stats']['details']['no_data']['total_amount'] +
        results['stats']['details']['justified']['total_amount']
    )
    results['stats']['financial_total'] = total_rehab_amount

    # --- Statistical Significance (Chi-Square) ---
    print("Performing Chi-Square Analysis...")
    
    # 1. Build Contingency Table (Region x Category)
    regions = set()
    cat_counts = {'justified': {}, 'low_priority': {}, 'no_data': {}, 'unaddressed': {}}
    
    for r in results['justified_projects']:
        reg = r.get('region') or 'Unknown'
        regions.add(reg)
        cat_counts['justified'][reg] = cat_counts['justified'].get(reg, 0) + 1
        
    for r in results['low_priority_projects']:
        reg = r.get('region') or 'Unknown'
        regions.add(reg)
        cat_counts['low_priority'][reg] = cat_counts['low_priority'].get(reg, 0) + 1

    for r in results['no_data_projects']:
        reg = r.get('region') or 'Unknown'
        regions.add(reg)
        cat_counts['no_data'][reg] = cat_counts['no_data'].get(reg, 0) + 1

    for r in results['unaddressed_assets']:
        # Unaddressed assets might have different keys, check visualization.py usually has 'region'
        reg = r.get('region') or 'Unknown'
        regions.add(reg)
        cat_counts['unaddressed'][reg] = cat_counts['unaddressed'].get(reg, 0) + 1
        
    sorted_regions = sorted(list(regions))
    
    # Create Matrix
    observed = []
    for reg in sorted_regions:
        row = [
            cat_counts['justified'].get(reg, 0),
            cat_counts['low_priority'].get(reg, 0),
            cat_counts['no_data'].get(reg, 0),
            cat_counts['unaddressed'].get(reg, 0)
        ]
        observed.append(row)
        
    observed_arr = np.array(observed)
    
    if observed_arr.sum() > 0:
        chi2, p, dof, expected = chi2_contingency(observed_arr)
        
        # Calculate Standardized Residuals
        with np.errstate(divide='ignore', invalid='ignore'):
            residuals = (observed_arr - expected) / np.sqrt(expected)
            residuals = np.nan_to_num(residuals)
            
        anomalies = []
        cols = ['Low Risk', 'Highest Risk', 'High Risk', 'Medium Risk'] 
        
        for i, reg in enumerate(sorted_regions):
            for j, col_name in enumerate(cols):
                # User request: exclude Low Risk anomalies
                if col_name == 'Low Risk':
                    continue

                res_val = residuals[i][j]
                if res_val > 2.0: # Significantly HIGHER
                    anomalies.append({
                        'region': reg,
                        'category': col_name,
                        'residual': round(float(res_val), 2),
                        'observed': int(observed[i][j]),
                        'expected': round(float(expected[i][j]), 1),
                        'significance': 'High' if res_val > 4.0 else 'Moderate'
                    })
        
        results['stats']['chi_square'] = {
            'p_value': float(p),
            'significant': bool(p < 0.05),
            'anomalies': anomalies
        }
        print(f"  Chi-Square p-value: {p:.5f}")
        print(f"  Found {len(anomalies)} statistical anomalies.")
        
    else:
        results['stats']['chi_square'] = {'significant': False, 'reason': 'Insufficient Data'}

    # Create unified 'matches' list for frontend
    results['matches'] = (
        results['justified_projects'] + 
        results['low_priority_projects'] + 
        results['no_data_projects']
    )
    
    # Keep individual lists for detailed stats if needed, or rely on 'details' having top regions
    # del results['justified_projects']
    # del results['low_priority_projects']
    # del results['no_data_projects']
    
    print(f"Analysis Complete.")
    print(f"  Flagged Low Priority: {results['stats']['low_priority_count']}")
    print(f"  Flagged No Data: {results['stats']['no_data_count']}")
    
    # Save to JSON
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    print(f"Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    generate_cache()

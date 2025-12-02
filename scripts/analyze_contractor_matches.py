#!/usr/bin/env python3
"""
Analyze contractor matches for Elizaldy Co and Edwin Gardiola.
This script counts all projects with contractors related to these congressmen
and compares the numbers to see if they're being matched correctly.
"""

import pandas as pd
from pathlib import Path
from collections import defaultdict
import re

PARQUET_DIR = Path(__file__).parent.parent / 'data' / 'parquet'
CLASSIFIED_PARQUET = PARQUET_DIR / 'integrated_projects_classified.parquet'
INTEGRATED_PARQUET = PARQUET_DIR / 'integrated_projects.parquet'
DIME_PARQUET = PARQUET_DIR / 'dime_projects.parquet'
PHILGEPS_PARQUET = PARQUET_DIR / 'philgeps_contracts.parquet'
MICROSITE_PARQUET = PARQUET_DIR / 'infrawatch_projects.parquet'
TRANSPARENCY_PARQUET = PARQUET_DIR / 'transparency_projects.parquet'
FLOOD_PARQUET = PARQUET_DIR / 'flood_projects.parquet'
CONTRACTOR_PARQUET = PARQUET_DIR / 'contractor_dynasty_matches.parquet'
POLITICIAN_CONTRACTORS_PARQUET = PARQUET_DIR / 'politician_contractors.parquet'

# Known contractors for Elizaldy Co and Edwin Gardiola
ELIZALDY_CO_CONTRACTORS = [
    'SUNWEST', 'SUN WEST', 'SUNWEST CONSTRUCTION', 'SUN WEST CONSTRUCTION',
    'FS CO', 'FS CO BUILDERS', 'FS CO BUILDERS AND SUPPLY',
    'F.S. CO', 'F.S. CO BUILDERS'
]

EDWIN_GARDIOLA_CONTRACTORS = [
    'NEWINGTON', 'NEWINGTON BUILDERS', 'NEWINGTON BUILDERS INC',
    'LOUREL', 'LOUREL CORP', 'LOUREL CORPORATION',
    'S-ANG', 'S-ANG GENERAL', 'S-ANG GENERAL CONSTRUCTION',
    'SANG', 'SANG GENERAL', 'SANG GENERAL CONSTRUCTION'
]

def normalize_contractor_name(name):
    """Normalize contractor name for matching"""
    if not name:
        return ''
    # Remove common suffixes and normalize
    name = str(name).upper().strip()
    name = re.sub(r'\s+', ' ', name)  # Normalize spaces
    name = re.sub(r'[.,]', '', name)  # Remove punctuation
    return name

def load_contractor_links():
    """Load contractor links from parquet files"""
    contractors_by_congressman = defaultdict(set)
    
    # Load from contractor_dynasty_matches.parquet
    if CONTRACTOR_PARQUET.exists():
        try:
            df = pd.read_parquet(CONTRACTOR_PARQUET)
            for _, row in df.iterrows():
                first_name = str(row.get('dynasty_first_name', '')).strip()
                last_name = str(row.get('dynasty_last_name', '')).strip()
                company = normalize_contractor_name(row.get('company_name', ''))
                if first_name and last_name and company:
                    key = f"{first_name} {last_name}".upper()
                    contractors_by_congressman[key].add(company)
            print(f"✅ Loaded {len(df)} contractor links from contractor_dynasty_matches.parquet")
        except Exception as e:
            print(f"⚠️  Failed to load from contractor_dynasty_matches.parquet: {e}")
    
    # Load from politician_contractors.parquet
    if POLITICIAN_CONTRACTORS_PARQUET.exists():
        try:
            df = pd.read_parquet(POLITICIAN_CONTRACTORS_PARQUET)
            for _, row in df.iterrows():
                # Try different column name variations
                first_name = str(row.get('first_name') or row.get('dynasty_first_name') or row.get('politician_first_name') or '').strip()
                last_name = str(row.get('last_name') or row.get('dynasty_last_name') or row.get('politician_last_name') or '').strip()
                company = normalize_contractor_name(row.get('company_name') or row.get('contractor_name') or '')
                if first_name and last_name and company:
                    key = f"{first_name} {last_name}".upper()
                    contractors_by_congressman[key].add(company)
            print(f"✅ Loaded {len(df)} contractor links from politician_contractors.parquet")
        except Exception as e:
            print(f"⚠️  Failed to load from politician_contractors.parquet: {e}")
    
    return contractors_by_congressman

def find_matching_projects(df, all_contractor_names, source_name='Unknown'):
    """Find projects with matching contractors in a dataframe"""
    matching_projects = []
    
    # Define possible contractor column names by source
    # Check what columns are actually available in the dataframe
    available_columns = set(df.columns) if hasattr(df, 'columns') else set()
    
    # Standard column name (used in classified/integrated parquet)
    contractor_columns = ['contractor']
    
    # Add source-specific column names based on what's available
    if 'contractor_name' in available_columns:
        contractor_columns.append('contractor_name')
    if 'awardee_name' in available_columns:
        contractor_columns.append('awardee_name')
    if 'philgeps_awardee_name' in available_columns:
        contractor_columns.append('philgeps_awardee_name')
    if 'supplier_name' in available_columns:
        contractor_columns.append('supplier_name')
    if 'vendor_name' in available_columns:
        contractor_columns.append('vendor_name')
    if 'company_name' in available_columns:
        contractor_columns.append('company_name')
    # For DIME, check for 'contractors' (plural) which might be a list
    if 'contractors' in available_columns:
        contractor_columns.append('contractors')
    
    # Debug: Show what columns we're checking
    if source_name not in ['Classified', 'Integrated (all sources)']:
        print(f"      Checking columns: {contractor_columns}")
        print(f"      Available columns with 'contractor' or 'awardee': {[c for c in available_columns if 'contractor' in c.lower() or 'awardee' in c.lower() or 'supplier' in c.lower()][:10]}")
    
    for _, project in df.iterrows():
        # Try all possible contractor column names
        contractor = ''
        contractor_source_col = None
        
        for col in contractor_columns:
            if col in project.index or col in project:
                contractor_val = project.get(col, '')
                
                # Handle list values (e.g., DIME's 'contractors' field)
                if isinstance(contractor_val, list):
                    if contractor_val:
                        contractor_val = ', '.join(str(v) for v in contractor_val if v)
                    else:
                        contractor_val = ''
                
                if contractor_val and str(contractor_val).strip() and str(contractor_val).upper() != 'N/A':
                    contractor = normalize_contractor_name(contractor_val)
                    contractor_source_col = col
                    break
        
        if not contractor:
            continue
        
        # Check if contractor matches any of our target contractors
        matched_contractor = None
        for target_contractor in all_contractor_names:
            if target_contractor in contractor or contractor in target_contractor:
                matched_contractor = target_contractor
                break
        
        if matched_contractor:
            # Determine source
            source = 'Unknown'
            sources_list = project.get('sources_list', [])
            if isinstance(sources_list, list) and sources_list:
                source = sources_list[0]
            elif project.get('source'):
                source = project.get('source')
            elif project.get('_source'):
                source = project.get('_source')
            
            # Get original contractor value for display
            original_contractor = project.get(contractor_source_col, '') if contractor_source_col else project.get('contractor', '')
            if isinstance(original_contractor, list):
                original_contractor = ', '.join(str(v) for v in original_contractor if v)
            
            matching_projects.append({
                'contractor': original_contractor,
                'contractor_normalized': contractor,
                'matched_contractor': matched_contractor,
                'contractor_congressman': project.get('contractor_congressman', ''),
                'district_congressman': project.get('district_congressman', ''),
                'project_name': project.get('project_name', ''),
                'amount': project.get('amount', 0),
                'location': project.get('location', ''),
                'source': source,
                'sources_list': sources_list if isinstance(sources_list, list) else [],
                'contractor_column': contractor_source_col  # Track which column was used
            })
    
    return matching_projects

def analyze_contractor_matches():
    """Analyze contractor matches for Elizaldy Co and Edwin Gardiola"""
    print("🔍 Analyzing contractor matches for Elizaldy Co and Edwin Gardiola...")
    
    # Load contractor links
    print("\n📥 Loading contractor links...")
    contractors_by_congressman = load_contractor_links()
    
    # Find Elizaldy Co and Edwin Gardiola in contractor links
    elizaldy_key = None
    gardiola_key = None
    
    for key in contractors_by_congressman.keys():
        # Try to find Elizaldy Co - check for variations
        if 'ELIZALDY' in key and 'CO' in key:
            elizaldy_key = key
        # Also check for "SALCEDO CO" which might be the full name
        elif 'SALCEDO' in key and 'CO' in key:
            elizaldy_key = key
        
        # Try to find Edwin Gardiola - check for variations
        if 'EDWIN' in key and 'GARDIOLA' in key:
            gardiola_key = key
        # Also check for "TIRSO" or "LOLENG" which might be in the name
        elif 'TIRSO' in key and 'GARDIOLA' in key:
            gardiola_key = key
        elif 'LOLENG' in key and 'GARDIOLA' in key:
            gardiola_key = key
    
    print(f"\n📋 Contractor Links Found:")
    if elizaldy_key:
        print(f"   ✅ Elizaldy Co: {len(contractors_by_congressman[elizaldy_key])} contractors")
        print(f"      Key: {elizaldy_key}")
        print(f"      {', '.join(sorted(contractors_by_congressman[elizaldy_key]))}")
    else:
        print(f"   ❌ Elizaldy Co: NOT FOUND in contractor links")
        print(f"   Available keys with 'CO': {[k for k in contractors_by_congressman.keys() if 'CO' in k]}")
    
    if gardiola_key:
        print(f"   ✅ Edwin Gardiola: {len(contractors_by_congressman[gardiola_key])} contractors")
        print(f"      Key: {gardiola_key}")
        print(f"      {', '.join(sorted(contractors_by_congressman[gardiola_key]))}")
    else:
        print(f"   ❌ Edwin Gardiola: NOT FOUND in contractor links")
        print(f"   Available keys with 'GARDIOLA': {[k for k in contractors_by_congressman.keys() if 'GARDIOLA' in k]}")
    
    # Load projects from ALL sources
    print(f"\n📥 Loading projects from ALL sources...")
    all_dfs = []
    source_counts = {}
    
    # Try classified first (deduplicated)
    if CLASSIFIED_PARQUET.exists():
        df_classified = pd.read_parquet(CLASSIFIED_PARQUET)
        all_dfs.append(('Classified (deduplicated)', df_classified))
        source_counts['Classified'] = len(df_classified)
        print(f"   ✅ Classified: {len(df_classified)} projects")
    
    # Try integrated (all projects before deduplication)
    if INTEGRATED_PARQUET.exists():
        df_integrated = pd.read_parquet(INTEGRATED_PARQUET)
        all_dfs.append(('Integrated (all sources)', df_integrated))
        source_counts['Integrated'] = len(df_integrated)
        print(f"   ✅ Integrated: {len(df_integrated)} projects")
    
    # Try individual source files
    source_files = [
        ('DIME', DIME_PARQUET),
        ('PhilGEPS', PHILGEPS_PARQUET),
        ('Microsite', MICROSITE_PARQUET),
        ('Transparency', TRANSPARENCY_PARQUET),
        ('SSP/Flood', FLOOD_PARQUET),
    ]
    
    for source_name, parquet_path in source_files:
        if parquet_path.exists():
            try:
                df_source = pd.read_parquet(parquet_path)
                all_dfs.append((source_name, df_source))
                source_counts[source_name] = len(df_source)
                print(f"   ✅ {source_name}: {len(df_source)} projects")
            except Exception as e:
                print(f"   ⚠️  {source_name}: Failed to load ({e})")
    
    if not all_dfs:
        print(f"\n❌ No parquet files found!")
        return
    
    # Build contractor name variations
    all_contractor_names = set()
    if elizaldy_key:
        all_contractor_names.update(contractors_by_congressman[elizaldy_key])
    if gardiola_key:
        all_contractor_names.update(contractors_by_congressman[gardiola_key])
    
    # Also add known contractor patterns
    all_contractor_names.update([normalize_contractor_name(c) for c in ELIZALDY_CO_CONTRACTORS])
    all_contractor_names.update([normalize_contractor_name(c) for c in EDWIN_GARDIOLA_CONTRACTORS])
    
    print(f"\n🔍 Searching for projects with these contractors...")
    print(f"   Total contractor name variations: {len(all_contractor_names)}")
    
    # For analysis, we want to check ALL sources separately to see if there are more projects
    # that aren't in the classified parquet
    print(f"\n📊 Analyzing ALL sources separately...")
    
    # Store results from each source
    all_matching_projects = []
    source_results = {}
    
    # Analyze classified first
    if CLASSIFIED_PARQUET.exists():
        print(f"\n🔍 Analyzing Classified parquet...")
        matching = find_matching_projects(df_classified, all_contractor_names, 'Classified')
        all_matching_projects.extend(matching)
        source_results['Classified'] = len(matching)
        print(f"   Found {len(matching)} matching projects in Classified")
    
    # Analyze each individual source
    for source_name, df_source in all_dfs:
        if source_name == 'Classified (deduplicated)':
            continue  # Already analyzed
        
        print(f"\n🔍 Analyzing {source_name}...")
        matching = find_matching_projects(df_source, all_contractor_names, source_name)
        all_matching_projects.extend(matching)
        source_results[source_name] = len(matching)
        print(f"   Found {len(matching)} matching projects in {source_name}")
    
    # Remove duplicates (same project from multiple sources)
    # Use project_name + contractor + amount as unique key
    unique_projects = {}
    for proj in all_matching_projects:
        key = (
            str(proj.get('project_name', '')).upper(),
            str(proj.get('contractor', '')).upper(),
            str(proj.get('amount', ''))
        )
        if key not in unique_projects:
            unique_projects[key] = proj
        else:
            # Merge sources
            existing = unique_projects[key]
            existing_sources = existing.get('sources_list', [])
            if isinstance(existing_sources, list):
                if proj.get('source', 'Unknown') not in existing_sources:
                    existing_sources.append(proj.get('source', 'Unknown'))
            else:
                existing['sources_list'] = [existing.get('source', 'Unknown'), proj.get('source', 'Unknown')]
    
    matching_projects = list(unique_projects.values())
    print(f"\n📊 Total unique projects across all sources: {len(matching_projects)}")
    
    print(f"\n📋 Projects by source (before deduplication):")
    for source, count in sorted(source_results.items(), key=lambda x: -x[1]):
        print(f"   - {source}: {count} projects")
    
    # Show breakdown by source for unique projects
    projects_by_source = defaultdict(int)
    for proj in matching_projects:
        sources = proj.get('sources_list', [])
        if isinstance(sources, list):
            for source in sources:
                projects_by_source[source] += 1
        else:
            projects_by_source[proj.get('source', 'Unknown')] += 1
    
    print(f"\n📊 Unique projects by source:")
    for source, count in sorted(projects_by_source.items(), key=lambda x: -x[1]):
        print(f"   - {source}: {count} projects")
    
    # Analyze by congressman assignment
    print("\n" + "="*80)
    print("📊 CONTRACTOR MATCH ANALYSIS")
    print("="*80)
    
    # Group by contractor
    by_contractor = defaultdict(lambda: {
        'total': 0,
        'by_congressman': defaultdict(int),
        'total_amount': 0,
        'sample_projects': []
    })
    
    for proj in matching_projects:
        contractor = proj['matched_contractor']
        by_contractor[contractor]['total'] += 1
        assigned_cm = proj['contractor_congressman'] or proj['district_congressman'] or 'Unassigned'
        by_contractor[contractor]['by_congressman'][assigned_cm] += 1
        
        # Parse amount
        amount = proj['amount']
        if isinstance(amount, str):
            amount_str = amount.replace('₱', '').replace(',', '').strip()
            try:
                amount = float(amount_str)
            except:
                amount = 0
        else:
            amount = float(amount) if amount else 0
        
        by_contractor[contractor]['total_amount'] += amount
        
        if len(by_contractor[contractor]['sample_projects']) < 3:
            by_contractor[contractor]['sample_projects'].append(proj)
    
    print(f"\n📋 Projects by Contractor:")
    for contractor in sorted(by_contractor.keys()):
        stats = by_contractor[contractor]
        print(f"\n   🏢 {contractor}:")
        print(f"      Total projects: {stats['total']}")
        print(f"      Total amount: ₱{stats['total_amount']:,.2f}")
        print(f"      Assigned to:")
        for cm, count in sorted(stats['by_congressman'].items(), key=lambda x: -x[1]):
            print(f"         - {cm}: {count} projects")
        
        # Show sample projects
        if stats['sample_projects']:
            print(f"      Sample projects:")
            for sample in stats['sample_projects']:
                print(f"         - {sample['project_name'][:60]}...")
                print(f"           Contractor: {sample['contractor']}")
                print(f"           Assigned to: {sample['contractor_congressman'] or sample['district_congressman'] or 'Unassigned'}")
    
    # Check for Elizaldy Co and Gardiola specifically
    print("\n" + "="*80)
    print("🔍 ELIZALDY CO & EDWIN GARDIOLA SPECIFIC ANALYSIS")
    print("="*80)
    
    elizaldy_projects = [p for p in matching_projects if any(c in p['matched_contractor'] for c in ['SUNWEST', 'FS CO', 'F.S. CO'])]
    gardiola_projects = [p for p in matching_projects if any(c in p['matched_contractor'] for c in ['NEWINGTON', 'LOUREL', 'S-ANG', 'SANG'])]
    
    print(f"\n👤 Elizaldy Co related contractors:")
    print(f"   Total projects: {len(elizaldy_projects)}")
    elizaldy_by_cm = defaultdict(int)
    elizaldy_total_amount = 0
    for proj in elizaldy_projects:
        cm = proj['contractor_congressman'] or proj['district_congressman'] or 'Unassigned'
        elizaldy_by_cm[cm] += 1
        amount = proj['amount']
        if isinstance(amount, str):
            amount_str = amount.replace('₱', '').replace(',', '').strip()
            try:
                amount = float(amount_str)
            except:
                amount = 0
        else:
            amount = float(amount) if amount else 0
        elizaldy_total_amount += amount
    
    print(f"   Total amount: ₱{elizaldy_total_amount:,.2f}")
    print(f"   Assigned to:")
    for cm, count in sorted(elizaldy_by_cm.items(), key=lambda x: -x[1]):
        status = "✅" if 'CO' in cm.upper() and 'ELIZALDY' in cm.upper() else "❌"
        print(f"      {status} {cm}: {count} projects")
    
    if 'ELIZALDY' not in str(elizaldy_by_cm.keys()).upper() and 'CO' not in str(elizaldy_by_cm.keys()).upper():
        print(f"\n   ⚠️  ISSUE: No projects assigned to Elizaldy Co!")
        print(f"   Sample projects:")
        for proj in elizaldy_projects[:5]:
            print(f"      - Contractor: {proj['contractor']}")
            print(f"        Assigned to: {proj['contractor_congressman'] or proj['district_congressman'] or 'Unassigned'}")
    
    print(f"\n👤 Edwin Gardiola related contractors:")
    print(f"   Total projects: {len(gardiola_projects)}")
    gardiola_by_cm = defaultdict(int)
    gardiola_total_amount = 0
    for proj in gardiola_projects:
        cm = proj['contractor_congressman'] or proj['district_congressman'] or 'Unassigned'
        gardiola_by_cm[cm] += 1
        amount = proj['amount']
        if isinstance(amount, str):
            amount_str = amount.replace('₱', '').replace(',', '').strip()
            try:
                amount = float(amount_str)
            except:
                amount = 0
        else:
            amount = float(amount) if amount else 0
        gardiola_total_amount += amount
    
    print(f"   Total amount: ₱{gardiola_total_amount:,.2f}")
    print(f"   Assigned to:")
    for cm, count in sorted(gardiola_by_cm.items(), key=lambda x: -x[1]):
        status = "✅" if 'GARDIOLA' in cm.upper() and 'EDWIN' in cm.upper() else "❌"
        print(f"      {status} {cm}: {count} projects")
    
    if 'GARDIOLA' not in str(gardiola_by_cm.keys()).upper() and 'EDWIN' not in str(gardiola_by_cm.keys()).upper():
        print(f"\n   ⚠️  ISSUE: No projects assigned to Edwin Gardiola!")
        print(f"   Sample projects:")
        for proj in gardiola_projects[:5]:
            print(f"      - Contractor: {proj['contractor']}")
            print(f"        Assigned to: {proj['contractor_congressman'] or proj['district_congressman'] or 'Unassigned'}")

if __name__ == '__main__':
    analyze_contractor_matches()










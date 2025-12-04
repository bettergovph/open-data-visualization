#!/usr/bin/env python3
"""
Analyze Davao City projects by district to verify Isidro Ungab vs Paolo Duterte assignments.
This script counts projects by district (1st, 2nd, 3rd) and shows which congressman they're assigned to.
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

def extract_district_number(district_str):
    """Extract district number from district string"""
    if not district_str:
        return None
    
    district_str_upper = str(district_str).upper()
    # Try patterns like "1ST DISTRICT", "1ST", "FIRST DISTRICT"
    match = re.search(r'\b(\d+)(ST|ND|RD|TH)\s*DISTRICT\b', district_str_upper, re.IGNORECASE)
    if match:
        return int(match.group(1))
    
    # Try just number with ordinal
    match = re.search(r'\b(\d+)(ST|ND|RD|TH)\b', district_str_upper, re.IGNORECASE)
    if match:
        return int(match.group(1))
    
    return None

def analyze_davao_city_projects():
    """Analyze Davao City projects by district"""
    print("🔍 Analyzing Davao City projects by district...")
    
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
    
    # Use classified if available, otherwise use integrated, otherwise combine all
    if CLASSIFIED_PARQUET.exists():
        df = df_classified
        print(f"\n📊 Using Classified parquet (deduplicated): {len(df)} projects")
    elif INTEGRATED_PARQUET.exists():
        df = df_integrated
        print(f"\n📊 Using Integrated parquet (all sources): {len(df)} projects")
    else:
        # Combine all individual sources
        df = pd.concat([df_source for _, df_source in all_dfs], ignore_index=True)
        print(f"\n📊 Combined all sources: {len(df)} total projects")
    
    print(f"\n📋 Source breakdown:")
    for source, count in source_counts.items():
        print(f"   - {source}: {count:,} projects")
    
    # Filter Davao City projects
    # Check location, project_district, project_province_city_district fields
    davao_keywords = ['DAVAO CITY', 'DAVAO DEL SUR']
    
    # Handle missing columns gracefully
    location_col = df.get('location', pd.Series(dtype=str))
    district_col = df.get('project_district', pd.Series(dtype=str))
    province_col = df.get('project_province_city_district', pd.Series(dtype=str))
    
    davao_mask = (
        location_col.astype(str).str.contains('DAVAO CITY|DAVAO DEL SUR', case=False, na=False) |
        district_col.astype(str).str.contains('DAVAO CITY|DAVAO DEL SUR', case=False, na=False) |
        province_col.astype(str).str.contains('DAVAO CITY|DAVAO DEL SUR', case=False, na=False)
    )
    
    davao_projects = df[davao_mask].copy()
    print(f"✅ Found {len(davao_projects)} Davao City/Davao Del Sur projects")
    
    # Show breakdown by source
    if 'sources_list' in davao_projects.columns:
        davao_by_source = defaultdict(int)
        for _, proj in davao_projects.iterrows():
            sources = proj.get('sources_list', [])
            if isinstance(sources, list):
                for source in sources:
                    davao_by_source[source] += 1
            elif proj.get('source'):
                davao_by_source[proj.get('source')] += 1
        
        if davao_by_source:
            print(f"\n📊 Davao City projects by source:")
            for source, count in sorted(davao_by_source.items(), key=lambda x: -x[1]):
                print(f"   - {source}: {count} projects")
    
    if len(davao_projects) == 0:
        print("⚠️  No Davao City projects found")
        return
    
    # Analyze by district
    district_stats = defaultdict(lambda: {
        'total': 0,
        'by_congressman': defaultdict(int),
        'by_match_type': defaultdict(int),
        'sample_locations': []
    })
    
    # Also track projects without district info
    no_district = {
        'total': 0,
        'by_congressman': defaultdict(int),
        'sample_locations': []
    }
    
    for _, project in davao_projects.iterrows():
        location = str(project.get('location', '')).upper()
        project_district = str(project.get('project_district', '')).upper()
        district_cm = project.get('district_congressman', '')
        contractor_cm = project.get('contractor_congressman', '')
        match_type = project.get('match_type', '')
        amount = project.get('amount', 0)
        
        # Extract district number
        district_num = None
        if project_district:
            district_num = extract_district_number(project_district)
        if not district_num and location:
            district_num = extract_district_number(location)
        
        # Determine which congressman this project is assigned to
        assigned_cm = district_cm or contractor_cm or 'Unassigned'
        
        if district_num:
            district_key = f"{district_num}st" if district_num == 1 else f"{district_num}nd" if district_num == 2 else f"{district_num}rd" if district_num == 3 else f"{district_num}th"
            district_key = f"{district_key} District"
            
            district_stats[district_key]['total'] += 1
            district_stats[district_key]['by_congressman'][assigned_cm] += 1
            district_stats[district_key]['by_match_type'][match_type] += 1
            
            # Store sample locations (up to 5 per district)
            if len(district_stats[district_key]['sample_locations']) < 5:
                district_stats[district_key]['sample_locations'].append({
                    'location': project.get('location', ''),
                    'project_district': project.get('project_district', ''),
                    'congressman': assigned_cm,
                    'match_type': match_type
                })
        else:
            no_district['total'] += 1
            no_district['by_congressman'][assigned_cm] += 1
            if len(no_district['sample_locations']) < 5:
                no_district['sample_locations'].append({
                    'location': project.get('location', ''),
                    'project_district': project.get('project_district', ''),
                    'congressman': assigned_cm,
                    'match_type': match_type
                })
    
    # Print results
    print("\n" + "="*80)
    print("📊 DAVAO CITY PROJECTS BY DISTRICT")
    print("="*80)
    
    for district in sorted(district_stats.keys(), key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 999):
        stats = district_stats[district]
        print(f"\n🏛️  {district.upper()}:")
        print(f"   Total projects: {stats['total']}")
        print(f"   By Congressman:")
        for cm, count in sorted(stats['by_congressman'].items(), key=lambda x: -x[1]):
            print(f"      - {cm}: {count} projects")
        print(f"   By Match Type:")
        for mt, count in sorted(stats['by_match_type'].items(), key=lambda x: -x[1]):
            print(f"      - {mt}: {count} projects")
        
        # Show sample locations
        if stats['sample_locations']:
            print(f"   Sample locations:")
            for sample in stats['sample_locations'][:3]:
                print(f"      - Location: {sample['location']}")
                print(f"        District: {sample['project_district']}")
                print(f"        Assigned to: {sample['congressman']} ({sample['match_type']})")
    
    if no_district['total'] > 0:
        print(f"\n⚠️  Projects without district info: {no_district['total']}")
        print(f"   By Congressman:")
        for cm, count in sorted(no_district['by_congressman'].items(), key=lambda x: -x[1]):
            print(f"      - {cm}: {count} projects")
        if no_district['sample_locations']:
            print(f"   Sample locations:")
            for sample in no_district['sample_locations'][:3]:
                print(f"      - Location: {sample['location']}")
                print(f"        District: {sample['project_district']}")
                print(f"        Assigned to: {sample['congressman']} ({sample['match_type']})")
    
    # Check for Isidro Ungab / Paolo Duterte conflicts
    print("\n" + "="*80)
    print("🔍 ISIDRO UNGAB vs PAOLO DUTERTE ANALYSIS")
    print("="*80)
    
    ungab_1st = 0
    duterte_1st = 0
    ungab_3rd = 0
    duterte_3rd = 0
    
    for _, project in davao_projects.iterrows():
        district_num = extract_district_number(str(project.get('project_district', '')))
        district_cm = project.get('district_congressman', '')
        
        if district_num == 1:
            if 'UNGAB' in str(district_cm).upper():
                ungab_1st += 1
            elif 'DUTERTE' in str(district_cm).upper() and 'PAOLO' in str(district_cm).upper():
                duterte_1st += 1
        elif district_num == 3:
            if 'UNGAB' in str(district_cm).upper():
                ungab_3rd += 1
            elif 'DUTERTE' in str(district_cm).upper() and 'PAOLO' in str(district_cm).upper():
                duterte_3rd += 1
    
    print(f"\n1st District assignments:")
    print(f"   Paolo Duterte: {duterte_1st} projects ✅ (should be all)")
    print(f"   Isidro Ungab: {ungab_1st} projects ❌ (should be 0)")
    
    print(f"\n3rd District assignments:")
    print(f"   Isidro Ungab: {ungab_3rd} projects ✅ (should be all)")
    print(f"   Paolo Duterte: {duterte_3rd} projects ❌ (should be 0)")
    
    if ungab_1st > 0:
        print(f"\n⚠️  ISSUE: Isidro Ungab has {ungab_1st} projects in 1st District (should be Paolo Duterte's)")
        # Show examples
        print(f"   Examples:")
        for _, project in davao_projects.iterrows():
            district_num = extract_district_number(str(project.get('project_district', '')))
            district_cm = project.get('district_congressman', '')
            if district_num == 1 and 'UNGAB' in str(district_cm).upper():
                print(f"      - Location: {project.get('location', '')}")
                print(f"        District: {project.get('project_district', '')}")
                print(f"        Assigned to: {district_cm}")
                ungab_1st -= 1
                if ungab_1st <= 0:
                    break
    
    if duterte_3rd > 0:
        print(f"\n⚠️  ISSUE: Paolo Duterte has {duterte_3rd} projects in 3rd District (should be Isidro Ungab's)")
        # Show the specific project(s)
        print(f"   Problematic project(s):")
        for _, project in davao_projects.iterrows():
            district_num = extract_district_number(str(project.get('project_district', '')))
            district_cm = project.get('district_congressman', '')
            if district_num == 3 and 'DUTERTE' in str(district_cm).upper() and 'PAOLO' in str(district_cm).upper():
                print(f"      - Project Name: {project.get('project_name', 'N/A')}")
                print(f"        Location: {project.get('location', 'N/A')}")
                print(f"        District: {project.get('project_district', 'N/A')}")
                print(f"        Contractor: {project.get('contractor', 'N/A')}")
                print(f"        Amount: {project.get('amount', 'N/A')}")
                print(f"        Source: {project.get('source', project.get('sources_list', 'N/A'))}")
                print(f"        Match Type: {project.get('match_type', 'N/A')}")
                print(f"        Match Score: {project.get('district_match_score', project.get('match_score', 'N/A'))}")
                duterte_3rd -= 1
                if duterte_3rd <= 0:
                    break

if __name__ == '__main__':
    analyze_davao_city_projects()













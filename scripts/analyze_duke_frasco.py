#!/usr/bin/env python3
"""
Analyze projects assigned to Duke Frasco.
This script analyzes all projects assigned to Duke Frasco to verify correct matching.
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

def analyze_duke_frasco():
    """Analyze projects assigned to Duke Frasco"""
    print("🔍 Analyzing projects assigned to Duke Frasco...")
    
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
    
    # Filter for Duke Frasco projects
    # Check both district_congressman and contractor_congressman fields
    duke_mask = (
        df.get('district_congressman', pd.Series(dtype=str)).astype(str).str.contains('FRASCO', case=False, na=False) |
        df.get('contractor_congressman', pd.Series(dtype=str)).astype(str).str.contains('FRASCO', case=False, na=False)
    )
    
    duke_projects = df[duke_mask].copy()
    print(f"\n✅ Found {len(duke_projects)} projects assigned to Duke Frasco")
    
    if len(duke_projects) == 0:
        print("⚠️  No projects found for Duke Frasco")
        return
    
    # Show breakdown by source
    if 'sources_list' in duke_projects.columns:
        duke_by_source = defaultdict(int)
        for _, proj in duke_projects.iterrows():
            sources = proj.get('sources_list', [])
            if isinstance(sources, list):
                for source in sources:
                    duke_by_source[source] += 1
            elif proj.get('source'):
                duke_by_source[proj.get('source')] += 1
        
        if duke_by_source:
            print(f"\n📊 Duke Frasco projects by source:")
            for source, count in sorted(duke_by_source.items(), key=lambda x: -x[1]):
                print(f"   - {source}: {count} projects")
    
    # Analyze by match type
    print("\n" + "="*80)
    print("📊 DUKE FRASCO PROJECT ANALYSIS")
    print("="*80)
    
    # By match type
    match_type_counts = defaultdict(int)
    for _, proj in duke_projects.iterrows():
        match_type = proj.get('match_type', 'unknown')
        match_type_counts[match_type] += 1
    
    print(f"\n📋 By Match Type:")
    for match_type, count in sorted(match_type_counts.items(), key=lambda x: -x[1]):
        print(f"   - {match_type}: {count} projects")
    
    # By district vs contractor match
    district_matches = 0
    contractor_matches = 0
    both_matches = 0
    
    for _, proj in duke_projects.iterrows():
        has_district = bool(proj.get('district_congressman', ''))
        has_contractor = bool(proj.get('contractor_congressman', ''))
        
        if has_district and has_contractor:
            both_matches += 1
        elif has_district:
            district_matches += 1
        elif has_contractor:
            contractor_matches += 1
    
    print(f"\n📋 By Match Method:")
    print(f"   - District match only: {district_matches} projects")
    print(f"   - Contractor match only: {contractor_matches} projects")
    print(f"   - Both district and contractor: {both_matches} projects")
    
    # Analyze by district
    print(f"\n📋 By District:")
    district_counts = defaultdict(int)
    district_samples = defaultdict(list)
    
    for _, proj in duke_projects.iterrows():
        district = proj.get('project_district', 'Unknown')
        district_str = str(district) if district else 'Unknown'
        district_counts[district_str] += 1
        
        if len(district_samples[district_str]) < 3:
            district_samples[district_str].append({
                'project_name': proj.get('project_name', 'N/A'),
                'location': proj.get('location', 'N/A'),
                'contractor': proj.get('contractor', 'N/A'),
                'amount': proj.get('amount', 0),
                'source': proj.get('source', 'N/A'),
                'match_type': proj.get('match_type', 'unknown')
            })
    
    for district, count in sorted(district_counts.items(), key=lambda x: -x[1]):
        print(f"\n   🏛️  {district}:")
        print(f"      Total projects: {count}")
        if district_samples[district]:
            print(f"      Sample projects:")
            for sample in district_samples[district][:3]:
                print(f"         - {sample['project_name'][:60]}...")
                print(f"           Location: {sample['location']}")
                print(f"           Contractor: {sample['contractor']}")
                print(f"           Match Type: {sample['match_type']}")
                print(f"           Source: {sample['source']}")
    
    # Analyze by location/province
    print(f"\n📋 By Location/Province:")
    location_counts = defaultdict(int)
    
    for _, proj in duke_projects.iterrows():
        location = proj.get('location', 'Unknown')
        location_str = str(location) if location else 'Unknown'
        # Extract province/city from location
        if 'CEBU' in location_str.upper():
            location_counts['Cebu'] += 1
        elif 'DAVAO' in location_str.upper():
            location_counts['Davao'] += 1
        else:
            location_counts[location_str[:50]] += 1
    
    for location, count in sorted(location_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"   - {location}: {count} projects")
    
    # Check for potential issues
    print("\n" + "="*80)
    print("🔍 POTENTIAL ISSUES")
    print("="*80)
    
    # Check for projects in wrong districts
    issues = []
    for _, proj in duke_projects.iterrows():
        district = proj.get('project_district', '')
        location = proj.get('location', '')
        
        # Duke Frasco should be Cebu 5th District
        # Check if project is in Davao (from the earlier analysis showing Davao projects)
        if 'DAVAO' in str(location).upper() or 'DAVAO' in str(district).upper():
            issues.append({
                'type': 'Wrong Location',
                'project_name': proj.get('project_name', 'N/A'),
                'location': location,
                'district': district,
                'contractor': proj.get('contractor', 'N/A'),
                'source': proj.get('source', 'N/A')
            })
    
    if issues:
        print(f"\n⚠️  Found {len(issues)} potential issues:")
        for issue in issues[:10]:  # Show first 10
            print(f"\n   ❌ {issue['type']}:")
            print(f"      Project: {issue['project_name'][:60]}...")
            print(f"      Location: {issue['location']}")
            print(f"      District: {issue['district']}")
            print(f"      Contractor: {issue['contractor']}")
            print(f"      Source: {issue['source']}")
    else:
        print("\n✅ No obvious issues found")
    
    # Show total amount
    total_amount = 0
    for _, proj in duke_projects.iterrows():
        amount = proj.get('amount', 0)
        if isinstance(amount, (int, float)):
            total_amount += float(amount)
        elif isinstance(amount, str):
            try:
                amount_str = amount.replace('₱', '').replace(',', '').strip()
                total_amount += float(amount_str)
            except:
                pass
    
    print(f"\n💰 Total Amount: ₱{total_amount:,.2f}")
    
    # Show sample projects
    print("\n" + "="*80)
    print("📋 SAMPLE PROJECTS")
    print("="*80)
    
    for idx, (_, proj) in enumerate(duke_projects.head(10).iterrows()):
        print(f"\n   {idx + 1}. {proj.get('project_name', 'N/A')[:80]}")
        print(f"      Location: {proj.get('location', 'N/A')}")
        print(f"      District: {proj.get('project_district', 'N/A')}")
        print(f"      Contractor: {proj.get('contractor', 'N/A')}")
        print(f"      Amount: ₱{proj.get('amount', 0):,.2f}")
        print(f"      Match Type: {proj.get('match_type', 'unknown')}")
        print(f"      District Congressman: {proj.get('district_congressman', 'N/A')}")
        print(f"      Contractor Congressman: {proj.get('contractor_congressman', 'N/A')}")
        print(f"      Source: {proj.get('source', 'N/A')}")

if __name__ == '__main__':
    analyze_duke_frasco()













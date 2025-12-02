#!/usr/bin/env python3
"""
Analyze Palawan projects and Jose Alvarez assignments.
This script analyzes all projects in Palawan and those assigned to Jose Alvarez to verify correct matching.
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
    match = re.search(r'\b(\d+)(ST|ND|RD|TH)\s*DISTRICT\b', district_str_upper, re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r'\b(\d+)(ST|ND|RD|TH)\b', district_str_upper, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None

def analyze_palawan_projects():
    """Analyze Palawan projects and Jose Alvarez assignments"""
    print("🔍 Analyzing Palawan projects and Jose Alvarez assignments...")
    
    # Load projects from ALL sources
    print(f"\n📥 Loading projects from ALL sources...")
    all_dfs = []
    source_counts = {}
    
    if CLASSIFIED_PARQUET.exists():
        df_classified = pd.read_parquet(CLASSIFIED_PARQUET)
        all_dfs.append(('Classified (deduplicated)', df_classified))
        source_counts['Classified'] = len(df_classified)
        print(f"   ✅ Classified: {len(df_classified)} projects")
    
    if INTEGRATED_PARQUET.exists():
        df_integrated = pd.read_parquet(INTEGRATED_PARQUET)
        all_dfs.append(('Integrated (all sources)', df_integrated))
        source_counts['Integrated'] = len(df_integrated)
        print(f"   ✅ Integrated: {len(df_integrated)} projects")
    
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
    
    if CLASSIFIED_PARQUET.exists():
        df = df_classified
        print(f"\n📊 Using Classified parquet (deduplicated): {len(df)} projects")
    elif INTEGRATED_PARQUET.exists():
        df = df_integrated
        print(f"\n📊 Using Integrated parquet (all sources): {len(df)} projects")
    else:
        df = pd.concat([df_source for _, df_source in all_dfs], ignore_index=True)
        print(f"\n📊 Combined all sources: {len(df)} total projects")
    
    # Filter for Palawan projects
    location_col = df.get('location', pd.Series(dtype=str))
    district_col = df.get('project_district', pd.Series(dtype=str))
    province_col = df.get('project_province_city_district', pd.Series(dtype=str))
    
    palawan_mask = (
        location_col.astype(str).str.contains('PALAWAN', case=False, na=False) |
        district_col.astype(str).str.contains('PALAWAN', case=False, na=False) |
        province_col.astype(str).str.contains('PALAWAN', case=False, na=False)
    )
    
    palawan_projects = df[palawan_mask].copy()
    print(f"\n✅ Found {len(palawan_projects)} Palawan projects")
    
    # Filter for Jose Alvarez projects (be more specific - look for "JOSE" and "ALVAREZ")
    # Also check for other Alvarez congressmen to compare
    jose_mask = (
        (df.get('district_congressman', pd.Series(dtype=str)).astype(str).str.contains('JOSE', case=False, na=False) &
         df.get('district_congressman', pd.Series(dtype=str)).astype(str).str.contains('ALVAREZ', case=False, na=False)) |
        (df.get('contractor_congressman', pd.Series(dtype=str)).astype(str).str.contains('JOSE', case=False, na=False) &
         df.get('contractor_congressman', pd.Series(dtype=str)).astype(str).str.contains('ALVAREZ', case=False, na=False))
    )
    
    jose_projects = df[jose_mask].copy()
    print(f"✅ Found {len(jose_projects)} projects assigned to Jose Alvarez")
    
    # Also get all Alvarez congressmen to see the breakdown
    all_alvarez_mask = (
        df.get('district_congressman', pd.Series(dtype=str)).astype(str).str.contains('ALVAREZ', case=False, na=False) |
        df.get('contractor_congressman', pd.Series(dtype=str)).astype(str).str.contains('ALVAREZ', case=False, na=False)
    )
    
    all_alvarez_projects = df[all_alvarez_mask].copy()
    print(f"✅ Found {len(all_alvarez_projects)} total projects assigned to any Alvarez congressman")
    
    # Show breakdown of all Alvarez congressmen
    if len(all_alvarez_projects) > 0:
        print(f"\n📊 Breakdown of all Alvarez congressmen:")
        alvarez_by_cm = defaultdict(int)
        for _, proj in all_alvarez_projects.iterrows():
            district_cm = proj.get('district_congressman', '')
            contractor_cm = proj.get('contractor_congressman', '')
            cm_name = district_cm if district_cm and 'ALVAREZ' in str(district_cm).upper() else (contractor_cm if contractor_cm else 'Unknown')
            if cm_name:
                alvarez_by_cm[cm_name] += 1
        
        for cm_name, count in sorted(alvarez_by_cm.items(), key=lambda x: -x[1]):
            print(f"   - {cm_name}: {count} projects")
    
    if len(palawan_projects) == 0 and len(jose_projects) == 0:
        print("⚠️  No Palawan or Jose Alvarez projects found")
        return
    
    # Show breakdown by source for Palawan
    if len(palawan_projects) > 0:
        print(f"\n📊 Palawan projects by source:")
        if 'sources_list' in palawan_projects.columns:
            palawan_by_source = defaultdict(int)
            for _, proj in palawan_projects.iterrows():
                sources = proj.get('sources_list', [])
                if isinstance(sources, list):
                    for source in sources:
                        palawan_by_source[source] += 1
                elif proj.get('source'):
                    palawan_by_source[proj.get('source')] += 1
            
            for source, count in sorted(palawan_by_source.items(), key=lambda x: -x[1]):
                print(f"   - {source}: {count} projects")
    
    # Analyze Palawan projects by congressman
    print("\n" + "="*80)
    print("📊 PALAWAN PROJECTS BY CONGRESSMAN")
    print("="*80)
    
    palawan_by_cm = defaultdict(lambda: {
        'total': 0,
        'by_match_type': defaultdict(int),
        'by_district': defaultdict(int),
        'sample_projects': []
    })
    
    for _, proj in palawan_projects.iterrows():
        district_cm = proj.get('district_congressman', 'Unassigned')
        contractor_cm = proj.get('contractor_congressman', '')
        match_type = proj.get('match_type', 'unknown')
        district = proj.get('project_district', 'Unknown')
        
        cm_name = district_cm if district_cm and district_cm != 'None' else (contractor_cm if contractor_cm else 'Unassigned')
        
        palawan_by_cm[cm_name]['total'] += 1
        palawan_by_cm[cm_name]['by_match_type'][match_type] += 1
        palawan_by_cm[cm_name]['by_district'][str(district)] += 1
        
        if len(palawan_by_cm[cm_name]['sample_projects']) < 3:
            palawan_by_cm[cm_name]['sample_projects'].append({
                'project_name': proj.get('project_name', 'N/A'),
                'location': proj.get('location', 'N/A'),
                'district': district,
                'contractor': proj.get('contractor', 'N/A'),
                'match_type': match_type
            })
    
    print(f"\n📋 Palawan projects by Congressman:")
    for cm_name, stats in sorted(palawan_by_cm.items(), key=lambda x: -x[1]['total']):
        print(f"\n   👤 {cm_name}:")
        print(f"      Total projects: {stats['total']}")
        print(f"      By match type:")
        for match_type, count in sorted(stats['by_match_type'].items(), key=lambda x: -x[1]):
            print(f"         - {match_type}: {count} projects")
        print(f"      By district:")
        for district, count in sorted(stats['by_district'].items(), key=lambda x: -x[1])[:5]:
            print(f"         - {district}: {count} projects")
        if stats['sample_projects']:
            print(f"      Sample projects:")
            for sample in stats['sample_projects']:
                print(f"         - {sample['project_name'][:60]}...")
                print(f"           Location: {sample['location']}")
                print(f"           District: {sample['district']}")
    
    # Analyze Jose Alvarez projects
    if len(jose_projects) > 0:
        print("\n" + "="*80)
        print("📊 JOSE ALVAREZ PROJECT ANALYSIS")
        print("="*80)
        
        # By match type
        match_type_counts = defaultdict(int)
        for _, proj in jose_projects.iterrows():
            match_type = proj.get('match_type', 'unknown')
            match_type_counts[match_type] += 1
        
        print(f"\n📋 By Match Type:")
        for match_type, count in sorted(match_type_counts.items(), key=lambda x: -x[1]):
            print(f"   - {match_type}: {count} projects")
        
        # By district vs contractor match
        district_matches = 0
        contractor_matches = 0
        both_matches = 0
        
        for _, proj in jose_projects.iterrows():
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
        
        # By district
        print(f"\n📋 By District:")
        district_counts = defaultdict(int)
        district_samples = defaultdict(list)
        
        for _, proj in jose_projects.iterrows():
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
        
        # Check for issues with Jose Alvarez assignments
        print("\n" + "="*80)
        print("🔍 POTENTIAL ISSUES")
        print("="*80)
        
        issues = []
        for _, proj in jose_projects.iterrows():
            location = proj.get('location', '')
            district = proj.get('project_district', '')
            
            # Check if project is NOT in Palawan
            location_str = str(location).upper()
            district_str = str(district).upper()
            
            is_palawan = 'PALAWAN' in location_str or 'PALAWAN' in district_str
            
            if not is_palawan:
                issues.append({
                    'type': 'Non-Palawan Location',
                    'project_name': proj.get('project_name', 'N/A'),
                    'location': location,
                    'district': district,
                    'contractor': proj.get('contractor', 'N/A'),
                    'source': proj.get('source', 'N/A')
                })
            
            # Check if project is in Palawan but wrong district (should be 2nd District)
            elif is_palawan:
                district_num = extract_district_number(district_str)
                if district_num and district_num != 2:
                    issues.append({
                        'type': 'Wrong Palawan District',
                        'project_name': proj.get('project_name', 'N/A'),
                        'location': location,
                        'district': district,
                        'expected': 'Palawan 2nd District',
                        'contractor': proj.get('contractor', 'N/A'),
                        'source': proj.get('source', 'N/A')
                    })
        
        if issues:
            print(f"\n⚠️  Found {len(issues)} potential issues:")
            for issue in issues[:10]:
                print(f"\n   ❌ {issue['type']}:")
                print(f"      Project: {issue['project_name'][:60]}...")
                print(f"      Location: {issue['location']}")
                print(f"      District: {issue['district']}")
                if 'expected' in issue:
                    print(f"      Expected: {issue['expected']}")
                print(f"      Contractor: {issue['contractor']}")
                print(f"      Source: {issue['source']}")
        else:
            print("\n✅ All Jose Alvarez projects are correctly in Palawan 2nd District")
        
        # Also check if Palawan 2nd District projects are going to other congressmen
        print("\n" + "="*80)
        print("🔍 PALAWAN 2ND DISTRICT PROJECTS")
        print("="*80)
        
        palawan_2nd_mask = (
            palawan_projects.get('project_district', pd.Series(dtype=str)).astype(str).str.contains('2ND|2ND|SECOND', case=False, na=False)
        )
        palawan_2nd_projects = palawan_projects[palawan_2nd_mask].copy()
        
        print(f"\n✅ Found {len(palawan_2nd_projects)} Palawan 2nd District projects")
        
        if len(palawan_2nd_projects) > 0:
            palawan_2nd_by_cm = defaultdict(int)
            for _, proj in palawan_2nd_projects.iterrows():
                district_cm = proj.get('district_congressman', 'Unassigned')
                contractor_cm = proj.get('contractor_congressman', '')
                cm_name = district_cm if district_cm and district_cm != 'None' else (contractor_cm if contractor_cm else 'Unassigned')
                palawan_2nd_by_cm[cm_name] += 1
            
            print(f"\n📋 Palawan 2nd District projects by Congressman:")
            for cm_name, count in sorted(palawan_2nd_by_cm.items(), key=lambda x: -x[1]):
                status = "✅" if "JOSE" in cm_name.upper() and "ALVAREZ" in cm_name.upper() else "❌"
                print(f"   {status} {cm_name}: {count} projects")
            
            # Check if Jose Alvarez is getting his projects
            jose_2nd_count = sum(count for cm_name, count in palawan_2nd_by_cm.items() 
                                if "JOSE" in cm_name.upper() and "ALVAREZ" in cm_name.upper())
            
            if jose_2nd_count == 0:
                print(f"\n⚠️  ISSUE: Jose Alvarez (Palawan 2nd District) has NO projects assigned!")
                print(f"   Total Palawan 2nd District projects: {len(palawan_2nd_projects)}")
                print(f"   These projects are going to: {', '.join(palawan_2nd_by_cm.keys())}")
            elif jose_2nd_count < len(palawan_2nd_projects):
                print(f"\n⚠️  ISSUE: Jose Alvarez should have {len(palawan_2nd_projects)} Palawan 2nd District projects,")
                print(f"   but only {jose_2nd_count} are assigned to him.")
                print(f"   Missing projects are going to: {', '.join([cm for cm in palawan_2nd_by_cm.keys() if 'JOSE' not in cm.upper() or 'ALVAREZ' not in cm.upper()])}")
        
        # Show total amount
        total_amount = 0
        for _, proj in jose_projects.iterrows():
            amount = proj.get('amount', 0)
            if isinstance(amount, (int, float)):
                total_amount += float(amount)
            elif isinstance(amount, str):
                try:
                    amount_str = amount.replace('₱', '').replace(',', '').strip()
                    total_amount += float(amount_str)
                except:
                    pass
        
        print(f"\n💰 Total Amount for Jose Alvarez: ₱{total_amount:,.2f}")
        
        # Show sample projects
        print("\n" + "="*80)
        print("📋 SAMPLE JOSE ALVAREZ PROJECTS")
        print("="*80)
        
        for idx, (_, proj) in enumerate(jose_projects.head(10).iterrows()):
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
    analyze_palawan_projects()










#!/usr/bin/env python3
"""
Load PCAB Regular License data from CSV and merge into PhilGEPS contracts parquet file.

This script:
1. Reads PCAB_REGULAR_LICENSE_COMBINED.csv
2. Loads existing philgeps_contracts.parquet
3. Matches PCAB licenses to PhilGEPS contracts by contractor name
4. Adds PCAB license columns to the parquet
5. Saves updated parquet file
"""

import pandas as pd
import duckdb
from pathlib import Path
from typing import Dict, List, Optional
import re
from datetime import datetime

# Paths
ROOT_DIR = Path(__file__).parent.parent
CSV_PATH = ROOT_DIR / 'database' / 'PCAB_REGULAR_LICENSE_COMBINED.csv'
PARQUET_DIR = ROOT_DIR / 'data' / 'parquet'
PARQUET_PATH = PARQUET_DIR / 'philgeps_contracts.parquet'
BACKUP_PATH = PARQUET_DIR / 'philgeps_contracts.parquet.backup'

def normalize_contractor_name(name: str) -> str:
    """Normalize contractor name for matching."""
    if not name or pd.isna(name):
        return ""
    
    # Convert to string and uppercase
    name = str(name).upper().strip()
    
    # Remove common suffixes and prefixes
    name = re.sub(r'\s+(INC\.?|INCORPORATED|CORP\.?|CORPORATION|CO\.?|COMPANY|OPC|OPC\.?)$', '', name)
    name = re.sub(r'^THE\s+', '', name)
    
    # Remove extra whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    
    # Remove special characters but keep spaces
    name = re.sub(r'[^\w\s]', '', name)
    
    return name

def load_pcab_csv() -> pd.DataFrame:
    """Load PCAB license CSV file."""
    print(f"📖 Reading PCAB CSV from {CSV_PATH}...")
    
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"PCAB CSV file not found: {CSV_PATH}")
    
    df = pd.read_csv(CSV_PATH)
    print(f"✅ Loaded {len(df):,} PCAB license records")
    print(f"   Columns: {', '.join(df.columns.tolist())}")
    
    # Normalize contractor names for matching
    df['normalized_name'] = df['nameOfFirm'].apply(normalize_contractor_name)
    
    # Parse validToDate
    df['validToDate'] = pd.to_datetime(df['validToDate'], errors='coerce')
    
    # Create a mapping: normalized_name -> list of license records
    # For contractors with multiple licenses, we'll keep the most recent valid one
    license_map = {}
    for _, row in df.iterrows():
        normalized = row['normalized_name']
        if not normalized:
            continue
        
        if normalized not in license_map:
            license_map[normalized] = []
        
        license_map[normalized].append({
            'nameOfFirm': row['nameOfFirm'],
            'licenseNumber': row['licenseNumber'],
            'AMO': row['AMO'],
            'Category': row['Category'],
            'validToDate': row['validToDate'],
            'regForGovInfraProjects': row['regForGovInfraProjects']
        })
    
    # For each contractor, select the license with the latest validToDate
    best_licenses = {}
    for normalized, licenses in license_map.items():
        # Sort by validToDate (most recent first), then by Category (higher is better: AAAA > AAA > AA > A > B > C > D > E)
        category_order = {'AAAA': 8, 'AAA': 7, 'AA': 6, 'A': 5, 'B': 4, 'C': 3, 'D': 2, 'E': 1}
        
        sorted_licenses = sorted(
            licenses,
            key=lambda x: (
                pd.Timestamp.max if pd.isna(x['validToDate']) else x['validToDate'],
                category_order.get(x['Category'], 0)
            ),
            reverse=True
        )
        
        best_licenses[normalized] = sorted_licenses[0]
    
    print(f"✅ Created license mapping for {len(best_licenses):,} unique contractors")
    
    return pd.DataFrame(list(best_licenses.values()))

def load_philgeps_parquet() -> pd.DataFrame:
    """Load existing PhilGEPS contracts parquet file."""
    print(f"\n📖 Loading PhilGEPS parquet from {PARQUET_PATH}...")
    
    if not PARQUET_PATH.exists():
        raise FileNotFoundError(f"PhilGEPS parquet file not found: {PARQUET_PATH}")
    
    # Use DuckDB to load parquet
    conn = duckdb.connect()
    df = conn.execute(f'SELECT * FROM "{PARQUET_PATH}"').df()
    conn.close()
    
    print(f"✅ Loaded {len(df):,} PhilGEPS contract records")
    print(f"   Columns: {len(df.columns)} total columns")
    
    return df

def merge_pcab_licenses(philgeps_df: pd.DataFrame, pcab_df: pd.DataFrame) -> pd.DataFrame:
    """Merge PCAB license data into PhilGEPS contracts."""
    print(f"\n🔗 Merging PCAB licenses with PhilGEPS contracts...")
    
    # Create normalized contractor name columns for matching
    # Try multiple possible contractor name columns
    contractor_cols = [
        'contractor_name',
        'philgeps_awardee_name',
        'awardee_name',
        'contractor'
    ]
    
    contractor_col = None
    for col in contractor_cols:
        if col in philgeps_df.columns:
            contractor_col = col
            break
    
    if not contractor_col:
        print("⚠️  No contractor name column found in PhilGEPS data")
        print(f"   Available columns: {', '.join(philgeps_df.columns.tolist()[:20])}...")
        return philgeps_df
    
    print(f"   Using contractor column: {contractor_col}")
    
    # Normalize contractor names in PhilGEPS data
    philgeps_df['_normalized_contractor'] = philgeps_df[contractor_col].apply(normalize_contractor_name)
    
    # Create normalized name column in PCAB data
    pcab_df['_normalized_contractor'] = pcab_df['nameOfFirm'].apply(normalize_contractor_name)
    
    # Create a lookup dictionary from PCAB data
    pcab_lookup = {}
    for _, row in pcab_df.iterrows():
        normalized = row['_normalized_contractor']
        if normalized:
            pcab_lookup[normalized] = {
                'pcab_license_number': row['licenseNumber'],
                'pcab_amo': row['AMO'],
                'pcab_category': row['Category'],
                'pcab_valid_to_date': row['validToDate'],
                'pcab_reg_for_gov_infra': row['regForGovInfraProjects']
            }
    
    # Merge PCAB data into PhilGEPS contracts
    matches = 0
    for idx, row in philgeps_df.iterrows():
        normalized = row['_normalized_contractor']
        if normalized and normalized in pcab_lookup:
            pcab_data = pcab_lookup[normalized]
            for key, value in pcab_data.items():
                philgeps_df.at[idx, key] = value
            matches += 1
    
    print(f"✅ Matched {matches:,} contracts with PCAB licenses ({matches/len(philgeps_df)*100:.1f}%)")
    
    # Remove temporary column
    philgeps_df = philgeps_df.drop(columns=['_normalized_contractor'], errors='ignore')
    
    return philgeps_df

def save_parquet(df: pd.DataFrame, backup: bool = True):
    """Save updated dataframe to parquet file."""
    print(f"\n💾 Saving updated parquet file...")
    
    # Create backup if requested
    if backup and PARQUET_PATH.exists():
        print(f"   Creating backup: {BACKUP_PATH}")
        import shutil
        shutil.copy2(PARQUET_PATH, BACKUP_PATH)
        print(f"   ✅ Backup created")
    
    # Ensure parquet directory exists
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save to parquet using DuckDB (preserves schema better)
    conn = duckdb.connect()
    conn.execute(f'CREATE OR REPLACE TABLE temp_philgeps AS SELECT * FROM df')
    conn.execute(f'COPY temp_philgeps TO "{PARQUET_PATH}" (FORMAT PARQUET)')
    conn.close()
    
    print(f"✅ Saved {len(df):,} records to {PARQUET_PATH}")
    
    # Print summary of new columns
    new_columns = [col for col in df.columns if col.startswith('pcab_')]
    if new_columns:
        print(f"   Added PCAB columns: {', '.join(new_columns)}")
        
        # Print statistics
        for col in new_columns:
            non_null = df[col].notna().sum()
            print(f"      {col}: {non_null:,} non-null values ({non_null/len(df)*100:.1f}%)")

def main():
    """Main function."""
    print("=" * 80)
    print("PCAB License Data Loader for PhilGEPS Parquet")
    print("=" * 80)
    
    try:
        # Load PCAB CSV
        pcab_df = load_pcab_csv()
        
        # Load PhilGEPS parquet
        philgeps_df = load_philgeps_parquet()
        
        # Merge PCAB licenses
        merged_df = merge_pcab_licenses(philgeps_df, pcab_df)
        
        # Save updated parquet
        save_parquet(merged_df, backup=True)
        
        print("\n" + "=" * 80)
        print("✅ Successfully loaded PCAB licenses into PhilGEPS parquet!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())





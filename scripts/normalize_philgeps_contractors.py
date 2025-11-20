#!/usr/bin/env python3
"""
Normalize PhilGEPS contractors using SEC, PCAB, and PhilGEPS license data as clues.

This script:
1. Loads SEC contractor data from PostgreSQL
2. Uses PCAB license data (already in parquet)
3. Uses PhilGEPS license data (from contracts)
4. Normalizes contractor names using all three sources as clues
5. Moves dates to a separate structure
6. Updates parquet with normalized data
"""

import pandas as pd
import duckdb
import asyncpg
import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import re
from datetime import datetime
from difflib import SequenceMatcher
from dotenv import load_dotenv

load_dotenv()

# Paths
ROOT_DIR = Path(__file__).parent.parent
PARQUET_DIR = ROOT_DIR / 'data' / 'parquet'
PARQUET_PATH = PARQUET_DIR / 'philgeps_contracts.parquet'
BACKUP_PATH = PARQUET_DIR / 'philgeps_contracts.parquet.backup'
DATES_PARQUET_PATH = PARQUET_DIR / 'philgeps_dates.parquet'

# Database config
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'user': os.getenv('POSTGRES_USER', 'budget_admin'),
    'password': os.getenv('POSTGRES_PASSWORD', ''),
    'database': os.getenv('POSTGRES_DB_SEC', 'sec')
}

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

def fuzzy_similarity(name1: str, name2: str) -> float:
    """Calculate fuzzy similarity between two names."""
    if not name1 or not name2:
        return 0.0
    
    norm1 = normalize_contractor_name(name1)
    norm2 = normalize_contractor_name(name2)
    
    if norm1 == norm2:
        return 1.0
    
    return SequenceMatcher(None, norm1, norm2).ratio()

async def load_sec_contractors() -> Dict[str, Dict]:
    """Load SEC contractors from PostgreSQL database."""
    print("📖 Loading SEC contractors from database...")
    
    try:
        conn = await asyncpg.connect(**DB_CONFIG)
        
        # Get all contractors with SEC data
        rows = await conn.fetch('''
            SELECT 
                contractor_name,
                sec_number,
                date_registered,
                status,
                address
            FROM contractors
            WHERE sec_number IS NOT NULL AND sec_number != ''
            ORDER BY contractor_name
        ''')
        
        await conn.close()
        
        # Build lookup: normalized_name -> {original_name, sec_number, ...}
        sec_lookup = {}
        for row in rows:
            original_name = row['contractor_name']
            normalized = normalize_contractor_name(original_name)
            
            if normalized:
                # Store multiple variants if same normalized name
                if normalized not in sec_lookup:
                    sec_lookup[normalized] = []
                
                sec_lookup[normalized].append({
                    'original_name': original_name,
                    'sec_number': row['sec_number'],
                    'date_registered': row['date_registered'],
                    'status': row['status'],
                    'address': row['address']
                })
        
        print(f"✅ Loaded {len(rows):,} SEC contractors")
        print(f"   Unique normalized names: {len(sec_lookup):,}")
        
        return sec_lookup
        
    except Exception as e:
        print(f"⚠️  Error loading SEC contractors: {e}")
        return {}

def build_contractor_clues(philgeps_df: pd.DataFrame, sec_lookup: Dict) -> Dict[str, Dict]:
    """
    Build a comprehensive clue dictionary using SEC, PCAB, and PhilGEPS data.
    
    Returns: normalized_name -> {
        'canonical_name': best canonical name,
        'sec_number': SEC number if found,
        'pcab_license': PCAB license number if found,
        'variants': set of all name variants,
        'confidence': confidence score
    }
    """
    print("\n🔍 Building contractor clues from all sources...")
    
    clues = {}
    
    # Get contractor name columns
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
        print("⚠️  No contractor name column found")
        return clues
    
    # Process each unique contractor
    unique_contractors = philgeps_df[contractor_col].dropna().unique()
    print(f"   Processing {len(unique_contractors):,} unique contractors...")
    
    for contractor_name in unique_contractors:
        if pd.isna(contractor_name) or not str(contractor_name).strip():
            continue
        
        normalized = normalize_contractor_name(str(contractor_name))
        if not normalized:
            continue
        
        if normalized not in clues:
            clues[normalized] = {
                'canonical_name': str(contractor_name).strip(),
                'sec_number': None,
                'pcab_license': None,
                'variants': set([str(contractor_name).strip()]),
                'confidence': 0.0,
                'source': 'philgeps'
            }
        else:
            clues[normalized]['variants'].add(str(contractor_name).strip())
        
        # Check SEC lookup
        if normalized in sec_lookup:
            sec_data = sec_lookup[normalized][0]  # Take first match
            clues[normalized]['sec_number'] = sec_data['sec_number']
            clues[normalized]['canonical_name'] = sec_data['original_name']  # Use SEC name as canonical
            clues[normalized]['confidence'] = max(clues[normalized]['confidence'], 0.9)
            clues[normalized]['source'] = 'sec'
        
        # Check PCAB data (if available in parquet)
        if 'pcab_license_number' in philgeps_df.columns:
            pcab_rows = philgeps_df[
                (philgeps_df[contractor_col] == contractor_name) &
                (philgeps_df['pcab_license_number'].notna())
            ]
            if len(pcab_rows) > 0:
                pcab_license = pcab_rows.iloc[0]['pcab_license_number']
                if pd.notna(pcab_license):
                    clues[normalized]['pcab_license'] = str(pcab_license)
                    clues[normalized]['confidence'] = max(clues[normalized]['confidence'], 0.8)
                    if clues[normalized]['source'] == 'philgeps':
                        clues[normalized]['source'] = 'pcab'
    
    # Find fuzzy matches and merge similar contractors
    print("   Finding fuzzy matches...")
    normalized_names = list(clues.keys())
    merged = set()
    
    for i, norm1 in enumerate(normalized_names):
        if norm1 in merged:
            continue
        
        for norm2 in normalized_names[i+1:]:
            if norm2 in merged:
                continue
            
            similarity = fuzzy_similarity(norm1, norm2)
            if similarity >= 0.95:  # Very high similarity threshold
                # Merge norm2 into norm1
                clues[norm1]['variants'].update(clues[norm2]['variants'])
                if clues[norm2]['sec_number'] and not clues[norm1]['sec_number']:
                    clues[norm1]['sec_number'] = clues[norm2]['sec_number']
                    clues[norm1]['canonical_name'] = clues[norm2]['canonical_name']
                    clues[norm1]['confidence'] = max(clues[norm1]['confidence'], clues[norm2]['confidence'])
                if clues[norm2]['pcab_license'] and not clues[norm1]['pcab_license']:
                    clues[norm1]['pcab_license'] = clues[norm2]['pcab_license']
                merged.add(norm2)
    
    # Remove merged entries
    for key in merged:
        del clues[key]
    
    print(f"✅ Built clues for {len(clues):,} normalized contractors")
    print(f"   Merged {len(merged):,} duplicate contractors")
    
    return clues

def normalize_contractors_in_dataframe(df: pd.DataFrame, clues: Dict[str, Dict]) -> pd.DataFrame:
    """Apply normalization to contractor names in dataframe."""
    print("\n🔄 Normalizing contractor names in dataframe...")
    
    contractor_cols = [
        'contractor_name',
        'philgeps_awardee_name',
        'awardee_name',
        'contractor'
    ]
    
    contractor_col = None
    for col in contractor_cols:
        if col in df.columns:
            contractor_col = col
            break
    
    if not contractor_col:
        print("⚠️  No contractor name column found")
        return df
    
    # Add normalized contractor name column
    df['contractor_name_normalized'] = df[contractor_col].apply(
        lambda x: normalize_contractor_name(str(x)) if pd.notna(x) else None
    )
    
    # Add canonical name column
    df['contractor_name_canonical'] = None
    df['contractor_sec_number'] = None
    df['contractor_pcab_license'] = None
    df['contractor_normalization_confidence'] = 0.0
    
    normalized_count = 0
    for idx, row in df.iterrows():
        normalized = row['contractor_name_normalized']
        if normalized and normalized in clues:
            clue = clues[normalized]
            df.at[idx, 'contractor_name_canonical'] = clue['canonical_name']
            df.at[idx, 'contractor_sec_number'] = clue['sec_number']
            df.at[idx, 'contractor_pcab_license'] = clue['pcab_license']
            df.at[idx, 'contractor_normalization_confidence'] = clue['confidence']
            normalized_count += 1
    
    print(f"✅ Normalized {normalized_count:,} contractor names ({normalized_count/len(df)*100:.1f}%)")
    
    return df

def extract_dates_to_separate_table(df: pd.DataFrame) -> pd.DataFrame:
    """Extract all date columns to a separate dates table."""
    print("\n📅 Extracting dates to separate table...")
    
    # Find all date/timestamp columns
    date_columns = []
    for col in df.columns:
        if 'date' in col.lower() or 'timestamp' in col.lower():
            date_columns.append(col)
    
    print(f"   Found {len(date_columns)} date columns: {', '.join(date_columns)}")
    
    # Create dates dataframe
    dates_data = []
    
    # Get a unique identifier for each row (use index or create one)
    if 'project_id' in df.columns:
        id_col = 'project_id'
    elif 'philgeps_reference_id' in df.columns:
        id_col = 'philgeps_reference_id'
    elif 'contract_id' in df.columns:
        id_col = 'contract_id'
    else:
        # Create a synthetic ID
        df['_synthetic_id'] = df.index
        id_col = '_synthetic_id'
    
    for idx, row in df.iterrows():
        row_id = row[id_col] if id_col in df.columns else idx
        
        for date_col in date_columns:
            date_value = row[date_col]
            if pd.notna(date_value):
                dates_data.append({
                    'record_id': row_id,
                    'date_type': date_col,
                    'date_value': date_value,
                    'source': 'philgeps'
                })
    
    dates_df = pd.DataFrame(dates_data)
    
    if len(dates_df) > 0:
        print(f"✅ Extracted {len(dates_df):,} date records")
        print(f"   Date types: {dates_df['date_type'].nunique()}")
    else:
        print("⚠️  No date records extracted")
    
    return dates_df

async def main():
    """Main function."""
    print("=" * 80)
    print("PhilGEPS Contractor Normalization")
    print("Using SEC, PCAB, and PhilGEPS license data as clues")
    print("=" * 80)
    
    try:
        # Load PhilGEPS parquet
        print(f"\n📖 Loading PhilGEPS parquet from {PARQUET_PATH}...")
        if not PARQUET_PATH.exists():
            raise FileNotFoundError(f"Parquet file not found: {PARQUET_PATH}")
        
        conn = duckdb.connect()
        philgeps_df = conn.execute(f'SELECT * FROM "{PARQUET_PATH}"').df()
        conn.close()
        
        print(f"✅ Loaded {len(philgeps_df):,} PhilGEPS contract records")
        
        # Load SEC contractors
        sec_lookup = await load_sec_contractors()
        
        # Build contractor clues
        clues = build_contractor_clues(philgeps_df, sec_lookup)
        
        # Normalize contractors in dataframe
        normalized_df = normalize_contractors_in_dataframe(philgeps_df.copy(), clues)
        
        # Extract dates to separate table
        dates_df = extract_dates_to_separate_table(normalized_df)
        
        # Save updated parquet
        print(f"\n💾 Saving updated parquet file...")
        
        # Create backup
        if PARQUET_PATH.exists():
            import shutil
            shutil.copy2(PARQUET_PATH, BACKUP_PATH)
            print(f"   ✅ Backup created: {BACKUP_PATH}")
        
        # Save main parquet
        PARQUET_DIR.mkdir(parents=True, exist_ok=True)
        conn = duckdb.connect()
        conn.register('normalized_df', normalized_df)
        conn.execute(f'CREATE OR REPLACE TABLE temp_philgeps AS SELECT * FROM normalized_df')
        conn.execute(f'COPY temp_philgeps TO "{PARQUET_PATH}" (FORMAT PARQUET)')
        conn.close()
        
        print(f"✅ Saved {len(normalized_df):,} records to {PARQUET_PATH}")
        
        # Save dates parquet
        if len(dates_df) > 0:
            conn = duckdb.connect()
            conn.register('dates_df', dates_df)
            conn.execute(f'CREATE OR REPLACE TABLE temp_dates AS SELECT * FROM dates_df')
            conn.execute(f'COPY temp_dates TO "{DATES_PARQUET_PATH}" (FORMAT PARQUET)')
            conn.close()
            
            print(f"✅ Saved {len(dates_df):,} date records to {DATES_PARQUET_PATH}")
        
        # Print summary
        print("\n" + "=" * 80)
        print("✅ Normalization Complete!")
        print("=" * 80)
        print(f"   Total contracts: {len(normalized_df):,}")
        print(f"   Normalized contractors: {normalized_df['contractor_name_canonical'].notna().sum():,}")
        print(f"   With SEC numbers: {normalized_df['contractor_sec_number'].notna().sum():,}")
        print(f"   With PCAB licenses: {normalized_df['contractor_pcab_license'].notna().sum():,}")
        print(f"   Date records extracted: {len(dates_df):,}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == '__main__':
    import asyncio
    exit(asyncio.run(main()))


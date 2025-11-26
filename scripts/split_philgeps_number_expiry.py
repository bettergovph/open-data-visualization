#!/usr/bin/env python3
"""
Split PhilGEPS number and expiry date in the merchant parquet file.

This script:
1. Reads philgeps_merchant_info.parquet
2. Parses reg_philgeps_number to extract number and expiry
3. Updates the parquet with separate columns
"""

import pandas as pd
import re
from pathlib import Path
import shutil

# Paths
ROOT_DIR = Path(__file__).parent.parent
MERCHANT_PARQUET = ROOT_DIR / 'database' / 'philgeps_merchant_info.parquet'
BACKUP_PARQUET = ROOT_DIR / 'database' / 'philgeps_merchant_info.parquet.backup'

def parse_philgeps_number(philgeps_str):
    """Parse PhilGEPS number string to extract number and expiry."""
    if pd.isna(philgeps_str) or not isinstance(philgeps_str, str):
        return None, None
    
    # Pattern: "200707-15109-1931522274 (Exp:2026-04-08 23:59:59)"
    match = re.search(r'^(.+?)\s*\(Exp:([^)]+)\)', philgeps_str)
    if match:
        number = match.group(1).strip()
        expiry_str = match.group(2).strip()
        # Extract just the date part (YYYY-MM-DD)
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', expiry_str)
        if date_match:
            expiry = date_match.group(1)
        else:
            expiry = expiry_str
        return number, expiry
    else:
        # No expiry found, return original as number
        return philgeps_str, None

def main():
    """Main function."""
    print("=" * 80)
    print("Split PhilGEPS Number and Expiry Date")
    print("=" * 80)
    
    if not MERCHANT_PARQUET.exists():
        print(f"❌ Merchant parquet file not found: {MERCHANT_PARQUET}")
        return 1
    
    try:
        # Create backup
        print(f"\n📖 Reading merchant parquet from {MERCHANT_PARQUET}...")
        shutil.copy2(MERCHANT_PARQUET, BACKUP_PARQUET)
        print(f"✅ Backup created: {BACKUP_PARQUET}")
        
        # Read parquet
        df = pd.read_parquet(MERCHANT_PARQUET, engine='pyarrow')
        print(f"✅ Loaded {len(df):,} merchant records")
        
        # Check if columns already exist
        if 'reg_philgeps_expiry' in df.columns:
            print("⚠️  reg_philgeps_expiry column already exists. Updating...")
        
        # Parse PhilGEPS numbers
        print("\n🔍 Parsing PhilGEPS numbers...")
        results = df['reg_philgeps_number'].apply(parse_philgeps_number)
        
        # Split results into number and expiry
        df['reg_philgeps_number'] = results.apply(lambda x: x[0] if x[0] else None)
        df['reg_philgeps_expiry'] = results.apply(lambda x: x[1] if x[1] else None)
        
        # Count how many had expiry dates
        with_expiry = df['reg_philgeps_expiry'].notna().sum()
        print(f"✅ Parsed {with_expiry:,} PhilGEPS numbers with expiry dates")
        print(f"   {len(df) - with_expiry:,} without expiry dates")
        
        # Save updated parquet
        print(f"\n💾 Saving updated parquet file...")
        df.to_parquet(MERCHANT_PARQUET, engine='pyarrow', index=False)
        print(f"✅ Saved {len(df):,} records to {MERCHANT_PARQUET}")
        
        # Show sample
        print("\n📊 Sample of parsed data:")
        sample = df[df['reg_philgeps_expiry'].notna()][['reg_philgeps_number', 'reg_philgeps_expiry']].head(3)
        for idx, row in sample.iterrows():
            print(f"   Number: {row['reg_philgeps_number']}")
            print(f"   Expiry: {row['reg_philgeps_expiry']}")
            print()
        
        print("=" * 80)
        print("✅ Successfully split PhilGEPS numbers and expiry dates!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == '__main__':
    exit(main())




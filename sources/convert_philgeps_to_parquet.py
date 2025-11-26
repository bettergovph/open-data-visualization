#!/usr/bin/env python3
"""
Convert fixed PhilGEPS JSON to Parquet format.
"""

import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any


def flatten_registration_details(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten registration_details object into top-level fields."""
    flattened = entry.copy()
    
    # Extract registration_details
    reg_details = entry.get('registration_details', {})
    if isinstance(reg_details, dict):
        # Add all registration detail fields as top-level with prefix
        for key, value in reg_details.items():
            if value is not None:
                flattened[f'reg_{key}'] = value
    
    # Remove the nested registration_details
    if 'registration_details' in flattened:
        del flattened['registration_details']
    
    return flattened


def convert_to_dataframe(data: Dict[str, Any]) -> pd.DataFrame:
    """Convert JSON data to pandas DataFrame."""
    results = data.get('results', [])
    
    if not results:
        print("⚠️  No results found in JSON file")
        return pd.DataFrame()
    
    # Flatten all entries
    flattened_results = []
    for entry in results:
        flattened = flatten_registration_details(entry)
        flattened_results.append(flattened)
    
    # Create DataFrame
    df = pd.DataFrame(flattened_results)
    
    # Reorder columns for better readability
    # Put important columns first
    priority_columns = [
        'contractor_name',
        'normalized_name',
        'name',
        'company_type',
        'project_count',
        'reg_status',
        'reg_philgeps_number',
        'reg_mayor\'s_permit',
        'reg_tax_clearance',
        'reg_dti',
        'reg_sec',
        'reg_approved_date',
    ]
    
    # Get all columns
    all_columns = list(df.columns)
    
    # Reorder: priority columns first, then rest
    ordered_columns = []
    for col in priority_columns:
        if col in all_columns:
            ordered_columns.append(col)
            all_columns.remove(col)
    
    # Add remaining columns
    ordered_columns.extend(sorted(all_columns))
    
    # Reorder DataFrame
    df = df[ordered_columns]
    
    return df


def main():
    input_file = Path('database/philgeps_merchant_info_fixed.json')
    output_file = Path('database/philgeps_merchant_info.parquet')
    
    if not input_file.exists():
        print(f"❌ Input file not found: {input_file}")
        return
    
    print(f"📖 Reading {input_file}...")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"📊 Converting {len(data.get('results', []))} entries to DataFrame...")
    df = convert_to_dataframe(data)
    
    if df.empty:
        print("❌ DataFrame is empty")
        return
    
    print(f"✅ DataFrame created: {len(df)} rows, {len(df.columns)} columns")
    print(f"\nColumns: {', '.join(df.columns[:10])}...")
    print(f"\nSample data:")
    print(df.head(3).to_string())
    
    # Save to Parquet
    print(f"\n💾 Saving to {output_file}...")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_file, index=False, engine='pyarrow', compression='snappy')
    
    # Get file size
    file_size_mb = output_file.stat().st_size / (1024 * 1024)
    print(f"✅ Saved! File size: {file_size_mb:.2f} MB")
    
    # Show summary statistics
    print(f"\n📊 Summary:")
    print(f"  Total entries: {len(df)}")
    print(f"  With status: {df['reg_status'].notna().sum()}")
    print(f"  With PhilGEPS number: {df['reg_philgeps_number'].notna().sum()}")
    print(f"  With company type: {df['company_type'].notna().sum()}")
    
    if 'reg_status' in df.columns:
        print(f"\n  Status distribution:")
        print(df['reg_status'].value_counts().head(10))
    
    if 'company_type' in df.columns:
        print(f"\n  Company type distribution:")
        print(df['company_type'].value_counts().head(10))


if __name__ == "__main__":
    main()








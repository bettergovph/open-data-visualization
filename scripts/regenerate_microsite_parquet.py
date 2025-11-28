#!/usr/bin/env python3
"""Regenerate Microsite parquet with extracted JSONB columns"""
import asyncio
import sys
from pathlib import Path

# Import the export function
sys.path.insert(0, str(Path(__file__).parent / 'database'))
from export_to_parquet import export_infrawatch_projects, OUTPUT_DIR

async def main():
    print("🔄 Regenerating Microsite parquet with extracted columns...")
    
    # Export from PostgreSQL
    df = await export_infrawatch_projects()
    
    if df.empty:
        print("⚠️  No data exported")
        return
    
    # Save to parquet
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    infrawatch_path = OUTPUT_DIR / 'infrawatch_projects.parquet'
    df.to_parquet(infrawatch_path, compression='snappy', engine='pyarrow', index=False)
    size_mb = infrawatch_path.stat().st_size / 1024 / 1024
    
    print(f"\n✅ Saved: {infrawatch_path}")
    print(f"   Rows: {len(df):,}")
    print(f"   Columns: {len(df.columns)}")
    print(f"   Size: {size_mb:.2f} MB")
    
    # Show key columns
    key_cols = ['project_name', 'project_description', 'contractor_name', 
                'organization_name', 'infrawatch_implementing_agency', 'source']
    print(f"\nKey columns check:")
    for col in key_cols:
        if col in df.columns:
            non_null = df[col].notna().sum()
            print(f"   ✓ {col}: {non_null:,} non-null")
        else:
            print(f"   ✗ {col}: MISSING")
    
    # Show sample
    print(f"\nSample row:")
    if len(df) > 0:
        sample = df.iloc[0]
        for col in ['project_name', 'project_description', 'organization_name', 'infrawatch_implementing_agency']:
            if col in df.columns and pd.notna(sample[col]):
                val = str(sample[col])[:150]
                print(f"   {col}: {val}")

if __name__ == '__main__':
    import pandas as pd
    asyncio.run(main())


import sys
import pandas as pd
from pathlib import Path
import duckdb

def check_content():
    print("🔍 Checking Parquet Content...")
    parquet_dir = Path('static/data/parquet')
    
    # Check DIME
    dime_path = parquet_dir / 'dime_projects.parquet'
    if dime_path.exists():
        dime_df = pd.read_parquet(dime_path)
        print(f"\n📊 DIME Projects: {len(dime_df)} rows")
        print(f"   Columns: {list(dime_df.columns)}")
        if 'source' in dime_df.columns:
            print(f"   Unique Sources: {dime_df['source'].unique()}")
        else:
            print("   ❌ 'source' column missing")
            
        if not dime_df.empty:
            print(f"   Sample Row: {dime_df.iloc[0].to_dict()}")
    else:
        print("❌ dime_projects.parquet not found")
            
    # Check SSP (Flood)
    flood_path = parquet_dir / 'flood_projects.parquet'
    if flood_path.exists():
        flood_df = pd.read_parquet(flood_path)
        print(f"\n📊 Flood Projects: {len(flood_df)} rows")
        print(f"   Columns: {list(flood_df.columns)}")
        if 'source' in flood_df.columns:
            print(f"   Unique Sources: {flood_df['source'].unique()}")
        else:
            print("   ❌ 'source' column missing")
    else:
        print("❌ flood_projects.parquet not found")

if __name__ == "__main__":
    check_content()

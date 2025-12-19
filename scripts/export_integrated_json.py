#!/usr/bin/env python3
"""
Export integrated projects from Parquet to JSON for API serving.
This is a utility script to generate static/data/integrated_projects.json
from data/parquet/integrated_projects_classified.parquet.
"""

from pathlib import Path
import pandas as pd
import sys

def main():
    # Define paths
    BASE_DIR = Path(__file__).parent.parent
    PARQUET_FILE = BASE_DIR / 'data' / 'parquet' / 'integrated_projects_classified.parquet'
    JSON_FILE = BASE_DIR / 'static' / 'data' / 'integrated_projects.json'

    print(f"Checking for {PARQUET_FILE}...")
    
    if not PARQUET_FILE.exists():
        print(f"❌ Error: Parquet file not found at {PARQUET_FILE}")
        print("   Please wait for the main generation script to complete.")
        return 1
        
    print(f"reading parquet file ({PARQUET_FILE.stat().st_size / (1024*1024):.2f} MB)...")
    try:
        df = pd.read_parquet(PARQUET_FILE)
        print(f"✅ Loaded {len(df)} rows.")
        
        print(f"💾 Saving to JSON {JSON_FILE}...")
        df.to_json(str(JSON_FILE), orient='records', default_handler=str, date_format='iso')
        print(f"✅ Successfully saved JSON to {JSON_FILE}")
        
    except Exception as e:
        print(f"❌ Error during conversion: {e}")
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())

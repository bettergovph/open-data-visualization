
import duckdb
import pandas as pd
from pathlib import Path

DATA_DIR = Path('data/parquet')
FILES = [
    'dime_projects.parquet',
    'philgeps_contracts.parquet',
    'microsite_projects.parquet',
    'transparency_projects.parquet',
    'flood_control_projects.parquet'
]

print("Checking Parquet Schemas...")

for f in FILES:
    p = DATA_DIR / f
    if not p.exists():
        print(f"❌ {f} NOT FOUND")
        continue
    
    try:
        df = duckdb.query(f"SELECT * FROM '{p}' LIMIT 1").df()
        cols = sorted(list(df.columns))
        print(f"\n📂 {f} ({len(cols)} columns):")
        
        # Check for suspicious 'dynasty' columns
        suspicious = [c for c in cols if 'dynasty' in c.lower() or 'congressman' in c.lower() or 'politician' in c.lower()]
        if suspicious:
            print(f"  ⚠️  Suspicious Columns: {suspicious}")
        
        # Print all columns for comparison
        # print(cols) 
        
    except Exception as e:
        print(f"❌ Error reading {f}: {e}")

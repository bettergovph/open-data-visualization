
import duckdb
import pandas as pd

try:
    print("Columns in philgeps_contracts.parquet:")
    df = duckdb.query("SELECT * FROM 'data/parquet/philgeps_contracts.parquet' LIMIT 1").df()
    for col in df.columns:
        print(f"  {col}")
    
    print("\nSample Data (contractor columns):")
    # Check for contractor-like columns
    cols = [c for c in df.columns if 'contractor' in c.lower() or 'awardee' in c.lower()]
    if cols:
        print(duckdb.query(f"SELECT {', '.join(cols)} FROM 'data/parquet/philgeps_contracts.parquet' LIMIT 5").df())
    else:
        print("No contractor columns found!")

except Exception as e:
    print(f"Error: {e}")

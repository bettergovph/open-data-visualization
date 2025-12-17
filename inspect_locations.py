import duckdb
import pandas as pd

parquet_path = 'static/data/unified_locations.parquet'
try:
    print(f"Inspecting {parquet_path}...")
    con = duckdb.connect()
    # Get schema
    schema = con.execute(f"DESCRIBE SELECT * FROM '{parquet_path}'").fetchall()
    print("Schema:")
    for col in schema:
        print(col)
        
    # Sample data
    print("\nSample Data (first 5 rows):")
    df = con.execute(f"SELECT * FROM '{parquet_path}' LIMIT 5").df()
    print(df)
    
    # Check count of non-null barangays
    count = con.execute(f"SELECT count(*) FROM '{parquet_path}' WHERE barangay IS NOT NULL AND barangay != ''").fetchone()[0]
    print(f"\nNon-empty barangays count: {count}")
    
except Exception as e:
    print(f"Error: {e}")

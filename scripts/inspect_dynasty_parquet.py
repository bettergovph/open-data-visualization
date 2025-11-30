import duckdb
import pandas as pd
from pathlib import Path

# Path to the parquet file
parquet_path = Path('data/parquet/political_dynasties.parquet')

if not parquet_path.exists():
    print(f"Error: {parquet_path} does not exist.")
    exit(1)

print(f"Inspecting {parquet_path}...")

# Connect to DuckDB
con = duckdb.connect()

# Inspect schema first
print("Schema:")
print(con.execute("DESCRIBE SELECT * FROM read_parquet('data/parquet/political_dynasties.parquet')").df())

# Query for Davao City, Leyte, and Southern Leyte related entries
# Using * to avoid column name errors for now
query = """
    SELECT *
    FROM read_parquet('data/parquet/political_dynasties.parquet')
    WHERE 
        UPPER(province) LIKE '%DAVAO%' 
        OR UPPER(province) LIKE '%LEYTE%' 
"""

df = con.execute(query).df()
print("\n--- Davao & Leyte Entries (First 5 rows) ---")
print(df.head().to_string())


print("\n--- Davao & Leyte Entries ---")
print(df.to_string())

# Specific check for overlaps or weird assignments
print("\n--- Potential Issues ---")
# Check for duplicates or overlaps in districts
duplicates = df[df.duplicated(subset=['province', 'district', 'position'], keep=False)]
if not duplicates.empty:
    print("Duplicates found:")
    print(duplicates[['first_name', 'last_name', 'province', 'district', 'position']].to_string())
else:
    print("No obvious duplicates based on province/district/position.")

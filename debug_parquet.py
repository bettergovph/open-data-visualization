import duckdb
from pathlib import Path

path = Path("/home/joebert/open-data-visualization/data/parquet/philgeps_contracts.parquet")
print(f"Path: {path}")
print(f"Exists: {path.exists()}")

try:
    con = duckdb.connect()
    query = f"SELECT * FROM '{path}' LIMIT 5"
    res = con.execute(query).fetchall()
    print(f"Result count: {len(res)}")
    print(res)
except Exception as e:
    print(f"Error: {e}")

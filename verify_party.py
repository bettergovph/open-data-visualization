import duckdb
from pathlib import Path

parquet_path = Path("/home/joebert/open-data-visualization/data/parquet/politician_contractors.parquet")

if not parquet_path.exists():
    print("File does not exist")
    exit(1)

conn = duckdb.connect()
cols = conn.execute(f'DESCRIBE SELECT * FROM "{parquet_path}"').fetchall()
print("Columns:")
for col in cols:
    print(f"  {col[0]} ({col[1]})")

print("\nSample Data:")
sample = conn.execute(f'SELECT * FROM "{parquet_path}" LIMIT 5').fetchall()
for row in sample:
    print(row)

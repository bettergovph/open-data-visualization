import duckdb
import os

files = ['dime_projects.parquet', 'relationships.parquet', 'classified_projects.parquet']

for f in files:
    path = f'data/parquet/{f}'
    print(f"\nChecking {path}...")
    if os.path.exists(path):
        try:
            print(duckdb.sql(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall())
            if f == 'classified_projects.parquet':
                print("Sources:", duckdb.sql(f"SELECT source, COUNT(*) FROM read_parquet('{path}') GROUP BY source").fetchall())
        except Exception as e:
            print("Error:", e)
    else:
        print("File not found.")

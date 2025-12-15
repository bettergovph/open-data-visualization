import duckdb
import os

files = ['politician_contractors.parquet', 'relationships.parquet', 'dime_projects.parquet']

for f in files:
    path = f'data/parquet/{f}'
    print(f"\n--- Checking {f} ---")
    if os.path.exists(path):
        try:
            # Describe
            print("Schema:")
            print(duckdb.sql(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall())
            
            # Count
            count = duckdb.sql(f"SELECT COUNT(*) FROM read_parquet('{path}')").fetchone()[0]
            print(f"Row Count: {count}")
            
            # Sample
            print("Sample Data:")
            print(duckdb.sql(f"SELECT * FROM read_parquet('{path}') LIMIT 5").fetchall())
            
            if f == 'politician_contractors.parquet':
                print("Source Stats:")
                print(duckdb.sql(f"SELECT source, COUNT(*) FROM read_parquet('{path}') GROUP BY source").fetchall())
                
        except Exception as e:
            print("Error:", e)
    else:
        print("File not found.")

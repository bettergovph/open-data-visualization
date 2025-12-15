import duckdb
import os

print("Checking Unified Projects...")
if os.path.exists('data/parquet/unified_projects.parquet'):
    try:
        res = duckdb.sql("SELECT source, COUNT(*) FROM read_parquet('data/parquet/unified_projects.parquet') GROUP BY source").fetchall()
        print("Unified Sources:", res)
    except Exception as e:
        print("Error reading unified:", e)
else:
    print("unified_projects.parquet does not exist")

print("\nChecking DIME Parquet...")
if os.path.exists('data/parquet/dime_projects.parquet'):
    try:
        count = duckdb.sql("SELECT COUNT(*) FROM read_parquet('data/parquet/dime_projects.parquet')").fetchone()[0]
        print("DIME Projects Count:", count)
    except Exception as e:
        print("Error reading dime:", e)

print("\nChecking Relationships Parquet...")
if os.path.exists('data/parquet/relationships.parquet'):
    try:
        count = duckdb.sql("SELECT COUNT(*) FROM read_parquet('data/parquet/relationships.parquet')").fetchone()[0]
        print("Relationships Count:", count)
    except Exception as e:
        print("Error reading relationships:", e)

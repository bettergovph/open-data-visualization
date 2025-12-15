import duckdb
try:
    print("Schema:")
    print(duckdb.sql("DESCRIBE SELECT * FROM read_parquet('data/parquet/politician_contractors.parquet')").fetchall())
    print("Sample:")
    print(duckdb.sql("SELECT * FROM read_parquet('data/parquet/politician_contractors.parquet') LIMIT 5").fetchall())
except Exception as e:
    print(e)

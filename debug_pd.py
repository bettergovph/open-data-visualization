import duckdb
try:
    print("Schema:")
    print(duckdb.sql("DESCRIBE SELECT * FROM read_parquet('data/parquet/political_dynasties.parquet')").fetchall())
    print("Sample:")
    print(duckdb.sql("SELECT * FROM read_parquet('data/parquet/political_dynasties.parquet') LIMIT 5").fetchall())
except Exception as e:
    print(e)

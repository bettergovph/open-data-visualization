
import duckdb
import pandas as pd

try:
    con = duckdb.connect()
    print("Schema:")
    print(con.execute("DESCRIBE SELECT * FROM 'static/data/parquet/transparency_projects.parquet'").fetchall())
    print("\nSample Data:")
    print(con.execute("SELECT * FROM 'static/data/parquet/transparency_projects.parquet' LIMIT 2").fetchall())
except Exception as e:
    print(e)

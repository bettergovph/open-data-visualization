import duckdb
con = duckdb.connect()
print(con.execute("SELECT DISTINCT region FROM read_parquet('static/data/unified_locations.parquet') ORDER BY region").fetchall())

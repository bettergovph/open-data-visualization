import duckdb
con = duckdb.connect()
con.execute("CREATE TABLE locs AS SELECT * FROM read_parquet('static/data/unified_locations.parquet')")
df = con.execute("SELECT * FROM locs WHERE municipality LIKE '%BACOLOD%' ORDER BY province, municipality").fetch_df()
print(df)

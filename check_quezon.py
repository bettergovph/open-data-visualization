import duckdb
con = duckdb.connect()
con.execute("CREATE TABLE locs AS SELECT * FROM read_parquet('static/data/unified_locations.parquet')")
df = con.execute("SELECT DISTINCT province, municipality FROM locs WHERE province LIKE '%QUEZON%' OR municipality LIKE '%QUEZON%' ORDER BY province, municipality").fetch_df()
print(df)

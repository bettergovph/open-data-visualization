import duckdb

con = duckdb.connect()
con.execute("CREATE TABLE ul AS SELECT * FROM read_parquet('static/data/unified_locations.parquet')")

# Check for Mike Tan entries
print("=== Mike Tan Entries ===")
res = con.execute("SELECT province, municipality, district, congressman FROM ul WHERE congressman ILIKE '%Mike Tan%' OR congressman ILIKE '%Michael Tan%'").fetchall()
for r in res[:20]:
    print(r)

# Check specifically for QC entries with Mike Tan
print("\n=== Mike Tan in QC? ===")
res = con.execute("SELECT * FROM ul WHERE province ILIKE '%Quezon City%' AND (congressman ILIKE '%Mike Tan%' OR congressman ILIKE '%Michael Tan%')").fetchall()
for r in res:
    print(r)

# Check Tatalon
print("\n=== Tatalon Entries ===")
res = con.execute("SELECT * FROM ul WHERE barangay ILIKE 'Tatalon'").fetchall()
for r in res:
    print(r)

# Check Las Piñas
print("\n=== Las Piñas Entries ===")
res = con.execute("SELECT DISTINCT congressman FROM ul WHERE province ILIKE '%Las Piñas%' OR municipality ILIKE '%Las Piñas%'").fetchall()
for r in res:
    print(r)

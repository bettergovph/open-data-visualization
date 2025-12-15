#!/usr/bin/env python3
"""Check district assignments for Tanauan, Lipa, Anilao"""
import duckdb
import json

con = duckdb.connect()
con.execute("CREATE TABLE ul AS SELECT * FROM read_parquet('static/data/unified_locations.parquet')")

print("=== Tanauan in unified_locations ===")
result = con.execute("SELECT DISTINCT province, municipality, district, congressman FROM ul WHERE municipality ILIKE '%tanauan%'").fetchall()
for r in result:
    print(f"  {r}")

print("\n=== Lipa in unified_locations ===")
result = con.execute("SELECT DISTINCT province, municipality, district, congressman FROM ul WHERE municipality ILIKE '%lipa%'").fetchall()
for r in result:
    print(f"  {r}")

print("\n=== Anilao in unified_locations ===")
result = con.execute("SELECT DISTINCT province, municipality, barangay, district, congressman FROM ul WHERE barangay ILIKE '%anilao%' OR municipality ILIKE '%anilao%'").fetchall()
for r in result:
    print(f"  {r}")

# Check districts.json
print("\n=== Check districts.json for Batangas municipalities ===")
with open('static/data/districts.json', 'r') as f:
    data = json.load(f)
batangas = data['districts'].get('Batangas', {})
munis = batangas.get('municipalities', {})
for muni in ['Tanauan', 'Tanauan City', 'Lipa', 'Lipa City', 'Mabini']:
    print(f"  {muni}: {munis.get(muni, 'NOT FOUND')}")

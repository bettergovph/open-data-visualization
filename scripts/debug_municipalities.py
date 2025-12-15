#!/usr/bin/env python3
"""
Debug why municipalities aren't matching - check districts.json vs unified_locations
"""
import json
import duckdb

# Check districts.json for Cebu
with open('static/data/districts.json', 'r') as f:
    districts = json.load(f)

print("=== Cebu in districts.json ===")
cebu = districts['districts'].get('Cebu', {})
print(f"Representatives: {cebu.get('representatives', {})}")
print(f"Municipalities: {len(cebu.get('municipalities', {}))} entries")
if cebu.get('municipalities'):
    for m in list(cebu.get('municipalities', {}).keys())[:10]:
        print(f"  - {m}")

print("\n=== Cordova in unified_locations ===")
con = duckdb.connect()
con.execute("CREATE TABLE ul AS SELECT * FROM read_parquet('static/data/unified_locations.parquet')")
result = con.execute("SELECT DISTINCT province, municipality, district, congressman FROM ul WHERE municipality ILIKE '%cordova%'").fetchall()
for r in result:
    print(f"  {r}")

print("\n=== Isabel in unified_locations ===")
result = con.execute("SELECT DISTINCT province, municipality, district, congressman FROM ul WHERE municipality ILIKE '%isabel%'").fetchall()
for r in result:
    print(f"  {r}")

print("\n=== Impasug-ong in unified_locations ===")
result = con.execute("SELECT DISTINCT province, municipality, district, congressman FROM ul WHERE municipality ILIKE '%impasug%'").fetchall()
for r in result:
    print(f"  {r}")

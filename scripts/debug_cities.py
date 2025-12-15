#!/usr/bin/env python3
"""Check and fix city entries - Davao City, CDO, Cebu City"""
import json
import duckdb

# Check unified_locations for these cities
con = duckdb.connect()
con.execute("CREATE TABLE ul AS SELECT * FROM read_parquet('static/data/unified_locations.parquet')")

print("=== Davao City in unified_locations ===")
result = con.execute("SELECT DISTINCT province, municipality, district, congressman FROM ul WHERE municipality ILIKE '%davao%' AND municipality ILIKE '%city%'").fetchall()
for r in result:
    print(f"  {r}")

print("\n=== Cagayan de Oro in unified_locations ===")
result = con.execute("SELECT DISTINCT province, municipality, district, congressman FROM ul WHERE municipality ILIKE '%cagayan%oro%' OR municipality ILIKE '%cdo%'").fetchall()
for r in result:
    print(f"  {r}")

print("\n=== Cebu City in unified_locations ===")
result = con.execute("SELECT DISTINCT province, municipality, district, congressman FROM ul WHERE municipality ILIKE '%cebu%city%' OR (municipality ILIKE '%cebu%' AND province = 'CEBU')").fetchall()[:10]
for r in result:
    print(f"  {r}")

# Check districts.json
print("\n=== Check districts.json for cities ===")
with open('static/data/districts.json', 'r') as f:
    data = json.load(f)

for city in ['Davao City', 'City of Davao', 'Cagayan de Oro', 'Cagayan de Oro City', 'Cebu City', 'City of Cebu']:
    if city in data['districts']:
        print(f"  {city}: {data['districts'][city].get('representatives', {})}")
    else:
        print(f"  {city}: NOT FOUND")

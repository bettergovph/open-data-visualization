#!/usr/bin/env python3
"""Debug Biñan matching issue"""
import unicodedata
import duckdb

# Check what's in unified_locations for Biñan
con = duckdb.connect()
con.execute("CREATE TABLE ul AS SELECT * FROM read_parquet('static/data/unified_locations.parquet')")

print("=== Biñan in unified_locations ===")
result = con.execute("SELECT DISTINCT province, municipality, district, congressman FROM ul WHERE municipality ILIKE '%bi_an%' OR municipality ILIKE '%biñan%'").fetchall()
for r in result:
    print(f"  {r}")

# Test project name
test_name = "Construction of Multi-Purpose Building (Barangay Hall), Barangay Biñan, City of Biñan, Laguna"
print(f"\n=== Test Name ===")
print(f"  Original: {test_name}")

name_ascii = unicodedata.normalize('NFKD', test_name).encode('ASCII', 'ignore').decode('ASCII').lower()
print(f"  ASCII: {name_ascii}")

# Check if BIÑAN is in the lookup
municipality_lookup = {}
result = con.execute("SELECT DISTINCT province, municipality, district, congressman FROM ul WHERE congressman IS NOT NULL AND congressman != 'TBD' AND congressman != 'Unknown'").fetchall()
for prov, muni, dist, cong in result:
    if muni and cong:
        muni_clean = muni.upper().replace("CITY OF ", "").replace("MUNICIPALITY OF ", "").strip()
        municipality_lookup[muni_clean] = (prov, dist, cong)
        muni_ascii = unicodedata.normalize('NFKD', muni_clean).encode('ASCII', 'ignore').decode('ASCII')
        municipality_lookup[muni_ascii.upper()] = (prov, dist, cong)

print(f"\n=== Testing lookup for Biñan ===")
print(f"  'BIÑAN' in lookup: {'BIÑAN' in municipality_lookup}")
print(f"  'BINAN' in lookup: {'BINAN' in municipality_lookup}")
print(f"  Lookup value for BIÑAN: {municipality_lookup.get('BIÑAN')}")
print(f"  Lookup value for BINAN: {municipality_lookup.get('BINAN')}")

# Test the search
print(f"\n=== Testing search in project name ===")
for muni_key in ['BIÑAN', 'BINAN', 'biñan', 'binan']:
    muni_key_lower = muni_key.lower()
    in_name = muni_key_lower in test_name.lower()
    in_ascii = muni_key_lower in name_ascii
    print(f"  '{muni_key_lower}' in name: {in_name}, in name_ascii: {in_ascii}")

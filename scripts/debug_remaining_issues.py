#!/usr/bin/env python3
"""Debug the 4 remaining location mismatch issues"""
import json
import duckdb

# Load integrated matrix
with open('static/data/integrated_matrix.json', 'r') as f:
    matrix = json.load(f)

print("=== 1. Isidro Ungab (Davao City 3rd) - should NOT have Davao del Norte/Davao de Oro projects ===")
for entry in matrix['ranking']:
    if 'Ungab' in entry.get('congressman', ''):
        print(f"  {entry['congressman']}: {entry['district']}, {entry['province']}")
        print(f"    Project count: {entry['project_count']}")
        for p in entry['projects'][:5]:
            print(f"    - {p['name'][:100]}")
        print()

print("\n=== 2. Mike Tan (Quezon Province) - should NOT have QC projects ===")
for entry in matrix['ranking']:
    if 'Mike Tan' in entry.get('congressman', '') or 'Michael Tan' in entry.get('congressman', ''):
        print(f"  {entry['congressman']}: {entry['district']}, {entry['province']}")
        print(f"    Project count: {entry['project_count']}")
        for p in entry['projects'][:3]:
            print(f"    - {p['name'][:100]}")
        print()

print("\n=== 3. Vargas-Alfonso (Cagayan 2nd) - should NOT have CDO projects ===")
for entry in matrix['ranking']:
    if 'Vargas' in entry.get('congressman', '') or 'Alfonso' in entry.get('congressman', ''):
        print(f"  {entry['congressman']}: {entry['district']}, {entry['province']}")
        print(f"    Project count: {entry['project_count']}")
        for p in entry['projects'][:3]:
            print(f"    - {p['name'][:100]}")
        print()

print("\n=== 4. Unknown congressman for Palawan ===")
for entry in matrix['ranking']:
    if 'Palawan' in entry.get('province', '').upper() or 'PALAWAN' in entry.get('district', '').upper():
        print(f"  {entry['congressman']}: {entry['district']}, {entry['province']}")
        print(f"    Project count: {entry['project_count']}")
        for p in entry['projects'][:3]:
            print(f"    - {p['name'][:100]}")
        print()

# Check unified_locations for these areas
print("\n=== Check unified_locations ===")
con = duckdb.connect()
con.execute("CREATE TABLE ul AS SELECT * FROM read_parquet('static/data/unified_locations.parquet')")

print("\nPalawan congressmen:")
result = con.execute("SELECT DISTINCT district, congressman FROM ul WHERE province = 'PALAWAN'").fetchall()
for r in result:
    print(f"  {r}")

print("\nDavao del Norte congressmen:")
result = con.execute("SELECT DISTINCT district, congressman FROM ul WHERE province = 'DAVAO DEL NORTE'").fetchall()
for r in result:
    print(f"  {r}")

print("\nDavao de Oro congressmen:")
result = con.execute("SELECT DISTINCT district, congressman FROM ul WHERE province = 'DAVAO DE ORO'").fetchall()
for r in result:
    print(f"  {r}")

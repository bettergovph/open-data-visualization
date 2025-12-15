import duckdb
from pathlib import Path

path = Path("/home/joebert/open-data-visualization/data/parquet/integrated_projects.parquet")
con = duckdb.connect()

print(f"--- Inspecting {path} ---")
# Get all columns
api_cols = con.execute(f"DESCRIBE SELECT * FROM '{path}'").fetchall()
col_names = [c[0] for c in api_cols]

print(f"Total Columns: {len(col_names)}")
print(sorted(col_names))

# Check for potential duplicates (fragmented schema)
fragmented_suspects = [
    ['amount', 'cost', 'budget', 'price'],
    ['contractor', 'awardee'],
    ['desc', 'description'],
    ['loc', 'province', 'city', 'mun', 'town', 'district']
]

print("\n--- Potential Fragmentation ---")
for group in fragmented_suspects:
    print(f"Checking group: {group}")
    found = [c for c in col_names if any(g in c.lower() for g in group)]
    for f in found:
        count = con.execute(f"SELECT COUNT({f}) FROM '{path}'").fetchone()[0]
        print(f"  {f}: {count} non-nulls")

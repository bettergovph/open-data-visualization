import duckdb
import pandas as pd

parquet_path = "data/parquet/integrated_projects.parquet"

print(f"Loading {parquet_path}...")
conn = duckdb.connect()
df = conn.execute(f"SELECT * FROM '{parquet_path}' LIMIT 5").df()
print("Columns:", df.columns.tolist())

# Count unique sources
print("\nUnique sources and counts:")
counts = conn.execute(f"SELECT source, COUNT(*) as count FROM '{parquet_path}' GROUP BY source").df()
print(counts)

# Check for global_id duplicates
print("\nGlobal ID Stats:")
global_counts = conn.execute(f"SELECT global_id, COUNT(*) as c, COUNT(DISTINCT source) as source_count FROM '{parquet_path}' GROUP BY global_id HAVING c > 1 ORDER BY c DESC LIMIT 5").df()
print(global_counts)

# Check for project_name exact matches across sources
print("\nProject Name Cross-Source Matches:")
name_counts = conn.execute(f"SELECT project_name, COUNT(DISTINCT source) as source_count, STRING_AGG(DISTINCT source, ',') as sources FROM '{parquet_path}' GROUP BY project_name HAVING source_count > 1 ORDER BY source_count DESC LIMIT 10").df()
print(name_counts)

# Check total unique project names
query_total = f"SELECT COUNT(*) FROM '{parquet_path}'"
query_unique = f"SELECT COUNT(DISTINCT project_name) FROM '{parquet_path}'"

print(f"\nTotal rows: {conn.execute(query_total).fetchone()[0]}")
print(f"Total unique project names: {conn.execute(query_unique).fetchone()[0]}")

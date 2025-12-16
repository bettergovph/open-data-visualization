
import duckdb

con = duckdb.connect()
print("Loading integrated_projects.parquet...")
con.execute("CREATE TABLE projects AS SELECT * FROM read_parquet('data/parquet/integrated_projects.parquet')")

print("Total rows:", con.execute("SELECT COUNT(*) FROM projects").fetchone()[0])

print("\n--- Exact Duplicates (All cols) ---")
exact = con.execute("SELECT COUNT(*) FROM (SELECT * FROM projects GROUP BY ALL HAVING COUNT(*) > 1)").fetchone()[0]
print(f"Groups with exact duplicates: {exact}")

print("\n--- Duplicates by Name + Amount + Location ---")
shared = con.execute("""
    SELECT COUNT(*) 
    FROM (
        SELECT project_name, amount, location 
        FROM projects 
        WHERE amount IS NOT NULL
        GROUP BY project_name, amount, location 
        HAVING COUNT(*) > 1
    )
""").fetchone()[0]
print(f"Groups with same Name+Amount+Location: {shared}")

print("\n--- Duplicates by Amount + Location (fuzzy name) ---")
# This might be too aggressive if multiple projects have same amount in same province
amount_loc = con.execute("""
    SELECT COUNT(*) 
    FROM (
        SELECT amount, location 
        FROM projects 
        WHERE amount IS NOT NULL
        GROUP BY amount, location 
        HAVING COUNT(*) > 1
    )
""").fetchone()[0]
print(f"Groups with same Amount+Location: {amount_loc}")

print("\n--- Overlap between Sources ---")
print("Top overlapping pairs (Same Name + Amount):")
rows = con.execute("""
    WITH dups AS (
        SELECT project_name, amount, list(source) as sources
        FROM projects
        WHERE amount IS NOT NULL
        GROUP BY project_name, amount
        HAVING COUNT(DISTINCT source) > 1
    )
    SELECT sources, COUNT(*) as cnt
    FROM dups
    GROUP BY sources
    ORDER BY cnt DESC
    LIMIT 10
""").fetchall()

for row in rows:
    print(f"{row[0]}: {row[1]}")

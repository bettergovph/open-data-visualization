import duckdb
import pandas as pd

parquet_path = 'data/parquet/politician_contractors.parquet'
dynasties_path = 'data/parquet/political_dynasties.parquet'

print(f"Checking {parquet_path}...")

try:
    con = duckdb.connect()
    
    # Load dynasties to get IDs
    con.execute(f"CREATE TABLE dynasties AS SELECT * FROM read_parquet('{dynasties_path}')")
    
    targets = ['Bernadette Herrera', 'Eddie Villanueva', 'Elizaldy Salcedo Co', 'Conrado Estrella III']
    target_ids = []
    
    print("\nTarget IDs:")
    for name in targets:
        # Search for name (first + last)
        parts = name.split()
        last = parts[-1]
        first = parts[0]
        
        # Simple search using first/last
        res = con.execute(f"SELECT id, first_name, last_name FROM dynasties WHERE last_name ILIKE '%{last}%' AND first_name ILIKE '%{first}%'").fetchall()
        for r in res:
            print(f"  Found {name}: ID {r[0]} ({r[1]} {r[2]})")
            target_ids.append(r[0])

    if not target_ids:
        print("No target IDs found.")
        exit()
        
    target_ids_str = ','.join(map(str, target_ids))
    
    # Load contractors
    con.execute(f"CREATE TABLE contractors AS SELECT * FROM read_parquet('{parquet_path}')")
    
    print("\nContractor Links:")
    links = con.execute(f"SELECT * FROM contractors WHERE politician_id IN ({target_ids_str})").fetchall()
    
    if not links:
        print("  No links found for these IDs.")
    else:
        for link in links:
            # Adjust index based on schema, assuming: id, politician_id, contractor_name, ...
            print(f"  Politician ID {link[1]}: {link[2]}")

except Exception as e:
    print(f"Error: {e}")

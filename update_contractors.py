
import duckdb
from pathlib import Path

parquet_path = Path('static/data/parquet/politician_contractors.parquet')
pd_path = parquet_path.parent / 'political_dynasties.parquet'

if not parquet_path.exists() or not pd_path.exists():
    print("Files not found")
    exit(1)

con = duckdb.connect()

# 1. Get IDs for Eric Yap, Edvic Yap, Erwin Tulfo
print("Finding IDs...")
ids = {}
for name in ['Eric Yap', 'Edvic Yap', 'Erwin Tulfo']:
    # Split name for search
    parts = name.split()
    first = parts[0].lower()
    last = parts[-1].lower()
    
    res = con.execute(f"""
        SELECT id, first_name, last_name FROM read_parquet('{pd_path}') 
        WHERE lower(first_name) LIKE '%{first}%' AND lower(last_name) LIKE '%{last}%'
    """).fetchall()
    
    if res:
        print(f"Found {name}: {res[0]}")
        ids[name] = res[0][0]
    else:
        print(f"Could not find {name}")

# 2. Prepare new rows
# Schema: politician_id, contractor_name, source, role?, etc.
# Check schema first
schema = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{parquet_path}')").fetchall()
cols = [r[0] for r in schema]
print(f"Schema: {cols}")

# Define new entries
new_entries = []

if 'Eric Yap' in ids:
    new_entries.append({
        'politician_id': ids['Eric Yap'],
        'contractor_name': 'SILVERWOLVES CONSTRUCTION CORPORATION',
        'source': 'Inquirer: Anomalous Flood Control Projects (2025)',
        'role': 'Owner (Beneficial)'
    })
    new_entries.append({
        'politician_id': ids['Eric Yap'],
        'contractor_name': 'ST. TIMOTHY CORPORATION',
        'source': 'Inquirer: Anomalous Flood Control Projects (2025)',
        'role': 'Owner (Beneficial)'
    })

if 'Edvic Yap' in ids:
    # Assuming same link via family/freeze order
    new_entries.append({
        'politician_id': ids['Edvic Yap'],
        'contractor_name': 'SILVERWOLVES CONSTRUCTION CORPORATION',
        'source': 'Inquirer: Freeze Order (2025)',
        'role': 'Owner (Beneficial)'
    })

if 'Erwin Tulfo' in ids:
    new_entries.append({
        'politician_id': ids['Erwin Tulfo'],
        'contractor_name': 'WJ CONSTRUCTION',
        'source': 'ABS-CBN: CCTV Visit (2025)',
        'role': 'Linked'
    })

# 3. Append to Parquet
if new_entries:
    print(f"Adding {len(new_entries)} new entries...")
    
    # Create temp table with existing data
    con.execute("CREATE TABLE current_data AS SELECT * FROM read_parquet('"+str(parquet_path)+"')")
    
    # Insert new data
    # We need to match schema exactly. 
    # Use simple INSERT if columns align, or construct INSERT statement
    
    # Get max ID for auto-increment
    max_id = con.execute("SELECT MAX(id) FROM current_data").fetchone()[0] or 0
    print(f"Max ID: {max_id}")
    
    current_id = max_id
    
    for entry in new_entries:
        pass # Placeholder loop for setup
        
    for entry in new_entries:
        # Construct values based on schema
        vals = []
        current_id += 1
        
        for col in cols:
            val = entry.get(col, None)
            # Handle specific defaults if needed (e.g. created_at)
            if col == 'created_at' and val is None:
                val = '2025-12-13'
            if col == 'id':
                # Auto-increment
                val = current_id
            
            vals.append(val)
        
        # Prepare params
        placeholders = ','.join(['?'] * len(vals))
        con.execute(f"INSERT INTO current_data VALUES ({placeholders})", vals)
    
    # Write back to Parquet
    print("Writing back to parquet...")
    con.execute(f"COPY current_data TO '{parquet_path}' (FORMAT PARQUET)")
    print("Done.")

else:
    print("No entries to add.")

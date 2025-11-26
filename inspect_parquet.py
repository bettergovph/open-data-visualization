import duckdb
from pathlib import Path
import sys

# Add parent directory to path to handle imports if needed, but for this simple script we just need duckdb
PARQUET_DIR = Path('data/parquet')
INTEGRATED_PARQUET = PARQUET_DIR / 'integrated_projects.parquet'

if not INTEGRATED_PARQUET.exists():
    print(f"File not found: {INTEGRATED_PARQUET}")
    # Check absolute path
    abs_path = Path.cwd() / INTEGRATED_PARQUET
    print(f"Checked absolute path: {abs_path}")
    exit(1)

conn = duckdb.connect()
print(f"Inspecting {INTEGRATED_PARQUET}...")

try:
    # Count rows
    count = conn.execute(f"SELECT count(*) FROM '{INTEGRATED_PARQUET}'").fetchone()[0]
    print(f"Total rows: {count}")

    # Columns
    cols = conn.execute(f"DESCRIBE SELECT * FROM '{INTEGRATED_PARQUET}'").fetchall()
    print("Columns:")
    col_names = []
    for col in cols:
        print(f"  {col[0]} ({col[1]})")
        col_names.append(col[0])

    # Unique sources
    print("Unique sources:")
    if 'source' in col_names:
        sources = conn.execute(f"SELECT DISTINCT source, count(*) FROM '{INTEGRATED_PARQUET}' GROUP BY source").fetchall()
        for s in sources:
            print(f"  {s[0]}: {s[1]}")
    elif '_source' in col_names:
        sources = conn.execute(f"SELECT DISTINCT _source, count(*) FROM '{INTEGRATED_PARQUET}' GROUP BY _source").fetchall()
        for s in sources:
            print(f"  {s[0]} (from _source): {s[1]}")
    else:
        print("  No 'source' or '_source' column found!")

    # Analyze text column lengths by source to find "rich" text columns
    print("\nText column average lengths by source (finding rich text):")
    
    # Potential text columns to check
    text_cols = [
        'project_description', 'project_name', 'description', 
        'notice_title', 'award_title', 'philgeps_award_title', 'philgeps_award_title',
        'program', 'project_type', 'work_type', 'remarks',
        'contract_name', 'contract_profile', 'implementing_agency'
    ]
    existing_text_cols = [c for c in text_cols if c in col_names]
    
    if existing_text_cols:
        # Build a query to get avg length for each text column grouped by source
        select_clause = ", ".join([f"CAST(AVG(LENGTH(CAST({c} AS VARCHAR))) AS INTEGER) as {c}_len" for c in existing_text_cols])
        
        if 'source' in col_names:
            query = f"SELECT source, {select_clause} FROM '{INTEGRATED_PARQUET}' GROUP BY source"
        else:
            query = f"SELECT _source, {select_clause} FROM '{INTEGRATED_PARQUET}' GROUP BY _source"
            
        stats = conn.execute(query).fetchall()
        
        # Print results
        result_cols = ['source'] + existing_text_cols
        print(f"  {' | '.join(result_cols)}")
        print(f"  {'-'*120}")
        for row in stats:
            # Format None as 0
            row_fmt = [str(x) if x is not None else '0' for x in row]
            print(f"  {' | '.join(row_fmt)}")
            
        # Also print sample values for the longest columns
        print("\nSample values for rich text columns:")
        for col in existing_text_cols:
            print(f"\n  Column: {col}")
            query = f"SELECT {col} FROM '{INTEGRATED_PARQUET}' WHERE {col} IS NOT NULL AND LENGTH(CAST({col} AS VARCHAR)) > 50 LIMIT 3"
            samples = conn.execute(query).fetchall()
            for s in samples:
                print(f"    - {s[0][:100]}...")
    else:
        print("  No known text columns found.")

except Exception as e:
    print(f"Error inspecting parquet: {e}")

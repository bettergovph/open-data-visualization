#!/usr/bin/env python3
"""Check which parquet file has the extracted JSONB columns"""
import duckdb
from pathlib import Path

# Check both infrawatch_projects.parquet and integrated_projects_classified.parquet
files_to_check = [
    'data/parquet/infrawatch_projects.parquet',
    'data/parquet/integrated_projects_classified.parquet',
    'data/parquet/integrated_projects.parquet'
]

conn = duckdb.connect()

for file_path in files_to_check:
    path = Path(file_path)
    if not path.exists():
        print(f"\n❌ {file_path} - File not found")
        continue
    
    print(f"\n=== {path.name} ===")
    try:
        # Check if it has Microsite/Infrawatch data
        count = conn.execute(f'SELECT COUNT(*) FROM "{path}"').fetchone()[0]
        print(f"Total rows: {count:,}")
        
        if count == 0:
            print("⚠️  Empty file")
            continue
        
        # Get columns
        cols = conn.execute(f'DESCRIBE SELECT * FROM "{path}" LIMIT 1').fetchall()
        col_names = [c[0] for c in cols]
        print(f"Total columns: {len(col_names)}")
        
        # Check for source column
        source_cols = [c for c in col_names if 'source' in c.lower()]
        if source_cols:
            print(f"Source columns: {source_cols}")
            # Count Microsite/Infrawatch
            for sc in source_cols:
                try:
                    microsite_count = conn.execute(
                        f'SELECT COUNT(*) FROM "{path}" WHERE UPPER(CAST("{sc}" AS VARCHAR)) = \'MICROSITE\' OR UPPER(CAST("{sc}" AS VARCHAR)) = \'INFRAWATCH\''
                    ).fetchone()[0]
                    if microsite_count > 0:
                        print(f"  Microsite/Infrawatch rows via {sc}: {microsite_count:,}")
                except:
                    pass
        
        # Check for JSONB-like columns (data, jsonb_data, etc.)
        jsonb_cols = [c for c in col_names if any(x in c.lower() for x in ['data', 'jsonb', 'json'])]
        if jsonb_cols:
            print(f"⚠️  Found JSONB-like columns: {jsonb_cols}")
            print("   This file might still have JSONB data that needs extraction")
        else:
            print("✓ No JSONB columns - data is already extracted")
        
        # Check for extracted columns (project_name, project_description, etc.)
        extracted_cols = [c for c in col_names if any(x in c.lower() for x in ['project_name', 'project_description', 'contractor_name', 'organization_name', 'implementing_agency'])]
        if extracted_cols:
            print(f"✓ Found extracted columns: {extracted_cols[:10]}")
        
        # Show all column names
        print(f"\nAll columns ({len(col_names)}):")
        for i, col in enumerate(col_names, 1):
            print(f"  {i}. {col}")
        
        # Sample row for Microsite if available
        if source_cols:
            for sc in source_cols:
                try:
                    sample = conn.execute(
                        f'SELECT * FROM "{path}" WHERE UPPER(CAST("{sc}" AS VARCHAR)) = \'MICROSITE\' OR UPPER(CAST("{sc}" AS VARCHAR)) = \'INFRAWATCH\' LIMIT 1'
                    ).fetchall()
                    if sample:
                        print(f"\nSample Microsite row (first 15 columns):")
                        row_dict = dict(zip(col_names, sample[0]))
                        for i, (col, val) in enumerate(list(row_dict.items())[:15]):
                            if val:
                                val_str = str(val)[:100]
                                print(f"  {col}: {val_str}")
                        break
                except:
                    pass
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

conn.close()

#!/usr/bin/env python3
"""Simple check for Microsite data and location columns"""
import duckdb
from pathlib import Path

conn = duckdb.connect()

# Expected columns for Microsite
expected_cols = [
    "Contract Details", "Project Description", "Project Title", "Title",
    "Contractor", "Contractor Name", "Contractor_Name",
    "Implementing Agency", "Fund Source", "Project Location", "location", "city", "City"
]

# Check infrawatch_projects.parquet
path = Path('data/parquet/infrawatch_projects.parquet')
print(f"=== {path.name} ===")
if path.exists():
    try:
        count = conn.execute(f'SELECT COUNT(*) FROM "{path}"').fetchone()[0]
        print(f"Rows: {count:,}")
        
        if count > 0:
            # Get all columns
            all_cols = [row[0] for row in conn.execute(f'DESCRIBE SELECT * FROM "{path}" LIMIT 1').fetchall()]
            print(f"Total columns: {len(all_cols)}")
            
            # Check which expected columns exist
            found_cols = [c for c in expected_cols if c in all_cols]
            print(f"Found expected columns: {found_cols}")
            missing_cols = [c for c in expected_cols if c not in all_cols]
            if missing_cols:
                print(f"Missing expected columns: {missing_cols}")
            
            # Check for non-null data in location-related columns
            location_cols = [c for c in all_cols if any(x in c.lower() for x in ['province', 'city', 'municipality', 'barangay', 'location', 'agency', 'contract', 'description'])]
            print(f"\nLocation-related columns found: {location_cols[:10]}")
            
            # Check data in key columns
            for col in found_cols[:5]:
                try:
                    non_null = conn.execute(f'SELECT COUNT(*) FROM "{path}" WHERE "{col}" IS NOT NULL AND "{col}" != \'\'').fetchone()[0]
                    print(f"  {col}: {non_null:,} non-null values")
                except:
                    pass
            
            # Sample row
            sample = conn.execute(f'SELECT * FROM "{path}" LIMIT 1').fetchall()
            if sample:
                row_dict = dict(zip(all_cols, sample[0]))
                print("\nSample row (location-related fields):")
                for col in location_cols[:8]:
                    if col in row_dict and row_dict[col]:
                        val = str(row_dict[col])[:120]
                        print(f"  {col}: {val}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
else:
    print("File not found")

# Check classified file
path2 = Path('data/parquet/integrated_projects_classified.parquet')
print(f"\n=== {path2.name} (Microsite) ===")
if path2.exists():
    try:
        # Check for source column
        all_cols = [row[0] for row in conn.execute(f'DESCRIBE SELECT * FROM "{path2}" LIMIT 1').fetchall()]
        source_col = None
        for col in ['source', '_source', 'Source', 'SOURCE']:
            if col in all_cols:
                source_col = col
                break
        
        if source_col:
            # Count Microsite/Infrawatch
            queries = [
                f'SELECT COUNT(*) FROM "{path2}" WHERE "{source_col}" = \'Microsite\'',
                f'SELECT COUNT(*) FROM "{path2}" WHERE UPPER("{source_col}") = \'MICROSITE\'',
                f'SELECT COUNT(*) FROM "{path2}" WHERE "{source_col}" = \'Infrawatch\'',
                f'SELECT COUNT(*) FROM "{path2}" WHERE UPPER("{source_col}") = \'INFRAWATCH\'',
            ]
            count = 0
            for q in queries:
                try:
                    count = conn.execute(q).fetchone()[0]
                    if count > 0:
                        break
                except:
                    continue
            
            print(f"Microsite/Infrawatch rows: {count:,}")
            
            if count > 0:
                # Get sample
                sample = conn.execute(f'SELECT * FROM "{path2}" WHERE UPPER("{source_col}") = \'MICROSITE\' OR UPPER("{source_col}") = \'INFRAWATCH\' LIMIT 1').fetchall()
                if sample:
                    row_dict = dict(zip(all_cols, sample[0]))
                    loc_cols = [c for c in all_cols if any(x in c.lower() for x in ['province', 'city', 'municipality', 'barangay', 'location', 'agency', 'contract', 'description', 'title'])]
                    print(f"Location columns: {loc_cols[:10]}")
                    print("\nSample Microsite row:")
                    for col in loc_cols[:8]:
                        if col in row_dict and row_dict[col]:
                            val = str(row_dict[col])[:120]
                            print(f"  {col}: {val}")
        else:
            print("No source column found")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
else:
    print("File not found")

conn.close()

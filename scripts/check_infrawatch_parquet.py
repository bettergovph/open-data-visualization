#!/usr/bin/env python3
"""Quick check for infrawatch_projects.parquet"""
import duckdb
from pathlib import Path

path = Path('data/parquet/infrawatch_projects.parquet')
print(f'File exists: {path.exists()}')

if path.exists():
    conn = duckdb.connect()
    try:
        count = conn.execute(f'SELECT COUNT(*) FROM "{path}"').fetchone()[0]
        print(f'Total rows: {count:,}')
        
        if count > 0:
            # Get columns
            cols = conn.execute(f'DESCRIBE SELECT * FROM "{path}" LIMIT 1').fetchall()
            col_names = [c[0] for c in cols]
            print(f'Total columns: {len(col_names)}')
            print(f'\nAll column names:')
            for i, col in enumerate(col_names, 1):
                print(f'  {i}. {col}')
            
            # Check location columns
            loc_cols = [c for c in col_names if any(x in c.lower() for x in ['province', 'city', 'municipality', 'barangay', 'region', 'agency', 'location'])]
            print(f'\nLocation columns found: {len(loc_cols)}')
            if loc_cols:
                print(f'  {loc_cols[:15]}')
            
            # Check non-null counts for location columns
            print('\nNon-null counts for location columns:')
            for col in loc_cols[:10]:
                try:
                    non_null = conn.execute(f'SELECT COUNT(*) FROM "{path}" WHERE "{col}" IS NOT NULL AND "{col}" != \'\'').fetchone()[0]
                    pct = (non_null / count * 100) if count > 0 else 0
                    print(f'  {col}: {non_null:,} ({pct:.1f}%)')
                except Exception as e:
                    print(f'  {col}: Error - {str(e)[:50]}')
            
            # Find ALL columns and show their content
            print('\n=== ALL COLUMNS ===')
            sample = conn.execute(f'SELECT * FROM "{path}" LIMIT 1').fetchall()
            if sample:
                row_dict = dict(zip(col_names, sample[0]))
                
                # Find text columns (likely containing location info)
                text_cols = []
                for col in col_names:
                    if col in row_dict and row_dict[col]:
                        val_str = str(row_dict[col])
                        if len(val_str) > 20:  # Any text column
                            text_cols.append((col, len(val_str), val_str))
                
                # Sort by length
                text_cols.sort(key=lambda x: x[1], reverse=True)
                print(f'\nText columns (sorted by length):')
                for col, length, preview in text_cols[:20]:
                    print(f'  {col}: {length} chars')
                    print(f'    Preview: {preview[:200]}...')
                
                # Check which columns the code expects
                expected_cols = ['Contract Details', 'Project Description', 'Project Title', 'Title', 
                                'Implementing Agency', 'Fund Source', 'Project Location', 'location',
                                'contract_details', 'project_description', 'project_title', 'title',
                                'implementing_agency', 'fund_source', 'project_location']
                print(f'\n=== Checking expected columns ===')
                for exp_col in expected_cols:
                    # Try exact match
                    if exp_col in col_names:
                        val = row_dict.get(exp_col)
                        if val:
                            print(f'  ✓ {exp_col}: {len(str(val))} chars - {str(val)[:150]}...')
                    # Try case-insensitive
                    else:
                        matches = [c for c in col_names if c.lower() == exp_col.lower()]
                        if matches:
                            for match in matches:
                                val = row_dict.get(match)
                                if val:
                                    print(f'  ✓ {match} (matches {exp_col}): {len(str(val))} chars - {str(val)[:150]}...')
        else:
            print('⚠️  File exists but is empty!')
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()
    finally:
        conn.close()
else:
    print('⚠️  File does not exist!')

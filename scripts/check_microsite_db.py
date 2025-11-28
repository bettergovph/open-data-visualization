#!/usr/bin/env python3
"""
Diagnostic script to check Microsite/Infrawatch database contents.
This helps identify why Microsite projects aren't being found.
"""

import sys
from pathlib import Path
import duckdb
import pandas as pd

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Parquet file paths
PARQUET_DIR = Path(__file__).parent.parent / 'data' / 'parquet'
INTEGRATED_PARQUET = PARQUET_DIR / 'integrated_projects.parquet'
CLASSIFIED_PARQUET = PARQUET_DIR / 'integrated_projects_classified.parquet'
INFRAWATCH_PARQUET = PARQUET_DIR / 'infrawatch_projects.parquet'

def check_parquet_file(parquet_path: Path, file_name: str):
    """Check a parquet file for Microsite/Infrawatch projects"""
    if not parquet_path.exists():
        print(f"❌ {file_name} does not exist: {parquet_path}")
        return
    
    print(f"\n📊 Checking {file_name}: {parquet_path}")
    print("=" * 80)
    
    try:
        conn = duckdb.connect()
        
        # Get total row count
        total_count = conn.execute(f'SELECT COUNT(*) FROM "{parquet_path}"').fetchone()[0]
        print(f"✅ Total rows: {total_count:,}")
        
        if total_count == 0:
            print("⚠️  File is empty!")
            return
        
        # Get column names
        columns = conn.execute(f'DESCRIBE SELECT * FROM "{parquet_path}"').fetchall()
        column_names = [col[0] for col in columns]
        print(f"\n📋 Columns ({len(column_names)}):")
        for col in column_names[:20]:  # Show first 20
            print(f"   - {col}")
        if len(column_names) > 20:
            print(f"   ... and {len(column_names) - 20} more")
        
        # Check for source-related columns
        source_columns = [col for col in column_names if 'source' in col.lower() or 'type' in col.lower()]
        if source_columns:
            print(f"\n🔍 Source-related columns found: {source_columns}")
            
            # Check unique values in source columns
            for col in source_columns:
                try:
                    unique_values = conn.execute(
                        f'SELECT DISTINCT "{col}" FROM "{parquet_path}" WHERE "{col}" IS NOT NULL LIMIT 50'
                    ).fetchall()
                    values = [v[0] for v in unique_values if v[0]]
                    if values:
                        print(f"   {col} unique values: {sorted(set(str(v).upper() for v in values))[:20]}")
                except Exception as e:
                    print(f"   ⚠️  Could not query {col}: {e}")
        
        # Check for Microsite/Infrawatch in any text columns
        print(f"\n🔍 Searching for Microsite/Infrawatch mentions...")
        text_columns = [col for col in column_names if any(keyword in col.lower() for keyword in ['name', 'title', 'description', 'source', 'type'])]
        
        for col in text_columns[:10]:  # Check first 10 text columns
            try:
                # Count rows containing microsite or infrawatch
                count = conn.execute(
                    f'''SELECT COUNT(*) FROM "{parquet_path}" 
                    WHERE UPPER(CAST("{col}" AS VARCHAR)) LIKE '%MICROSITE%' 
                    OR UPPER(CAST("{col}" AS VARCHAR)) LIKE '%INFRAWATCH%' '''
                ).fetchone()[0]
                if count > 0:
                    print(f"   {col}: {count:,} rows contain 'microsite' or 'infrawatch'")
            except:
                pass
        
        # Sample a few rows
        print(f"\n📄 Sample rows (first 3):")
        sample = conn.execute(f'SELECT * FROM "{parquet_path}" LIMIT 3').fetchall()
        if sample:
            for i, row in enumerate(sample, 1):
                print(f"\n   Row {i}:")
                row_dict = dict(zip(column_names, row))
                # Show key fields
                for key in ['source', '_source', 'Source', 'SOURCE', 'project_name', 'Project Name', 
                           'Contract Details', 'Project Description', 'Title']:
                    if key in row_dict and row_dict[key]:
                        value = str(row_dict[key])
                        if len(value) > 100:
                            value = value[:100] + "..."
                        print(f"      {key}: {value}")
        
        # Count by source if source column exists
        source_col = None
        for col in ['source', '_source', 'Source', 'SOURCE']:
            if col in column_names:
                source_col = col
                break
        
        if source_col:
            print(f"\n📊 Count by {source_col}:")
            counts = conn.execute(
                f'SELECT "{source_col}", COUNT(*) as cnt FROM "{parquet_path}" GROUP BY "{source_col}" ORDER BY cnt DESC'
            ).fetchall()
            for source_val, count in counts:
                print(f"   {source_val}: {count:,}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error checking {file_name}: {e}")
        import traceback
        traceback.print_exc()

def main():
    print("🔍 Microsite/Infrawatch Database Diagnostic Tool")
    print("=" * 80)
    
    # Check separate Infrawatch file
    check_parquet_file(INFRAWATCH_PARQUET, "infrawatch_projects.parquet")
    
    # Check integrated file
    if INTEGRATED_PARQUET.exists():
        check_parquet_file(INTEGRATED_PARQUET, "integrated_projects.parquet")
    
    # Check classified file
    if CLASSIFIED_PARQUET.exists():
        check_parquet_file(CLASSIFIED_PARQUET, "integrated_projects_classified.parquet")
    
    print("\n" + "=" * 80)
    print("✅ Diagnostic complete")

if __name__ == '__main__':
    main()

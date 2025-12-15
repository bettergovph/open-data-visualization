#!/usr/bin/env python3
"""
Generate integrated_projects.parquet by combining all 5 source Parquet files.
Normalize schemas and ensure source columns are set correctly.
"""

import duckdb
from pathlib import Path
import os
import sys

# Define Paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data" / "parquet"
OUTPUT_FILE = DATA_DIR / "integrated_projects.parquet"

# Source Configurations
SOURCES = [
    {
        "name": "DIME",
        "file": "dime_projects.parquet",
        "source_label": "DIME"
    },
    {
        "name": "PhilGEPS",
        "file": "philgeps_contracts.parquet",
        "source_label": "PhilGEPS"
    },
    {
        "name": "Microsite",
        "file": "infrawatch_projects.parquet",
        "source_label": "Microsite",
        "alt_file": "microsite_projects.parquet"
    },
    {
        "name": "Transparency",
        "file": "transparency_projects.parquet",
        "source_label": "Transparency"
    },
    {
        "name": "SSP",
        "file": "flood_projects.parquet",
        "source_label": "SSP"
    }
]

def generate_integrated_parquet():
    print("🚀 Starting Integrated Parquet Generation...")
    
    con = duckdb.connect()
    union_parts = []
    
    for source in SOURCES:
        file_path = DATA_DIR / source["file"]
        
        # Check for alternate file if primary doesn't exist
        if not file_path.exists() and "alt_file" in source:
             alt_path = DATA_DIR / source["alt_file"]
             if alt_path.exists():
                 file_path = alt_path
        
        if not file_path.exists():
            print(f"⚠️  {source['name']} file not found: {file_path}")
            continue
            
        print(f"📦 Processing {source['name']} from {file_path.name}...")
        
        # Create a view for this source with explicit source columns
        label = source['source_label']
        view_name = f"view_{source['name'].lower()}"
        
        try:
            # We use SELECT * but force overwrite the source column to be consistent
            # And ensure _source exists for compatibility
            # Also cast timestamps to VARCHAR to avoid union type mismatch (TIMESTAMPTZ vs TIMESTAMP_NS)
            
            # Identify timestamp columns to cast
            cols_info = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{str(file_path)}')").fetchall()
            cols = [c[0] for c in cols_info]
            col_set = set(cols)
            
            select_parts = []
            
            # --- NORMALIZATION LOGIC ---
            # Define priority lists for unified columns
            # We use COALESCE in the projection or explicit selection if we know the specific column
            
            # 1. Amount
            if 'amount' in col_set: amount_expr = "amount"
            elif 'contract_amount' in col_set: amount_expr = "contract_amount"
            elif 'Contract Amount' in col_set: amount_expr = '"Contract Amount"' # Transparency
            elif 'Contract Price' in col_set: amount_expr = '"Contract Price"' # Transparency
            elif 'cost_php' in col_set: amount_expr = "cost_php" # Transparency
            elif 'infrawatch_contract_price' in col_set: amount_expr = "infrawatch_contract_price" # Microsite
            elif 'dime_cost' in col_set: amount_expr = "dime_cost"
            else: amount_expr = "NULL"
            
            # 2. Project Name
            if 'project_name' in col_set: name_expr = "project_name"
            elif 'project_title' in col_set: name_expr = "project_title"
            elif 'program' in col_set: name_expr = "program" # DIME sometimes uses program
            elif 'notice_title' in col_set: name_expr = "notice_title" # Transparency
            elif 'award_title' in col_set: name_expr = "award_title"
            elif 'description' in col_set: name_expr = "description"
            else: name_expr = "NULL"
            
            # 3. Contractor
            if 'contractor_name' in col_set: contractor_expr = "contractor_name"
            elif 'contractor' in col_set: contractor_expr = "contractor"
            elif 'awardee_name' in col_set: contractor_expr = "awardee_name"
            elif 'philgeps_awardee_name' in col_set: contractor_expr = "philgeps_awardee_name"
            else: contractor_expr = "NULL"
            
            # 4. Location
            # Combine strict location fields if available, otherwise fallback to generic location string
            if 'location' in col_set: loc_expr = "location"
            elif 'philgeps_area_of_delivery' in col_set: loc_expr = "philgeps_area_of_delivery"
            elif 'province' in col_set: loc_expr = "province" 
            else: loc_expr = "NULL"
            
            # Build the SELECT list
            # We add normalized columns with 'unified_' prefix (or overwrite standard ones if we prefer)
            # Let's overwrite standard ones to ensure downstream scripts find them easily
            
            # Pass through existing columns with quoting and casting
            for col in cols:
                if col in ['source', '_source']:
                    continue # Skip, we overwrite these
                
                quoted_col = f'"{col}"'
                
                # Cast date/time columns to string to be safe
                if any(x in col for x in ['date', 'time', 'at']) or col in ['created_at', 'updated_at']:
                    select_parts.append(f"CAST({quoted_col} AS VARCHAR) AS {quoted_col}")
                else:
                    select_parts.append(quoted_col)
            
            select_query = ", ".join(select_parts)
            
            # Append normalized columns (COALESCE logic handled by python selection above)
            # We explicitly cast amount to DOUBLE to fix the DECIMAL overflow issue upstream too
            con.execute(f"""
                CREATE OR REPLACE VIEW {view_name} AS 
                SELECT 
                    {select_query},
                    CAST({amount_expr} AS DOUBLE) AS amount,
                    CAST({name_expr} AS VARCHAR) AS project_name,
                    CAST({contractor_expr} AS VARCHAR) AS contractor,
                    CAST({loc_expr} AS VARCHAR) AS location,
                    '{label}'::VARCHAR as source,
                    '{label}'::VARCHAR as _source
                FROM read_parquet('{str(file_path)}')
            """)

            
            # Verify count
            count = con.execute(f"SELECT COUNT(*) FROM {view_name}").fetchone()[0]
            print(f"   - Loaded {count} records")
            
            if count > 0:
                union_parts.append(f"SELECT * FROM {view_name}")
                
        except Exception as e:
            print(f"❌ Error processing {source['name']}: {e}")

    if not union_parts:
        print("❌ No data loaded from any source. Aborting.")
        return

    print(f"\n🔄 Combining {len(union_parts)} sources...")
    
    # UNION BY NAME fills missing columns with NULLs, preserving all schema info
    union_query = " UNION ALL BY NAME ".join(union_parts)
    
    try:
        # Export to Parquet
        print(f"💾 Saving to {OUTPUT_FILE}...")
        con.execute(f"COPY ({union_query}) TO '{str(OUTPUT_FILE)}' (FORMAT PARQUET)")
        
        # Verify result
        final_count = con.execute(f"SELECT COUNT(*) FROM '{str(OUTPUT_FILE)}'").fetchone()[0]
        file_size_mb = OUTPUT_FILE.stat().st_size / (1024 * 1024)
        print(f"✅ Success! Generated integrated_projects.parquet")
        print(f"   - Total Projects: {final_count}")
        print(f"   - File Size: {file_size_mb:.2f} MB")
        
    except Exception as e:
        print(f"❌ Failed to write integrated file: {e}")
    finally:
        con.close()

if __name__ == "__main__":
    generate_integrated_parquet()

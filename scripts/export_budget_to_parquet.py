#!/usr/bin/env python3
"""
Export Budget Data to Parquet
Exports budget_2020-2025 from PostgreSQL and budget_amendments_2026.json to Parquet files
for efficient DuckDB processing.
"""

import os
import json
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
import duckdb

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'budget_analysis',
    'user': 'budget_admin',
    'password': 'wuQ5gBYCKkZiOGb61chLcByMu'
}

OUTPUT_DIR = Path("data/parquet")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def export_historical_years():
    print("Connecting to database...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        years = list(range(2020, 2026)) # 2020 to 2025
        
        for year in years:
            print(f"\nProcessing {year}...")
            table_name = f"budget_{year}"
            
            # Check if table exists
            try:
                cursor.execute(f"SELECT 1 FROM {table_name} LIMIT 1")
            except psycopg2.errors.UndefinedTable:
                print(f"  Table {table_name} does not exist, skipping.")
                conn.rollback()
                continue
            
            # Check available columns for source location info
            cursor.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table_name}'")
            available_cols = {row['column_name'] for row in cursor.fetchall()}
            
            select_columns = [
                "id",
                "amt as amount",
                "dsc as description",
                "uacs_dpt_dsc as department_desc",
                "uacs_reg_id as region_id",
                "uacs_agy_dsc as agency_desc",
                "year",
                "source_file"
            ]
            
            # Conditionally add source location columns
            if 'sourceline' in available_cols:
                select_columns.append("sourceline")
            if 'source_row' in available_cols:
                select_columns.append("source_row")
            if 'source_col' in available_cols:
                select_columns.append("source_col")

            query = f"""
                SELECT 
                    {', '.join(select_columns)}
                FROM {table_name}
                WHERE amt > 0
            """
            
            # Read using pandas directly? No, use chunks to be safe with memory
            # But "all in memory" request relies on us preparing the parquet files efficiently first.
            # We can use pd.read_sql
            
            try:
                df = pd.read_sql(query, conn)
                print(f"  Fetched {len(df)} rows.")
                
                # Standardize columns
                df['amount'] = df['amount'].astype(float)
                # Handle potentially non-numeric years (e.g. "GAA-2024")
                df['year'] = pd.to_numeric(df['year'], errors='coerce').fillna(year).astype(int)
                
                output_file = OUTPUT_DIR / f"budget_{year}.parquet"
                print(f"  Saving to {output_file}...")
                df.to_parquet(output_file, index=False)
                print("  Done.")
                
            except Exception as e:
                print(f"  Error exporting {year}: {e}")
                conn.rollback()
                
    except Exception as e:
        print(f"Database error: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

def export_2026_json():
    print("\nProcessing 2026 (JSON)...")
    json_path = Path("static/data/budget_amendments_2026.json")
    if not json_path.exists():
        print(f"  {json_path} not found.")
        return

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        items = data.get('line_items', []) + data.get('projects', [])
        print(f"  Loaded {len(items)} items from JSON.")
        
        # Normalize to flat structure
        normalized_items = []
        for item in items:
            # Extract relevant fields matching the schema we want
            # This needs to cover what find_resurrected_projects expects
            
            # extract amounts
            final_amount = item.get('final_amount')
            original_amount = item.get('original_amount')
            amount = float(final_amount) if final_amount is not None else (float(original_amount) if original_amount is not None else 0.0)
            
            normalized_items.append({
                'id': str(item.get('id', '')),
                'name': item.get('name', ''),
                'revised_name': item.get('revised_name', ''),
                'description': item.get('description', ''),
                'amount': amount,
                'source_sheet': item.get('source_sheet', ''),
                'source_row': item.get('source_row'),
                'contractor': item.get('contractor') or (item.get('contractors')[0] if item.get('contractors') else None)
            })
            
        df = pd.DataFrame(normalized_items)
        output_file = OUTPUT_DIR / "budget_2026_amendments.parquet"
        print(f"  Saving to {output_file}...")
        df.to_parquet(output_file, index=False)
        print("  Done.")
        
    except Exception as e:
        print(f"  Error exporting 2026 JSON: {e}")

if __name__ == "__main__":
    export_historical_years()
    export_2026_json()

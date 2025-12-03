#!/usr/bin/env python3
"""
Import contractor links from CSV file into contractor_dynasty_matches parquet.
This script reads the gardiola_contractors.csv file and adds contractor links
for congressmen who are not yet in the contractor_dynasty_matches table.
"""

import csv
import re
from pathlib import Path
import pandas as pd
import duckdb

# Paths
PARQUET_DIR = Path(__file__).parent.parent / 'data' / 'parquet'
CSV_FILE = Path(__file__).parent.parent / 'database' / 'gardiola_contractors.csv'
CONTRACTOR_PARQUET = PARQUET_DIR / 'contractor_dynasty_matches.parquet'
POLITICIAN_CONTRACTORS_PARQUET = PARQUET_DIR / 'politician_contractors.parquet'
DYNASTY_DB = PARQUET_DIR / 'dynasty_data.duckdb'

def parse_name(name_str):
    """Parse congressman name into first_name and last_name"""
    name = name_str.strip()
    
    # Handle "Zaldy Co (former)" -> "Zaldy Co"
    name = re.sub(r'\s*\(.*?\)', '', name)
    
    # Split by comma if present (e.g., "Last, First")
    if ',' in name:
        parts = [p.strip() for p in name.split(',')]
        if len(parts) >= 2:
            last_name = parts[0]
            first_name = parts[1]
            return first_name, last_name
    
    # Split by space
    parts = name.split()
    if len(parts) >= 2:
        first_name = parts[0]
        last_name = ' '.join(parts[1:])
        return first_name, last_name
    elif len(parts) == 1:
        return parts[0], ''
    
    return '', ''

def parse_contractors(contractor_str):
    """Parse contractor string into list of contractor names"""
    if not contractor_str:
        return []
    
    # Split by comma, but handle cases like "Newington Builders Inc, Lourel Corp"
    contractors = []
    for item in contractor_str.split(','):
        item = item.strip()
        if item:
            contractors.append(item)
    
    return contractors

def main():
    print("📥 Importing contractor links from CSV...")
    
    if not CSV_FILE.exists():
        print(f"❌ CSV file not found: {CSV_FILE}")
        return
    
    # Read CSV
    new_contractors = []
    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            congressman = row.get('Congressman', '').strip()
            contractors_str = row.get('Contractor(s)', '').strip()
            
            if not congressman or not contractors_str:
                continue
            
            first_name, last_name = parse_name(congressman)
            contractors = parse_contractors(contractors_str)
            
            for contractor in contractors:
                new_contractors.append({
                    'dynasty_first_name': first_name,
                    'dynasty_last_name': last_name,
                    'company_name': contractor,
                    'role': 'owner'  # Default role
                })
    
    print(f"✅ Parsed {len(new_contractors)} contractor links from CSV")
    
    # Load existing contractors
    existing_contractors = []
    if CONTRACTOR_PARQUET.exists():
        try:
            df_existing = pd.read_parquet(CONTRACTOR_PARQUET)
            existing_contractors = df_existing.to_dict('records')
            print(f"✅ Loaded {len(existing_contractors)} existing contractor links from contractor_dynasty_matches.parquet")
        except Exception as e:
            print(f"⚠️  Failed to load existing contractors: {e}")
    
    # Also load from politician_contractors.parquet if it exists
    if POLITICIAN_CONTRACTORS_PARQUET.exists():
        try:
            df_politician = pd.read_parquet(POLITICIAN_CONTRACTORS_PARQUET)
            # Map columns to standard format
            politician_contractors = []
            for _, row in df_politician.iterrows():
                # Try different column name variations
                first_name = row.get('first_name') or row.get('dynasty_first_name') or row.get('politician_first_name') or ''
                last_name = row.get('last_name') or row.get('dynasty_last_name') or row.get('politician_last_name') or ''
                company_name = row.get('company_name') or row.get('contractor_name') or ''
                role = row.get('role') or row.get('relationship_type') or 'owner'
                
                if first_name and last_name and company_name:
                    politician_contractors.append({
                        'dynasty_first_name': first_name,
                        'dynasty_last_name': last_name,
                        'company_name': company_name,
                        'role': role
                    })
            
            existing_contractors.extend(politician_contractors)
            print(f"✅ Loaded {len(politician_contractors)} additional contractor links from politician_contractors.parquet")
        except Exception as e:
            print(f"⚠️  Failed to load from politician_contractors.parquet: {e}")
    
    if not existing_contractors and DYNASTY_DB.exists():
        try:
            conn = duckdb.connect(str(DYNASTY_DB))
            try:
                result = conn.execute("SELECT dynasty_first_name, dynasty_last_name, company_name, role FROM contractor_dynasty_matches").fetchall()
                existing_contractors = [
                    {
                        'dynasty_first_name': row[0],
                        'dynasty_last_name': row[1],
                        'company_name': row[2],
                        'role': row[3]
                    }
                    for row in result
                ]
                print(f"✅ Loaded {len(existing_contractors)} existing contractor links from DuckDB")
            finally:
                conn.close()
        except Exception as e:
            print(f"⚠️  Failed to load existing contractors from DuckDB: {e}")
    
    # Check for duplicates
    existing_set = set()
    for item in existing_contractors:
        key = (
            (item.get('dynasty_first_name') or '').upper().strip(),
            (item.get('dynasty_last_name') or '').upper().strip(),
            (item.get('company_name') or '').upper().strip()
        )
        existing_set.add(key)
    
    # Filter out duplicates
    unique_new = []
    for item in new_contractors:
        key = (
            (item.get('dynasty_first_name') or '').upper().strip(),
            (item.get('dynasty_last_name') or '').upper().strip(),
            (item.get('company_name') or '').upper().strip()
        )
        if key not in existing_set:
            unique_new.append(item)
            existing_set.add(key)  # Add to set to prevent duplicates within new_contractors
    
    print(f"✅ Found {len(unique_new)} new unique contractor links to add")
    
    if not unique_new:
        print("ℹ️  No new contractor links to add")
        return
    
    # Combine and save
    all_contractors = existing_contractors + unique_new
    df = pd.DataFrame(all_contractors)
    
    # Save to parquet
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CONTRACTOR_PARQUET, index=False)
    print(f"✅ Saved {len(all_contractors)} total contractor links to {CONTRACTOR_PARQUET}")
    
    # Also update DuckDB if it exists
    if DYNASTY_DB.exists():
        try:
            conn = duckdb.connect(str(DYNASTY_DB))
            try:
                # Drop and recreate table
                conn.execute("DROP TABLE IF EXISTS contractor_dynasty_matches")
                conn.execute("""
                    CREATE TABLE contractor_dynasty_matches AS
                    SELECT * FROM df
                """)
                print(f"✅ Updated DuckDB table with {len(all_contractors)} contractor links")
            finally:
                conn.close()
        except Exception as e:
            print(f"⚠️  Failed to update DuckDB: {e}")
    
    # Print summary
    print("\n📊 Summary of new contractor links:")
    for item in unique_new:
        name = f"{item['dynasty_first_name']} {item['dynasty_last_name']}".strip()
        print(f"   - {name}: {item['company_name']}")
    
    if unique_new:
        print(f"\n✅ Successfully imported {len(unique_new)} new contractor links!")
        print("   Run the cache generation script to see these contractors matched to projects.")
    else:
        print("\nℹ️  No new contractor links to import (all already exist)")

if __name__ == '__main__':
    main()












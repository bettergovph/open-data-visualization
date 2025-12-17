import duckdb
import json
import os
from collections import Counter

def scan_sunwest_variants():
    # Connect to DuckDB
    con = duckdb.connect()
    
    # Path to parquet files (adjusting for absolute path execution context if needed, but simple relative usually works if cwd correctly set, using relative to cwd)
    
    print("Scanning for 'SUNWEST' variants in parquet files...")
    
    # Query to find all distinct contractor names containing SUNWEST
    query = """
    SELECT distinct contractor 
    FROM read_parquet('static/data/source_*.parquet') 
    WHERE upper(contractor) LIKE '%SUNWEST%'
    ORDER BY contractor
    """
    
    try:
        results = con.execute(query).fetchall()
        
        variants = [row[0] for row in results if row[0]]
        print(f"Found {len(variants)} unique variants:")
        for v in variants:
            print(f"- {v}")
            
        # Also check for likely partners or related entities
        print("\nSaving variants to 'sunwest_variants.json'...")
        with open('sunwest_variants.json', 'w', encoding='utf-8') as f:
            json.dump(variants, f, indent=2)
            
    except Exception as e:
        print(f"Error querying: {e}")

if __name__ == "__main__":
    scan_sunwest_variants()

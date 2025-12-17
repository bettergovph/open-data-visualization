import duckdb
import os
import sys

def debug_links():
    print("Connecting to DuckDB...")
    con = duckdb.connect(':memory:')
    
    parquet_file = 'data/parquet/politician_contractors.parquet'
    if not os.path.exists(parquet_file):
        print(f"File not found: {parquet_file}")
        return

    # Check for Ernix Dionisio
    first_name_match = "ERNESTO"
    last_name_match = "DIONISIO" # or "JR." to see what the old pattern found
    
    print(f"Searching for contractors directly in politician_contractors...")
    
    query = """
    SELECT *
    FROM read_parquet('data/parquet/politician_contractors.parquet') 
    LIMIT 5
    """
    
    try:
        results = con.execute(query).fetchall()
        columns = [desc[0] for desc in con.description]
        
        print(f"\nFound {len(results)} matches:")
        for row in results:
            print("-" * 40)
            for i, col in enumerate(columns):
                print(f"{col}: {row[i]}")
    except Exception as e:
        print(f"Error querying parquet: {e}")

if __name__ == "__main__":
    debug_links()

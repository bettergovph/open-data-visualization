import duckdb
import pandas as pd

try:
    con = duckdb.connect()
    # Read everything for Ernix
    query = """
    SELECT * 
    FROM read_parquet('data/parquet/political_dynasties.parquet') 
    WHERE first_name ILIKE '%Ernix%' OR last_name ILIKE '%Dionisio%'
    """
    df = con.execute(query).fetch_df()
    
    print("Columns:", df.columns.tolist())
    print("\nRows found:", len(df))
    for idx, row in df.iterrows():
        print(f"\n--- Row {idx} ---")
        for col in ['full_name', 'position', 'province', 'district', 'party_list', 'contractors']:
            if col in df.columns:
                print(f"{col}: {row[col]}")
            
except Exception as e:
    print(f"Error: {e}")

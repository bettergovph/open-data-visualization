import duckdb
import json
import os

def extract_all_contractors():
    print("Connecting to DuckDB...")
    con = duckdb.connect()
    
    # Target the unified projects file
    parquet_path = os.path.abspath('static/data/parquet/integrated_projects_matched.parquet')
    
    if not os.path.exists(parquet_path):
        # Fallback to checking other likely candidates if the specific one isn't the "unified" one the user meant
        # But let's try this one first.
        print(f"⚠️ File not found at {parquet_path}, trying broad scan of parquet dir...")
        parquet_path = os.path.abspath('static/data/parquet/*.parquet')
    
    print(f"Reading from: {parquet_path}")
    
    # We need to query for 'contractor' column.
    # Note: Not all parquet files might have 'contractor' column if we use *.parquet wildcard.
    # So we should probably target specific files or handle schema differences.
    # But for 'integrated_projects_matched.parquet', it should exist.
    
    query = f"""
    SELECT distinct contractor_name 
    FROM read_parquet('{parquet_path.replace(os.sep, '/')}') 
    WHERE contractor_name IS NOT NULL 
    AND length(trim(contractor_name)) > 0
    ORDER BY contractor_name
    """
    
    try:
        results = con.execute(query).fetchall()
        unique_contractors = [row[0] for row in results]
        
        print(f"Found {len(unique_contractors)} unique contractor names.")
        
        output_file = 'unique_contractors.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(unique_contractors, f, indent=2)
            
        print(f"✅ Saved to {output_file}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        # If column doesn't exist, try inspecting schema
        try:
            print("Inspecting schema...")
            con.execute(f"DESCRIBE SELECT * FROM read_parquet('{parquet_path.replace(os.sep, '/')}') LIMIT 1").show()
        except:
            pass

if __name__ == "__main__":
    extract_all_contractors()

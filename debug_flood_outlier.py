import duckdb
import pandas as pd
import glob

def check_flood_outlier():
    con = duckdb.connect(':max_memory:')
    try:
        # Check flood parquet files specifically
        # Locate flood files
        files = glob.glob('data/parquet/flood*.parquet')
        if not files:
            print("No flood parquet files found.")
            return

        print(f"Checking files: {files}")
        
        # We need to filter for projects that WOUL matches Mark Anthony Santos
        # Since matches are dynamic, we look for projects with huge amounts first
        
        for f in files:
            print(f"Scanning {f}...")
            # Check for crazy amounts > 1 trillion
            query = f"""
            SELECT * 
            FROM read_parquet('{f}')
            WHERE CAST(contract_amount AS DOUBLE) > 1000000000000
            LIMIT 5
            """
            try:
                results = con.execute(query).fetchall()
                if results:
                    print(f"Found CRAZY amounts in {f}:")
                    for r in results:
                        print(r)
            except Exception as e:
                # schema might differ
                print(f"Skipping query on {f} due to schema/error: {e}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_flood_outlier()

import duckdb

def check_mark_santos():
    con = duckdb.connect(':memory:')
    # Load config to get variations if needed, but simple query first
    
    # We need to check integrated_projects.parquet or just generate for him
    # Let's try to query the integrated file if it exists
    try:
        query = """
        SELECT * FROM read_parquet('data/parquet/integrated_projects.parquet')
        WHERE congressman = 'Mark Anthony Santos'
        ORDER BY amount DESC
        LIMIT 5
        """
        results = con.execute(query).fetchall()
        print(f"Top projects for Mark Anthony Santos:")
        for res in results:
            print(res)
    except Exception as e:
        print(f"Error reading parquet: {e}")
        # If integrated file doesn't exist or doesn't have congressman column yet (since we are generating it),
        # we might need to look at raw data.
        # But the user saw this in the output, so it must be in the pipeline.

if __name__ == "__main__":
    check_mark_santos()

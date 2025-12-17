import duckdb

def check_mark_outlier():
    con = duckdb.connect(':memory:')
    try:
        # Check source integrated file
        query = """
        SELECT project_name, amount, source 
        FROM read_parquet('data/parquet/integrated_projects.parquet')
        WHERE congressman = 'Mark Anthony Santos'
        ORDER BY amount DESC
        LIMIT 1
        """
        result = con.execute(query).fetchone()
        if result:
            print(f"Top project in integrated: {result}")
            print(f"Amount: {result[1]:.2f}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_mark_outlier()

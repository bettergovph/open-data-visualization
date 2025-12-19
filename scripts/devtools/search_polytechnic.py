
import duckdb

try:
    con = duckdb.connect()
    print("Searching for 'Polytechnic' in Transparency Projects...")
    # Use case-insensitive search
    query = """
    SELECT contract_id, project_name, amount 
    FROM 'static/data/parquet/transparency_projects.parquet' 
    WHERE lower(project_name) LIKE '%polytechnic%'
    """
    rows = con.execute(query).fetchall()
    print(f"Found {len(rows)} matches:")
    for r in rows:
        print(r)
except Exception as e:
    print(e)

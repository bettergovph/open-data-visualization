
import duckdb
from pathlib import Path

parquet_path = Path('static/data/parquet/politician_contractors.parquet')
if not parquet_path.exists():
    print("Not found")
    exit(1)

root_dir = parquet_path.parent
pd_path = root_dir / 'political_dynasties.parquet'

print(f"Checking Zaldy Co in {parquet_path}...")
try:
    con = duckdb.connect()
    res = con.execute(f"""
        SELECT pd.first_name, pd.last_name, pc.contractor_name, pc.source
        FROM read_parquet('{parquet_path}') pc
        JOIN read_parquet('{pd_path}') pd ON pc.politician_id = pd.id
        WHERE lower(pd.last_name) LIKE '%co%' AND lower(pd.first_name) LIKE '%zaldy%'
    """).fetchall()
    
    print("--- Zaldy Co Matches ---")
    for r in res:
        print(r)
        
except Exception as e:
    print(e)


import duckdb
from pathlib import Path

parquet_path = Path('database/parquet/politician_contractors.parquet')
if not parquet_path.exists():
    # Try finding it
    import os
    for root, dirs, files in os.walk('.'):
        if 'politician_contractors.parquet' in files:
            parquet_path = Path(root) / 'politician_contractors.parquet'
            break
            
root_dir = parquet_path.parent

print(f"Checking {parquet_path}...")
try:
    con = duckdb.connect()
    pd_path = root_dir / 'political_dynasties.parquet'
    if not pd_path.exists():
         print("Cannot find political_dynasties.parquet")
         exit(1)

    print(f"Joining {parquet_path} with {pd_path}...")
    
    # Check for Momo
    res_momo = con.execute(f"""
        SELECT pd.first_name, pd.last_name, pc.contractor_name, pc.source
        FROM read_parquet('{parquet_path}') pc
        JOIN read_parquet('{pd_path}') pd ON pc.politician_id = pd.id
        WHERE 
        (lower(pd.first_name) LIKE '%momo%' OR lower(pd.last_name) LIKE '%momo%' OR 
         lower(pc.contractor_name) LIKE '%swerte%' OR lower(pc.contractor_name) LIKE '%suerte%')
    """).fetchall()
    
    print("--- Momo / La Swerte Matches ---")
    for r in res_momo:
        print(r)

    # Check for Yap / Tulfo
    res_yap = con.execute(f"""
        SELECT pd.first_name, pd.last_name, pc.contractor_name, pc.source
        FROM read_parquet('{parquet_path}') pc
        JOIN read_parquet('{pd_path}') pd ON pc.politician_id = pd.id
        WHERE 
        ((lower(pd.last_name) LIKE '%yap%' AND (lower(pc.source) LIKE '%tulfo%' OR lower(pc.source) LIKE '%campaign%')) OR
        (lower(pd.first_name) LIKE '%tulfo%' OR lower(pd.last_name) LIKE '%tulfo%'))
    """).fetchall()

    print("--- Yap / Tulfo Matches ---")
    for r in res_yap:
        print(r)
        
except Exception as e:
    import traceback
    traceback.print_exc()


import duckdb
from pathlib import Path

base_dir = Path(".").resolve()
# Try both files
files = [
    base_dir / "data" / "parquet" / "integrated_projects_classified.parquet",
    base_dir / "data" / "parquet" / "integrated_projects.parquet"
]

for p in files:
    if p.exists():
        print(f"Checking {p.name}...")
        try:
            conn = duckdb.connect()
            # Escape path
            path_str = str(p).replace("'", "''")
            # Get columns
            query = f"SELECT * FROM read_parquet('{path_str}') LIMIT 0"
            conn.execute(query)
            cols = [desc[0] for desc in conn.description]
            print(f"Columns: {cols}")
            
            # Check for amount columns
            amount_cols = [c for c in cols if c in ['amount', 'dime_cost', 'infrawatch_contract_price']]
            print(f"Found amount columns: {amount_cols}")
            conn.close()
            break
        except Exception as e:
            print(f"Error: {e}")

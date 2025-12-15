import duckdb
from pathlib import Path

base_dir = Path("/home/joebert/open-data-visualization/data/parquet")
files = [
    "dime_projects.parquet",
    "philgeps_contracts.parquet",
    "infrawatch_projects.parquet",
    "transparency_projects.parquet",
    "flood_projects.parquet"
]

con = duckdb.connect()
for f in files:
    path = base_dir / f
    if path.exists():
        print(f"--- {f} ---")
        try:
            cols = con.execute(f"DESCRIBE SELECT * FROM '{path}'").fetchall()
            print([c[0] for c in cols])
        except Exception as e:
            print(f"Error: {e}")
    else:
        print(f"--- {f} NOT FOUND ---")

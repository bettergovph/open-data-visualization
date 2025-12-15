
import pandas as pd
from pathlib import Path

path = Path('static/data/parquet/politician_contractors.parquet')
if path.exists():
    df = pd.read_parquet(path)
    print(f"Columns: {list(df.columns)}")
    if not df.empty:
        print("Sample Row:")
        print(df.iloc[0])
else:
    print("File not found")

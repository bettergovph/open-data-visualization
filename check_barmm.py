
import duckdb
import pandas as pd

try:
    con = duckdb.connect()
    df = con.execute("SELECT DISTINCT province, district FROM 'static/data/unified_locations.parquet' WHERE province ILIKE '%TAWI%' OR province ILIKE '%BASILAN%' OR province ILIKE '%MAGUINDANAO%' ORDER BY province, district").fetchdf()
    print(df)
except Exception as e:
    print(e)

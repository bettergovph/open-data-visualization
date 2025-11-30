import duckdb
import pandas as pd

con = duckdb.connect()

query = """
    SELECT 
        id, 
        first_name, 
        last_name, 
        province, 
        municipality_city, 
        position,
        year,
        party
    FROM read_parquet('data/parquet/political_dynasties.parquet')
    WHERE 
        (UPPER(last_name) = 'DUTERTE' AND UPPER(first_name) LIKE '%PAOLO%')
        OR (UPPER(last_name) = 'UNGAB' AND UPPER(first_name) LIKE '%ISIDRO%')
        OR (UPPER(last_name) = 'GARCIA' AND UPPER(first_name) LIKE '%VINCENT%')
        OR (UPPER(last_name) = 'ROMUALDEZ' AND UPPER(first_name) LIKE '%MARTIN%')
    ORDER BY last_name, year DESC
"""

df = con.execute(query).df()
print(df.to_string())

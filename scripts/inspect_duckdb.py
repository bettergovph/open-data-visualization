import duckdb

conn = duckdb.connect('data/parquet/dynasty_data.duckdb')
rows = conn.execute("""
    SELECT 
        c.full_name, 
        c.district_number, 
        dm.municipality
    FROM congressmen c
    LEFT JOIN district_municipalities dm ON c.district_key = dm.district_key
    WHERE c.province = 'Iloilo'
    LIMIT 20
""").fetchall()

for row in rows:
    print(row)

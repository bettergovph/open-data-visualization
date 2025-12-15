import duckdb
try:
    print('DIME:', duckdb.sql("SELECT COUNT(1) FROM read_parquet('data/parquet/dime_projects.parquet')").fetchone()[0])
except Exception as e:
    print('DIME Error:', e)
    
try:
    print('Relationships:', duckdb.sql("SELECT COUNT(1) FROM read_parquet('data/parquet/relationships.parquet')").fetchone()[0])
except Exception as e:
    print('Relationships Error:', e)

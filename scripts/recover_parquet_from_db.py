
import psycopg2
import pandas as pd
from pathlib import Path
import os

# Configuration
PARQUET_DIR = Path('data/parquet')
CREDENTIALS = {
    'user': 'budget_admin',
    'password': 'wuQ5gBYCKkZiOGb61chLcByMu',
    'host': 'localhost',
    'port': '5432'
}

EXPORTS = [
    {
        'db': 'infrawatch',
        'table': 'infrawatch_projects',
        'parquet_name': 'microsite_projects.parquet'
    },
    {
        'db': 'flood',
        'table': 'flagged_flood_projects',
        'parquet_name': 'flood_control_projects.parquet'
    }
]

def export_table(config):
    db = config['db']
    table = config['table']
    output_file = PARQUET_DIR / config['parquet_name']
    
    print(f"\n🚀 Exporting {db}.{table} -> {output_file}...")
    
    try:
        conn = psycopg2.connect(database=db, **CREDENTIALS)
        
        # Read using pandas (efficient for medium datasets)
        # using chunksize if needed, but for now assuming fits in memory
        query = f"SELECT * FROM {table}"
        
        print("   Reading from database...")
        df = pd.read_sql(query, conn)
        print(f"   Loaded {len(df)} rows.")
        
        # Clean columns if needed (convert objects/dicts to str if pyarrow complains)
        # Common issue with JSON columns in Postgres
        for col in df.columns:
            if df[col].dtype == 'object':
                # Try to detect if it's a complex object
                try:
                    # Convert only if it contains dict/list, or fillna
                    pass 
                except:
                    df[col] = df[col].astype(str)

        print("   Writing parquet...")
        df.to_parquet(output_file, index=False)
        print(f"   ✅ Success: {output_file}")
        
    except Exception as e:
        print(f"   ❌ Failed: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    for task in EXPORTS:
        export_table(task)

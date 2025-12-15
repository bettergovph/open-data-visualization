
import psycopg2
import pandas as pd

CREDENTIALS = {
    'user': 'budget_admin',
    'password': 'wuQ5gBYCKkZiOGb61chLcByMu',
    'host': 'localhost',
    'port': '5432'
}

DATABASES = ['budget_analysis', 'infrawatch', 'flood', 'dime', 'philgeps']

print("Listing All Tables...")

for db in DATABASES:
    print(f"\n--- Checking DB: {db} ---")
    try:
        conn = psycopg2.connect(database=db, **CREDENTIALS)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        
        tables = cur.fetchall()
        for t in tables:
            print(f"  - {t[0]}")
        
        conn.close()
    except Exception as e:
        print(f"  ⚠️  Connection Error: {e}")

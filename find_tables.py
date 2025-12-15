
import psycopg2
import pandas as pd

CREDENTIALS = {
    'user': 'budget_admin',
    'password': 'wuQ5gBYCKkZiOGb61chLcByMu',
    'host': 'localhost',
    'port': '5432'
}

DATABASES = ['budget_analysis', 'infrawatch', 'flood', 'dime', 'philgeps']

POSSIBLE_TABLES = [
    'microsite_projects', 
    'flood_control_projects',
    'transparency_projects', # Check this one too as it had columns issue? No, it was just missing in logic maybe.
    'dime_projects', # Just to check schema
]

print("Scanning Databases...")

for db in DATABASES:
    print(f"\n--- Checking DB: {db} ---")
    try:
        conn = psycopg2.connect(database=db, **CREDENTIALS)
        cur = conn.cursor()
        
        for table in POSSIBLE_TABLES:
            # Check if table exists
            cur.execute(f"""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = '{table}'
                );
            """)
            exists = cur.fetchone()[0]
            
            if exists:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]
                print(f"  ✅ Found '{table}' (Rows: {count})")
            else:
                pass
                # print(f"  ❌ '{table}' not found")
        
        conn.close()
    except Exception as e:
        print(f"  ⚠️  Connection Error: {e}")

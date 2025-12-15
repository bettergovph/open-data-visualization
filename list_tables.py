
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Try getting DB url
db_url = os.getenv('DATABASE_URL')
if not db_url:
    # constructing from parts if url not present
    user = os.getenv('POSTGRES_USER', 'postgres')
    password = os.getenv('POSTGRES_PASSWORD', 'postgres')
    host = os.getenv('POSTGRES_SERVER', 'localhost')
    port = os.getenv('POSTGRES_PORT', '5432')
    db = os.getenv('POSTGRES_DB', 'budget_db')
    db_url = f"postgresql://{user}:{password}@{host}:{port}/{db}"

print(f"Connecting to DB...") # Don't print full URL to avoid leaking creds in logs if not needed

try:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
    """)
    
    tables = cur.fetchall()
    print("\nTables found:")
    for t in tables:
        print(f" - {t[0]}")
        
        # Check counts for interesting tables
        if t[0] in ['microsite_projects', 'flood_control_projects', 'contractor_dynasty_matches', 'politician_contractors']:
            cur.execute(f"SELECT COUNT(*) FROM {t[0]}")
            count = cur.fetchone()[0]
            print(f"   (Rows: {count})")

except Exception as e:
    print(f"Error: {e}")

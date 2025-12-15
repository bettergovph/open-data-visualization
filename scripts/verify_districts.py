
import duckdb
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
PARQUET_PATH = BASE_DIR / "static" / "data" / "unified_locations.parquet"

def verify():
    if not PARQUET_PATH.exists():
        print("Parquet file not found.")
        return

    conn = duckdb.connect()
    
    # Check District Stats
    print("Checking District Coverage...")
    stats = conn.execute(f"""
        SELECT 
            district, 
            COUNT(*) as count
        FROM read_parquet('{PARQUET_PATH}')
        GROUP BY district
        ORDER BY count DESC
    """).fetchall()
    
    unknown_count = 0
    total_count = 0
    
    for dist, count in stats:
        total_count += count
        if dist == "Unknown":
            unknown_count = count
        if dist in ["Unknown", "Lone District", "1st District"]:
             print(f"{dist}: {count}")
             
    print(f"Total Rows: {total_count}")
    print(f"Unknown Districts: {unknown_count}")
    print(f"Coverage: {100 - (unknown_count/total_count*100):.2f}%")
    
    # Sample Unknowns
    if unknown_count > 0:
        print("\nSample Unknown Locations:")
        samples = conn.execute(f"""
            SELECT region, province, municipality, barangay 
            FROM read_parquet('{PARQUET_PATH}')
            WHERE district = 'Unknown'
            LIMIT 10
        """).fetchall()
        for r in samples:
            print(r)

if __name__ == "__main__":
    verify()

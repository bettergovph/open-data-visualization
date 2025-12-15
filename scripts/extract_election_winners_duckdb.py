import duckdb
import json
import re
from pathlib import Path
from datetime import datetime

OUTPUT_FILE = Path("static/data/elections_2025_winners.json")
DATA_GLOB = "../ph-elections2025/data/**/*.csv"

def extract_winners():
    print(f"🦆 Connecting to DuckDB to process election results from {DATA_GLOB}...")
    con = duckdb.connect(database=':memory:')
    
    # 1. Load Data
    # Use auto_detect=True and union_by_name=True to handle CSV variations
    
    print("   Reading CSVs (this may take a moment)...")
    try:
        con.execute(f"""
            CREATE TABLE summary AS 
            SELECT 
                contest_name, 
                candidate_name, 
                SUM(votes) as total_votes
            FROM read_csv('{DATA_GLOB}', 
                auto_detect=True,
                union_by_name=True,
                filename=True,
                ignore_errors=True
            )
            WHERE contest_name LIKE '%MEMBER, HOUSE OF REPRESENTATIVES%'
            GROUP BY contest_name, candidate_name
        """)
    except Exception as e:
        print(f"❌ Error reading CSVs: {e}")
        return

    print("   ✅ Aggregation Complete. Ranking candidates...")
    
    # 2. Rank Candidates
    try:
        df = con.execute("""
            WITH Ranked AS (
                SELECT 
                    contest_name,
                    candidate_name,
                    total_votes,
                    ROW_NUMBER() OVER (PARTITION BY contest_name ORDER BY total_votes DESC) as rank
                FROM summary
            )
            SELECT * FROM Ranked WHERE rank <= 3 ORDER BY contest_name, rank
        """).fetchdf()
    except Exception as e:
        print(f"❌ Error ranking candidates (maybe empty table?): {e}")
        return
    
    print(f"   Fetched {len(df)} candidate records.")
    
    # 3. Process into clean JSON
    results = {}
    
    for _, row in df.iterrows():
        contest = row['contest_name']
        
        if contest not in results:
            results[contest] = {
                "winner": None,
                "candidates": []
            }
            
        cand = {
            "name": row['candidate_name'],
            "votes": int(row['total_votes']),
            "rank": int(row['rank'])
        }
        results[contest]["candidates"].append(cand)
        
        if row['rank'] == 1:
            results[contest]["winner"] = cand
            
    # Save
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
        
    print(f"✅ Saved winners to {OUTPUT_FILE}")

if __name__ == "__main__":
    extract_winners()

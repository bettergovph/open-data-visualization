
import pandas as pd
from pathlib import Path

def check_file(filename):
    path = Path(f'static/data/parquet/{filename}')
    print(f"\n📂 {filename}")
    if not path.exists():
        print("   ❌ File not found")
        return
        
    try:
        # Read only schema if possible or just head
        df = pd.read_parquet(path)
        cols = list(df.columns)
        
        # Find potential contractor columns
        candidates = [c for c in cols if 'contract' in c.lower() or 'awardee' in c.lower() or 'company' in c.lower()]
        
        print(f"   Shape: {df.shape}")
        print(f"   Potential Contractor Columns: {candidates}")
        
        # Print sample values for candidates
        if not df.empty:
            sample = df.iloc[0]
            for c in candidates:
                val = sample[c]
                print(f"      - {c}: {val}")
                
    except Exception as e:
        print(f"   ⚠️ Error reading: {e}")

def main():
    files = [
        'dime_projects.parquet',
        'flood_projects.parquet',
        'philgeps_contracts.parquet',
        'infrawatch_projects.parquet',
        'political_dynasties.parquet',
        'politician_contractors.parquet'
    ]
    
    print("🔍 Inspecting Contractor Columns across Databases...")
    for f in files:
        check_file(f)

if __name__ == "__main__":
    main()

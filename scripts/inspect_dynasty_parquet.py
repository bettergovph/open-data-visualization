
import pandas as pd
from pathlib import Path

def inspect_dynasty():
    path = Path('static/data/parquet/political_dynasties.parquet')
    if not path.exists():
        print("❌ File not found")
        return
        
    df = pd.read_parquet(path)
    print(f"📊 Rows: {len(df)}")
    print(f"📋 Columns: {list(df.columns)}")
    
    # Check for contractors column or similar
    contractor_cols = [c for c in df.columns if 'contract' in c.lower()]
    print(f"🔍 potential contractor columns: {contractor_cols}")
    
    # Sample row
    if not df.empty:
        sample = df.iloc[0]
        print("\n🔍 Sample Row:")
        print(sample)
        
        # Check non-empty contractors
        if 'contractors' in df.columns:
            with_contractors = df[df['contractors'].map(lambda x: len(x) > 0 if isinstance(x, (list, tuple)) else False)]
            print(f"\n✅ Rows with contractors: {len(with_contractors)}")
            if not with_contractors.empty:
                print("   Sample contractor entry:")
                print(with_contractors.iloc[0]['contractors'])
            else:
                print("   ❌ No rows have contractors populated")

if __name__ == "__main__":
    inspect_dynasty()

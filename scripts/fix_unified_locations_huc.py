import pandas as pd
import os

def fix_hucs():
    parquet_path = "static/data/unified_locations.parquet"
    
    if not os.path.exists(parquet_path):
        print(f"Error: {parquet_path} not found.")
        return

    try:
        print(f"Reading {parquet_path}...")
        df = pd.read_parquet(parquet_path)
        
        # Puerto Princesa fix
        # Find rows where province is 'CITY OF PUERTO PRINCESA (CAPITAL)' (or similar) and change to 'PALAWAN'
        # Check current values first
        print("Before fix:")
        print(df[df['province'].str.contains("PUERTO PRINCESA", case=False, na=False)]['province'].unique())
        
        mask_pp = df['province'].str.contains("PUERTO PRINCESA", case=False, na=False)
        count_pp = mask_pp.sum()
        
        if count_pp > 0:
            print(f"Merging {count_pp} Puerto Princesa rows into PALAWAN...")
            df.loc[mask_pp, 'province'] = 'PALAWAN'
        else:
            print("No Puerto Princesa rows found to fix.")
            
        # Optional: Check if we need to do others? User only mentioned Puerto Princesa for now.
        
        print("Saving updated parquet...")
        df.to_parquet(parquet_path)
        print("Success.")
        
    except Exception as e:
        print(f"Error fixing file: {e}")

if __name__ == "__main__":
    fix_hucs()

import pandas as pd

def inspect_data():
    try:
        df = pd.read_parquet("static/data/unified_locations.parquet")
        # Filter for anything related to Puerto Princesa or Palawan
        mask = df.astype(str).apply(lambda x: x.str.contains("Puerto Princesa|Palawan", case=False, na=False)).any(axis=1)
        subset = df[mask]
        
        print("Columns:", df.columns.tolist())
        print(f"Found {len(subset)} rows.")
        
        # specific check for the user's reported hierarchy
        print("\n--- Hierarchy Check ---")
        if 'region' in df.columns and 'province' in df.columns and 'district' in df.columns:
             # Check unique districts for Puerto Princesa Province/City
             pp = df[df['province'].str.contains("Puerto Princesa", case=False, na=False)]
             if not pp.empty:
                 print("Districts under 'CITY OF PUERTO PRINCESA':", pp['district'].unique())
             
             pal = df[df['province'].str.contains("Palawan", case=False, na=False)]
             if not pal.empty:
                 print("Districts under 'PALAWAN':", pal['district'].unique())

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inspect_data()

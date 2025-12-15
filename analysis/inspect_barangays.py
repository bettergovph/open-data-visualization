import pandas as pd

def inspect_barangays():
    df = pd.read_parquet("static/data/unified_locations.parquet")
    
    cities = ["Caloocan", "Marikina"]
    
    for city in cities:
        print(f"\n--- {city} Barangays (Parquet) ---")
        mask = df['province'].str.contains(city, case=False, na=False)
        print(df[mask]['barangay'].head(20).tolist())
        print(f"Total Unique: {df[mask]['barangay'].nunique()}")
        print(sorted(df[mask]['barangay'].unique().tolist())[:10])

if __name__ == "__main__":
    inspect_barangays()

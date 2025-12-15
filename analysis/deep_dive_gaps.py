import pandas as pd

def deep_dive():
    df = pd.read_parquet("static/data/unified_locations.parquet")
    
    # 1. Caloocan - Check all rows
    print("\n--- CALOOCAN RAW DUMP ---")
    cal = df[df['province'].str.contains("Caloocan", case=False, na=False)]
    print(cal[['province', 'district', 'municipality']].drop_duplicates().to_string())

    # 2. Quezon City
    print("\n--- QC RAW DUMP ---")
    qc = df[df['province'].str.contains("Quezon City", case=False, na=False)]
    print(qc[['province', 'district', 'municipality']].drop_duplicates().to_string())

    # 3. Davao City
    print("\n--- DAVAO CITY RAW DUMP ---")
    dav = df[df['province'].str.contains("City of Davao", case=False, na=False)]
    print(dav[['province', 'district', 'municipality']].drop_duplicates().to_string())

    # 4. Marikina
    print("\n--- MARIKINA RAW DUMP ---")
    mar = df[df['province'].str.contains("Marikina", case=False, na=False)]
    print(mar[['province', 'district', 'municipality']].drop_duplicates().to_string())

    # 5. Cebu City
    print("\n--- CEBU CITY RAW DUMP ---")
    ceb = df[df['province'].str.contains("City of Cebu", case=False, na=False)]
    print(ceb[['province', 'district', 'municipality']].drop_duplicates().to_string())

if __name__ == "__main__":
    deep_dive()

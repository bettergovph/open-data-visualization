import pandas as pd
import json

def debug_failures():
    df = pd.read_parquet("static/data/unified_locations.parquet")
    
    print("--- Marikina Debug ---")
    mask = df['province'].str.contains("Marikina", case=False, na=False)
    m_rows = df[mask]
    print(f"Total Rows: {len(m_rows)}")
    print("Unique Barangays in Parquet:", m_rows['barangay'].unique().tolist())
    
    # Check map keys
    with open("static/data/districts_generated.json", "r") as f:
        mData = json.load(f)
        try:
            gen_map = mData["City Of Marikina"]["barangays"]
            print("Map Keys Sample:", list(gen_map.keys())[:10])
        except:
            print("Error loading map keys")

    print("\n--- Davao del Sur Debug ---")
    mask = df['province'].str.contains("Davao del Sur", case=False, na=False)
    d_rows = df[mask]
    print(f"Total Rows: {len(d_rows)}")
    print("Unique Municipalities in Parquet:", d_rows['municipality'].unique().tolist())
    print("Unique Barangays in Parquet (Sample):", d_rows['barangay'].unique().tolist()[:10])
    
    # Check map keys
    with open("static/data/districts.json.wiki-backup", "r") as f:
        wData = json.load(f)
        try:
            w_map = wData["Davao del Sur"]["municipalities"]
            print("Map Keys Sample:", list(w_map.keys())[:10])
        except:
             print("Error loading map keys")

if __name__ == "__main__":
    debug_failures()

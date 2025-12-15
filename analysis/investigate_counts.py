import pandas as pd
import json

def investigate_counts():
    parquet_path = "static/data/unified_locations.parquet"
    df = pd.read_parquet(parquet_path)
    
    # QC Check
    qc_mask = df['province'].str.contains("Quezon City", case=False, na=False) | \
              df['municipality'].str.contains("Quezon City", case=False, na=False)
    
    qc_df = df[qc_mask]
    print(f"QC Total Rows: {len(qc_df)}")
    print("District Breakdown:")
    print(qc_df['district'].value_counts(dropna=False))
    
    # Check districts.json
    try:
        with open("static/data/districts.json", "r") as f:
            d_data = json.load(f)
            qc_districts = d_data.get('districts', {}).get('Quezon City', {})
            print(f"\nDistricts.json QC Entry Keys: {list(qc_districts.keys())}")
            # print sample
            if qc_districts:
                first_key = list(qc_districts.keys())[0]
                print(f"Sample {first_key}: {qc_districts[first_key]}")
    except Exception as e:
        print(f"Error reading districts.json: {e}")

if __name__ == "__main__":
    investigate_counts()

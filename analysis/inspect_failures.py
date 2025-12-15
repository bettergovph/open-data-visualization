import pandas as pd
import json

def inspect_failures():
    df = pd.read_parquet("static/data/unified_locations.parquet")
    
    # 1. Caloocan Unknowns -> List sample
    print("--- Caloocan Unknowns ---")
    cal_mask = (df['province'].str.contains("Caloocan", case=False, na=False)) & \
               (df['district'] == 'Unknown')
    print(df[cal_mask]['barangay'].unique().tolist()[:20])
    
    # 2. QC Failures
    # Simulating the failed match: Load json, try match, print failures
    print("\n--- QC Match Failures ---")
    with open("static/data/districts.json", "r") as f:
        d_data = json.load(f)
        qc_map = d_data['districts']['Quezon City']['barangays']
        
    qc_mask = df['province'].str.contains("Quezon City", case=False, na=False)
    qc_rows = df[qc_mask]
    
    failed_brgys = []
    
    for _, row in qc_rows.iterrows():
        brgy = row.get('barangay', '')
        found = False
        for dist, b_list in qc_map.items():
            if any(brgy.lower() == b.lower() for b in b_list) or \
               any(brgy.lower() in b.lower() for b in b_list):
               found = True
               break
        if not found:
            failed_brgys.append(brgy)
            
    print(list(set(failed_brgys)))

if __name__ == "__main__":
    inspect_failures()

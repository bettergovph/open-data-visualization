import pandas as pd
import json
import os

INPUT_FILE = '/home/joebert/open-data-visualization/data/parquet/parsed_dpwh_2026.parquet'
OUTPUT_DIR = '/home/joebert/open-data-visualization/static/data'
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'dpwh_2026.json')

def process_data():
    try:
        print(f"Reading {INPUT_FILE}...")
        df = pd.read_parquet(INPUT_FILE)
        
        # Replace NaN with safe values for JSON
        df = df.fillna("")
        
        print("Converting to dict...")
        data = df.to_dict(orient='records')
        
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        print(f"Writing to {OUTPUT_FILE}...")
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(data, f)
            
        print("Done!")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    process_data()

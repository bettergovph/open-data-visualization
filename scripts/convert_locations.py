import pandas as pd
import os

def convert_parquet_to_json():
    parquet_path = "static/data/unified_locations.parquet"
    json_path = "static/data/unified_locations.json"
    
    if not os.path.exists(parquet_path):
        print(f"Error: {parquet_path} not found.")
        return

    try:
        print(f"Reading {parquet_path}...")
        df = pd.read_parquet(parquet_path)
        
        print(f"Converting to JSON...")
        # orient='records' is usually best for a list of objects
        df.to_json(json_path, orient='records', indent=2) 
        
        print(f"Success! Saved to {json_path}")
        print(f"File size: {os.path.getsize(json_path) / 1024 / 1024:.2f} MB")
        
    except Exception as e:
        print(f"Error converting file: {e}")

if __name__ == "__main__":
    convert_parquet_to_json()

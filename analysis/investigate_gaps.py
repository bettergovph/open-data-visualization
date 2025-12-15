import pandas as pd
import os

def investigate_gaps():
    parquet_path = "static/data/unified_locations.parquet"
    df = pd.read_parquet(parquet_path)
    
    queries = {
        "Butuan": "Agusan del Norte",
        "Caloocan": "City of Caloocan",
        "Cebu": "City of Cebu", # Look for "Cebu" vs "City of Cebu"
        "Davao": "City of Davao", # Look for "Davao" generally
        "Lucena": "City of Lucena",
        "Marikina": "City of Marikina",
        "Digos": "Davao del Sur", # Digos is capital
        "Quezon City": "Quezon City" # Look for variations
    }
    
    print("--- Searching for missing counterparts ---")
    
    for term, context in queries.items():
        print(f"\n🔎 Query: {term} (Context: {context})")
        # Find unique province names containing the term
        matches = df[df['province'].str.contains(term, case=False, na=False)]['province'].unique()
        print(f"   Found Provinces: {matches}")
        
        # Breakdown of districts for these matches
        for m in matches:
            dists = df[df['province'] == m]['district'].unique()
            print(f"   -> {m}: {sorted(list(dists))}")

if __name__ == "__main__":
    investigate_gaps()

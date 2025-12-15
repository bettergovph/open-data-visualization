import pandas as pd
import re
import os

def hunt_missing_districts():
    parquet_path = "static/data/unified_locations.parquet"
    if not os.path.exists(parquet_path):
        print(f"Error: {parquet_path} not found.")
        return

    try:
        df = pd.read_parquet(parquet_path)
        
        # 1. Normalize districts to extract numbers
        def extract_district_number(d_str):
            if not isinstance(d_str, str): return None
            # Match "1st", "2nd", "3rd", "4th" ... or just digits
            match = re.search(r'(\d+)(?:st|nd|rd|th)?\s+District', d_str, re.IGNORECASE)
            if match:
                return int(match.group(1))
            
            # Simple number match if "District" word is missing but implied (rare)
            # match = re.search(r'^(\d+)$', d_str)
            # if match: return int(match.group(1))
            
            return None

        # Filter out "Lone District", "Unknown", etc.
        valid_districts = df[
            df['district'].str.contains(r'\d', na=False) & 
            ~df['district'].str.contains("Lone", case=False, na=False)
        ].copy()

        valid_districts['dist_num'] = valid_districts['district'].apply(extract_district_number)
        
        # Group by Province
        provinces = valid_districts.groupby('province')
        
        print(f"Scanning {len(provinces)} provinces for gaps...\n")
        
        found_issues = 0
        
        for prov, group in provinces:
            # unique district numbers
            nums = sorted([n for n in group['dist_num'].unique() if n is not None])
            if not nums: continue
            
            max_dist = max(nums)
            expected_set = set(range(1, max_dist + 1))
            actual_set = set(nums)
            
            missing = sorted(list(expected_set - actual_set))
            
            if missing:
                found_issues += 1
                print(f"🚩 {prov}")
                print(f"   Found: {nums}")
                print(f"   Missing: {missing}")
                
                # Check if these missing "districts" exist as separate HUCs/Provinces in the original DF?
                # e.g., if finding "Cebu" has 1,2,3... but missing X, exists "Cebu City" with X?
                # Attempt to find potential matches in top-level provinces
                for m in missing:
                    potential_match = df[df['province'].str.contains(f"District", case=False, na=False)] 
                    # Checking if any province name matches pattern relative to the missing one is hard without specific logic
                    pass
                print("-" * 40)
        
        if found_issues == 0:
            print("✅ No gap patterns found in district numbering!")
        else:
            print(f"\nFound {found_issues} provinces with district numbering gaps.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    hunt_missing_districts()

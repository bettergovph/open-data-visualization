import json
import re

def find_multiterm():
    with open("static/data/districts.json", "r") as f:
        data = json.load(f)
        
    districts = data.get("districts", {})
    count = 0
    
    for prov, info in districts.items():
        reps = info.get("representatives", {})
        for dist, rep_str in reps.items():
            # Check if semicolon exists AND ends with present
            if ";" in rep_str and "present)" in rep_str:
                print(f"[{prov} - {dist}]")
                print(f"  Value: {rep_str}")
                
                # Check if my previous regex would match
                match = re.search(r'^(.*?) \((\d{4})-present\)', rep_str)
                if match:
                    print(f"  Regex MATCHED: {match.groups()}")
                else:
                    print(f"  Regex FAILED")
                
                count += 1
                print("-" * 20)
                if count >= 30: return

if __name__ == "__main__":
    find_multiterm()

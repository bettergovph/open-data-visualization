import json
import os

FILES = [
    "static/data/districts.json.wiki-backup",
    "static/data/districts_generated.json",
    "static/data/philippines-provinces-lite.json"
]

KEYWORDS = ["Marikina", "Davao del Sur"]

def search():
    for fpath in FILES:
        if not os.path.exists(fpath):
            print(f"Skipping {fpath} (not found)")
            continue
            
        print(f"--- Scanning {fpath} ---")
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                # Read line by line if huge, but these seem manageable (< 50MB except maybe provinces)
                # For provinces-lite (13MB) it's fine.
                # But to get context, let's load text 
                content = f.read()
                
            lines = content.split('\n')
            for i, line in enumerate(lines):
                for k in KEYWORDS:
                    if k in line:
                        print(f"Found '{k}' at line {i}: {line.strip()[:200]}")
                        # Print context if it looks like a key
                        if "{" in line or "[" in line or ":" in line:
                             for j in range(1, 25):
                                 if i + j < len(lines):
                                     print(f"    {lines[i+j].strip()[:200]}")
                             print("    ...")
                             break # One context per match is likely enough or too noisy
        except Exception as e:
            print(f"Error reading {fpath}: {e}")
        print("\n")

if __name__ == "__main__":
    search()

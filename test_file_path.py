#!/usr/bin/env python3
import json
from pathlib import Path

# Test the file path resolution
data_file = Path("static/data/flood_dime_contractor_correlation_all_years.json")
print(f"File path: {data_file}")
print(f"Absolute path: {data_file.absolute()}")
print(f"Exists: {data_file.exists()}")

if data_file.exists():
    with open(data_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"Data keys: {list(data.keys())}")
    print(f"Status: {data.get('status')}")
    print(f"Contractors count: {len(data.get('contractors', []))}")
else:
    print("File does not exist!")

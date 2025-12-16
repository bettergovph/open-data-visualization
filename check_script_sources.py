
import duckdb
import os
from pathlib import Path

BASE_DIR = Path(".").resolve()
DATA_DIR = BASE_DIR / "data" / "parquet"

SOURCES = [
    {"name": "DIME", "file": "dime_projects.parquet"},
    {"name": "PhilGEPS", "file": "philgeps_contracts.parquet"},
    {"name": "Microsite", "file": "infrawatch_projects.parquet", "alt_file": "microsite_projects.parquet"},
    {"name": "Transparency", "file": "transparency_projects.parquet"},
    {"name": "SSP", "file": "flood_projects.parquet"}
]

print("--- Checking Source Files from Script ---")
for source in SOURCES:
    file_path = DATA_DIR / source["file"]
    
    # Check alternate
    used_alt = False
    if not file_path.exists() and "alt_file" in source:
        alt_path = DATA_DIR / source["alt_file"]
        if alt_path.exists():
            file_path = alt_path
            used_alt = True
    
    if file_path.exists():
        try:
            count = duckdb.query(f"SELECT COUNT(*) FROM '{file_path}'").fetchone()[0]
            print(f"{source['name']}: Found {'(ALT)' if used_alt else ''} at {file_path.name} - {count} rows")
        except Exception as e:
             print(f"{source['name']}: Error reading {file_path.name} - {e}")
    else:
        print(f"{source['name']}: MISSING (Tried {source['file']} {('and ' + source['alt_file']) if 'alt_file' in source else ''})")

print("\n--- Checking Potential Better Candidates ---")
candidates = [
    "infrawatch_projects_enriched.parquet",
    "flood_control_projects.parquet"
]
for c in candidates:
    f = DATA_DIR / c
    if f.exists():
         count = duckdb.query(f"SELECT COUNT(*) FROM '{f}'").fetchone()[0]
         print(f"Candidate: {c} - {count} rows")
    else:
         print(f"Candidate: {c} - Not Found")

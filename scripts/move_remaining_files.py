#!/usr/bin/env python3
"""Script to move remaining non-API Python files and markdown files"""
import os
import shutil
from pathlib import Path

# API-related files that should stay in root
API_FILES = {
    'visualization.py',
    'budget_client.py',
    'budget_postgres_client.py',
    'nep_postgres_client.py',
    'relationship_sources_client.py',
    'flood_db_client.py',
    'infrawatch_postgres_client.py',
    'dime_client.py',
    'flood_client.py',  # Need to check if this is used
}

base_dir = Path(__file__).parent
scripts_dir = base_dir / 'scripts'
analysis_dir = base_dir / 'analysis'

# Find all Python files in root
py_files = [f for f in base_dir.iterdir() if f.is_file() and f.suffix == '.py' and f.name not in API_FILES]

# Find all markdown files in root (except README.md)
md_files = [f for f in base_dir.iterdir() if f.is_file() and f.suffix == '.md' and f.name != 'README.md']

print("Python files to move:")
for f in py_files:
    print(f"  - {f.name}")

print("\nMarkdown files to move:")
for f in md_files:
    print(f"  - {f.name}")

# Move Python files to scripts/
moved_py = []
for f in py_files:
    try:
        dst = scripts_dir / f.name
        shutil.move(str(f), str(dst))
        moved_py.append(f.name)
        print(f"✓ Moved {f.name} to scripts/")
    except Exception as e:
        print(f"✗ Error moving {f.name}: {e}")

# Move markdown files to analysis/
moved_md = []
for f in md_files:
    try:
        dst = analysis_dir / f.name
        shutil.move(str(f), str(dst))
        moved_md.append(f.name)
        print(f"✓ Moved {f.name} to analysis/")
    except Exception as e:
        print(f"✗ Error moving {f.name}: {e}")

print(f"\nSummary:")
print(f"  Moved {len(moved_py)} Python files to scripts/")
print(f"  Moved {len(moved_md)} markdown files to analysis/")

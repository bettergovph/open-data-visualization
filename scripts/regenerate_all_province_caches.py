#!/usr/bin/env python3
"""Regenerate all province caches with Infrawatch/Microsite data."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

async def main():
    """Regenerate all province caches."""
    static_data = Path(__file__).parent.parent / 'static' / 'data'
    
    # Find all province cache directories
    province_dirs = sorted(static_data.glob('province-projects-*'))
    
    # Extract province names from directory names
    provinces = []
    for dir_path in province_dirs:
        if dir_path.is_dir():
            # Convert "province-projects-davao-del-norte" -> "Davao del Norte"
            slug = dir_path.name.replace('province-projects-', '')
            province_name = ' '.join(word.capitalize() for word in slug.split('-'))
            provinces.append(province_name)
    
    total = len(provinces)
    print(f"🚀 Regenerating {total} province caches with Infrawatch/Microsite data...")
    print("")
    
    for current, province in enumerate(provinces, 1):
        print(f"[{current}/{total}] Processing: {province}")
        
        # Run the cache generator
        result = subprocess.run(
            [sys.executable, 'scripts/generate_province_projects_cache.py', province],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True
        )
        
        # Filter output to show only relevant lines
        for line in result.stdout.split('\n'):
            if any(keyword in line for keyword in [
                'Found', 'Total projects', 'SSP:', 'DIME:', 
                'PhilGEPS:', 'Microsite:', 'Total cost:', 'Cache generated'
            ]):
                print(f"   {line}")
        
        if result.returncode != 0:
            print(f"   ❌ Error processing {province}")
            if result.stderr:
                print(f"   {result.stderr}")
        
        print("")
    
    print("✅ All province caches regenerated!")

if __name__ == '__main__':
    asyncio.run(main())


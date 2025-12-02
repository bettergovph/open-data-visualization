#!/usr/bin/env python3
"""
Regenerate all roads cache files (historical + 2026)
This script runs both:
1. regenerate_historical_roads_with_categorization.py (2020-2025)
2. regenerate_2026_roads_cache.py (2026)

These scripts work together to generate the complete dataset.
"""

import sys
import subprocess
from pathlib import Path

def main():
    """Run both regeneration scripts in sequence"""
    script_dir = Path(__file__).parent
    
    print("=" * 80)
    print(" REGENERATING ALL ROADS CACHE FILES")
    print("=" * 80)
    print()
    
    # Step 1: Regenerate historical roads (2020-2025)
    print("📅 Step 1: Regenerating historical roads cache (2020-2025)...")
    print("-" * 80)
    historical_script = script_dir / "regenerate_historical_roads_with_categorization.py"
    
    if not historical_script.exists():
        print(f"❌ Error: {historical_script} not found")
        sys.exit(1)
    
    result1 = subprocess.run(
        [sys.executable, str(historical_script)],
        cwd=script_dir.parent,
        capture_output=False
    )
    
    if result1.returncode != 0:
        print(f"\n❌ Error: Historical roads regeneration failed with exit code {result1.returncode}")
        sys.exit(1)
    
    print()
    print("=" * 80)
    print()
    
    # Step 2: Regenerate 2026 roads cache
    print("📅 Step 2: Regenerating 2026 roads cache...")
    print("-" * 80)
    cache_2026_script = script_dir / "regenerate_2026_roads_cache.py"
    
    if not cache_2026_script.exists():
        print(f"❌ Error: {cache_2026_script} not found")
        sys.exit(1)
    
    result2 = subprocess.run(
        [sys.executable, str(cache_2026_script)],
        cwd=script_dir.parent,
        capture_output=False
    )
    
    if result2.returncode != 0:
        print(f"\n❌ Error: 2026 roads cache regeneration failed with exit code {result2.returncode}")
        sys.exit(1)
    
    print()
    print("=" * 80)
    print(" ✅ ALL ROADS CACHE REGENERATION COMPLETED SUCCESSFULLY")
    print("=" * 80)
    print()
    print("📊 Generated files:")
    print("   - static/data/historical_roads_2020_2025.json")
    print("   - static/data/api_cache/roads_cost_analysis_cache.json")
    print()

if __name__ == "__main__":
    main()


#!/usr/bin/env python3
"""
Regenerate all dynasty-related JSON cache files after database cleanup
"""

import asyncio
import subprocess
import sys
from pathlib import Path


def run_script(script_path, description):
    """Run a Python script and return success status"""
    print(f"\n{'='*80}")
    print(f"🔄 {description}")
    print(f"{'='*80}")
    
    script_full_path = Path(__file__).parent.parent / script_path
    if not script_full_path.exists():
        print(f"❌ Script not found: {script_path}")
        return False
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_full_path)],
            cwd=str(script_full_path.parent.parent),
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )
        
        if result.returncode == 0:
            print(f"✅ {description} - SUCCESS")
            if result.stdout:
                # Print last 20 lines of output
                lines = result.stdout.strip().split('\n')
                for line in lines[-20:]:
                    print(f"   {line}")
            return True
        else:
            print(f"❌ {description} - FAILED")
            if result.stderr:
                print("Error output:")
                for line in result.stderr.strip().split('\n')[-10:]:
                    print(f"   {line}")
            return False
    except subprocess.TimeoutExpired:
        print(f"⏱️ {description} - TIMEOUT (>10 minutes)")
        return False
    except Exception as e:
        print(f"❌ {description} - EXCEPTION: {e}")
        return False


async def main():
    print("=" * 80)
    print("REGENERATING DYNASTY JSON CACHE FILES")
    print("=" * 80)
    print("\nThis will regenerate all dynasty-related JSON cache files")
    print("based on the cleaned database (non-person entities removed).\n")
    
    scripts_to_run = [
        # 1. Dynasty surnames cache (used in charts/visualizations)
        ('family_analysis/family_scraper/generate_dynasty_surnames.py', 
         'Dynasty Surnames Cache'),
        
        # 2. Dynasty animation cache (all years + master index)
        ('cache_dynasty_animation.py', 
         'Dynasty Animation Cache (All Years)'),
        
        # 3. Relationship constellations cache (used in network view)
        ('scripts/database/generate_relationship_constellations_cache.py', 
         'Relationship Constellations Cache'),
        
        # 4. Dynasty flags cache (used in map visualizations)
        ('scripts/generate_dynasty_flags.py', 
         'Dynasty Flags Cache'),
        
        # 5. Poverty correlation cache (depends on dynasty surnames cache)
        ('scripts/analysis/compute_cri_analysis.py', 
         'Poverty Correlation Cache (CRI Analysis)'),
    ]
    
    results = {}
    
    for script_path, description in scripts_to_run:
        success = run_script(script_path, description)
        results[description] = success
    
    # Summary
    print("\n" + "=" * 80)
    print("REGENERATION SUMMARY")
    print("=" * 80)
    
    success_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    
    for description, success in results.items():
        status = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"  {status}: {description}")
    
    print(f"\nTotal: {success_count}/{total_count} scripts succeeded")
    
    if success_count == total_count:
        print("\n✅ All dynasty JSON cache files regenerated successfully!")
        print("\nThe following cache files have been updated:")
        print("  - static/data/dynasty_surnames_cache.json")
        print("  - static/data/dynasty_animation_cache/*.json")
        print("  - static/data/relationship_chains_cache.json")
        print("  - static/data/dynasty_flags_cache.json")
        print("  - static/data/poverty_correlation_cache.json")
    else:
        print("\n⚠️ Some scripts failed. Please check the error messages above.")
    
    return success_count == total_count


if __name__ == '__main__':
    success = asyncio.run(main())
    sys.exit(0 if success else 1)


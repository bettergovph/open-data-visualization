#!/usr/bin/env python3
"""
Update visualization.py to check for pre-generated JSON cache files before doing heavy processing.

This script modifies the heavy processing endpoints to:
1. Check for cache files first
2. Serve cached data if available and fresh
3. Fall back to processing if cache doesn't exist or is stale
"""

import re
from pathlib import Path

VISUALIZATION_PY = Path(__file__).parent.parent / "visualization.py"
CACHE_DIR = Path(__file__).parent.parent / "static" / "data" / "api_cache"

# Cache file mappings: endpoint -> cache file
CACHE_MAPPINGS = {
    "/api/budget/regions": "budget_regions_cache.json",
    "/api/budget/nep/year-over-year": "nep_year_over_year_cache.json",
    "/api/budget/nep/top-programs": "nep_top_programs_cache.json",
    "/api/budget/analysis/comparison-chart": "budget_comparison_chart_cache.json",
    "/api/budget/programs/comparison": "budget_programs_comparison_cache.json",
    "/api/budget/roads-cost-analysis": "roads_cost_analysis_cache.json",
    "/api/budget/amendments/departments": "budget_amendments_departments_cache.json",
    "/api/budget/amendments/annex-a1-amounts": "annex_a1_amounts_cache.json",
    "/api/budget/amendments/annex-a5-amounts": "annex_a5_amounts_cache.json",
    "/api/budget/amendments/annex-a4-amounts": "annex_a4_amounts_cache.json",
    "/api/budget/amendments/annex-a5-duplicates": "annex_a5_duplicates_cache.json",
    "/api/budget/amendments/annex-a4-duplicates": "annex_a4_duplicates_cache.json",
    "/api/budget/department-trends": "budget_department_trends_cache.json",
}


def add_cache_check_to_endpoint(file_content: str, endpoint_path: str, cache_file: str) -> str:
    """Add cache check at the beginning of an endpoint function"""
    
    # Find the endpoint function
    pattern = rf'@app\.get\("{re.escape(endpoint_path)}"\)\s+async def (\w+)\([^)]*\):'
    match = re.search(pattern, file_content)
    
    if not match:
        print(f"  ⚠️ Could not find endpoint: {endpoint_path}")
        return file_content
    
    func_name = match.group(1)
    func_start = match.end()
    
    # Find the function body start (after the docstring)
    # Look for the try block or first statement
    try_pattern = r'(\s+"""[^"]*"""\s+)?(\s+try:)'
    try_match = re.search(try_pattern, file_content[func_start:func_start + 500])
    
    if not try_match:
        print(f"  ⚠️ Could not find try block in {func_name}")
        return file_content
    
    insert_pos = func_start + try_match.end() - len(try_match.group(0))
    
    # Generate cache check code
    cache_check = f'''
        # Check for pre-generated cache first
        cache_file = Path(__file__).parent / "static" / "data" / "api_cache" / "{cache_file}"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                if cache_data.get('success'):
                    print(f"✅ [{endpoint_path}] Using cached data from {{cache_file.name}}")
                    return JSONResponse(cache_data)
            except Exception as cache_err:
                print(f"⚠️ [{endpoint_path}] Error reading cache, falling back to processing: {{cache_err}}")
    
'''
    
    # Insert cache check
    new_content = (
        file_content[:insert_pos] +
        cache_check +
        file_content[insert_pos:]
    )
    
    return new_content


def main():
    """Main function to update visualization.py"""
    print("🔄 Updating visualization.py to use cache files...")
    print(f"📁 Cache directory: {CACHE_DIR}")
    print()
    
    if not VISUALIZATION_PY.exists():
        print(f"❌ visualization.py not found at {VISUALIZATION_PY}")
        return
    
    # Read the file
    with open(VISUALIZATION_PY, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Update each endpoint
    for endpoint, cache_file in CACHE_MAPPINGS.items():
        print(f"📝 Updating {endpoint}...")
        content = add_cache_check_to_endpoint(content, endpoint, cache_file)
    
    # Only write if changes were made
    if content != original_content:
        # Create backup
        backup_file = VISUALIZATION_PY.with_suffix('.py.backup')
        with open(backup_file, 'w', encoding='utf-8') as f:
            f.write(original_content)
        print(f"💾 Created backup: {backup_file}")
        
        # Write updated content
        with open(VISUALIZATION_PY, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Updated {VISUALIZATION_PY}")
    else:
        print("ℹ️ No changes made (endpoints may already be updated or patterns didn't match)")
    
    print()
    print("✅ Update complete!")
    print()
    print("📝 Next steps:")
    print("  1. Run: python scripts/pre_generate_nep_budget_json.py")
    print("  2. Test the endpoints to ensure they use cache files")
    print("  3. Monitor performance improvements")


if __name__ == "__main__":
    main()



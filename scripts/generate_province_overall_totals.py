#!/usr/bin/env python3
"""
Script to generate overall totals cache for all provinces
This aggregates total projects and total cost across all provinces
"""
import json
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def generate_overall_totals():
    """Generate overall totals from all province cache directories"""
    cache_base_dir = Path(__file__).parent.parent / 'static' / 'data'
    output_file = cache_base_dir / 'province-overall-totals.json'
    
    total_projects = 0
    total_cost = 0
    province_count = 0
    
    print("🔄 Calculating overall totals from province caches...")
    
    # Iterate through all province cache directories
    for province_dir in cache_base_dir.glob('province-projects-*/summary.json'):
        try:
            with open(province_dir, 'r', encoding='utf-8') as f:
                summary_data = json.load(f)
            
            summary = summary_data.get('summary', {})
            province_projects = summary.get('total', 0)
            province_cost = summary_data.get('total_cost', 0)
            
            if province_projects > 0:
                total_projects += province_projects
                total_cost += province_cost
                province_count += 1
                print(f"   ✅ {province_dir.parent.name}: {province_projects} projects, {province_cost:,.2f}")
        except Exception as e:
            print(f"   ⚠️  Error reading {province_dir}: {e}")
            continue
    
    # Create cache data
    cache_data = {
        "success": True,
        "total_projects": total_projects,
        "total_cost": total_cost,
        "province_count": province_count,
        "generated_at": datetime.now().isoformat(),
        "cache_version": "1.0",
        "description": "Overall totals across all provinces (aggregated from province cache summary.json files)"
    }
    
    # Save to file
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Overall totals cache generated:")
    print(f"   📊 Total Projects: {total_projects:,}")
    print(f"   💰 Total Cost: ₱{total_cost:,.2f}")
    print(f"   🗺️  Provinces: {province_count}")
    print(f"   💾 Saved to: {output_file}")
    
    return cache_data

if __name__ == '__main__':
    generate_overall_totals()


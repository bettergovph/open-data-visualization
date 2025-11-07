#!/usr/bin/env python3
"""
Combine all individual congressman caches into dynasty-projects-cache.json
"""

import json
import glob
from pathlib import Path
from datetime import datetime

def parse_amount(amount):
    """Parse amount consistently"""
    if isinstance(amount, (int, float)):
        return float(amount) if amount else 0
    elif isinstance(amount, str):
        amount_str = amount.replace('₱', '').replace(',', '').strip()
        try:
            return float(amount_str) if amount_str else 0
        except (ValueError, AttributeError):
            return 0
    else:
        return 0

def main():
    print("🚀 Combining all congressman caches into dynasty-projects-cache.json...")
    
    # Find all congressman cache files
    data_dir = Path(__file__).parent.parent / 'static' / 'data'
    cache_pattern = str(data_dir / 'congressman-projects-*' / 'all-projects-cache.json')
    cache_files = glob.glob(cache_pattern)
    
    print(f"📁 Found {len(cache_files)} congressman caches")
    
    all_projects = []
    total_summary = {
        "total": 0,
        "dime": 0,
        "philgeps": 0,
        "ssp": 0,
        "district_projects": 0,
        "contractor_projects": 0
    }
    
    # Load all projects from individual caches
    for cache_file_path in cache_files:
        try:
            with open(cache_file_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            if cache_data.get('success', False):
                projects = cache_data.get('projects', [])
                all_projects.extend(projects)
                
                # Aggregate summary
                summary = cache_data.get('summary', {})
                total_summary['total'] += summary.get('total', 0)
                total_summary['dime'] += summary.get('dime', 0)
                total_summary['philgeps'] += summary.get('philgeps', 0)
                total_summary['ssp'] += summary.get('ssp', 0)
                total_summary['district_projects'] += summary.get('district_projects', 0)
                total_summary['contractor_projects'] += summary.get('contractor_projects', 0)
                
                congressman = cache_data.get('congressman', 'Unknown')
                print(f"   ✅ {congressman}: {len(projects)} projects")
        except Exception as e:
            print(f"   ⚠️  Error loading {cache_file_path}: {e}")
            continue
    
    print(f"\n📊 Total projects loaded: {len(all_projects)}")
    
    # Calculate congressman statistics for charts
    congressman_stats = {}
    for proj in all_projects:
        congressman = proj.get('congressman', 'Unknown')
        if not congressman_stats.get(congressman):
            congressman_stats[congressman] = {
                "name": congressman,
                "count": 0,
                "total_cost": 0
            }
        
        congressman_stats[congressman]["count"] += 1
        congressman_stats[congressman]["total_cost"] += parse_amount(proj.get('amount', 0))
    
    # Convert to sorted array for chart data
    chart_data = sorted(
        list(congressman_stats.values()),
        key=lambda x: x["count"],
        reverse=True
    )
    
    # Calculate dashboard statistics
    total_cost_all = sum(stat["total_cost"] for stat in chart_data)
    district_count = total_summary['district_projects']
    contractor_count = total_summary['contractor_projects']
    district_cost = sum(
        parse_amount(proj.get('amount', 0))
        for proj in all_projects if proj.get('match_type') == 'district'
    )
    contractor_cost = sum(
        parse_amount(proj.get('amount', 0))
        for proj in all_projects if proj.get('match_type') == 'contractor'
    )
    
    dashboard_stats = {
        "total_cost_all": total_cost_all,
        "total_projects": len(all_projects),
        "district_count": district_count,
        "district_cost": district_cost,
        "contractor_count": contractor_count,
        "contractor_cost": contractor_cost
    }
    
    # Save combined cache
    cache_data = {
        "success": True,
        "projects": all_projects,
        "summary": total_summary,
        "chart_data": chart_data,
        "dashboard_stats": dashboard_stats,
        "generated_at": datetime.utcnow().isoformat(),
        "cache_version": "2.0",
        "source": "combined_individual_caches",
        "term_validated": True
    }
    
    output_file = data_dir / 'dynasty-projects-cache.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Combined cache saved to {output_file}")
    print(f"   Total projects: {len(all_projects)}")
    print(f"   Total cost: ₱{total_cost_all:,.2f}")
    print(f"   District matches: {district_count} (₱{district_cost:,.2f})")
    print(f"   Contractor matches: {contractor_count} (₱{contractor_cost:,.2f})")
    print(f"   Congressmen: {len(congressman_stats)}")

if __name__ == '__main__':
    main()


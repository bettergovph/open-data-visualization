#!/usr/bin/env python3
"""
Generate top-200-congressmen.json cache for the congressman visual tab.
Pre-calculates chart data and dashboard statistics so the frontend can page
through a horizontal Top 200 view without recomputing aggregates on load.
"""

import glob
import json
from datetime import datetime
from pathlib import Path


def parse_amount(value):
    """Normalize numeric strings into floats."""
    if isinstance(value, (int, float)):
        return float(value) if value else 0.0
    if isinstance(value, str):
        cleaned = value.replace('₱', '').replace(',', '').strip()
        try:
            return float(cleaned) if cleaned else 0.0
        except (ValueError, AttributeError):
            return 0.0
    return 0.0


def main():
    print("🚀 Generating top-200-congressmen.json cache...")

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
        "contractor_projects": 0,
    }

    for cache_file_path in cache_files:
        try:
            with open(cache_file_path, 'r', encoding='utf-8') as handle:
                cache_data = json.load(handle)

            if cache_data.get('success'):
                projects = cache_data.get('projects', [])
                all_projects.extend(projects)

                summary = cache_data.get('summary', {})
                total_summary['total'] += summary.get('total', 0)
                total_summary['dime'] += summary.get('dime', 0)
                total_summary['philgeps'] += summary.get('philgeps', 0)
                total_summary['ssp'] += summary.get('ssp', 0)
                total_summary['district_projects'] += summary.get('district_projects', 0)
                total_summary['contractor_projects'] += summary.get('contractor_projects', 0)
        except Exception as exc:  # pylint: disable=broad-except
            print(f"   ⚠️  Error loading {cache_file_path}: {exc}")

    print(f"\n📊 Total projects loaded: {len(all_projects)}")

    congressman_stats = {}
    for project in all_projects:
        name = project.get('congressman', 'Unknown')
        stats = congressman_stats.setdefault(name, {"name": name, "count": 0, "total_cost": 0.0})
        stats["count"] += 1
        stats["total_cost"] += parse_amount(project.get('amount', 0))

    stats_list = list(congressman_stats.values())
    stats_list.sort(key=lambda item: item['count'], reverse=True)
    top_by_count = stats_list[:200]

    stats_by_cost = sorted(congressman_stats.values(), key=lambda item: item['total_cost'], reverse=True)
    top_by_cost = stats_by_cost[:200]

    combined_names = set()
    combined_chart_data = []
    for entry in top_by_count + top_by_cost:
        if entry['name'] not in combined_names:
            combined_names.add(entry['name'])
            combined_chart_data.append(entry)

    combined_chart_data.sort(key=lambda item: item['count'], reverse=True)

    print("\n📈 Top 20 Congressmen by Project Count (preview):")
    for idx, entry in enumerate(top_by_count[:20], 1):
        print(f"   {idx}. {entry['name']}: {entry['count']} projects, ₱{entry['total_cost']:,.2f}")

    print("\n💰 Top 20 Congressmen by Total Cost (preview):")
    for idx, entry in enumerate(top_by_cost[:20], 1):
        print(f"   {idx}. {entry['name']}: ₱{entry['total_cost']:,.2f} ({entry['count']} projects)")

    district_projects = total_summary['district_projects']
    contractor_projects = total_summary['contractor_projects']

    district_cost = sum(
        parse_amount(project.get('amount', 0))
        for project in all_projects
        if project.get('match_type') == 'district'
    )
    contractor_cost = sum(
        parse_amount(project.get('amount', 0))
        for project in all_projects
        if project.get('match_type') == 'contractor'
    )

    dashboard_stats = {
        "total_cost_all": sum(entry['total_cost'] for entry in stats_list),
        "total_projects": len(all_projects),
        "district_count": district_projects,
        "district_cost": district_cost,
        "contractor_count": contractor_projects,
        "contractor_cost": contractor_cost,
    }

    output = {
        "success": True,
        "chart_data": combined_chart_data,
        "chart_data_by_count": top_by_count,
        "chart_data_by_cost": top_by_cost,
        "dashboard_stats": dashboard_stats,
        "summary": total_summary,
        "total_congressmen": len(congressman_stats),
        "generated_at": datetime.utcnow().isoformat(),
        "cache_version": "2.0",
    }

    output_path = data_dir / 'top-200-congressmen.json'
    with open(output_path, 'w', encoding='utf-8') as handle:
        json.dump(output, handle, indent=2, ensure_ascii=False)

    print(f"\n✅ Saved to {output_path}")
    print(f"   Total projects: {len(all_projects)}")
    print(f"   District matches: {district_projects} (₱{district_cost:,.2f})")
    print(f"   Contractor matches: {contractor_projects} (₱{contractor_cost:,.2f})")
    print(f"   Total congressmen covered: {len(congressman_stats)}")


if __name__ == '__main__':
    main()

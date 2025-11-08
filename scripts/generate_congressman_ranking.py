#!/usr/bin/env python3
"""
Generate congressman-ranking.json containing complete rankings for all cached
congressmen. The output powers the visual tab so we can render a Top 10 view by
default, page through the full list, and focus on any congressman without
additional aggregation on the frontend.
"""

from __future__ import annotations

import glob
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Tuple


def parse_amount(value):
    """Normalize numeric strings into floats."""
    if isinstance(value, (int, float)):
        return float(value) if value else 0.0
    if isinstance(value, str):
        cleaned = value.replace("₱", "").replace(",", "").strip()
        try:
            return float(cleaned) if cleaned else 0.0
        except (ValueError, AttributeError):
            return 0.0
    return 0.0


def normalize_slug(name: str) -> str:
    """Mirror the slug logic used by the FastAPI service."""
    if not name:
        return ""
    normalized = unicodedata.normalize("NFD", name)
    stripped = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    slug = stripped.lower().replace(" ", "-")
    slug = re.sub(r"[^\w-]", "", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-")


def load_cache_paths() -> Tuple[Path, Iterable[str]]:
    data_root = Path(__file__).parent.parent / "static" / "data"
    pattern = str(data_root / "congressman-projects-*" / "all-projects-cache.json")
    cache_files = glob.glob(pattern)
    return data_root, cache_files


def aggregate_congressman_stats(cache_path: str) -> Dict[str, Dict[str, float]]:
    with open(cache_path, "r", encoding="utf-8") as handle:
        cache = json.load(handle)

    if not cache.get("success", False):
        return {}

    name = cache.get("congressman") or "Unknown"
    summary = cache.get("summary") or {}
    dashboard = cache.get("dashboard_stats") or {}

    count = summary.get("total")
    cost = dashboard.get("total_cost_all")

    # Fallbacks for caches that predate dashboard summaries
    projects = cache.get("projects") or []
    if count is None:
        count = len(projects)
    if cost is None:
        cost = sum(parse_amount(p.get("amount", 0)) for p in projects)

    district_count = dashboard.get("district_count")
    contractor_count = dashboard.get("contractor_count")
    district_cost = dashboard.get("district_cost")
    contractor_cost = dashboard.get("contractor_cost")

    if district_count is None:
        district_count = len([p for p in projects if p.get("match_type") == "district"])
    if contractor_count is None:
        contractor_count = len([p for p in projects if p.get("match_type") == "contractor"])
    if district_cost is None:
        district_cost = sum(
            parse_amount(p.get("amount", 0)) for p in projects if p.get("match_type") == "district"
        )
    if contractor_cost is None:
        contractor_cost = sum(
            parse_amount(p.get("amount", 0)) for p in projects if p.get("match_type") == "contractor"
        )

    return {
        name: {
            "name": name,
            "slug": normalize_slug(name),
            "count": int(count or 0),
            "total_cost": float(cost or 0.0),
            "district_count": int(district_count or 0),
            "district_cost": float(district_cost or 0.0),
            "contractor_count": int(contractor_count or 0),
            "contractor_cost": float(contractor_cost or 0.0),
            "sources_breakdown": {
                "total": int(summary.get("total", count or 0)),
                "ssp": int(summary.get("ssp", 0)),
                "dime": int(summary.get("dime", 0)),
                "philgeps": int(summary.get("philgeps", 0)),
                "microsite": int(summary.get("microsite", summary.get("infrawatch", 0))),
            },
        }
    }


def main():
    print("🚀 Generating congressman-ranking.json cache...")
    data_root, cache_files = load_cache_paths()
    print(f"📁 Found {len(cache_files)} congressman caches")

    ranking: Dict[str, Dict[str, float]] = {}
    summary_totals = {
        "total": 0,
        "ssp": 0,
        "dime": 0,
        "philgeps": 0,
        "microsite": 0,
        "district_projects": 0,
        "contractor_projects": 0,
    }
    totals_cost = {
        "total_cost_all": 0.0,
        "district_cost": 0.0,
        "contractor_cost": 0.0,
    }

    for cache_path in cache_files:
        try:
            stats_map = aggregate_congressman_stats(cache_path)
        except Exception as exc:  # pylint: disable=broad-except
            print(f"   ⚠️  Error loading {cache_path}: {exc}")
            continue

        for name, stats in stats_map.items():
            existing = ranking.get(name)
            if existing:
                existing["count"] = max(existing["count"], stats["count"])
                existing["total_cost"] = max(existing["total_cost"], stats["total_cost"])
            else:
                ranking[name] = stats

            summary = stats.get("sources_breakdown", {})
            summary_totals["total"] += summary.get("total", stats["count"])
            summary_totals["ssp"] += summary.get("ssp", 0)
            summary_totals["dime"] += summary.get("dime", 0)
            summary_totals["philgeps"] += summary.get("philgeps", 0)
            summary_totals["microsite"] += summary.get("microsite", 0)
            summary_totals["district_projects"] += stats.get("district_count", 0)
            summary_totals["contractor_projects"] += stats.get("contractor_count", 0)

            totals_cost["total_cost_all"] += stats.get("total_cost", 0.0)
            totals_cost["district_cost"] += stats.get("district_cost", 0.0)
            totals_cost["contractor_cost"] += stats.get("contractor_cost", 0.0)

    ranking_list = list(ranking.values())
    ranking_by_count = sorted(ranking_list, key=lambda item: item["count"], reverse=True)
    ranking_by_cost = sorted(ranking_list, key=lambda item: item["total_cost"], reverse=True)
    top_10_by_count = ranking_by_count[:10]
    top_10_by_cost = ranking_by_cost[:10]

    print("\n📈 Top 10 Congressmen by Project Count (preview):")
    for idx, entry in enumerate(top_10_by_count, 1):
        print(f"   {idx}. {entry['name']}: {entry['count']} projects, ₱{entry['total_cost']:,.2f}")

    print("\n💰 Top 10 Congressmen by Total Cost (preview):")
    for idx, entry in enumerate(top_10_by_cost, 1):
        print(f"   {idx}. {entry['name']}: ₱{entry['total_cost']:,.2f} ({entry['count']} projects)")

    dashboard_stats = {
        "total_cost_all": totals_cost["total_cost_all"],
        "total_projects": summary_totals["total"],
        "district_count": summary_totals["district_projects"],
        "district_cost": totals_cost["district_cost"],
        "contractor_count": summary_totals["contractor_projects"],
        "contractor_cost": totals_cost["contractor_cost"],
    }

    output = {
        "success": True,
        "ranking_by_count": ranking_by_count,
        "ranking_by_cost": ranking_by_cost,
        "top_10_by_count": top_10_by_count,
        "top_10_by_cost": top_10_by_cost,
        "dashboard_stats": dashboard_stats,
        "summary": summary_totals,
        "total_congressmen": len(ranking_by_count),
        "generated_at": datetime.utcnow().isoformat(),
        "cache_version": "3.0",
    }

    output_path = data_root / "congressman-ranking.json"
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2, ensure_ascii=False)

    print(f"\n✅ Saved to {output_path}")
    print(f"   Total projects (summary): {summary_totals['total']}")
    print(f"   District matches: {summary_totals['district_projects']} (₱{totals_cost['district_cost']:,.2f})")
    print(f"   Contractor matches: {summary_totals['contractor_projects']} (₱{totals_cost['contractor_cost']:,.2f})")
    print(f"   Total congressmen covered: {len(ranking_by_count)}")


if __name__ == "__main__":
    main()


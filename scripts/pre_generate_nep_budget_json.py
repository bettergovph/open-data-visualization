#!/usr/bin/env python3
"""
Pre-generate JSON files for heavy processing endpoints on /nep and /budget pages.

This script identifies heavy processing endpoints and pre-generates their JSON responses
to static files, which can then be served directly instead of computing on each request.

Heavy endpoints identified:
- /api/budget/regions (yearly data aggregation)
- /api/budget/nep/year-over-year (yearly aggregation)
- /api/budget/nep/top-programs (sorting and aggregation)
- /api/budget/analysis/comparison-chart (database queries for multiple years)
- /api/budget/programs/comparison (database queries for multiple years)
- /api/budget/roads-cost-analysis (chainage parsing, categorization)
- /api/budget/roads-cost-analysis-all-years (multi-year processing)
- /api/budget/amendments/departments (data loading and filtering)
- /api/budget/amendments/annex-a1-amounts (filtering and extraction)
- /api/budget/amendments/annex-a5-amounts (filtering and extraction)
- /api/budget/amendments/annex-a4-amounts (filtering and extraction)
- /api/budget/amendments/annex-a5-duplicates (duplicate detection results)
- /api/budget/amendments/annex-a4-duplicates (duplicate detection results)
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# Add parent directory to path to import visualization modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import the same functions used in visualization.py
from budget_client import (
    get_budget_overview_stats,
    get_budget_departments,
    get_budget_agencies,
    get_budget_expense_categories,
    get_budget_regions,
)
from nep_postgres_client import (
    get_budget_overview_stats as get_nep_overview_stats,
    get_budget_departments as get_nep_departments,
    get_budget_agencies as get_nep_agencies,
    get_budget_expense_categories as get_nep_expense_categories,
    get_budget_regions as get_nep_regions,
)
from nep_client import get_nep_year_over_year, get_nep_top_programs
from budget_postgres_client import get_budget_department_trends
import asyncpg
from dotenv import load_dotenv

load_dotenv()

DATA_ROOT = Path(__file__).parent.parent / "static" / "data"
CACHE_DIR = DATA_ROOT / "api_cache"

# Ensure cache directory exists
CACHE_DIR.mkdir(parents=True, exist_ok=True)


async def generate_budget_regions_cache():
    """Pre-generate /api/budget/regions data for all years"""
    print("📊 Generating budget regions cache...")
    
    cache_data = {}
    years = [2020, 2021, 2022, 2023, 2024, 2025]
    
    for year in years:
        try:
            result = await get_budget_regions(str(year), limit=1000)  # Get all regions
            cache_data[str(year)] = result
            print(f"  ✅ Year {year}: {len(result.get('regions', []))} regions")
        except Exception as e:
            print(f"  ❌ Year {year}: {e}")
            cache_data[str(year)] = {"success": False, "error": str(e), "regions": []}
    
    # Save to cache
    cache_file = CACHE_DIR / "budget_regions_cache.json"
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump({
            "success": True,
            "data": cache_data,
            "generated_at": datetime.now().isoformat(),
            "years": years
        }, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Saved budget regions cache to {cache_file}")
    return cache_data


async def generate_nep_year_over_year_cache():
    """Pre-generate /api/budget/nep/year-over-year data"""
    print("📊 Generating NEP year-over-year cache...")
    
    try:
        result = await get_nep_year_over_year()
        
        cache_file = CACHE_DIR / "nep_year_over_year_cache.json"
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump({
                "success": True,
                **result,
                "generated_at": datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Saved NEP year-over-year cache to {cache_file}")
        return result
    except Exception as e:
        print(f"❌ Error generating NEP year-over-year cache: {e}")
        return None


async def generate_nep_top_programs_cache():
    """Pre-generate /api/budget/nep/top-programs data for multiple years"""
    print("📊 Generating NEP top programs cache...")
    
    cache_data = {}
    years = [2020, 2021, 2022, 2023, 2024, 2025, 2026]
    
    for year in years:
        try:
            result = await get_nep_top_programs(str(year), limit=20)
            cache_data[str(year)] = result
            print(f"  ✅ Year {year}: {len(result.get('programs', []))} programs")
        except Exception as e:
            print(f"  ❌ Year {year}: {e}")
            cache_data[str(year)] = {"success": False, "error": str(e), "programs": []}
    
    cache_file = CACHE_DIR / "nep_top_programs_cache.json"
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump({
            "success": True,
            "data": cache_data,
            "generated_at": datetime.now().isoformat(),
            "years": years
        }, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Saved NEP top programs cache to {cache_file}")
    return cache_data


async def generate_budget_comparison_chart_cache():
    """Pre-generate /api/budget/analysis/comparison-chart data"""
    print("📊 Generating budget comparison chart cache...")
    
    try:
        # Connect to databases
        budget_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database='budget_analysis'
        )
        
        nep_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database='nep'
        )
        
        years = [2020, 2021, 2022, 2023, 2024, 2025]
        budget_amounts = []
        nep_amounts = []
        
        for year in years:
            # Get budget data
            budget_table = f"budget_{year}"
            try:
                budget_result = await budget_conn.fetchrow(f"""
                    SELECT COALESCE(SUM(amt), 0) as total_amount
                    FROM {budget_table}
                    WHERE amt IS NOT NULL AND amt > 0
                """)
                budget_amount = float(budget_result['total_amount']) if budget_result else 0
            except Exception as e:
                print(f"  ⚠️ Error fetching budget data for {year}: {e}")
                budget_amount = 0
            
            # Get NEP data
            nep_table = f"budget_{year}"
            try:
                nep_result = await nep_conn.fetchrow(f"""
                    SELECT COALESCE(SUM(amount), 0) as total_amount
                    FROM {nep_table}
                    WHERE amount IS NOT NULL AND amount > 0
                """)
                nep_amount = float(nep_result['total_amount']) if nep_result else 0
            except Exception as e:
                print(f"  ⚠️ Error fetching NEP data for {year}: {e}")
                nep_amount = 0
            
            budget_amounts.append(budget_amount)
            nep_amounts.append(nep_amount)
        
        await budget_conn.close()
        await nep_conn.close()
        
        chart_data = {
            "years": years,
            "budget_amounts": budget_amounts,
            "nep_amounts": nep_amounts
        }
        
        cache_file = CACHE_DIR / "budget_comparison_chart_cache.json"
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump({
                "success": True,
                **chart_data,
                "generated_at": datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Saved budget comparison chart cache to {cache_file}")
        return chart_data
        
    except Exception as e:
        print(f"❌ Error generating budget comparison chart cache: {e}")
        import traceback
        traceback.print_exc()
        return None


async def generate_budget_programs_comparison_cache():
    """Pre-generate /api/budget/programs/comparison data"""
    print("📊 Generating budget programs comparison cache...")
    
    try:
        # Connect to databases
        budget_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database='budget_analysis'
        )
        
        nep_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database='nep'
        )
        
        programs = [
            "Convergence and Special Support Program",
            "Local Program",
            "Asset Preservation Program",
            "Flood Management Program",
            "General Administration and Support",
            "Bridge Program",
            "Network Development Program",
            "Support to Operations"
        ]
        
        program_data = []
        
        for program in programs:
            budget_yearly = {}
            budget_total = 0
            budget_count = 0
            
            for year in range(2020, 2026):
                budget_table = f"budget_{year}"
                year_total = 0
                year_count = 0
                
                try:
                    budget_result = await budget_conn.fetch(f"""
                        SELECT dsc, amt, year
                        FROM {budget_table}
                        WHERE dsc ILIKE '%{program}%' AND amt > 0
                    """)
                    
                    for row in budget_result:
                        year_total += float(row['amt'])
                        year_count += 1
                        budget_total += float(row['amt'])
                        budget_count += 1
                    
                    budget_yearly[str(year)] = year_total
                except Exception as e:
                    print(f"  ⚠️ Error fetching budget data for {program} in {year}: {e}")
                    budget_yearly[str(year)] = 0
            
            nep_yearly = {}
            nep_total = 0
            nep_count = 0
            
            for year in range(2020, 2027):
                nep_table = f"budget_{year}"
                year_total = 0
                year_count = 0
                
                try:
                    nep_result = await nep_conn.fetch(f"""
                        SELECT description, amount, fiscal_year
                        FROM {nep_table}
                        WHERE description ILIKE '%{program}%' AND amount > 0
                    """)
                    
                    for row in nep_result:
                        year_total += float(row['amount'])
                        year_count += 1
                        nep_total += float(row['amount'])
                        nep_count += 1
                    
                    nep_yearly[str(year)] = year_total
                except Exception as e:
                    print(f"  ⚠️ Error fetching NEP data for {program} in {year}: {e}")
                    nep_yearly[str(year)] = 0
            
            program_data.append({
                'program': program,
                'budget_total': budget_total,
                'budget_count': budget_count,
                'budget_yearly': budget_yearly,
                'nep_total': nep_total,
                'nep_count': nep_count,
                'nep_yearly': nep_yearly
            })
        
        await budget_conn.close()
        await nep_conn.close()
        
        result = {
            "success": True,
            "programs": program_data,
            "total_programs": len(programs),
            "generated_at": datetime.now().isoformat()
        }
        
        cache_file = CACHE_DIR / "budget_programs_comparison_cache.json"
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Saved budget programs comparison cache to {cache_file}")
        return result
        
    except Exception as e:
        print(f"❌ Error generating budget programs comparison cache: {e}")
        import traceback
        traceback.print_exc()
        return None


async def generate_roads_cost_analysis_cache():
    """Pre-generate /api/budget/roads-cost-analysis data"""
    print("📊 Generating roads cost analysis cache...")
    
    try:
        import re
        from difflib import SequenceMatcher
        
        # Load budget amendments data
        json_path = Path('static/data/budget_amendments_2026.json')
        if not json_path.exists():
            print(f"  ⚠️ Budget amendments file not found: {json_path}")
            return None
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        all_items = data.get('line_items', []) + data.get('projects', [])
        
        # Helper functions (simplified versions from visualization.py)
        def extract_all_chainage_ranges(name: str):
            ranges = []
            pattern_k = r'K(\d+)\s*\+\s*\(?(-?\d+)\)?\s*-\s*K(\d+)\s*\+\s*\(?(-?\d+)\)?'
            for match in re.finditer(pattern_k, name, re.IGNORECASE):
                ranges.append((int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))))
            pattern_chainage = r'Chainage\s+(\d+)\s*-\s*Chainage\s+(\d+)'
            for match in re.finditer(pattern_chainage, name, re.IGNORECASE):
                start_total = int(match.group(1))
                end_total = int(match.group(2))
                start_km = start_total // 1000
                start_m = start_total % 1000
                end_km = end_total // 1000
                end_m = end_total % 1000
                ranges.append((start_km, start_m, end_km, end_m))
            return ranges
        
        def calculate_distance(chainage_ranges):
            if not chainage_ranges:
                return None, None, []
            total_distance_m = 0
            individual_distances_m = []
            def to_meters(km, m):
                return km * 1000 + m
            for chainage_range in chainage_ranges:
                start_km, start_m, end_km, end_m = chainage_range
                start_total = to_meters(start_km, start_m)
                end_total = to_meters(end_km, end_m)
                distance_m = abs(end_total - start_total)
                individual_distances_m.append(distance_m)
                total_distance_m += distance_m
            distance_km = total_distance_m / 1000.0
            breakdown = ' + '.join([f'{int(d)}m' for d in individual_distances_m]) + f' = {int(total_distance_m)}m' if len(individual_distances_m) > 1 else None
            return distance_km, breakdown, individual_distances_m
        
        def format_chainage_display(name: str, ranges):
            if not ranges:
                return None
            chainage_strings = []
            pattern_k = r'(K\d+\s*\+\s*\(?-?\d+\)?\s*-\s*K\d+\s*\+\s*\(?-?\d+\)?)'
            for match in re.finditer(pattern_k, name, re.IGNORECASE):
                chainage_strings.append(match.group(1))
            pattern_chainage = r'(Chainage\s+\d+\s*-\s*Chainage\s+\d+)'
            for match in re.finditer(pattern_chainage, name, re.IGNORECASE):
                chainage_strings.append(match.group(1))
            if chainage_strings:
                return ', '.join(chainage_strings)
            return None
        
        # Process projects
        road_projects = []
        national_road_projects = []
        secondary_road_projects = []
        bridge_projects = []
        traffic_signs_projects = []
        
        for item in all_items:
            name = item.get('name', '') or item.get('description', '')
            if not name:
                continue
            
            chainage_ranges = extract_all_chainage_ranges(name)
            if not chainage_ranges:
                continue
            
            amount = abs(item.get('final_amount', 0) or item.get('original_amount', 0))
            if amount <= 0:
                continue
            
            distance_km, breakdown, individual_distances = calculate_distance(chainage_ranges)
            if not distance_km or distance_km <= 0:
                continue
            
            cost_per_km = amount / distance_km
            chainage_display = format_chainage_display(name, chainage_ranges) or 'N/A'
            
            project_data = {
                'name': name,
                'chainage_display': chainage_display,
                'chainage_ranges': chainage_ranges,
                'distance_km': distance_km,
                'distance_breakdown': breakdown,
                'amount': amount,
                'cost_per_km': cost_per_km,
                'source_sheet': item.get('source_sheet'),
                'region': item.get('location', {}).get('region') if isinstance(item.get('location'), dict) else None
            }
            
            # Categorize (simplified)
            name_lower = name.lower()
            
            road_safety_keywords = [
                'installation', 'road safety', 'guardrail', 'traffic facilities', 'traffic facility',
                'lighting', 'streetlight', 'street light', 'led', 'solar', 'roadway lighting',
                'road sign', 'pavement marking', 'barrier', 'pedestrian overpass'
            ]
            is_road_safety = any(keyword in name_lower for keyword in road_safety_keywords)
            
            bridge_keywords = ['bridge', 'viaduct', 'flyover', 'overpass', 'underpass', 'footbridge', 'pedestrian bridge']
            is_bridge = any(keyword in name_lower for keyword in bridge_keywords)
            
            road_terms = [
                ' road', ' rd', ' highway', ' hiway', ' hway', ' h-way',
                'boulevard', ' blvd', ' avenue', ' ave', ' ave.',
                'junction', ' jct', ' old route', ' diversion',
                'extension', ' ext', ' street', ' st', ' st.',
                'expressway'
            ]
            is_road_term = any(term in name_lower for term in road_terms)
            
            if is_road_safety:
                traffic_signs_projects.append(project_data)
            elif is_bridge:
                bridge_projects.append(project_data)
            elif is_road_term or not is_bridge:
                # Simplified: assume national road if distance > 1km
                is_national_road = distance_km > 1.0
                if is_national_road:
                    national_road_projects.append(project_data)
                else:
                    secondary_road_projects.append(project_data)
            else:
                secondary_road_projects.append(project_data)
        
        # Sort by cost per km
        national_road_projects.sort(key=lambda x: x['cost_per_km'], reverse=True)
        secondary_road_projects.sort(key=lambda x: x['cost_per_km'], reverse=True)
        bridge_projects.sort(key=lambda x: x['cost_per_km'], reverse=True)
        traffic_signs_projects.sort(key=lambda x: x['cost_per_km'], reverse=True)
        
        road_projects = national_road_projects + secondary_road_projects
        
        result = {
            "success": True,
            "roads": {
                "projects": road_projects,
                "total": len(road_projects)
            },
            "national_roads": {
                "projects": national_road_projects,
                "total": len(national_road_projects)
            },
            "secondary_roads": {
                "projects": secondary_road_projects,
                "total": len(secondary_road_projects)
            },
            "bridges": {
                "projects": bridge_projects,
                "total": len(bridge_projects)
            },
            "traffic_signs": {
                "projects": traffic_signs_projects,
                "total": len(traffic_signs_projects)
            }
        }
        
        cache_file = CACHE_DIR / "roads_cost_analysis_cache.json"
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump({
                **result,
                "generated_at": datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Saved roads cost analysis cache to {cache_file}")
        return result
        
    except Exception as e:
        print(f"❌ Error generating roads cost analysis cache: {e}")
        import traceback
        traceback.print_exc()
        return None


async def generate_amendments_departments_cache():
    """Pre-generate /api/budget/amendments/departments data"""
    print("📊 Generating budget amendments departments cache...")
    
    try:
        json_path = DATA_ROOT / "budget_amendments_2026.json"
        if not json_path.exists():
            print(f"  ⚠️ Budget amendments file not found: {json_path}")
            return None
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Filter out agencies - only return top-level departments
        departments = [
            d for d in data['departments']
            if not d.get('is_agency', False)
        ]
        departments = sorted(departments, key=lambda d: d.get('original_amount', 0), reverse=True)
        
        result = {
            "success": True,
            "departments": departments,
            "metadata": data['metadata']
        }
        
        cache_file = CACHE_DIR / "budget_amendments_departments_cache.json"
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump({
                **result,
                "generated_at": datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Saved budget amendments departments cache to {cache_file}")
        return result
        
    except Exception as e:
        print(f"❌ Error generating budget amendments departments cache: {e}")
        import traceback
        traceback.print_exc()
        return None


async def generate_annex_amounts_cache():
    """Pre-generate annex amounts caches"""
    print("📊 Generating annex amounts caches...")
    
    try:
        json_path = DATA_ROOT / "budget_amendments_2026.json"
        if not json_path.exists():
            print(f"  ⚠️ Budget amendments file not found: {json_path}")
            return None
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Annex A-1 amounts
        annex_a1_projects = [
            p for p in data.get('projects', [])
            if p.get('source_sheet') == 'Annex A-1'
        ]
        annex_a1_amounts = [
            p.get('final_amount') or p.get('original_amount') or 0
            for p in annex_a1_projects
            if (p.get('final_amount') or p.get('original_amount') or 0) > 0
        ]
        
        # Annex A-5 amounts
        annex_a5_projects = [
            p for p in data.get('projects', [])
            if p.get('source_sheet') == 'Annex A-5'
        ]
        annex_a5_amounts = [
            p.get('final_amount') or p.get('original_amount') or 0
            for p in annex_a5_projects
            if (p.get('final_amount') or p.get('original_amount') or 0) > 0
        ]
        
        # Annex A-4 amounts
        annex_a4_projects = [
            p for p in data.get('projects', [])
            if p.get('source_sheet') == 'Annex A-4'
        ]
        annex_a4_amounts = [
            p.get('final_amount') or p.get('original_amount') or 0
            for p in annex_a4_projects
            if (p.get('final_amount') or p.get('original_amount') or 0) > 0
        ]
        
        # Save Annex A-1
        cache_file_a1 = CACHE_DIR / "annex_a1_amounts_cache.json"
        with open(cache_file_a1, 'w', encoding='utf-8') as f:
            json.dump({
                "success": True,
                "amounts": annex_a1_amounts,
                "total_projects": len(annex_a1_amounts),
                "generated_at": datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        print(f"  ✅ Saved Annex A-1 amounts cache: {len(annex_a1_amounts)} amounts")
        
        # Save Annex A-5
        cache_file_a5 = CACHE_DIR / "annex_a5_amounts_cache.json"
        with open(cache_file_a5, 'w', encoding='utf-8') as f:
            json.dump({
                "success": True,
                "amounts": annex_a5_amounts,
                "total_projects": len(annex_a5_amounts),
                "generated_at": datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        print(f"  ✅ Saved Annex A-5 amounts cache: {len(annex_a5_amounts)} amounts")
        
        # Save Annex A-4
        cache_file_a4 = CACHE_DIR / "annex_a4_amounts_cache.json"
        with open(cache_file_a4, 'w', encoding='utf-8') as f:
            json.dump({
                "success": True,
                "amounts": annex_a4_amounts,
                "total_projects": len(annex_a4_amounts),
                "generated_at": datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        print(f"  ✅ Saved Annex A-4 amounts cache: {len(annex_a4_amounts)} amounts")
        
        return {
            "a1": len(annex_a1_amounts),
            "a5": len(annex_a5_amounts),
            "a4": len(annex_a4_amounts)
        }
        
    except Exception as e:
        print(f"❌ Error generating annex amounts cache: {e}")
        import traceback
        traceback.print_exc()
        return None


async def generate_annex_duplicates_cache():
    """Pre-generate annex duplicates caches"""
    print("📊 Generating annex duplicates caches...")
    
    # Load from existing duplicate JSON files if they exist
    duplicates_a5_path = DATA_ROOT / "duplicates_a5_2026.json"
    duplicates_a4_path = DATA_ROOT / "duplicates_a4_2026.json"
    
    if duplicates_a5_path.exists():
        with open(duplicates_a5_path, 'r', encoding='utf-8') as f:
            duplicates_a5_data = json.load(f)
        
        cache_file_a5 = CACHE_DIR / "annex_a5_duplicates_cache.json"
        with open(cache_file_a5, 'w', encoding='utf-8') as f:
            json.dump({
                "success": True,
                **duplicates_a5_data,
                "generated_at": datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        print(f"  ✅ Saved Annex A-5 duplicates cache")
    else:
        print(f"  ⚠️ Annex A-5 duplicates file not found: {duplicates_a5_path}")
    
    if duplicates_a4_path.exists():
        with open(duplicates_a4_path, 'r', encoding='utf-8') as f:
            duplicates_a4_data = json.load(f)
        
        cache_file_a4 = CACHE_DIR / "annex_a4_duplicates_cache.json"
        with open(cache_file_a4, 'w', encoding='utf-8') as f:
            json.dump({
                "success": True,
                **duplicates_a4_data,
                "generated_at": datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        print(f"  ✅ Saved Annex A-4 duplicates cache")
    else:
        print(f"  ⚠️ Annex A-4 duplicates file not found: {duplicates_a4_path}")


async def generate_budget_department_trends_cache():
    """Pre-generate /api/budget/department-trends data"""
    print("📊 Generating budget department trends cache...")
    
    try:
        result = await get_budget_department_trends()
        
        cache_file = CACHE_DIR / "budget_department_trends_cache.json"
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump({
                "success": True,
                **result,
                "generated_at": datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Saved budget department trends cache to {cache_file}")
        return result
    except Exception as e:
        print(f"❌ Error generating budget department trends cache: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """Main function to generate all caches"""
    print("🚀 Starting pre-generation of JSON caches for /nep and /budget pages...")
    print(f"📁 Cache directory: {CACHE_DIR}")
    print()
    
    results = {}
    
    # Generate all caches
    try:
        results['budget_regions'] = await generate_budget_regions_cache()
        print()
        
        results['nep_year_over_year'] = await generate_nep_year_over_year_cache()
        print()
        
        results['nep_top_programs'] = await generate_nep_top_programs_cache()
        print()
        
        results['budget_comparison_chart'] = await generate_budget_comparison_chart_cache()
        print()
        
        results['budget_programs_comparison'] = await generate_budget_programs_comparison_cache()
        print()
        
        results['roads_cost_analysis'] = await generate_roads_cost_analysis_cache()
        print()
        
        results['amendments_departments'] = await generate_amendments_departments_cache()
        print()
        
        results['annex_amounts'] = await generate_annex_amounts_cache()
        print()
        
        await generate_annex_duplicates_cache()
        print()
        
        results['department_trends'] = await generate_budget_department_trends_cache()
        print()
        
    except Exception as e:
        print(f"❌ Error in main: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    print("✅ Pre-generation complete!")
    print(f"📁 All cache files saved to: {CACHE_DIR}")
    print()
    print("📝 Next steps:")
    print("  1. Update visualization.py to check for cache files first before processing")
    print("  2. Serve cached JSON files when available")
    print("  3. Fall back to processing if cache doesn't exist")


if __name__ == "__main__":
    asyncio.run(main())



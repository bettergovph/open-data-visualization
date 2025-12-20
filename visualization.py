import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
import os
import json
import csv
import re
import unicodedata
import time
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path


from typing import Any, Dict, Optional, Set, List, Tuple
from dotenv import load_dotenv
from collections import defaultdict
from urllib.parse import urlparse
import duckdb

load_dotenv()
from budget_client import (
    get_budget_overview_stats,
    get_budget_departments,
    get_budget_agencies,
    get_budget_expense_categories,
    get_budget_regions,
    get_budget_files,
    get_budget_columns,
    get_budget_scored_duplicates,
    get_budget_duplicates_count,
    get_budget_total_items_count
)
from nep_postgres_client import get_db_connection as get_nep_db_connection
import asyncpg
from relationship_sources_client import (
    fetch_relationship_articles,
    fetch_relationship_checklist,
)
from nep_postgres_client import (
    get_budget_overview_stats as get_nep_overview_stats,
    get_budget_departments as get_nep_departments,
    get_budget_agencies as get_nep_agencies,
    get_budget_expense_categories as get_nep_expense_categories,
    get_budget_regions as get_nep_regions,
    get_budget_data_browser as get_nep_data_browser,
    get_budget_columns as get_nep_columns,
    get_budget_scored_duplicates as get_nep_duplicates,
    get_budget_duplicates_count as get_nep_duplicates_count,
    get_budget_anomalies_count as get_nep_anomalies_count,
    get_budget_total_items_count as get_nep_total_items_count
)
from infrawatch_postgres_client import get_infrawatch_connection
from flood_db_client import search_flood_projects

DATA_ROOT = Path(__file__).resolve().parent / "static" / "data"
MAD_SCALE = 1.4826

_PHILGEPS_COORD_COLUMNS: Optional[Tuple[str, str]] = None
_PHILGEPS_COORD_CACHE: Dict[str, Optional[Dict[str, Any]]] = {}
_INFRAWATCH_COORD_CACHE: Dict[str, Optional[Dict[str, Any]]] = {}
_INFRAWATCH_TABLE_META: Optional[Dict[str, Any]] = None
_INFRAWATCH_LAT_KEYS = [
    "Latitude",
    "LATITUDE",
    "latitude",
    "Lat",
    "Lat (decimal degrees)",
    "Latitude (decimal)",
    "Latitude (DD)",
]
_INFRAWATCH_LNG_KEYS = [
    "Longitude",
    "LONGITUDE",
    "longitude",
    "Lon",
    "Long",
    "Lng",
    "Long (decimal degrees)",
    "Longitude (decimal)",
    "Longitude (DD)",
]
_INFRAWATCH_COORDINATE_FALLBACK_KEYS = [
    "Coordinates",
    "Coordinate",
    "GPS Coordinates",
    "GPS",
]
_INFRAWATCH_TITLE_KEYS = [
    "Project Name",
    "Project",
    "Project Title",
    "Project Description",
    "Contract Details",
    "Project Location",
]
_INFRAWATCH_PROVINCE_KEYS = [
    "Province",
    "Province/Location",
    "Location",
]
_INFRAWATCH_CITY_KEYS = [
    "City/Municipality",
    "City / Municipality",
    "Municipality",
    "City",
]


def _normalize_cache_name(name: str) -> str:
    if not name:
        return ""
    normalized = unicodedata.normalize("NFD", name)
    stripped = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    cleaned = re.sub(r"[^a-z0-9]+", " ", stripped.lower())
    return cleaned.strip()


def _normalize_congressman_slug(name: str) -> str:
    if not name:
        return ""
    normalized = unicodedata.normalize("NFD", name)
    stripped = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    slug = stripped.lower()
    slug = slug.replace(" ", "-")
    slug = re.sub(r"[^\w\-]", "", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug.strip("-")


def _read_json_file(path: Path) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception as exc:
        print(f"⚠️ Failed to read JSON cache {path}: {exc}")
        return None


def _get_dynasty_config_path() -> Path:
    return DATA_ROOT / "dynasty-projects-config.json"


@lru_cache(maxsize=1)
def _load_dynasty_config() -> Dict[str, Any]:
    config_path = _get_dynasty_config_path()
    data = _read_json_file(config_path)
    if isinstance(data, dict):
        return data
    return {}


def _find_congressman_cache(identifier: str) -> Optional[Path]:
    slug = _normalize_congressman_slug(identifier)
    candidate = DATA_ROOT / f"congressman-projects-{slug}"
    if candidate.exists():
        return candidate

    normalized_target = _normalize_cache_name(identifier)
    for cache_dir in DATA_ROOT.glob("congressman-projects-*"):
        if not cache_dir.is_dir():
            continue
        summary_data = _read_json_file(cache_dir / "summary.json")
        display_name = None
        if isinstance(summary_data, dict):
            display_name = summary_data.get("congressman")
        if not display_name:
            all_cache = _read_json_file(cache_dir / "all-projects-cache.json")
            if isinstance(all_cache, dict):
                display_name = all_cache.get("congressman")
        if display_name and _normalize_cache_name(display_name) == normalized_target:
            return cache_dir
    if candidate.exists():
        return candidate
    return None


def _gather_congressman_cache_stats() -> Dict[str, Any]:
    stats: Dict[str, Any] = {
        "directories": 0,
        "unique_total": 0,
        "with_projects": 0,
        "district_congressmen": 0,
        "partylist_representatives": 0,
        "names": []
    }
    if not DATA_ROOT.exists():
        return stats

    # Load config to identify party-list representatives
    config_path = DATA_ROOT / "dynasty-projects-config.json"
    config_data = _read_json_file(config_path)
    partylist_names = set()
    if isinstance(config_data, dict):
        for entry in config_data.get("target_congressmen", []):
            if not entry.get("province"):
                name = entry.get("display_name", "")
                if name:
                    partylist_names.add(_normalize_cache_name(name))

    unique_map: Dict[str, Dict[str, Any]] = {}

    for cache_dir in DATA_ROOT.glob("congressman-projects-*"):
        if not cache_dir.is_dir():
            continue
        stats["directories"] += 1

        summary_path = cache_dir / "summary.json"
        summary_data = _read_json_file(summary_path)

        name = None
        projects_total = 0
        if isinstance(summary_data, dict):
            name = summary_data.get("congressman")
            summary_total = summary_data.get("summary", {}).get("total")
            if summary_total is not None:
                try:
                    projects_total = int(summary_total)
                except (TypeError, ValueError):
                    projects_total = 0

        if name is None:
            all_projects_path = cache_dir / "all-projects-cache.json"
            all_projects_data = _read_json_file(all_projects_path)
            if isinstance(all_projects_data, dict):
                name = all_projects_data.get("congressman")
                projects = all_projects_data.get("projects")
                if isinstance(projects, list):
                    projects_total = max(projects_total, len(projects))

        if not name:
            slug = cache_dir.name.replace("congressman-projects-", "")
            name = slug.replace("-", " ").title()

        normalized = _normalize_cache_name(name)
        if normalized not in unique_map:
            unique_map[normalized] = {
                "name": name,
                "projects_total": 0,
                "is_partylist": normalized in partylist_names
            }

        entry = unique_map[normalized]
        if projects_total and projects_total > entry["projects_total"]:
            entry["projects_total"] = projects_total

    stats["unique_total"] = len(unique_map)
    stats["with_projects"] = sum(1 for entry in unique_map.values() if entry["projects_total"] > 0)
    
    # Count district vs party-list
    for entry in unique_map.values():
        if entry["projects_total"] > 0:
            if entry["is_partylist"]:
                stats["partylist_representatives"] += 1
            else:
                stats["district_congressmen"] += 1
    
    stats["names"] = sorted(entry["name"] for entry in unique_map.values())
    return stats


def _load_congressman_cache(slug_or_name: str) -> Optional[Dict[str, Any]]:
    cache_dir = _find_congressman_cache(slug_or_name)
    if not cache_dir:
        return None
    all_projects_path = cache_dir / "all-projects-cache.json"
    cache_data = _read_json_file(all_projects_path)
    if not isinstance(cache_data, dict):
        return None

    summary_path = cache_dir / "summary.json"
    summary_data = _read_json_file(summary_path)
    if isinstance(summary_data, dict):
        cache_data.setdefault("summary", summary_data.get("summary") or {})
        cache_data.setdefault("dashboard_stats", summary_data.get("dashboard_stats") or {})
        cache_data.setdefault("generated_at", summary_data.get("generated_at"))
        cache_data.setdefault("congressman", summary_data.get("congressman") or cache_data.get("congressman"))
        cache_data.setdefault("total_cost", summary_data.get("total_cost"))
    cache_data["cache_dir"] = str(cache_dir)
    cache_data["slug"] = cache_dir.name.replace("congressman-projects-", "", 1)
    return cache_data


def _gather_province_cache_stats() -> Dict[str, Any]:
    stats: Dict[str, Any] = {
        "directories": 0,
        "with_projects": 0,
        "unique_total": 0,
        "unique_with_projects": 0,
        "names": [],
        "names_with_projects": []
    }
    if not DATA_ROOT.exists():
        return stats

    province_names: Set[str] = set()
    provinces_with_projects: Set[str] = set()

    for cache_dir in DATA_ROOT.glob("province-projects-*"):
        if not cache_dir.is_dir():
            continue
        stats["directories"] += 1

        summary_path = cache_dir / "summary.json"
        summary_data = _read_json_file(summary_path)
        province_name = None
        total_projects = 0

        if isinstance(summary_data, dict):
            province_name = summary_data.get("province")
            summary_total = summary_data.get("summary", {}).get("total")
            if summary_total is not None:
                try:
                    total_projects = int(summary_total)
                except (TypeError, ValueError):
                    total_projects = 0

        if province_name:
            province_names.add(province_name)

        if total_projects and total_projects > 0:
            stats["with_projects"] += 1
            if province_name:
                provinces_with_projects.add(province_name)

    stats["unique_total"] = len(province_names) if province_names else stats["directories"]
    stats["unique_with_projects"] = len(provinces_with_projects) if provinces_with_projects else stats["with_projects"]
    stats["names"] = sorted(province_names)
    stats["names_with_projects"] = sorted(provinces_with_projects)
    return stats


def _extract_district_names(area_payload: Dict[str, Any]) -> Set[str]:
    district_names: Set[str] = set()
    if not isinstance(area_payload, dict):
        return district_names

    all_districts = area_payload.get("all_districts")
    if isinstance(all_districts, list):
        for label in all_districts:
            if label:
                district_names.add(str(label))

    municipalities = area_payload.get("municipalities")
    if isinstance(municipalities, dict):
        for label in municipalities.values():
            if label:
                district_names.add(str(label))

    barangays = area_payload.get("barangays")
    if isinstance(barangays, dict):
        for district_label in barangays.keys():
            if district_label:
                district_names.add(str(district_label))

    return district_names


def _gather_district_cache_stats(provinces_with_projects: Set[str]) -> Dict[str, Any]:
    stats: Dict[str, Any] = {
        "entries_total": 0,
        "districts_total": 0,
        "entries_matched": 0,
        "districts_matched": 0,
        "areas": []
    }

    districts_path = DATA_ROOT / "districts.json"
    payload = _read_json_file(districts_path)
    if not isinstance(payload, dict):
        return stats

    districts_map = payload.get("districts")
    if not isinstance(districts_map, dict):
        return stats

    stats["entries_total"] = len(districts_map)
    province_lookup = {name.lower(): name for name in provinces_with_projects}

    for area_name, area_payload in districts_map.items():
        district_names = _extract_district_names(area_payload)
        stats["districts_total"] += len(district_names)
        stats["areas"].append({
            "name": area_name,
            "districts": sorted(district_names)
        })

        normalized_area = area_name.lower()
        if normalized_area in province_lookup and district_names:
            stats["entries_matched"] += 1
            stats["districts_matched"] += len(district_names)

    stats["areas"] = sorted(stats["areas"], key=lambda item: item.get("name", ""))
    return stats


def _pluralize(count: int, singular: str, plural: Optional[str] = None) -> str:
    if plural is None:
        plural = singular + "s"
    word = singular if count == 1 else plural
    return f"{count} {word}"


def _compose_coverage_summary(congressmen_stats: Dict[str, Any], province_stats: Dict[str, Any], district_stats: Dict[str, Any]) -> Dict[str, Any]:
    # Count district congressmen and party-list separately
    district_congressmen = congressmen_stats.get("district_congressmen", 0)
    partylist_reps = congressmen_stats.get("partylist_representatives", 0)
    total_congressmen = congressmen_stats.get("with_projects") or congressmen_stats.get("unique_total") or 0
    
    # Use districts_matched if available, otherwise use districts_total (all districts in districts.json)
    districts_processed = district_stats.get("districts_matched", 0)
    if districts_processed == 0:
        districts_processed = district_stats.get("districts_total", 0)
    
    provinces_processed = province_stats.get("unique_with_projects") or province_stats.get("with_projects") or province_stats.get("unique_total") or 0

    if total_congressmen or districts_processed or provinces_processed:
        parts = []
        
        # Break down congressmen into district and party-list
        if district_congressmen > 0 and partylist_reps > 0:
            parts.append(f"{district_congressmen} district {_pluralize(district_congressmen, 'congressman', 'congressmen').split()[1]}")
            parts.append(f"{partylist_reps} party-list {_pluralize(partylist_reps, 'representative', 'representatives').split()[1]}")
        elif total_congressmen > 0:
            parts.append(_pluralize(total_congressmen, "congressman cache"))
        
        if districts_processed > 0:
            parts.append(_pluralize(districts_processed, "district listing"))
        
        if provinces_processed:
            parts.append(_pluralize(provinces_processed, "province cache"))

        if len(parts) == 1:
            message = f"Currently covering {parts[0]}."
        elif len(parts) == 2:
            message = f"Currently covering {parts[0]} and {parts[1]}."
        else:
            message = f"Currently covering {', '.join(parts[:-1])}, and {parts[-1]}."
    else:
        message = "Coverage stats are still being generated."

    return {
        "congressmen_processed": int(total_congressmen),
        "district_congressmen": int(district_congressmen),
        "partylist_representatives": int(partylist_reps),
        "districts_processed": int(districts_processed),
        "provinces_processed": int(provinces_processed),
        "message": message
    }


def _compute_integrated_coverage_snapshot() -> Dict[str, Any]:
    congressmen_stats = _gather_congressman_cache_stats()
    province_stats = _gather_province_cache_stats()
    district_stats = _gather_district_cache_stats(set(province_stats.get("names_with_projects", [])))

    summary = _compose_coverage_summary(congressmen_stats, province_stats, district_stats)

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    return {
        "generated_at": generated_at,
        "congressmen": congressmen_stats,
        "provinces": province_stats,
        "districts": district_stats,
        "coverage_summary": summary
    }


@lru_cache(maxsize=1)
def _cached_integrated_coverage_snapshot() -> Dict[str, Any]:
    return _compute_integrated_coverage_snapshot()

app = FastAPI(title="BetterGovPH API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return {"message": "BetterGovPH API", "status": "running"}


@app.get("/api/integrated/coverage")
async def get_integrated_coverage(refresh: bool = Query(False)) -> JSONResponse:
    if refresh:
        _cached_integrated_coverage_snapshot.cache_clear()
    snapshot = _cached_integrated_coverage_snapshot()
    return JSONResponse(content=snapshot)

@app.get("/api/mpb/top-buildings")
async def get_mpb_top_buildings() -> JSONResponse:
    """Return the list of top MPB buildings filtered and saved to `static/data/mpb_top_buildings.json`."""
    path = DATA_ROOT / "mpb_top_buildings.json"
    if not path.exists():
        return JSONResponse(content={"success": False, "error": "MPB data file not found", "buildings": []}, status_code=404)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Ensure we return a list for `buildings` key
        if not isinstance(data, list):
            return JSONResponse(content={"success": False, "error": "MPB data malformed", "buildings": []}, status_code=500)
        return JSONResponse(content={"success": True, "buildings": data})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(content={"success": False, "error": str(e), "buildings": []}, status_code=500)

# @app.get("/api/integrated/projects")
async def _deprecated_get_integrated_projects(
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    limit: int = Query(default=50, ge=1, le=1000, description="Number of projects per page"),
    project_name: Optional[str] = Query(default=None, description="Filter by project name/title"),
    contractor: Optional[str] = Query(default=None, description="Filter by contractor name")
) -> JSONResponse:
    """Get integrated projects from parquet file using DuckDB with filtering and pagination"""
    try:
        # Get the parquet file path (use absolute path)
        # CRITICAL: Use classified parquet (deduplicated) instead of integrated_projects.parquet
        base_dir = Path(__file__).parent.absolute()
        classified_file = base_dir / "data" / "parquet" / "integrated_projects_classified.parquet"
        integrated_file = base_dir / "data" / "parquet" / "integrated_projects.parquet"
        
        # Prefer classified (deduplicated) over integrated (all projects)
        if classified_file.exists():
            parquet_file = classified_file
            print(f"📊 Using classified parquet (deduplicated): {parquet_file.name}")
        elif integrated_file.exists():
            parquet_file = integrated_file
            print(f"⚠️  Using integrated parquet (not deduplicated): {parquet_file.name}")
        else:
            parquet_file = None
        
        if not parquet_file or not parquet_file.exists():
            return JSONResponse(
                content={
                    "success": False,
                    "error": f"Parquet file not found: {parquet_file}",
                    "projects": [],
                    "total": 0,
                    "total_pages": 0
                },
                status_code=404
            )
        
        # Connect to DuckDB
        conn = duckdb.connect()
        
        try:
            # Build WHERE clause with proper SQL escaping
            where_conditions = []
            
            def escape_sql_string(s: str) -> str:
                """Escape single quotes for SQL"""
                return s.replace("'", "''")
            
            if project_name:
                escaped_name = escape_sql_string(project_name)
                # Note: The parquet file has 'award_title' not 'philgeps_award_title'
                where_conditions.append(
                    f"(project_name ILIKE '%{escaped_name}%' OR "
                    f"award_title ILIKE '%{escaped_name}%' OR "
                    f"project_description ILIKE '%{escaped_name}%')"
                )
            
            if contractor:
                escaped_contractor = escape_sql_string(contractor)
                # Note: The parquet file has 'contractor' not 'contractor_name'
                # philgeps_awardee_name and organization_name don't exist in the parquet
                # Only search in contractor column
                where_conditions.append(
                    f"contractor ILIKE '%{escaped_contractor}%'"
                )
            
            where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
            
            # Calculate offset
            offset = (page - 1) * limit
            
            # Convert path to string and escape single quotes
            parquet_path_str = str(parquet_file).replace("'", "''")
            
            # Get total count
            count_query = f"""
                SELECT COUNT(*) as total
                FROM read_parquet('{parquet_path_str}')
                WHERE {where_clause}
            """
            
            count_result = conn.execute(count_query).fetchone()
            total = count_result[0] if count_result else 0
            total_pages = max(1, (total + limit - 1) // limit)
            
            # Get projects with pagination
            # Use SELECT * to get all columns, then filter/rename in Python
            # This avoids BinderException for columns that don't exist
            # Don't use ORDER BY in SQL - sort in Python after fetching to avoid column existence issues
            # For proper sorting, we need to fetch all matching rows, sort, then paginate
            # This is less efficient but avoids column existence errors
            select_query = f"""
                SELECT *
                FROM read_parquet('{parquet_path_str}')
                WHERE {where_clause}
            """
            
            # Execute query (fetch all matching rows, we'll sort and paginate in Python)
            results = conn.execute(select_query).fetchall()
            columns = [desc[0] for desc in conn.description]
            
            # Convert to list of dictionaries
            projects = []
            for row in results:
                project_dict = {}
                for i, col in enumerate(columns):
                    value = row[i]
                    # Convert timestamp and other types to string if needed
                    if value is not None:
                        if isinstance(value, datetime):
                            project_dict[col] = value.isoformat()
                        elif hasattr(value, 'isoformat'):  # Handle other datetime-like objects
                            project_dict[col] = value.isoformat()
                        elif isinstance(value, list):
                            # Handle list columns (like sources_list) - preserve as-is
                            project_dict[col] = value
                        elif col == 'sources_list':
                            # sources_list might come as a string or other format from DuckDB
                            # Try to parse it if it's a string representation of a list
                            try:
                                import ast
                                if isinstance(value, str):
                                    # Try to parse string representation of list
                                    parsed = ast.literal_eval(value)
                                    if isinstance(parsed, list):
                                        project_dict[col] = parsed
                                    else:
                                        project_dict[col] = [parsed] if parsed else []
                                else:
                                    project_dict[col] = [value] if value else []
                            except (ValueError, SyntaxError):
                                # If parsing fails, treat as single value
                                project_dict[col] = [value] if value else []
                        else:
                            project_dict[col] = value
                    else:
                        project_dict[col] = None
                
                # CRITICAL: Ensure sources_list is properly formatted as a list
                # This is essential for showing multiple DBs for each project
                if 'sources_list' in project_dict:
                    sources_list = project_dict['sources_list']
                    if not isinstance(sources_list, list):
                        # Convert to list if it's not already
                        if sources_list is not None and sources_list != '':
                            sources_list = [sources_list] if not isinstance(sources_list, list) else sources_list
                        else:
                            sources_list = []
                    project_dict['sources_list'] = sources_list
                else:
                    # If sources_list doesn't exist, try to create it from source field
                    if 'source' in project_dict and project_dict['source']:
                        project_dict['sources_list'] = [project_dict['source']]
                    else:
                        project_dict['sources_list'] = []
                
                # Source (for backward compatibility - use first source from sources_list)
                if 'source' not in project_dict or not project_dict['source']:
                    sources_list = project_dict.get('sources_list', [])
                    project_dict['source'] = sources_list[0] if sources_list else 'N/A'
                
                # Map award_title to philgeps_award_title for frontend compatibility
                if 'award_title' in project_dict and project_dict['award_title']:
                    project_dict['philgeps_award_title'] = project_dict['award_title']
                
                # Map contractor to contractor_name for frontend compatibility
                if 'contractor' in project_dict and project_dict['contractor']:
                    project_dict['contractor_name'] = project_dict['contractor']
                elif 'contractor_name' not in project_dict:
                    # Set empty if contractor column doesn't exist
                    project_dict['contractor_name'] = 'N/A'
                
                # Set philgeps_awardee_name and organization_name to N/A if not in parquet
                # These columns don't exist in the parquet file, so always set to N/A
                project_dict['philgeps_awardee_name'] = 'N/A'
                project_dict['organization_name'] = 'N/A'
                
                projects.append(project_dict)
            
            # Sort projects by amount (descending) then by project_name (ascending) in Python
            # This avoids SQL column existence issues
            def sort_key(proj):
                amount = proj.get('amount') or proj.get('dime_cost') or proj.get('infrawatch_contract_price') or 0
                try:
                    amount = float(amount) if amount else 0
                except (ValueError, TypeError):
                    amount = 0
                project_name = str(proj.get('project_name', '')).lower()
                return (-amount, project_name)  # Negative for descending amount
            
            projects.sort(key=sort_key)
            
            # Apply pagination after sorting
            paginated_projects = projects[offset:offset + limit]
            
            return JSONResponse(content={
                "success": True,
                "projects": paginated_projects,
                "total": total,
                "page": page,
                "limit": limit,
                "total_pages": total_pages
            })
            
        finally:
            conn.close()
            
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        return JSONResponse(
            content={
                "success": False,
                "error": error_msg,
                "projects": [],
                "total": 0,
                "total_pages": 0
            },
            status_code=500
        )

@app.get("/api/integrated/projects/csv")
async def export_integrated_projects_csv(
    project_name: Optional[str] = Query(default=None, description="Filter by project name/title"),
    contractor: Optional[str] = Query(default=None, description="Filter by contractor name"),
    green: bool = Query(default=False, description="Filter for green/clean projects"),
    dpwh_all: bool = Query(default=False, description="Filter for ALL Annex A-5 projects (w/ flags)")
) -> Response:
    """Export integrated projects to CSV with filtering (all pages)"""
    try:
        import csv
        import io
        
        # Get the parquet file path (use absolute path)
        base_dir = Path(__file__).parent.absolute()
        parquet_file = base_dir / "data" / "parquet" / "integrated_projects.parquet"
        
        # --- GREEN / DPWH ALL (ANNEX A-5 2026) CSV LOGIC ---
        if green or dpwh_all:
            import json
            import re
            
            # 1. Load 2026 Data (Annex A-5)
            json_path = base_dir / "static" / "data" / "budget_amendments_2026.json"
            if not json_path.exists():
                return JSONResponse({"error": "2026 Data not found"}, status_code=404)
            
            with open(json_path, 'r', encoding='utf-8') as f:
                data_2026 = json.load(f)
            
            # Combine projects and line_items, filter for Annex A-5
            raw_items = data_2026.get('projects', []) + data_2026.get('line_items', [])
            annex_a5_items = [
                item for item in raw_items 
                if item.get('source_sheet') == 'Annex A-5'
            ]
            
            def _coerce_amount(raw_amount: Any) -> Optional[float]:
                if raw_amount is None:
                    return None
                try:
                    return float(raw_amount)
                except (TypeError, ValueError):
                    return None

            # 2. Load Bad IDs (Resurrected & Flagged)
            resurrected_ids = set()
            flagged_ids = set()
            historical_amounts_by_pid: Dict[str, List[float]] = {}
            flagged_meta_by_pid: Dict[str, Dict[str, Any]] = {}
            
            # Resurrected
            res_path = base_dir / "static" / "data" / "resurrected_projects_dpwh.json"
            if res_path.exists():
                with open(res_path, 'r', encoding='utf-8') as f:
                    res_data = json.load(f)
                    for match in res_data.get('matches', []):
                        y2026 = match.get('year_2026') or {}
                        pid = y2026.get('id')
                        if pid:
                            pid_str = str(pid)
                            resurrected_ids.add(pid_str)
                            hist = match.get('historical')
                            if isinstance(hist, dict):
                                amt = _coerce_amount(hist.get('amount'))
                                if amt:
                                    historical_amounts_by_pid.setdefault(pid_str, []).append(amt)
                            elif isinstance(hist, list):
                                for entry in hist:
                                    if isinstance(entry, dict):
                                        amt = _coerce_amount(entry.get('amount'))
                                        if amt:
                                            historical_amounts_by_pid.setdefault(pid_str, []).append(amt)
                        
            # Flagged
            flagged_path = base_dir / "static" / "data" / "flagged_amount_projects_2026.json"
            if flagged_path.exists():
                with open(flagged_path, 'r', encoding='utf-8') as f:
                    flagged_list = json.load(f)
                    for item in flagged_list:
                        if not isinstance(item, dict):
                            continue
                        if str(item.get('source_sheet') or '').strip() != 'Annex A-5':
                            continue
                        if str(item.get('year') or '').strip() != '2026':
                            continue
                        pid = item.get('id')
                        if not pid:
                            continue
                        pid_str = str(pid)
                        if item.get('is_flagged') is True:
                            flagged_ids.add(pid_str)
                        flagged_meta_by_pid[pid_str] = item

            # Aggregate lines are typically region-only headers or broad rollups (often very high amount).
            aggregate_pattern = re.compile(
                r'^(?:[a-zA-Z0-9]+\.)?\s*(?:National Capital Region|Region\s+[IVX]+|Cordillera Administrative Region|Bangsamoro Autonomous Region|MIMAROPA|CALABARZON|SOCCSKSARGEN|Zamboanga Peninsula|Northern Mindanao|Davao Region|Caraga|Eastern Visayas|Central Visayas|Western Visayas|Bicol Region|Central Luzon|Cagayan Valley|Ilocos Region).*$',
                re.IGNORECASE
            )

            def _is_aggregate_row(title: str, amount: Optional[float]) -> bool:
                title = (title or "").strip()
                if not title:
                    return True
                if aggregate_pattern.match(title):
                    return True
                if amount is not None and amount >= 300_000_000:
                    if len(title) <= 80 and len(title.split()) <= 10:
                        return True
                return False
            
            # 3. Filter Projects (Green vs DPWH All)
            projects = []
            for item in annex_a5_items:
                pid = str(item.get('id'))
                p_name = item.get('name') or item.get('description') or ''
                amount = _coerce_amount(item.get('final_amount') or item.get('original_amount') or 0)

                # Search filter
                if project_name and project_name.lower() not in p_name.lower():
                    continue

                # Contractor filter (best-effort; Annex A-5 may not always have contractors)
                contractor_name = item.get('contractor') or 'N/A'
                if contractor and contractor.lower() not in str(contractor_name).lower():
                    continue

                is_resurrected = pid in resurrected_ids
                is_flagged = pid in flagged_ids
                is_aggregate = _is_aggregate_row(p_name, amount)

                # For Green: exclude flagged/resurrected/aggregate
                if green and (is_resurrected or is_flagged or is_aggregate):
                    continue

                # For DPWH All: include all Annex A-5, but remove aggregate headers/rollups
                if dpwh_all and is_aggregate:
                    continue

                status_labels = []
                if is_resurrected:
                    status_labels.append("Resurrected")
                if is_flagged:
                    status_labels.append("Flagged Amount")
                if not status_labels:
                    status_labels.append("Lower Cost")
                status = ", ".join(status_labels)

                baseline_amounts = historical_amounts_by_pid.get(pid) or []
                baseline_avg = sum(baseline_amounts) / len(baseline_amounts) if baseline_amounts else None
                baseline_samples = len(baseline_amounts)

                flagged_meta = flagged_meta_by_pid.get(pid) or {}
                threshold = _coerce_amount((flagged_meta.get('subcategory_stats') or {}).get('threshold'))
                distance_km = _coerce_amount(flagged_meta.get('distance_km'))

                baseline_kind = None
                if baseline_avg and amount is not None:
                    baseline_kind = 'historical_amount'
                    baseline_amount = baseline_avg
                elif threshold and distance_km and amount is not None:
                    baseline_kind = 'cost_per_km_threshold'
                    baseline_amount = float(threshold) * float(distance_km)
                else:
                    baseline_amount = baseline_avg

                over_under_amount = (amount - baseline_amount) if (baseline_amount and amount is not None) else None
                over_under_pct = (over_under_amount / baseline_amount) if (baseline_amount and over_under_amount is not None) else None

                projects.append({
                    'flag': 'GREEN' if status == "Lower Cost" else 'RED',
                    'status': status,
                    'project_name': p_name,
                    'amount': amount,
                    'baseline_kind': baseline_kind,
                    'baseline_amount': baseline_amount,
                    'baseline_samples': baseline_samples,
                    'over_under_amount': over_under_amount,
                    'over_under_pct': over_under_pct,
                    'contractor_name': contractor_name,
                    'source': 'Annex A-5 (2026)',
                    'location': (
                        item.get('location', {}).get('province') or
                        item.get('district') or
                        item.get('location', {}).get('region') or
                        item.get('hierarchy', {}).get('region') or
                        'Unknown'
                    )
                })

            # 4. Generate CSV
            output = io.StringIO()
            writer = csv.writer(output)
            if dpwh_all and not green:
                writer.writerow(['Flag', 'Status', 'Project Name', 'Amount', 'Baseline Amount', 'Baseline Samples', 'Over/Under Amount', 'Over/Under %', 'Contractor', 'Source', 'Location'])
                for p in projects:
                    pct = p.get('over_under_pct')
                    writer.writerow([
                        p['flag'],
                        p['status'],
                        p['project_name'],
                        p['amount'],
                        p.get('baseline_amount'),
                        p.get('baseline_samples'),
                        p.get('over_under_amount'),
                        (pct * 100.0) if isinstance(pct, (int, float)) else None,
                        p['contractor_name'],
                        p['source'],
                        p['location'],
                    ])
            else:
                writer.writerow(['Project Name', 'Amount', 'Contractor', 'Source', 'Location'])
                for p in projects:
                    writer.writerow([p['project_name'], p['amount'], p['contractor_name'], p['source'], p['location']])
            
            return Response(
                content=output.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=green_projects_dpwh_2026.csv"}
            )
        # --------------------------------

        if not parquet_file.exists():
            return JSONResponse(
                content={
                    "success": False,
                    "error": f"Parquet file not found: {parquet_file}"
                },
                status_code=404
            )
        
        # Connect to DuckDB
        conn = duckdb.connect()
        
        try:
            # Build WHERE clause with proper SQL escaping
            where_conditions = []
            
            def escape_sql_string(s: str) -> str:
                """Escape single quotes for SQL"""
                return s.replace("'", "''")
            
            if green:
                where_conditions.append("(flag_reason IS NULL OR flag_reason = '')")
                where_conditions.append("(historical_match IS NULL OR historical_match = '')")
            
            if project_name:
                escaped_name = escape_sql_string(project_name)
                where_conditions.append(
                    f"(project_name ILIKE '%{escaped_name}%' OR "
                    f"philgeps_award_title ILIKE '%{escaped_name}%' OR "
                    f"project_description ILIKE '%{escaped_name}%')"
                )
            
            if contractor:
                escaped_contractor = escape_sql_string(contractor)
                where_conditions.append(
                    f"(contractor_name ILIKE '%{escaped_contractor}%' OR "
                    f"philgeps_awardee_name ILIKE '%{escaped_contractor}%' OR "
                    f"organization_name ILIKE '%{escaped_contractor}%')"
                )
            
            where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
            
            # Convert path to string and escape single quotes
            parquet_path_str = str(parquet_file).replace("'", "''")
            
            # Get all projects (no pagination)
            select_query = f"""
                SELECT 
                    project_name,
                    project_description,
                    philgeps_award_title,
                    contractor_name,
                    philgeps_awardee_name,
                    organization_name,
                    amount,
                    contract_amount,
                    dime_cost,
                    infrawatch_contract_price,
                    source
                FROM read_parquet('{parquet_path_str}')
                WHERE {where_clause}
                ORDER BY 
                    COALESCE(amount, contract_amount, CAST(dime_cost AS DOUBLE), infrawatch_contract_price) DESC NULLS LAST,
                    project_name
            """
            
            # Execute query
            results = conn.execute(select_query).fetchall()
            columns = [desc[0] for desc in conn.description]
            
            # Create CSV in memory
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow(['Project Name', 'Contractor', 'Amount', 'Source'])
            
            # Write data rows
            for row in results:
                project_name_val = row[columns.index('project_name')] or row[columns.index('philgeps_award_title')] or row[columns.index('project_description')] or ''
                contractor_val = row[columns.index('contractor_name')] or row[columns.index('philgeps_awardee_name')] or row[columns.index('organization_name')] or ''
                amount_val = row[columns.index('amount')] or row[columns.index('contract_amount')] or row[columns.index('dime_cost')] or row[columns.index('infrawatch_contract_price')] or 0
                source_val = row[columns.index('source')] or ''
                
                # Format amount
                if amount_val:
                    try:
                        amount_formatted = f"{float(amount_val):,.2f}"
                    except (ValueError, TypeError):
                        amount_formatted = str(amount_val)
                else:
                    amount_formatted = ''
                
                writer.writerow([
                    str(project_name_val) if project_name_val else '',
                    str(contractor_val) if contractor_val else '',
                    amount_formatted,
                    str(source_val) if source_val else ''
                ])
            
            # Get CSV content
            csv_content = output.getvalue()
            output.close()
            
            # Generate filename with timestamp
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"integrated_projects_{timestamp}.csv"
            
            return Response(
                content=csv_content,
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}"
                }
            )
            
        finally:
            conn.close()
            
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        return JSONResponse(
            content={
                "success": False,
                "error": error_msg
            },
            status_code=500
        )

@app.get("/api/budget/files")
async def budget_list_files_api():
    """List uploaded Budget documents"""

@app.get("/api/pbc/gab-2026/sheets")
async def list_pbc_gab_2026_sheets() -> JSONResponse:
    # Try to load from cache first
    try:
        # Use absolute path based on script location (same pattern as other cache files)
        cache_file = os.path.join(os.path.dirname(__file__), "static", "data", "gab_2026_sheets.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    cache_data = json.load(f)
                    print(f"✅ [GAB 2026] sheets: loaded from cache ({len(cache_data.get('data', {}).get('sheets', []))} sheets)")
                    return JSONResponse(content=cache_data)
            except Exception as e:
                print(f"⚠️ [GAB 2026] Error loading cache, falling back to DB: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"⚠️ [GAB 2026] Cache file not found: {cache_file}, falling back to DB")
    except Exception as e:
        print(f"⚠️ [GAB 2026] Error checking cache file, falling back to DB: {e}")
        import traceback
        traceback.print_exc()
    
    # Fallback to database
    try:
        conn = await get_nep_db_connection()
    except Exception as e:
        print(f"💥 [GAB 2026] DB connection error: {e}")
        conn = None
    if not conn:
        print("💥 [GAB 2026] DB connection failed")
        return JSONResponse(status_code=500, content={"status": "error", "error": "DB connection failed"})
    try:
        try:
            rows = await conn.fetch("SELECT DISTINCT sheet_name FROM pbc_gab_2026_rows ORDER BY sheet_name")
            sheets = [r[0] for r in rows]
            print(f"✅ [GAB 2026] sheets: {len(sheets)} sheets found")
        except Exception as e:
            error_msg = str(e)
            print(f"💥 [GAB 2026] Error querying pbc_gab_2026_rows: {error_msg}")
            # Check if table doesn't exist
            if "does not exist" in error_msg or "relation" in error_msg.lower():
                print("⚠️ [GAB 2026] Table pbc_gab_2026_rows does not exist")
            # Table may not exist yet or other error; return empty list gracefully
            sheets = []
        return JSONResponse(content={"status": "ok", "data": {"sheets": sheets}})
    finally:
        if conn:
            await conn.close()

@app.get("/api/pbc/gab-2026/sheet")
async def get_pbc_gab_2026_sheet(name: str = Query(..., alias="name"), limit: int = 200) -> JSONResponse:
    # Try to load from cache first
    try:
        # Sanitize filename
        safe_filename = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_filename = safe_filename.replace(' ', '_')
        # Use absolute path based on script location (same pattern as other cache files)
        cache_file = os.path.join(os.path.dirname(__file__), "static", "data", "gab_2026_sheets", f"{safe_filename}.json")
        
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    cache_data = json.load(f)
                    # Apply limit if needed
                    if limit < 200 and cache_data.get('data', {}).get('rows'):
                        cache_data['data']['rows'] = cache_data['data']['rows'][:limit]
                    print(f"✅ [GAB 2026] sheet '{name}': loaded from cache ({len(cache_data.get('data', {}).get('rows', []))} rows)")
                    return JSONResponse(content=cache_data)
            except Exception as e:
                print(f"⚠️ [GAB 2026] Error loading cache, falling back to DB: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"⚠️ [GAB 2026] Cache file not found: {cache_file}, falling back to DB")
    except Exception as e:
        print(f"⚠️ [GAB 2026] Error checking cache file, falling back to DB: {e}")
        import traceback
        traceback.print_exc()
    
    # Fallback to database
    try:
        conn = await get_nep_db_connection()
    except Exception as e:
        print(f"💥 [GAB 2026] DB connection error: {e}")
        conn = None
    if not conn:
        print("💥 [GAB 2026] DB connection failed")
        return JSONResponse(status_code=500, content={"status": "error", "error": "DB connection failed"})
    try:
        try:
            rows = await conn.fetch(
                "SELECT row_index, data FROM pbc_gab_2026_rows WHERE sheet_name=$1 ORDER BY row_index LIMIT $2",
                name,
                limit,
            )
            data = [{"row_index": r[0], **(r[1] or {})} for r in rows]
            print(f"✅ [GAB 2026] sheet '{name}': {len(data)} rows")
        except Exception as e:
            error_msg = str(e)
            print(f"💥 [GAB 2026] Error querying sheet '{name}': {error_msg}")
            if "does not exist" in error_msg or "relation" in error_msg.lower():
                print("⚠️ [GAB 2026] Table pbc_gab_2026_rows does not exist")
            data = []
        return JSONResponse(content={"status": "ok", "data": {"rows": data}})
    finally:
        if conn:
            await conn.close()

@app.get("/api/pbc/gab-2026/headings")
async def get_pbc_gab_2026_headings() -> JSONResponse:
    try:
        conn = await get_nep_db_connection()
    except Exception:
        conn = None
    if not conn:
        return JSONResponse(status_code=500, content={"status": "error", "error": "DB connection failed"})
    try:
        # Fetch first sheet present in headings table
        rows = await conn.fetch(
            "SELECT sheet_name, label, data FROM pbc_gab_2026_headings ORDER BY sheet_name, id"
        )
        items = []
        for r in rows:
            items.append({"sheet_name": r[0], "label": r[1], "data": r[2] or {}})
        return JSONResponse(content={"status": "ok", "data": {"items": items}})
    except Exception:
        return JSONResponse(content={"status": "ok", "data": {"items": []}})
    finally:
        await conn.close()

@app.get("/api/pbc/gab-2026/headings_detail")
async def get_pbc_gab_2026_headings_detail() -> JSONResponse:
    # Try to load from cache first
    try:
        # Use absolute path based on script location (same pattern as other cache files)
        cache_file = os.path.join(os.path.dirname(__file__), "static", "data", "gab_2026_headings_detail.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    cache_data = json.load(f)
                    print(f"✅ [GAB 2026] headings_detail: loaded from cache ({len(cache_data.get('data', {}).get('items', []))} items)")
                    return JSONResponse(content=cache_data)
            except Exception as e:
                print(f"⚠️ [GAB 2026] Error loading cache, falling back to DB: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"⚠️ [GAB 2026] Cache file not found: {cache_file}, falling back to DB")
    except Exception as e:
        print(f"⚠️ [GAB 2026] Error checking cache file, falling back to DB: {e}")
        import traceback
        traceback.print_exc()
    
    # Fallback to database
    try:
        conn = await get_nep_db_connection()
    except Exception as e:
        print(f"💥 [GAB 2026] DB connection error: {e}")
        conn = None
    if not conn:
        print("💥 [GAB 2026] DB connection failed")
        return JSONResponse(status_code=500, content={"status": "error", "error": "DB connection failed"})
    try:
        rows = await conn.fetch(
            """
            SELECT sheet_name, label, original, hgab, delta
            FROM pbc_gab_2026_headings_detail
            WHERE sheet_name = (SELECT sheet_name FROM pbc_gab_2026_headings_detail LIMIT 1)
            ORDER BY COALESCE(hgab, 0) DESC, label ASC
            """
        )
        items = []
        for r in rows:
            items.append({
                "sheet_name": r[0],
                "label": r[1],
                "original": float(r[2]) if r[2] is not None else None,
                "hgab": float(r[3]) if r[3] is not None else None,
                "delta": float(r[4]) if r[4] is not None else None,
            })
        print(f"✅ [GAB 2026] headings_detail: {len(items)} items")
        return JSONResponse(content={"status": "ok", "data": {"items": items}})
    except Exception as e:
        error_msg = str(e)
        print(f"💥 [GAB 2026] Error querying pbc_gab_2026_headings_detail: {error_msg}")
        # Check if table doesn't exist
        if "does not exist" in error_msg or "relation" in error_msg.lower():
            print("⚠️ [GAB 2026] Table pbc_gab_2026_headings_detail does not exist")
        return JSONResponse(content={"status": "ok", "data": {"items": []}})
    finally:
        if conn:
            await conn.close()

@app.get("/api/budget/total-items/count")
async def budget_total_items_count_api():
    """Get total items count - no authentication required"""
    try:
        result = await get_budget_total_items_count()
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/duplicates")
async def budget_duplicates_api(year: str = "2025", page: int = 1, limit: int = 10, sort_by: str = "calculated_score", sort_order: str = "DESC"):
    """Get potential budget duplicates using 9-column matching system with pagination - no authentication required"""
    try:
        from budget_postgres_client import get_budget_scored_duplicates, get_budget_duplicates_total_count, convert_decimals
        
        # Calculate offset for pagination
        offset = (page - 1) * limit
        
        # Fetch paginated duplicates
        duplicates = await get_budget_scored_duplicates(year, limit, offset, sort_by, sort_order)
        
        # Get total count for pagination
        total_items_result = await get_budget_duplicates_total_count(year)
        total_items = total_items_result.get("count", 0)
        total_pages = max(1, (total_items + limit - 1) // limit)
        
        # Ensure all data is JSON serializable
        converted_duplicates = convert_decimals(duplicates)
        
        response_data = {
            "success": True,
            "duplicates": converted_duplicates,
            "total_items": total_items,
            "total_pages": total_pages,
            "current_page": page,
            "limit": limit,
            "year": year
        }
        
        return JSONResponse(response_data)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/duplicates/count")
async def budget_duplicates_count_api(year: str = "2025"):
    """Get budget duplicates count - no authentication required"""
    try:
        from budget_postgres_client import get_budget_duplicates_count
        result = await get_budget_duplicates_count(year)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/budget/resurrected-projects")
async def budget_resurrected_projects_api():
    """Get resurrected projects data (DPWH projects in 2026 that existed in previous years)"""
    try:
        json_path = Path('static/data/resurrected_projects_dpwh.json')
        if not json_path.exists():
            return JSONResponse({"success": False, "error": "Resurrected projects data not available. Please run the detection script first."}, status_code=404)
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return JSONResponse({"success": True, **data})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

def _categorize_road_safety_facilities(name: str, name_lower: str) -> list:
    """Categorize road safety facilities into subcategories and handle composite projects.
    Returns a list of subcategories found in the project name.
    Handles composite projects like "Road Safety Facilities (Pedestrian Overpass, Barrier)" 
    by counting each component separately.
    
    Based on actual data analysis, categories include:
    - Roadway Lighting (most common: 170 instances)
    - Pavement Markings (46 instances)
    - Road Signs (16 instances)
    - Guardrails (15 instances)
    - Off-carriageway Improvement (8 instances)
    - Traffic Signals (3 instances)
    - Pedestrian Overpass (39 standalone, 1 composite)
    - Solar LED Streetlights (14 instances)
    - Barrier (1 instance)
    """
    import re
    subcategories = []
    
    # Check for composite projects with parentheses
    # Pattern: "Road Safety Facilities (Item1, Item2, Item3)" or "Installation/Application of Road Safety Facilities (Item1, Item2)"
    composite_pattern = r'(?:road\s+safety\s+facilities|installation/application\s+of\s+road\s+safety\s+facilities)\s*\(([^)]+)\)'
    composite_match = re.search(composite_pattern, name_lower)
    
    if composite_match:
        # Split by comma and process each component
        components = [c.strip() for c in composite_match.group(1).split(',')]
        for component in components:
            component_lower = component.lower()
            
            # Handle composite components like "Street lights and Road Signs"
            if ' and ' in component_lower:
                # Split by "and" and process each part
                parts = [p.strip() for p in component_lower.split(' and ')]
                for part in parts:
                    subcategories.extend(_categorize_single_component(part))
            else:
                subcategories.extend(_categorize_single_component(component_lower))
    else:
        # Single project - check for keywords in the full name
        # Check for specific patterns first (more specific to less specific)
        
        # Solar LED Streetlights (specific pattern)
        if 'solar led streetlight' in name_lower or 'solar led street light' in name_lower:
            subcategories.append('Solar LED Streetlights')
        # Solar Street Lights
        elif 'solar street light' in name_lower:
            subcategories.append('Solar Street Lights')
        # Roadway Lighting
        elif 'roadway lighting' in name_lower:
            subcategories.append('Roadway Lighting')
        # General lighting
        elif any(kw in name_lower for kw in ['lighting', 'streetlight', 'street light', 'led']):
            subcategories.append('Lighting')
        
        # Guardrails
        if 'guardrail' in name_lower:
            subcategories.append('Guardrails')
        # Barrier (separate from guardrails)
        if 'barrier' in name_lower and 'guardrail' not in name_lower:
            subcategories.append('Barrier')
        
        # Traffic Signals (more specific than signs)
        if 'traffic signal' in name_lower:
            subcategories.append('Traffic Signals')
        # Road Signs
        elif 'road sign' in name_lower or ('sign' in name_lower and 'road' in name_lower and 'signal' not in name_lower):
            subcategories.append('Road Signs')
        
        # Pavement Markings
        if 'pavement marking' in name_lower or ('marking' in name_lower and 'pavement' in name_lower):
            subcategories.append('Pavement Markings')
        
        # Pedestrian Overpass
        if 'pedestrian overpass' in name_lower or ('overpass' in name_lower and 'pedestrian' in name_lower):
            subcategories.append('Pedestrian Overpass')
        
        # Off-carriageway Improvement (case-insensitive)
        if 'off-carriageway improvement' in name_lower or 'off-carriageway improvement' in name_lower:
            subcategories.append('Off-carriageway Improvement')
        
        # If no specific subcategory found, mark as generic
        if not subcategories:
            subcategories.append('Road Safety Facilities')
    
    # Remove duplicates while preserving order
    seen = set()
    unique_subcategories = []
    for subcat in subcategories:
        if subcat and subcat not in seen:  # Ensure subcat is not empty/None
            seen.add(subcat)
            unique_subcategories.append(subcat)
    
    # CRITICAL: Ensure we always return at least one subcategory
    # This should never happen, but defensive programming
    if not unique_subcategories:
        unique_subcategories.append('Road Safety Facilities')
    
    return unique_subcategories

def _categorize_single_component(component_lower: str) -> list:
    """Categorize a single component string into subcategories."""
    subcategories = []
    
    # Solar LED Streetlights (most specific first)
    if 'solar led streetlight' in component_lower or 'solar led street light' in component_lower:
        subcategories.append('Solar LED Streetlights')
    # Solar Street Lights
    elif 'solar street light' in component_lower:
        subcategories.append('Solar Street Lights')
    # Roadway Lighting
    elif 'roadway lighting' in component_lower:
        subcategories.append('Roadway Lighting')
    # General lighting
    elif any(kw in component_lower for kw in ['lighting', 'streetlight', 'street light', 'led']):
        subcategories.append('Lighting')
    
    # Guardrails
    if 'guardrail' in component_lower:
        subcategories.append('Guardrails')
    # Barrier (separate from guardrails)
    if 'barrier' in component_lower and 'guardrail' not in component_lower:
        subcategories.append('Barrier')
    
    # Traffic Signals (more specific than signs)
    if 'traffic signal' in component_lower:
        subcategories.append('Traffic Signals')
    # Road Signs
    elif 'road sign' in component_lower or ('sign' in component_lower and 'road' in component_lower and 'signal' not in component_lower):
        subcategories.append('Road Signs')
    
    # Pavement Markings
    if 'pavement marking' in component_lower or ('marking' in component_lower and 'pavement' in component_lower):
        subcategories.append('Pavement Markings')
    
    # Pedestrian Overpass
    if 'pedestrian overpass' in component_lower or ('overpass' in component_lower and 'pedestrian' in component_lower):
        subcategories.append('Pedestrian Overpass')
    
    # Off-carriageway Improvement (case-insensitive)
    if 'off-carriageway improvement' in component_lower or 'off-carriageway improvement' in component_lower:
        subcategories.append('Off-carriageway Improvement')
    
    # If no match, use the component name as-is (capitalized)
    if not subcategories:
        # Capitalize first letter of each word
        if component_lower.strip():  # Only add if component is not empty
            subcategories.append(component_lower.title())
        else:
            # Fallback if component is empty
            subcategories.append('Road Safety Facilities')
    
    # CRITICAL: Ensure we always return at least one subcategory
    if not subcategories:
        subcategories.append('Road Safety Facilities')
    
    return subcategories

def _is_new_installation(name: str, name_lower: str) -> bool:
    """Determine if a road safety facility is a new installation or maintenance/upgrade.
    Returns True for new installations, False for maintenance/upgrade.
    """
    # Keywords indicating maintenance/upgrade
    maintenance_keywords = [
        'maintenance', 'rehabilitation', 'repair', 'upgrade', 'upgrading',
        'improvement', 'replacement', 'rehab', 'restoration', 'renovation'
    ]
    
    # Keywords indicating new installation
    new_keywords = [
        'installation', 'install', 'construction', 'construct', 'new',
        'provision', 'provide', 'establishment', 'establish'
    ]
    
    # Check for maintenance keywords first (more specific)
    has_maintenance = any(keyword in name_lower for keyword in maintenance_keywords)
    has_new = any(keyword in name_lower for keyword in new_keywords)
    
    # If it has maintenance keywords, it's not new
    if has_maintenance:
        return False
    
    # If it has new keywords and no maintenance, it's new
    if has_new:
        return True
    
    # Default: if unclear, assume it's new (installation implies new)
    return True

def _categorize_road_work_type(name: str, name_lower: str) -> list:
    """Categorize road work type based on project name.
    Returns a list of work type categories (can be multiple for composite projects).
    Returns empty list if no specific category is found.
    
    Categories include:
    - Asphalt Overlay
    - Concreting
    - Rehabilitation
    - Reconstruction
    - Construction
    - Improvement
    - Widening
    - Preventive Maintenance
    - Upgrading
    - Restoration
    - Resurfacing
    - Road Reblocking
    - Drainage
    - Slope Protection
    - Bituminous Pavement
    - Paving
    """
    import re
    
    work_types = []
    
    # Check patterns in order of specificity (most specific first)
    work_type_patterns = [
        # Road Reblocking (specific pattern)
        (r'reblocking|road\s+reblocking', 'Road Reblocking'),
        
        # Asphalt Overlay
        (r'asphalt\s+overlay|item\s+304(?:\s*[-a-z])?|\basphalt\s+overlay\b', 'Asphalt Overlay'),
        
        # Concreting
        (r'concreting\s+of|concrete\s+pavement|pccp|portland\s+cement\s+concrete\s+pavement|item\s+311(?:\s*[-a-z])?', 'Concreting'),
        
        # Preventive Maintenance (specific pattern)
        (r'preventive\s+maintenance|periodic\s+maintenance|routine\s+maintenance', 'Preventive Maintenance'),
        
        # Widening
        (r'widening\s+of|road\s+widening|widening\s+with|widening\s+and|\bwidening\b', 'Widening'),
        
        # Rehabilitation
        (r'rehabilitation\s+of|rehabilitation/|rehabilitation\s+with|\brehabilitation\b', 'Rehabilitation'),
        
        # Reconstruction
        (r'reconstruction\s+of|reconstruction/', 'Reconstruction'),
        
        # Construction
        (r'construction\s+of', 'Construction'),
        
        # Improvement
        (r'improvement\s+of|road\s+improvement', 'Improvement'),
        
        # Upgrading
        (r'upgrading\s+of|upgrading/', 'Upgrading'),
        
        # Restoration
        (r'restoration\s+of', 'Restoration'),
        
        # Resurfacing
        (r'resurfacing', 'Resurfacing'),
        
        # Drainage
        (r'cross\s+drainage|drainage\s+structure|drainage\s+along', 'Drainage'),
        
        # Slope Protection
        (r'slope\s+protection|retaining\s+wall|riprap', 'Slope Protection'),
        
        # Bituminous Pavement
        (r'bituminous\s+pavement|bituminous\s+concrete', 'Bituminous Pavement'),
        
        # Paving
        (r'paving\s+of', 'Paving'),
    ]
    
    # Check all patterns to find multiple work types (for composite projects)
    for pattern, work_type in work_type_patterns:
        if re.search(pattern, name_lower, re.IGNORECASE):
            if work_type not in work_types:  # Avoid duplicates
                work_types.append(work_type)
    
    # Return list of work types (can be empty, single, or multiple)
    return work_types

def _is_new_construction(work_types: list, name: str, name_lower: str) -> bool:
    """Determine if a road project is new construction or maintenance/upgrade.
    Returns True for new construction, False for maintenance/upgrade.
    
    Rules:
    - If no work type is specified, it's automatically new construction
    - Work types that indicate new construction: Construction, Widening (new), Improvement (new)
    - Work types that indicate maintenance: Rehabilitation, Reconstruction, Asphalt Overlay,
      Preventive Maintenance, Road Reblocking, Resurfacing, Restoration, Upgrading, Concreting
    """
    # If no work types, it's automatically new construction
    if not work_types or len(work_types) == 0:
        return True
    
    # Maintenance/upgrade work types (if any of these are present, it's maintenance)
    maintenance_keywords = [
        'rehabilitation', 'reconstruction', 'asphalt overlay', 'preventive maintenance',
        'road reblocking', 'reblocking', 'resurfacing', 'restoration', 'upgrading',
        'concreting', 'repair', 'maintenance', 'restoration'
    ]
    
    # Check if any work type indicates maintenance
    for work_type in work_types:
        work_type_lower = work_type.lower() if work_type else ''
        if any(keyword in work_type_lower for keyword in maintenance_keywords):
            return False
    
    # Check name for additional maintenance indicators
    maintenance_name_patterns = [
        r'rehabilitation', r'reconstruction', r'asphalt\s+overlay', r'preventive\s+maintenance',
        r'reblocking', r'resurfacing', r'restoration', r'upgrading', r'repair', r'maintenance'
    ]
    import re
    for pattern in maintenance_name_patterns:
        if re.search(pattern, name_lower, re.IGNORECASE):
            return False
    
    # If no maintenance indicators found, assume new construction
    # (Construction, Widening, Improvement without maintenance context)
    return True

def _is_major_road(name: str, chainage_ranges: list) -> bool:
    """Determine if a road project is a major road (formerly "national road")
    Classification rules (in order):
    1. Highways (highway, hiway, hi-way) are automatically major roads
    2. Anything with "-" (dash) indicates cross-province or cross-municipality, so major road
    3. Any province, municipality, city named roads are major roads
    4. Any region named roads are major roads
    5. Those who can't be classified as major road is a minor road
    
    NO distance or segments logic is used.
    """
    if not name:
        return False
    
    name_lower = name.lower()
    
    # Rule 1: Highways are automatically major roads
    if any(term in name_lower for term in ['highway', 'hiway', 'hi-way']):
        return True
    
    # Rule 2: Anything with "-" (dash) indicates cross-province or cross-municipality
    # Extract road name part (before chainage notation)
    import re
    road_name_part = re.split(r'\s*-\s*k\d+|chainage', name_lower, maxsplit=1, flags=re.IGNORECASE)[0]
    
    # Check for dash/hyphen pattern (but exclude chainage notation)
    # Pattern: Location1-Location2 (min 3 chars each side, not just numbers)
    dash_pattern = r'([a-záéíóúñ\s]{3,})[\s]*[-–—][\s]*([a-záéíóúñ\s]{3,})'
    matches = re.finditer(dash_pattern, road_name_part)
    for match in matches:
        part1 = match.group(1).strip()
        part2 = match.group(2).strip()
        
        # Skip if either looks like a number or chainage notation
        if re.match(r'^[\d\s\+\-\(\)]+$', part1) or re.match(r'^[\d\s\+\-\(\)]+$', part2):
            continue
        
        # Remove common road terms
        part1 = re.sub(r'\s+(road|highway|national|rd|hway|hiway|jct|junction)\s*$', '', part1).strip()
        part2 = re.sub(r'\s+(road|highway|national|rd|hway|hiway|jct|junction)\s*$', '', part2).strip()
        
        # If both parts are at least 3 chars, it's likely cross-province/municipality
        if len(part1) >= 3 and len(part2) >= 3:
            return True
    
    # Rule 3 & 4: Check for province, municipality, city, or region names
    # Load comprehensive list of Philippine provinces, regions, cities, and municipalities
    philippine_provinces = [
        'abra', 'agusan del norte', 'agusan del sur', 'aklan', 'albay', 'antique', 'apayao', 'aurora',
        'basilan', 'bataan', 'batanes', 'batangas', 'benguet', 'biliran', 'bohol', 'bukidnon',
        'bulacan', 'cagayan', 'camarines norte', 'camarines sur', 'camiguin', 'capiz', 'catanduanes',
        'cavite', 'cebu', 'compostela valley', 'cotabato', 'davao del norte', 'davao del sur',
        'davao occidental', 'davao oriental', 'dinagat islands', 'eastern samar', 'guimaras',
        'ifugao', 'ilocos norte', 'ilocos sur', 'iloilo', 'isabela', 'kalinga', 'la union',
        'laguna', 'lanao del norte', 'lanao del sur', 'leyte', 'maguindanao', 'marinduque',
        'masbate', 'misamis occidental', 'misamis oriental', 'mountain province',
        'negros occidental', 'negros oriental', 'northern samar',
        'nueva ecija', 'nueva vizcaya', 'occidental mindoro', 'oriental mindoro', 'palawan',
        'pampanga', 'pangasinan', 'quezon', 'quirino', 'rizal', 'romblon', 'samar', 'sarangani',
        'siquijor', 'sorsogon', 'south cotabato', 'southern leyte', 'sultan kudarat', 'sulu',
        'surigao del norte', 'surigao del sur', 'tarlac', 'tawi-tawi', 'zambales',
        'zamboanga del norte', 'zamboanga del sur', 'zamboanga sibugay'
    ]
    
    philippine_regions = [
        'region i', 'region ii', 'region iii', 'region iv-a', 'region iv-b', 'region v',
        'region vi', 'region vii', 'region viii', 'region ix', 'region x', 'region xi',
        'region xii', 'region xiii', 'ncr', 'national capital region', 'cordillera',
        'car', 'bicol', 'cagayan valley', 'central luzon', 'calabarzon', 'mimaropa',
        'western visayas', 'central visayas', 'eastern visayas', 'zamboanga peninsula',
        'northern mindanao', 'davao', 'soccsksargen', 'caraga', 'bangsamoro', 'armm'
    ]
    
    # Major cities (partial list - can be expanded)
    major_cities = [
        'manila', 'cebu', 'davao', 'iloilo', 'baguio', 'quezon city', 'caloocan',
        'las piñas', 'makati', 'malabon', 'mandaluyong', 'marikina', 'muntinlupa',
        'navotas', 'parañaque', 'pasay', 'pasig', 'san juan', 'taguig', 'valenzuela',
        'bacoor', 'dasmarinas', 'dasmariñas', 'calamba', 'san pedro', 'biñan',
        'santa rosa', 'cabuyao', 'los baños', 'tacloban', 'ormoc', 'dumaguete',
        'bacolod', 'san carlos', 'silay', 'talisay', 'victorias', 'cadiz', 'roxas'
    ]
    
    # Check if road name contains province, region, or major city name
    for province in philippine_provinces:
        if province in name_lower:
            return True
    
    for region in philippine_regions:
        if region in name_lower:
            return True
    
    for city in major_cities:
        if city in name_lower:
            return True
    
    # Rule 5: If none of the above match, it's a minor road
    return False
    name_lower = name.lower()
    
    # Check for explicit "national" keyword
    if 'national' in name_lower:
        return True
    
    # Check for "highway" keyword - almost always indicates national road
    if 'highway' in name_lower:
        return True
    
    # Common Philippine provinces, cities, and regions (partial list - can be expanded)
    # These are common in national road names
    major_locations = [
        'manila', 'cebu', 'davao', 'iloilo', 'baguio', 'quezon', 'laguna', 'cavite',
        'bulacan', 'pampanga', 'bataan', 'nueva ecija', 'tarlac', 'pangasinan',
        'batangas', 'rizal', 'antipolo', 'caloocan', 'las piñas', 'makati', 'malabon',
        'mandaluyong', 'marikina', 'muntinlupa', 'navotas', 'parañaque', 'pasay',
        'pasig', 'pateros', 'san juan', 'taguig', 'valenzuela', 'bacoor', 'dasmarinas', 'dasmariñas',
        'calamba', 'san pedro', 'biñan', 'santa rosa', 'cabuyao', 'los baños',
        'bay', 'calauan', 'liliw', 'magdalena', 'pagsanjan', 'paete', 'pila',
        'riizal', 'victoria', 'nagcarlan', 'lumban', 'kalayaan', 'cavinti',
        'pila', 'siniloan', 'famy', 'mabitac', 'pangil', 'pakil', 'paete',
        'kalayaan', 'lumban', 'cavinti', 'luisiana', 'majayjay', 'liliw',
        'magdalena', 'pagsanjan', 'pila', 'riizal', 'victoria', 'nagcarlan',
        'zamboanga', 'cagayan', 'isabela', 'nueva vizcaya', 'quirino', 'aurora',
        'bataan', 'bataan', 'pampanga', 'tarlac', 'pangasinan', 'la union',
        'ilocos sur', 'ilocos norte', 'ilocos', 'abra', 'apayao', 'benguet', 'ifugao',
        'kalinga', 'mountain province', 'albay', 'camarines norte', 'camarines sur',
        'catanduanes', 'masbate', 'sorsogon', 'aklan', 'antique', 'capiz', 'guimaras',
        'negros occidental', 'negros oriental', 'bohol', 'cebu', 'leyte', 'southern leyte',
        'eastern samar', 'northern samar', 'samar', 'biliran', 'zamboanga del norte',
        'zamboanga del sur', 'zamboanga sibugay', 'bukidnon', 'malaybalay', 'camiguin', 'lanao del norte',
        'misamis occidental', 'misamis oriental', 'davao del norte', 'davao del sur',
        'davao oriental', 'davao de oro', 'davao occidental', 'compostela valley',
        'south cotabato', 'north cotabato', 'sultan kudarat', 'sarangani', 'cotabato',
        'agusan del norte', 'agusan del sur', 'agusan', 'surigao del norte', 'surigao del sur',
        'dinagat islands', 'basilan', 'lanao del sur', 'maguindanao', 'sulu', 'tawi-tawi',
        'roxas', 'toledo', 'infanta', 'dumaguete', 'north'
    ]
    
    # Check for cross-municipality/city/province roads (e.g., "Bacoor-Dasmariñas", "Pangasinan-Tarlac", "City1 to City2")
    # These are almost always national roads
    import re
    
    # Extract the road name part (before chainage notation)
    # Chainage typically starts with "K" or "Chainage", so split there
    road_name_part = re.split(r'\s*-\s*k\d+|chainage', name_lower, maxsplit=1, flags=re.IGNORECASE)[0]
    
    # Pattern: City1-City2, City1–City2 (en dash), City1 to City2, City1/City2
    # But exclude matches that are just numbers or chainage notation
    cross_municipality_patterns = [
        r'([a-záéíóúñ\s]{3,})[\s]*[-–—][\s]*([a-záéíóúñ\s]{3,})',  # hyphen, en dash, em dash (min 3 chars each)
        r'([a-záéíóúñ\s]{3,})[\s]+to[\s]+([a-záéíóúñ\s]{3,})',  # "to" separator (min 3 chars each)
        r'([a-záéíóúñ\s]{3,})[\s]*/[\s]*([a-záéíóúñ\s]{3,})',  # slash separator (min 3 chars each)
    ]
    
    for pattern in cross_municipality_patterns:
        matches = re.finditer(pattern, road_name_part)
        for match in matches:
            city1 = match.group(1).strip()
            city2 = match.group(2).strip()
            
            # Skip if either looks like a number or chainage notation
            if re.match(r'^[\d\s\+\-\(\)]+$', city1) or re.match(r'^[\d\s\+\-\(\)]+$', city2):
                continue
            
            # Remove common road terms that might be in the name
            city1 = re.sub(r'\s+(road|highway|national|rd|hway|hiway|jct|junction)\s*$', '', city1).strip()
            city2 = re.sub(r'\s+(road|highway|national|rd|hway|hiway|jct|junction)\s*$', '', city2).strip()
            
            # Skip if too short after cleaning
            if len(city1) < 3 or len(city2) < 3:
                continue
            
            # Check if both cities/provinces are in major locations
            city1_match = any(loc in city1 or city1 in loc for loc in major_locations)
            city2_match = any(loc in city2 or city2 in loc for loc in major_locations)
            
            # If both match major locations, it's a cross-province/municipality road = national road
            if city1_match and city2_match:
                return True  # Cross-province/municipality road = national road
    
    # Check if name contains major location names (indicating inter-city/province roads)
    contains_major_location = any(loc in name_lower for loc in major_locations)
    
    # Check for highway designations that typically indicate national roads
    highway_indicators = ['maharlika', 'andaya', 'pan-philippine', 'philippine-japan', 'jica']
    is_highway = any(indicator in name_lower for indicator in highway_indicators)
    
    # National roads are typically longer (but not always - some segments are short)
    # If it's a longer road (> 1km) with location names, it's likely national
    # If it's explicitly a highway, it's national
    # If it has "national" in name, it's national
    if is_highway:
        return True
    
    # If it contains major location names, it's likely a national road (regardless of length)
    # Roads named after major provinces/cities are national roads
    if contains_major_location:
        return True
    
    # Very long roads (> 5km) are likely national roads
    if distance_km > 5.0:
        return True
    
    # Secondary roads are typically very short (< 1km) and don't contain major location names
    # If it's short and doesn't have major locations, it's secondary (return False)
    return False

@app.get("/api/budget/roads-cost-analysis")
async def budget_roads_cost_analysis_api(year: str = Query("2026", description="Year to filter by (2020-2026)")):
    """Get road infrastructure projects (roads, bridges, traffic signs, etc.) with chainage, calculate distance and cost per km from budget amendments data"""
    try:
        # For 2026: Check for pre-generated cache first
        if year == "2026":
            cache_file = Path(__file__).parent / "static" / "data" / "api_cache" / "roads_cost_analysis_cache.json"
            if cache_file.exists():
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                    if cache_data.get('success'):
                        print(f"✅ [/api/budget/roads-cost-analysis] Using cached data from {cache_file.name} for year {year}")
                        return JSONResponse(cache_data)
                except Exception as cache_err:
                    print(f"⚠️ [/api/budget/roads-cost-analysis] Error reading cache, falling back to processing: {cache_err}")
        
        # For historical years (2020-2025) AND 2026 fallback: Use PostgreSQL database
        # This ensures we always use the same data source as the browser view
        if year in ['2020', '2021', '2022', '2023', '2024', '2025']:
            try:
                from budget_client import get_all_budget_items_for_analysis
                print(f"🔄 [/api/budget/roads-cost-analysis] Fetching {year} data from database...")
                db_result = await get_all_budget_items_for_analysis(year)
                
                if db_result.get('success'):
                    # Transform DB result to match expected format
                    # db_result['line_items'] already has {name, original_amount, location}
                    all_items = db_result.get('line_items', [])

                    # Standardize units: Convert 'Thousands' to 'Pesos' for historical data
                    # 2026 data is already in Pesos.
                    print(f"⚡ Scaling {len(all_items)} items for {year} by 1000 (Thousands -> Pesos)")
                    for item in all_items:
                        if 'amount' in item and item['amount'] is not None:
                             try:
                                 item['amount'] = float(item['amount']) * 1000
                             except (ValueError, TypeError):
                                 pass
                        
                        if 'original_amount' in item and item['original_amount'] is not None:
                             try:
                                 item['original_amount'] = float(item['original_amount']) * 1000
                             except (ValueError, TypeError):
                                 pass
                    
                    # We continue to the processing logic below, similar to how 2026 fallback works
                    # But first we need to make sure we don't try to load the static file again
                    # So we just assign to data like the 2026 fallback does
                    data = {'line_items': all_items, 'projects': []}
                    
                    # Skip the file loading part below
                    # We need to wrap this in a way that bypasses the file check
                    pass 
                else:
                     return JSONResponse({"success": False, "error": f"Database error for {year}: {db_result.get('error')}"}, status_code=500)
            except Exception as db_err:
                print(f"⚠️ [/api/budget/roads-cost-analysis] Error fetching from DB: {db_err}")
                return JSONResponse({"success": False, "error": f"Error fetching {year} data: {str(db_err)}"}, status_code=500)
        
        # For 2026 (fallback if cache doesn't exist) or other years: process from budget_amendments
        # If we already have data from DB (for 2020-2025), use it. Otherwise load file.
        from difflib import SequenceMatcher

        if 'data' not in locals():
            
            # Try year-specific file first, fallback to 2026
            json_path = Path(f'static/data/budget_amendments_{year}.json')
            if not json_path.exists():
                # Fallback to 2026 if year-specific file doesn't exist
                if year != "2026":
                    json_path = Path('static/data/budget_amendments_2026.json')
                if not json_path.exists():
                    return JSONResponse({"success": False, "error": f"Budget amendments {year} data not available"}, status_code=404)
            
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        
        all_items = data.get('line_items', []) + data.get('projects', [])
        
        def extract_all_chainage_ranges(name: str):
            """Extract all chainage ranges from name and return list of (start_km, start_m, end_km, end_m)"""
            if not name:
                return []

            ranges = []
            seen = set()

            def parse_number(value):
                if value is None:
                    return 0.0
                if isinstance(value, (int, float)):
                    return float(value)
                cleaned = str(value).replace(',', '')
                try:
                    return float(cleaned)
                except ValueError:
                    cleaned = re.sub(r'[^\d\.\-]', '', cleaned)
                    return float(cleaned) if cleaned else 0.0

            def add_range(start_km, start_m, end_km, end_m):
                key = (
                    float(parse_number(start_km)),
                    float(parse_number(start_m)),
                    float(parse_number(end_km)),
                    float(parse_number(end_m))
                )
                if key not in seen:
                    ranges.append(key)
                    seen.add(key)

            dash = r'[-–—]'
            number = r'\d+(?:[.,]\d+)?'

            pattern_k = rf'K({number})\s*\+\s*\(?(-?{number})\)?\s*{dash}\s*K({number})\s*\+\s*\(?(-?{number})\)?'
            for match in re.finditer(pattern_k, name, re.IGNORECASE):
                add_range(match.group(1), match.group(2), match.group(3), match.group(4))

            pattern_chainage = rf'Chainage\s+({number})\s*{dash}\s*Chainage\s+({number})'
            for match in re.finditer(pattern_chainage, name, re.IGNORECASE):
                start_total = parse_number(match.group(1))
                end_total = parse_number(match.group(2))
                add_range(start_total // 1000, start_total % 1000, end_total // 1000, end_total % 1000)

            pattern_sta = rf'Sta\.?\s*({number})\s*\+\s*({number})\s*{dash}\s*(?:Sta\.?\s*)?({number})\s*\+\s*({number})'
            for match in re.finditer(pattern_sta, name, re.IGNORECASE):
                add_range(match.group(1), match.group(2), match.group(3), match.group(4))

            pattern_plain = rf'(?<![A-Za-z0-9])({number})\s*\+\s*({number})\s*{dash}\s*({number})\s*\+\s*({number})'
            for match in re.finditer(pattern_plain, name):
                add_range(match.group(1), match.group(2), match.group(3), match.group(4))

            return ranges
        
        def calculate_distance(chainage_ranges):
            """Calculate total distance in kilometers from list of chainage ranges
            Returns: (total_distance_km, breakdown_string, individual_distances_m)
            """
            if not chainage_ranges:
                return None, None, []
            
            total_distance_m = 0
            individual_distances_m = []
            
            # Convert to total meters helper
            def to_meters(km, m):
                return km * 1000 + m
            
            for chainage_range in chainage_ranges:
                start_km, start_m, end_km, end_m = chainage_range
                
                start_total = to_meters(start_km, start_m)
                end_total = to_meters(end_km, end_m)
                
                # Distance in meters (absolute value) for this range
                distance_m = abs(end_total - start_total)
                individual_distances_m.append(distance_m)
                total_distance_m += distance_m
            
            # Convert to kilometers
            distance_km = total_distance_m / 1000.0
            
            # Create breakdown string if multiple ranges
            if len(individual_distances_m) > 1:
                breakdown = ' + '.join([f'{int(d)}m' for d in individual_distances_m]) + f' = {int(total_distance_m)}m'
            else:
                breakdown = None
            
            return distance_km, breakdown, individual_distances_m
        
        def format_chainage_display(name: str, ranges):
            """Format all chainage ranges for display"""
            if not ranges:
                return None

            chainage_strings = []
            pattern_k = r'(K\d+\s*\+\s*\(?-?\d+\)?\s*-\s*K\d+\s*\+\s*\(?-?\d+\)?)'
            for match in re.finditer(pattern_k, name, re.IGNORECASE):
                chainage_strings.append(match.group(1))
            pattern_chainage = r'(Chainage\s+\d+\s*-\s*Chainage\s+\d+)'
            for match in re.finditer(pattern_chainage, name, re.IGNORECASE):
                chainage_strings.append(match.group(1))
            pattern_sta = r'(Sta\.?\s*\d+\+\d+\s*-\s*(?:Sta\.?\s*)?\d+\+\d+)'
            for match in re.finditer(pattern_sta, name, re.IGNORECASE):
                chainage_strings.append(match.group(1))
            pattern_plain = r'(?<![A-Za-z0-9])(\d+\s*\+\s*\d+\s*-\s*\d+\s*\+\s*\d+)'
            for match in re.finditer(pattern_plain, name):
                chainage_strings.append(match.group(1))

            if chainage_strings:
                return ', '.join(chainage_strings)

            return None
        
        road_projects = []
        national_road_projects = []
        secondary_road_projects = []
        bridge_projects = []
        traffic_signs_projects = []
        nia_projects = []  # National Irrigation Administration projects with chainage
        fmr_projects = []  # Farm-to-Market Road projects with chainage
        multi_purpose_buildings_projects = []
        rockfall_netting_projects = []
        schools_projects = []
        
        for item in all_items:
            # Use revised_name if available, otherwise fall back to name or description
            name = item.get('revised_name') or item.get('name', '') or item.get('description', '')
            if not name:
                continue
            
            amount = abs(item.get('final_amount', 0) or item.get('original_amount', 0))
            if amount <= 0:
                continue
            
            # Categorize projects - check for non-road categories FIRST (they don't need chainage)
            name_lower = name.lower()
            
            # Multi-Purpose Building (also: bldg) - NO CHAINAGE REQUIRED
            building_keywords = ['multi-purpose building', 'multipurpose building', ' multi-purpose bldg', ' multipurpose bldg', ' bldg']
            is_multi_purpose_building = any(keyword in name_lower for keyword in building_keywords) and \
                                        ('road' not in name_lower or 'building' in name_lower or 'bldg' in name_lower)
            
            # Rockfall Netting (also: rocknetting) - NO CHAINAGE REQUIRED
            # Broader synonyms for Rockfall Netting
            rockfall_keywords = [
                'rockfall', 'rock fall', 'rock netting', 'rocknetting', 
                'active wire mesh', 'high tensile wire', 'erosion control mat',
                'soil nailing', 'rockfall protection', 'rockfall mitigation'
            ]
            is_rockfall_netting = any(keyword in name_lower for keyword in rockfall_keywords)

            # Check for NIA (National Irrigation Administration) projects - Annex A-4
            # Move NIA check here to allow projects WITHOUT chainage (e.g. Dams, Pumps)
            nia_keywords = [
                'national irrigation', 'irrigation system', 'irrigation project',
                'irrigation canal', 'communal irrigation', 'irrigation sub-program',
                'irrigation subprogram', 'irrigation facility', 'irrigation structure',
                'annex a-4', 'communal irrigation system', 'communal irrigation project',
                'communal irrigation scheme', 
                'canal lining', 'lateral canal', 'main canal', 'diversion dam', 
                'solar powered irrigation', 'pump irrigation'
            ]
            nia_keyword_patterns = [
                r'\bnis\b', r'\bnia\b', r'\bcis\b', r'\bcip\b', r'\bsip\b',
                r'\bc\.i\.s\b', r'\bc\.i\.p\b', r'\bs\.i\.p\b'
            ]
            
            pattern_hit = any(re.search(pattern, name_lower) for pattern in nia_keyword_patterns)
            
            # Use 'keyword_hit' logic to strictly exclude "Diversion Road" for NIA
            keyword_hit = False
            for k in nia_keywords:
                if k in name_lower:
                    # Filter out road diversions
                    if 'diversion' in k or 'diversion' in name_lower:
                        if 'road' in name_lower: continue
                    keyword_hit = True
                    break

            is_nia = (keyword_hit or pattern_hit) and \
                     'cnia' not in name_lower and \
                     'xdp' not in name_lower and \
                     'dystonia' not in name_lower
            
            # School (focus on building/classroom construction, not salaries or equipment) - NO CHAINAGE REQUIRED
            school_keywords = ['school', 'classroom', 'elementary school', 'high school', 'secondary school', 'primary school']
            school_exclude_keywords = ['salary', 'salaries', 'equipment', 'supplies', 'textbook', 'furniture', 'computer', 'laptop', 'tablet']
            is_school = any(keyword in name_lower for keyword in school_keywords) and \
                       not any(exclude in name_lower for exclude in school_exclude_keywords) and \
                       any(construct_keyword in name_lower for construct_keyword in ['construction', 'building', 'classroom', 'bldg', 'facility', 'repair', 'rehabilitation', 'renovation', 'improvement', 'completion'])
            
            # For non-road categories, process them even without chainage
            if is_multi_purpose_building or is_rockfall_netting or is_school or is_nia:
                # Check if it has chainage notation - extract ALL ranges (optional for these categories)
                chainage_ranges = extract_all_chainage_ranges(name)
                distance_km = 0
                breakdown = None
                individual_distances = []
                chainage_display = 'N/A'
                cost_per_km = amount  # For non-road projects, use amount as cost_per_km (or 0 if we want to avoid division)
                
                if chainage_ranges:
                    # If chainage exists, calculate distance
                    distance_km, breakdown, individual_distances = calculate_distance(chainage_ranges)
                    if distance_km and distance_km > 0:
                        cost_per_km = amount / distance_km
                    chainage_display = format_chainage_display(name, chainage_ranges) or 'N/A'
                
                project_data = {
                    'name': name,
                    'chainage_display': chainage_display,
                    'chainage_ranges': chainage_ranges or [],  # Store all ranges (empty if none)
                    'distance_km': distance_km,
                    'distance_breakdown': breakdown,  # e.g., "2 + 2 = 4m"
                    'amount': amount,
                    'cost_per_km': cost_per_km,
                    'source_sheet': item.get('source_sheet'),
                    'region': item.get('location', {}).get('region') if isinstance(item.get('location'), dict) else None
                }
                
                if is_multi_purpose_building:
                    multi_purpose_buildings_projects.append(project_data)
                    continue  # Skip further categorization
                elif is_rockfall_netting:
                    rockfall_netting_projects.append(project_data)
                    continue  # Skip further categorization
                elif is_nia:
                    nia_projects.append(project_data)
                    continue  # Skip further categorization
                elif is_school:
                    # Categorize school projects into subcategories
                    school_subcategory = 'Other School Projects'
                    if any(kw in name_lower for kw in ['classroom', 'class room']):
                        school_subcategory = 'Classroom Construction'
                    elif any(kw in name_lower for kw in ['building', 'bldg', 'facility']):
                        school_subcategory = 'School Building Construction'
                    elif any(kw in name_lower for kw in ['repair', 'rehabilitation', 'renovation', 'improvement']):
                        school_subcategory = 'School Building Repair/Rehabilitation'
                    elif any(kw in name_lower for kw in ['completion']):
                        school_subcategory = 'School Building Completion'
                    
                    project_data['school_subcategory'] = school_subcategory
                    schools_projects.append(project_data)
                    continue  # Skip further categorization
                # If none matched, continue to regular processing below
            
            # For road-related projects, require chainage notation
            # Check if it has chainage notation - extract ALL ranges
            chainage_ranges = extract_all_chainage_ranges(name)
            if not chainage_ranges:
                continue  # Skip road projects without chainage
            
            # Calculate total distance from all ranges
            distance_km, breakdown, individual_distances = calculate_distance(chainage_ranges)
            if not distance_km or distance_km <= 0:
                continue
            
            # Calculate cost per km
            cost_per_km = amount / distance_km
            
            chainage_display = format_chainage_display(name, chainage_ranges) or 'N/A'
            
            project_data = {
                'name': name,
                'chainage_display': chainage_display,
                'chainage_ranges': chainage_ranges,  # Store all ranges
                'distance_km': distance_km,
                'distance_breakdown': breakdown,  # e.g., "2 + 2 = 4m"
                'amount': amount,
                'cost_per_km': cost_per_km,
                'source_sheet': item.get('source_sheet'),
                'region': item.get('location', {}).get('region') if isinstance(item.get('location'), dict) else None
            }
            
            # Check for FMR (Farm-to-Market Road) projects first - Annex A-1
            # FMR projects typically have "FMR" in the name or "farm to market" / "farm-to-market"
            fmr_keywords = [' fmr', 'fmr ', 'farm to market', 'farm-to-market', 'farm to market road']
            # Exclude false positives like "CNIA" (military base) - only match standalone "FMR" or with spaces
            is_fmr = any(keyword in name_lower for keyword in fmr_keywords) and 'cnia' not in name_lower
            
            # Check for NIA (National Irrigation Administration) projects - Annex A-4
            # NIA projects have "irrigation" keywords but exclude false positives
            nia_keywords = [
                'national irrigation', 'irrigation system', 'irrigation project', 
                'irrigation canal', 'communal irrigation', 'irrigation sub-program',
                'irrigation subprogram', 'irrigation facility', 'irrigation structure'
            ]
            # Exclude false positives: CNIA (military), XDP (medical), etc.
            is_nia = any(keyword in name_lower for keyword in nia_keywords) and \
                     'cnia' not in name_lower and \
                     'xdp' not in name_lower and \
                     'dystonia' not in name_lower
            
            if is_fmr:
                fmr_projects.append(project_data)
                continue  # Skip further categorization for FMR
            elif is_nia:
                nia_projects.append(project_data)
                continue  # Skip further categorization for NIA
            
            # Road Safety Facilities: installations, guardrails, lighting, signs, markings
            # Only categorize those WITH chainage (already filtered above)
            # Includes: installation, road safety, guardrail, traffic facilities, lighting, signs, markings
            road_safety_keywords = [
                'installation', 'road safety', 'guardrail', 'traffic facilities', 'traffic facility',
                'lighting', 'streetlight', 'street light', 'led', 'solar', 'roadway lighting',
                'road sign', 'pavement marking', 'barrier', 'pedestrian overpass'
            ]
            is_road_safety = any(keyword in name_lower for keyword in road_safety_keywords)
            
            # Bridges: projects with bridge-related keywords ONLY (no distance heuristic to avoid false positives)
            # Include: bridge, viaduct, flyover, overpass, underpass, footbridge, pedestrian bridge
            bridge_keywords = ['bridge', 'viaduct', 'flyover', 'overpass', 'underpass', 'footbridge', 'pedestrian bridge']
            is_bridge = any(keyword in name_lower for keyword in bridge_keywords)
            
            # Road-related terms (these indicate roads, not bridges)
            # Includes: road, rd, highway, hiway, hway, h-way, boulevard, blvd, avenue, ave, junction, jct, 
            #           old route, diversion, extension, ext, street, st, expressway
            road_terms = [
                ' road', ' rd', ' highway', ' hiway', ' hway', ' h-way',
                'boulevard', ' blvd', ' avenue', ' ave', ' ave.',
                'junction', ' jct', ' old route', ' diversion',
                'extension', ' ext', ' street', ' st', ' st.',
                'expressway'
            ]
            is_road_term = any(term in name_lower for term in road_terms)
            
            if is_road_safety:
                # Categorize road safety facilities into subcategories
                subcategories = _categorize_road_safety_facilities(name, name_lower)
                # Defensive check: ensure subcategories is never empty
                if not subcategories or len(subcategories) == 0:
                    subcategories = ['Road Safety Facilities']
                project_data['road_safety_subcategories'] = subcategories
                project_data['is_new'] = _is_new_installation(name, name_lower)
                traffic_signs_projects.append(project_data)
            elif is_bridge:
                bridge_projects.append(project_data)
            # Roads: separate into national roads and secondary roads
            elif is_road_term or not is_bridge:
                # Categorize road work type (if found)
                work_types = _categorize_road_work_type(name, name_lower)
                if work_types:
                    # Store as list for composite work types
                    project_data['work_type'] = work_types[0] if len(work_types) == 1 else work_types
                    project_data['work_types'] = work_types  # Always store full list
                else:
                    project_data['work_type'] = None
                    project_data['work_types'] = []
                
                # Determine if it's a major road using classification rules
                is_major_road = _is_major_road(name, chainage_ranges)
                
                if is_major_road:
                    national_road_projects.append(project_data)
                else:
                    secondary_road_projects.append(project_data)
            else:
                # Fallback - treat as secondary road
                secondary_road_projects.append(project_data)
        
        # Calculate statistics for each category
        def calculate_statistics(projects):
            if not projects:
                return {
                    "min": None,
                    "max": None,
                    "mean": None,
                    "median": None,
                    "mode": None,
                    "std_dev": None,
                    "mad": None,
                    "threshold": None,
                    "count": 0
                }
            
            import statistics
            from collections import Counter
            
            costs = [p['cost_per_km'] for p in projects if p.get('cost_per_km', 0) > 0]
            if not costs:
                return {
                    "min": None,
                    "max": None,
                    "mean": None,
                    "median": None,
                    "mode": None,
                    "std_dev": None,
                    "mad": None,
                    "threshold": None,
                    "count": 0
                }
            
            costs_sorted = sorted(costs)
            mean = statistics.mean(costs)
            median_val = statistics.median(costs_sorted)
            deviations = [abs(c - median_val) for c in costs_sorted]
            mad = statistics.median(deviations) if deviations else 0
            threshold = median_val + (MAD_SCALE * mad) if mad else None
            
            # Calculate mode (most frequent value, rounded to nearest million for practical purposes)
            # Round to nearest 1M for mode calculation to avoid too many unique values
            rounded_costs = [round(c / 1000000) * 1000000 for c in costs]
            cost_counter = Counter(rounded_costs)
            mode_value = cost_counter.most_common(1)[0][0] if cost_counter else None
            
            try:
                std_dev = statistics.stdev(costs) if len(costs) > 1 else 0
            except statistics.StatisticsError:
                std_dev = 0
            
            return {
                "min": min(costs),
                "max": max(costs),
                "mean": mean,
                "median": median_val,
                "mode": mode_value,
                "std_dev": std_dev,
                "mad": mad,
                "threshold": threshold,
                "count": len(costs)
            }
        
        # Calculate subcategory-specific statistics and flag projects
        from collections import defaultdict
        
        # Group road safety facilities by subcategory
        # For composite projects (multiple subcategories), count in ALL subcategories
        # Use "average of average" approach: divide cost/km by number of components
        road_safety_by_subcategory = defaultdict(list)
        for project in traffic_signs_projects:
            subcategories = project.get('road_safety_subcategories', [])
            if subcategories:
                # For composite projects, count in ALL subcategories
                # Create a copy of project data with adjusted cost/km for statistics
                num_components = len(subcategories)
                original_cost_per_km = project.get('cost_per_km', 0)
                
                # For each subcategory, add project with cost/km divided by number of components
                # This represents "average cost per component" (average of average)
                for subcategory in subcategories:
                    # Create a copy for this subcategory with adjusted cost/km
                    project_copy = project.copy()
                    project_copy['cost_per_km_for_stats'] = original_cost_per_km / num_components if num_components > 0 else original_cost_per_km
                    project_copy['num_components'] = num_components
                    project_copy['original_cost_per_km'] = original_cost_per_km
                    road_safety_by_subcategory[subcategory].append(project_copy)
            else:
                # No subcategory - use "Road Safety Facilities" as default
                project_copy = project.copy()
                project_copy['cost_per_km_for_stats'] = project.get('cost_per_km', 0)
                project_copy['num_components'] = 1
                project_copy['original_cost_per_km'] = project.get('cost_per_km', 0)
                road_safety_by_subcategory['Road Safety Facilities'].append(project_copy)
        
        # Group roads by work type (within national/secondary)
        # For composite work types, count in ALL work types using "average of average"
        national_roads_by_work_type = defaultdict(list)
        secondary_roads_by_work_type = defaultdict(list)
        
        for project in national_road_projects:
            work_types = project.get('work_types', [])
            if not work_types:
                # Fallback to single work_type for backward compatibility
                work_type = project.get('work_type')
                work_types = [work_type] if work_type else []
            
            if work_types:
                # For composite work types, count in ALL work types
                num_components = len(work_types)
                original_cost_per_km = project.get('cost_per_km', 0)
                
                for work_type in work_types:
                    project_copy = project.copy()
                    project_copy['cost_per_km_for_stats'] = original_cost_per_km / num_components if num_components > 0 else original_cost_per_km
                    project_copy['num_components'] = num_components
                    project_copy['original_cost_per_km'] = original_cost_per_km
                    national_roads_by_work_type[work_type].append(project_copy)
            else:
                # No work type - use "Major Road" as default
                project_copy = project.copy()
                project_copy['cost_per_km_for_stats'] = project.get('cost_per_km', 0)
                project_copy['num_components'] = 1
                project_copy['original_cost_per_km'] = project.get('cost_per_km', 0)
                national_roads_by_work_type['Major Road'].append(project_copy)
        
        for project in secondary_road_projects:
            work_types = project.get('work_types', [])
            if not work_types:
                # Fallback to single work_type for backward compatibility
                work_type = project.get('work_type')
                work_types = [work_type] if work_type else []
            
            if work_types:
                # For composite work types, count in ALL work types
                num_components = len(work_types)
                original_cost_per_km = project.get('cost_per_km', 0)
                
                for work_type in work_types:
                    project_copy = project.copy()
                    project_copy['cost_per_km_for_stats'] = original_cost_per_km / num_components if num_components > 0 else original_cost_per_km
                    project_copy['num_components'] = num_components
                    project_copy['original_cost_per_km'] = original_cost_per_km
                    secondary_roads_by_work_type[work_type].append(project_copy)
            else:
                # No work type - use "Minor Road" as default
                project_copy = project.copy()
                project_copy['cost_per_km_for_stats'] = project.get('cost_per_km', 0)
                project_copy['num_components'] = 1
                project_copy['original_cost_per_km'] = project.get('cost_per_km', 0)
                secondary_roads_by_work_type['Minor Road'].append(project_copy)
        
        # Calculate statistics per subcategory/work_type and flag projects
        def flag_projects_by_subcategory(projects_by_subcategory, category_name):
            """Calculate subcategory statistics and flag projects that exceed threshold
            Uses 'average of average' approach for composite projects:
            - Statistics use cost_per_km_for_stats (divided by number of components)
            - Flagging uses original_cost_per_km against threshold
            """
            subcategory_stats = {}
            for subcategory, projects in projects_by_subcategory.items():
                # Use cost_per_km_for_stats for statistics (average of average for composites)
                stats_costs = [p.get('cost_per_km_for_stats', p.get('cost_per_km', 0)) for p in projects if p.get('cost_per_km_for_stats', p.get('cost_per_km', 0)) > 0]
                
                if not stats_costs:
                    subcategory_stats[subcategory] = {
                        "min": None, "max": None, "mean": None, "median": None,
                        "mode": None, "std_dev": None, "mad": None, "threshold": None, "count": 0
                    }
                    for project in projects:
                        project['is_flagged'] = False
                    continue
                
                import statistics
                from collections import Counter
                
                costs_sorted = sorted(stats_costs)
                mean = statistics.mean(stats_costs)
                median_val = statistics.median(costs_sorted)
                deviations = [abs(c - median_val) for c in costs_sorted]
                mad = statistics.median(deviations) if deviations else 0
                threshold = median_val + (MAD_SCALE * mad) if mad else None
                rounded_costs = [round(c / 1000000) * 1000000 for c in stats_costs]
                cost_counter = Counter(rounded_costs)
                mode_value = cost_counter.most_common(1)[0][0] if cost_counter else None
                try:
                    std_dev = statistics.stdev(stats_costs) if len(stats_costs) > 1 else 0
                except statistics.StatisticsError:
                    std_dev = 0
                
                stats = {
                    "min": min(stats_costs),
                    "max": max(stats_costs),
                    "mean": mean,
                    "median": median_val,
                    "mode": mode_value,
                    "std_dev": std_dev,
                    "mad": mad,
                    "threshold": threshold,  # Add threshold to stats
                    "count": len(projects)
                }
                subcategory_stats[subcategory] = stats
                
                # Flag projects that exceed MAD-derived threshold
                # Use original_cost_per_km for flagging (not the divided one)
                
                for project in projects:
                    project['subcategory'] = subcategory
                    project['subcategory_stats'] = stats
                    # Use original_cost_per_km for flagging comparison
                    cost_to_check = project.get('original_cost_per_km', project.get('cost_per_km', 0))
                    if threshold and cost_to_check > threshold:
                        project['is_flagged'] = True
                        project['flag_reason'] = f"Cost/km ({cost_to_check:,.2f}) exceeds {subcategory} threshold ({threshold:,.2f})"
                    else:
                        project['is_flagged'] = False

            return subcategory_stats

        def flag_projects_by_threshold_simple(projects, stats, category_name):
            """Flag projects using MAD-derived threshold"""
            if not projects or not stats:
                return

            median_val = stats.get('median')
            mad = stats.get('mad') or 0
            threshold = stats.get('threshold')
            if mad and median_val is not None:
                threshold = median_val + (MAD_SCALE * mad)

            if not threshold or threshold <= 0:
                for project in projects:
                    project['is_flagged'] = False
                return

            for project in projects:
                cost_per_km = project.get('cost_per_km', 0)
                if cost_per_km and cost_per_km > threshold:
                    project['is_flagged'] = True
                    project['flag_reason'] = f"Cost/km ({cost_per_km:,.2f}) exceeds {category_name} threshold ({threshold:,.2f})"
                else:
                    project['is_flagged'] = False
        
        # Flag road safety facilities by subcategory
        road_safety_subcategory_stats = flag_projects_by_subcategory(road_safety_by_subcategory, 'Road Safety Facilities')
        
        # Flag national roads by work type
        national_roads_work_type_stats = flag_projects_by_subcategory(national_roads_by_work_type, 'National Roads')
        
        # Flag secondary roads by work type
        secondary_roads_work_type_stats = flag_projects_by_subcategory(secondary_roads_by_work_type, 'Secondary Roads')
        
        # Merge flagged information back into original projects
        # Create a lookup map: (name, distance_km) -> flagged_project_copy
        def merge_flagging_back(original_projects, projects_by_subcategory_dict):
            """Merge flagging info from copies back into original projects"""
            flagged_map = {}
            for subcategory, flagged_projects in projects_by_subcategory_dict.items():
                for flagged_project in flagged_projects:
                    # Use name + distance as unique identifier
                    key = (flagged_project.get('name'), flagged_project.get('distance_km'))
                    flagged_map[key] = flagged_project
            
            # Update original projects with flagging info
            for project in original_projects:
                key = (project.get('name'), project.get('distance_km'))
                if key in flagged_map:
                    flagged_project = flagged_map[key]
                    # Merge flagging info, but keep original work_type/work_types
                    project['subcategory'] = flagged_project.get('subcategory')
                    project['subcategory_stats'] = flagged_project.get('subcategory_stats')
                    project['is_flagged'] = flagged_project.get('is_flagged', False)
                    project['flag_reason'] = flagged_project.get('flag_reason')
                    # Also ensure work_type/work_types are preserved
                    if flagged_project.get('work_type'):
                        project['work_type'] = flagged_project.get('work_type')
                    if flagged_project.get('work_types'):
                        project['work_types'] = flagged_project.get('work_types')
        
        merge_flagging_back(traffic_signs_projects, road_safety_by_subcategory)
        merge_flagging_back(national_road_projects, national_roads_by_work_type)
        merge_flagging_back(secondary_road_projects, secondary_roads_by_work_type)
        
        # Sort each category by cost per km descending
        national_road_projects.sort(key=lambda x: x['cost_per_km'], reverse=True)
        secondary_road_projects.sort(key=lambda x: x['cost_per_km'], reverse=True)
        bridge_projects.sort(key=lambda x: x['cost_per_km'], reverse=True)
        traffic_signs_projects.sort(key=lambda x: x['cost_per_km'], reverse=True)
        nia_projects.sort(key=lambda x: x['cost_per_km'], reverse=True)
        fmr_projects.sort(key=lambda x: x['cost_per_km'], reverse=True)
        multi_purpose_buildings_projects.sort(key=lambda x: x['cost_per_km'], reverse=True)
        rockfall_netting_projects.sort(key=lambda x: x['cost_per_km'], reverse=True)
        schools_projects.sort(key=lambda x: x['cost_per_km'], reverse=True)
        
        # Combine all roads for backward compatibility
        road_projects = national_road_projects + secondary_road_projects
        
        # Calculate overall category statistics
        national_roads_stats = calculate_statistics(national_road_projects)
        secondary_roads_stats = calculate_statistics(secondary_road_projects)
        roads_stats = calculate_statistics(road_projects)  # Combined stats
        bridges_stats = calculate_statistics(bridge_projects)
        flag_projects_by_threshold_simple(bridge_projects, bridges_stats, 'Bridges')
        traffic_signs_stats = calculate_statistics(traffic_signs_projects)
        nia_stats = calculate_statistics(nia_projects)
        flag_projects_by_threshold_simple(nia_projects, nia_stats, 'Irrigation Works (NIA)')
        fmr_stats = calculate_statistics(fmr_projects)
        flag_projects_by_threshold_simple(fmr_projects, fmr_stats, 'Farm-to-Market Roads')
        multi_purpose_buildings_stats = calculate_statistics(multi_purpose_buildings_projects)
        flag_projects_by_threshold_simple(multi_purpose_buildings_projects, multi_purpose_buildings_stats, 'Multi-Purpose Buildings')
        rockfall_netting_stats = calculate_statistics(rockfall_netting_projects)
        flag_projects_by_threshold_simple(rockfall_netting_projects, rockfall_netting_stats, 'Rockfall Netting')
        schools_stats = calculate_statistics(schools_projects)
        flag_projects_by_threshold_simple(schools_projects, schools_stats, 'Schools')
        
        return JSONResponse({
            "success": True,
            "roads": {
                "projects": road_projects,
                "total": len(road_projects),
                "statistics": roads_stats
            },
            "national_roads": {
                "projects": national_road_projects,
                "total": len(national_road_projects),
                "statistics": national_roads_stats,
                "subcategory_statistics": national_roads_work_type_stats
            },
            "secondary_roads": {
                "projects": secondary_road_projects,
                "total": len(secondary_road_projects),
                "statistics": secondary_roads_stats,
                "subcategory_statistics": secondary_roads_work_type_stats
            },
            "bridges": {
                "projects": bridge_projects,
                "total": len(bridge_projects),
                "statistics": bridges_stats
            },
            "traffic_signs": {
                "projects": traffic_signs_projects,
                "total": len(traffic_signs_projects),
                "statistics": traffic_signs_stats,
                "subcategory_statistics": road_safety_subcategory_stats
            },
            "nia": {
                "projects": nia_projects,
                "total": len(nia_projects),
                "statistics": nia_stats
            },
            "fmr": {
                "projects": fmr_projects,
                "total": len(fmr_projects),
                "statistics": fmr_stats
            },
            "multi_purpose_buildings": {
                "projects": multi_purpose_buildings_projects,
                "total": len(multi_purpose_buildings_projects),
                "statistics": multi_purpose_buildings_stats
            },
            "rockfall_netting": {
                "projects": rockfall_netting_projects,
                "total": len(rockfall_netting_projects),
                "statistics": rockfall_netting_stats
            },
            "schools": {
                "projects": schools_projects,
                "total": len(schools_projects),
                "statistics": schools_stats
            }
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/budget/category-statistics")
async def budget_category_statistics_api(year: str = "2026"):
    """Get category statistics showing average cost/km and flagged cost per category/subcategory"""
    try:
        # Load data using the existing roads cost analysis endpoint logic
        # We'll reuse the processing logic from budget_roads_cost_analysis_api
        from pathlib import Path
        import json
        from collections import defaultdict
        import statistics
        
        # Handle "all" years - load from pre-computed cache
        if year.lower() == "all":
            cache_path = Path(__file__).parent / "static" / "data" / "api_cache" / "roads_cost_analysis_cache.json"
            
            if cache_path.exists():
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                # Use pre-computed all_years_category_statistics if available
                if 'all_years_category_statistics' in cache_data:
                    return JSONResponse({
                        "success": True,
                        "year": "all",
                        "categories": cache_data['all_years_category_statistics']
                    })
            
            # Fallback: return error if cache doesn't exist
            return JSONResponse({"success": False, "error": "All years category statistics not found. Please regenerate cache files."}, status_code=404)
        
        # Load data based on year
        if year == "2026":
            # For 2026, use the cache
            cache_path = Path(__file__).parent / "static" / "data" / "api_cache" / "roads_cost_analysis_cache.json"
            if cache_path.exists():
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
            else:
                # Fallback: return error if cache doesn't exist
                return JSONResponse({"success": False, "error": "Cache file not found. Please regenerate cache."}, status_code=404)
            
            categories = []
            
            # Bridges
            bridges = cache_data.get('bridges', {}).get('projects', [])
            bridges_stats = cache_data.get('bridges', {}).get('statistics', {})
            bridges_flagged = [p for p in bridges if p.get('is_flagged', False)]
            bridges_flagged_cost = sum(p.get('amount', 0) for p in bridges_flagged)
            bridges_total_cost = sum(p.get('amount', 0) for p in bridges)
            
            bridges_threshold = bridges_stats.get('threshold', 0)
            
            categories.append({
                "category": "Bridges",
                "subcategory": None,
                "average_cost_per_km": bridges_stats.get('mean') or 0,
                "threshold_cost_per_km": bridges_threshold,
                "flagged_cost": bridges_flagged_cost,
                "total_cost": bridges_total_cost,
                "flagged_count": len(bridges_flagged),
                "total_count": len(bridges)
            })
            
            # Road Safety Facilities (subcategories)
            traffic_signs = cache_data.get('traffic_signs', {}).get('projects', [])
            subcategory_stats = cache_data.get('traffic_signs', {}).get('subcategory_statistics', {})
            for subcategory, stats in subcategory_stats.items():
                subcategory_projects = [
                    p for p in traffic_signs 
                    if p.get('subcategory') == subcategory or 
                       (subcategory in (p.get('road_safety_subcategories') or []))
                ]
                flagged_projects = [p for p in subcategory_projects if p.get('is_flagged', False)]
                flagged_cost = sum(p.get('amount', 0) for p in flagged_projects)
                total_cost = sum(p.get('amount', 0) for p in subcategory_projects)
                
                categories.append({
                    "category": "Road Safety Facilities",
                    "subcategory": subcategory,
                    "average_cost_per_km": stats.get('mean') or 0,
                    "threshold_cost_per_km": stats.get('threshold', 0),
                    "flagged_cost": flagged_cost,
                    "total_cost": total_cost,
                    "flagged_count": len(flagged_projects),
                    "total_count": stats.get('count', 0)
                })
            
            # Major Roads (work types)
            national_roads = cache_data.get('national_roads', {}).get('projects', [])
            national_work_type_stats = cache_data.get('national_roads', {}).get('subcategory_statistics', {})
            for work_type, stats in national_work_type_stats.items():
                work_type_projects = [
                    p for p in national_roads 
                    if p.get('subcategory') == work_type or
                       p.get('work_type') == work_type or
                       (work_type in (p.get('work_types') or []))
                ]
                flagged_projects = [p for p in work_type_projects if p.get('is_flagged', False)]
                flagged_cost = sum(p.get('amount', 0) for p in flagged_projects)
                total_cost = sum(p.get('amount', 0) for p in work_type_projects)
                
                categories.append({
                    "category": "Major Roads",
                    "subcategory": work_type,
                    "average_cost_per_km": stats.get('mean') or 0,
                    "threshold_cost_per_km": stats.get('threshold', 0),
                    "flagged_cost": flagged_cost,
                    "total_cost": total_cost,
                    "flagged_count": len(flagged_projects),
                    "total_count": stats.get('count', 0)
                })
            
            # Minor Roads (work types)
            secondary_roads = cache_data.get('secondary_roads', {}).get('projects', [])
            secondary_work_type_stats = cache_data.get('secondary_roads', {}).get('subcategory_statistics', {})
            for work_type, stats in secondary_work_type_stats.items():
                work_type_projects = [
                    p for p in secondary_roads 
                    if p.get('subcategory') == work_type or
                       p.get('work_type') == work_type or
                       (work_type in (p.get('work_types') or []))
                ]
                flagged_projects = [p for p in work_type_projects if p.get('is_flagged', False)]
                flagged_cost = sum(p.get('amount', 0) for p in flagged_projects)
                total_cost = sum(p.get('amount', 0) for p in work_type_projects)
                
                categories.append({
                    "category": "Minor Roads",
                    "subcategory": work_type,
                    "average_cost_per_km": stats.get('mean') or 0,
                    "threshold_cost_per_km": stats.get('threshold', 0),
                    "flagged_cost": flagged_cost,
                    "total_cost": total_cost,
                    "flagged_count": len(flagged_projects),
                    "total_count": stats.get('count', 0)
                })
            
            # Multi-Purpose Buildings (grouped by derived subcategories when available)
            multi_purpose_data = cache_data.get('multi_purpose_buildings', {})
            multi_purpose_buildings = multi_purpose_data.get('projects', [])
            multi_purpose_sub_stats = multi_purpose_data.get('subcategory_statistics', {})
            if multi_purpose_sub_stats:
                for subcategory, stats in multi_purpose_sub_stats.items():
                    subcategory_projects = [
                        p for p in multi_purpose_buildings
                        if (p.get('multi_purpose_subcategory') or 'Other Multi-Purpose Buildings') == subcategory
                    ]
                    flagged_projects = [p for p in subcategory_projects if p.get('is_flagged', False)]
                    flagged_cost = sum(p.get('amount', 0) for p in flagged_projects)
                    total_cost = sum(p.get('amount', 0) for p in subcategory_projects)
                    
                    categories.append({
                        "category": "Multi-Purpose Buildings",
                        "subcategory": subcategory,
                        "average_cost_per_km": stats.get('mean') or 0,
                        "threshold_cost_per_km": stats.get('threshold', 0),
                        "flagged_cost": flagged_cost,
                        "total_cost": total_cost,
                        "flagged_count": len(flagged_projects),
                        "total_count": stats.get('count', len(subcategory_projects))
                    })
            else:
                buildings_flagged = [p for p in multi_purpose_buildings if p.get('is_flagged', False)]
                buildings_stats_data = multi_purpose_data.get('statistics', {})
                buildings_avg_cost_km = buildings_stats_data.get('mean') or 0
                buildings_flagged_cost = sum(p.get('amount', 0) for p in buildings_flagged)
                buildings_total_cost = sum(p.get('amount', 0) for p in multi_purpose_buildings)
                buildings_threshold = buildings_stats_data.get('threshold', 0)
                
                categories.append({
                    "category": "Multi-Purpose Buildings",
                    "subcategory": None,
                    "average_cost_per_km": buildings_avg_cost_km,
                    "threshold_cost_per_km": buildings_threshold,
                    "flagged_cost": buildings_flagged_cost,
                    "total_cost": buildings_total_cost,
                    "flagged_count": len(buildings_flagged),
                    "total_count": len(multi_purpose_buildings)
                })

            # Irrigation Works (NIA)
            nia_data = cache_data.get('nia', {})
            nia_projects = nia_data.get('projects', [])
            nia_sub_stats = nia_data.get('subcategory_statistics', {})
            if nia_sub_stats:
                for subcategory, stats in nia_sub_stats.items():
                    subcategory_projects = [
                        p for p in nia_projects
                        if (p.get('nia_subcategory') or 'Other Irrigation Works') == subcategory
                    ]
                    flagged_projects = [p for p in subcategory_projects if p.get('is_flagged', False)]
                    flagged_cost = sum(p.get('amount', 0) for p in flagged_projects)
                    total_cost = sum(p.get('amount', 0) for p in subcategory_projects)
                    
                    categories.append({
                        "category": "Irrigation Works (NIA)",
                        "subcategory": subcategory,
                        "average_cost_per_km": stats.get('mean') or 0,
                        "threshold_cost_per_km": stats.get('threshold', 0),
                        "flagged_cost": flagged_cost,
                        "total_cost": total_cost,
                        "flagged_count": len(flagged_projects),
                        "total_count": stats.get('count', len(subcategory_projects))
                    })
            elif nia_projects:
                nia_stats_data = nia_data.get('statistics', {})
                nia_avg_cost_km = nia_stats_data.get('mean') or 0
                nia_flagged = [p for p in nia_projects if p.get('is_flagged', False)]
                nia_flagged_cost = sum(p.get('amount', 0) for p in nia_flagged)
                nia_total_cost = sum(p.get('amount', 0) for p in nia_projects)
                nia_threshold = nia_stats_data.get('threshold', 0)
                categories.append({
                    "category": "Irrigation Works (NIA)",
                    "subcategory": None,
                    "average_cost_per_km": nia_avg_cost_km,
                    "threshold_cost_per_km": nia_threshold,
                    "flagged_cost": nia_flagged_cost,
                    "total_cost": nia_total_cost,
                    "flagged_count": len(nia_flagged),
                    "total_count": len(nia_projects)
                })
            
            # Rockfall Netting (always include, even if empty)
            rockfall_netting = cache_data.get('rockfall_netting', {}).get('projects', [])
            rockfall_flagged = [p for p in rockfall_netting if p.get('is_flagged', False)]
            rockfall_stats_data = cache_data.get('rockfall_netting', {}).get('statistics', {})
            rockfall_avg_cost_km = rockfall_stats_data.get('mean') or 0
            rockfall_flagged_cost = sum(p.get('amount', 0) for p in rockfall_flagged)
            rockfall_total_cost = sum(p.get('amount', 0) for p in rockfall_netting)
            
            rockfall_threshold = rockfall_stats_data.get('threshold', 0)
            
            categories.append({
                "category": "Rockfall Netting",
                "subcategory": None,
                "average_cost_per_km": rockfall_avg_cost_km,
                "threshold_cost_per_km": rockfall_threshold,
                "flagged_cost": rockfall_flagged_cost,
                "total_cost": rockfall_total_cost,
                "flagged_count": len(rockfall_flagged),
                "total_count": len(rockfall_netting)
            })
            
            # Schools (with subcategories, always include even if empty)
            schools = cache_data.get('schools', {}).get('projects', [])
            schools_subcategory_stats = cache_data.get('schools', {}).get('subcategory_statistics', {})
            # If no subcategories exist, add a default entry for the overall category
            if not schools_subcategory_stats:
                schools_stats_data = cache_data.get('schools', {}).get('statistics', {})
                schools_avg_cost_km = schools_stats_data.get('mean') or 0
                schools_flagged = [p for p in schools if p.get('is_flagged', False)]
                schools_flagged_cost = sum(p.get('amount', 0) for p in schools_flagged)
                schools_total_cost = sum(p.get('amount', 0) for p in schools)
                schools_threshold = schools_stats_data.get('threshold', 0)
                categories.append({
                    "category": "Schools",
                    "subcategory": None,
                    "average_cost_per_km": schools_avg_cost_km,
                    "threshold_cost_per_km": schools_threshold,
                    "flagged_cost": schools_flagged_cost,
                    "total_cost": schools_total_cost,
                    "flagged_count": len(schools_flagged),
                    "total_count": len(schools)
                })
            for subcategory, stats in schools_subcategory_stats.items():
                subcategory_projects = [
                    p for p in schools
                    if p.get('school_subcategory') == subcategory
                ]
                flagged_projects = [p for p in subcategory_projects if p.get('is_flagged', False)]
                flagged_cost = sum(p.get('amount', 0) for p in flagged_projects)
                total_cost = sum(p.get('amount', 0) for p in subcategory_projects)
                categories.append({
                    "category": "Schools",
                    "subcategory": subcategory,
                    "average_cost_per_km": stats.get('mean') or 0,
                    "threshold_cost_per_km": stats.get('threshold', 0),
                    "flagged_cost": flagged_cost,
                    "total_cost": total_cost,
                    "flagged_count": len(flagged_projects),
                    "total_count": stats.get('count', 0)
                })
            
            # Sort by average_cost_per_km descending
            categories.sort(key=lambda x: x.get('average_cost_per_km') or 0, reverse=True)
            
            return JSONResponse({
                "success": True,
                "year": year,
                "categories": categories
            })
        else:
            # For historical years (and potentially others), reuse the logic from the roads cost analysis API
            # This API now fetches from DB for 2020-2025 and handles 2026 fallback
            print(f"🔄 [/api/budget/category-statistics] reuse budget_roads_cost_analysis_api for year {year}")
            
            # Call the API function directly (it's async)
            response = await budget_roads_cost_analysis_api(year)
            
            if response.status_code != 200:
                return JSONResponse({"success": False, "error": f"Error fetching data from analysis API for {year}"}, status_code=response.status_code)
            
            # Parse the JSON response body
            import json
            year_data = json.loads(response.body)
            
            if not year_data.get('success'):
                return JSONResponse({"success": False, "error": f"Analysis API returned failure for {year}: {year_data.get('error')}"}, status_code=500)
            
            # Process historical data to get category statistics
            categories = []
            
            # Bridges
            bridges_data = year_data.get('bridges', {})
            bridges = bridges_data.get('projects', [])
            if bridges:
                bridges_flagged = [p for p in bridges if p.get('is_flagged', False)]
                bridges_stats = bridges_data.get('statistics', {})
                bridges_avg_cost_km = bridges_stats.get('mean') or 0
                bridges_flagged_cost = sum(p.get('amount', 0) for p in bridges_flagged)
                bridges_total_cost = sum(p.get('amount', 0) for p in bridges)
                bridges_threshold = bridges_stats.get('threshold', 0)
                
                categories.append({
                    "category": "Bridges",
                    "subcategory": None,
                    "average_cost_per_km": bridges_avg_cost_km,
                    "threshold_cost_per_km": bridges_threshold,
                    "flagged_cost": bridges_flagged_cost,
                    "total_cost": bridges_total_cost,
                    "flagged_count": len(bridges_flagged),
                    "total_count": len(bridges)
                })
            
            # Road Safety Facilities
            traffic_data = year_data.get('traffic_signs', {})
            traffic_signs = traffic_data.get('projects', [])
            subcategory_stats = traffic_data.get('subcategory_statistics', {})
            
            if subcategory_stats:
                for subcategory, stats in subcategory_stats.items():
                    subcategory_projects = [
                        p for p in traffic_signs 
                        if p.get('subcategory') == subcategory or 
                           (subcategory in (p.get('road_safety_subcategories') or []))
                    ]
                    flagged_projects = [p for p in subcategory_projects if p.get('is_flagged', False)]
                    flagged_cost = sum(p.get('amount', 0) for p in flagged_projects)
                    total_cost = sum(p.get('amount', 0) for p in subcategory_projects)
                    
                    categories.append({
                        "category": "Road Safety Facilities",
                        "subcategory": subcategory,
                        "average_cost_per_km": stats.get('mean') or 0,
                        "threshold_cost_per_km": stats.get('threshold', 0),
                        "flagged_cost": flagged_cost,
                        "total_cost": total_cost,
                        "flagged_count": len(flagged_projects),
                        "total_count": stats.get('count', 0)
                    })
            
            # Major Roads (National Roads)
            national_data = year_data.get('national_roads', {})
            national_roads = national_data.get('projects', [])
            national_work_type_stats = national_data.get('subcategory_statistics', {})

            for work_type, stats in national_work_type_stats.items():
                work_type_projects = [
                    p for p in national_roads 
                    if p.get('subcategory') == work_type or
                       p.get('work_type') == work_type or
                       (work_type in (p.get('work_types') or []))
                ]
                flagged_projects = [p for p in work_type_projects if p.get('is_flagged', False)]
                flagged_cost = sum(p.get('amount', 0) for p in flagged_projects)
                total_cost = sum(p.get('amount', 0) for p in work_type_projects)
                
                categories.append({
                    "category": "Major Roads",
                    "subcategory": work_type,
                    "average_cost_per_km": stats.get('mean') or 0,
                    "threshold_cost_per_km": stats.get('threshold', 0),
                    "flagged_cost": flagged_cost,
                    "total_cost": total_cost,
                    "flagged_count": len(flagged_projects),
                    "total_count": stats.get('count', 0)
                })

            # Minor Roads (Secondary Roads)
            secondary_data = year_data.get('secondary_roads', {})
            secondary_roads = secondary_data.get('projects', [])
            secondary_work_type_stats = secondary_data.get('subcategory_statistics', {})
            
            for work_type, stats in secondary_work_type_stats.items():
                work_type_projects = [
                    p for p in secondary_roads 
                    if p.get('subcategory') == work_type or
                       p.get('work_type') == work_type or
                       (work_type in (p.get('work_types') or []))
                ]
                flagged_projects = [p for p in work_type_projects if p.get('is_flagged', False)]
                flagged_cost = sum(p.get('amount', 0) for p in flagged_projects)
                total_cost = sum(p.get('amount', 0) for p in work_type_projects)
                
                categories.append({
                    "category": "Minor Roads",
                    "subcategory": work_type,
                    "average_cost_per_km": stats.get('mean') or 0,
                    "threshold_cost_per_km": stats.get('threshold', 0),
                    "flagged_cost": flagged_cost,
                    "total_cost": total_cost,
                    "flagged_count": len(flagged_projects),
                    "total_count": stats.get('count', 0)
                })
            
            # Multi-Purpose Buildings
            mpb_data = year_data.get('multi_purpose_buildings', {})
            multi_purpose_buildings = mpb_data.get('projects', [])
            multi_purpose_sub_stats = mpb_data.get('subcategory_statistics', {})
            
            if multi_purpose_sub_stats:
                for subcategory, stats in multi_purpose_sub_stats.items():
                    subcategory_projects = [
                         p for p in multi_purpose_buildings
                         if (p.get('multi_purpose_subcategory') or 'Other Multi-Purpose Buildings') == subcategory
                    ]
                    flagged_projects = [p for p in subcategory_projects if p.get('is_flagged', False)]
                    flagged_cost = sum(p.get('amount', 0) for p in flagged_projects)
                    total_cost = sum(p.get('amount', 0) for p in subcategory_projects)
                    categories.append({
                        "category": "Multi-Purpose Buildings",
                        "subcategory": subcategory,
                        "average_cost_per_km": stats.get('mean') or 0,
                        "threshold_cost_per_km": stats.get('threshold', 0),
                        "flagged_cost": flagged_cost,
                        "total_cost": total_cost,
                        "flagged_count": len(flagged_projects),
                        "total_count": stats.get('count', len(subcategory_projects))
                    })
            else:
                 buildings_flagged = [p for p in multi_purpose_buildings if p.get('is_flagged', False)]
                 mpb_stats = mpb_data.get('statistics', {})
                 categories.append({
                    "category": "Multi-Purpose Buildings",
                    "subcategory": None,
                    "average_cost_per_km": mpb_stats.get('mean') or 0,
                    "threshold_cost_per_km": mpb_stats.get('threshold', 0),
                    "flagged_cost": sum(p.get('amount', 0) for p in buildings_flagged),
                    "total_cost": sum(p.get('amount', 0) for p in multi_purpose_buildings),
                    "flagged_count": len(buildings_flagged),
                    "total_count": len(multi_purpose_buildings)
                 })

            # Irrigation Works (NIA)
            nia_data = year_data.get('nia', {})
            nia_projects = nia_data.get('projects', [])
            nia_sub_stats = nia_data.get('subcategory_statistics', {})
            
            if nia_sub_stats:
                for subcategory, stats in nia_sub_stats.items():
                    subcategory_projects = [
                        p for p in nia_projects
                        if (p.get('nia_subcategory') or 'Other Irrigation Works') == subcategory
                    ]
                    flagged_projects = [p for p in subcategory_projects if p.get('is_flagged', False)]
                    flagged_cost = sum(p.get('amount', 0) for p in flagged_projects)
                    total_cost = sum(p.get('amount', 0) for p in subcategory_projects)
                    categories.append({
                        "category": "Irrigation Works (NIA)",
                        "subcategory": subcategory,
                        "average_cost_per_km": stats.get('mean') or 0,
                        "threshold_cost_per_km": stats.get('threshold', 0),
                        "flagged_cost": flagged_cost,
                        "total_cost": total_cost,
                        "flagged_count": len(flagged_projects),
                        "total_count": stats.get('count', len(subcategory_projects))
                    })
            elif nia_projects:
                nia_stats = nia_data.get('statistics', {})
                nia_flagged = [p for p in nia_projects if p.get('is_flagged', False)]
                categories.append({
                    "category": "Irrigation Works (NIA)",
                    "subcategory": None,
                    "average_cost_per_km": nia_stats.get('mean') or 0,
                    "threshold_cost_per_km": nia_stats.get('threshold', 0),
                    "flagged_cost": sum(p.get('amount', 0) for p in nia_flagged),
                    "total_cost": sum(p.get('amount', 0) for p in nia_projects),
                    "flagged_count": len(nia_flagged),
                    "total_count": len(nia_projects)
                })

            # Rockfall Netting
            rockfall_data = year_data.get('rockfall_netting', {})
            rockfall_netting = rockfall_data.get('projects', [])
            if rockfall_netting:
                rockfall_stats = rockfall_data.get('statistics', {})
                rockfall_flagged = [p for p in rockfall_netting if p.get('is_flagged', False)]
                categories.append({
                    "category": "Rockfall Netting",
                    "subcategory": None,
                    "average_cost_per_km": rockfall_stats.get('mean') or 0,
                    "threshold_cost_per_km": rockfall_stats.get('threshold', 0),
                    "flagged_cost": sum(p.get('amount', 0) for p in rockfall_flagged),
                    "total_cost": sum(p.get('amount', 0) for p in rockfall_netting),
                    "flagged_count": len(rockfall_flagged),
                    "total_count": len(rockfall_netting)
                })

            # Schools
            schools_data = year_data.get('schools', {})
            schools = schools_data.get('projects', [])
            schools_subcategory_stats = schools_data.get('subcategory_statistics', {})
            
            if schools_subcategory_stats:
                for subcategory, stats in schools_subcategory_stats.items():
                    subcategory_projects = [p for p in schools if p.get('school_subcategory') == subcategory]
                    flagged_projects = [p for p in subcategory_projects if p.get('is_flagged', False)]
                    flagged_cost = sum(p.get('amount', 0) for p in flagged_projects)
                    total_cost = sum(p.get('amount', 0) for p in subcategory_projects)
                    categories.append({
                        "category": "Schools",
                        "subcategory": subcategory,
                        "average_cost_per_km": stats.get('mean') or 0,
                        "threshold_cost_per_km": stats.get('threshold', 0),
                        "flagged_cost": flagged_cost,
                        "total_cost": total_cost,
                        "flagged_count": len(flagged_projects),
                        "total_count": stats.get('count', 0)
                    })
            elif schools:
                schools_stats = schools_data.get('statistics', {})
                schools_flagged = [p for p in schools if p.get('is_flagged', False)]
                categories.append({
                    "category": "Schools",
                    "subcategory": None,
                    "average_cost_per_km": schools_stats.get('mean') or 0,
                    "threshold_cost_per_km": schools_stats.get('threshold', 0),
                    "flagged_cost": sum(p.get('amount', 0) for p in schools_flagged),
                    "total_cost": sum(p.get('amount', 0) for p in schools),
                    "flagged_count": len(schools_flagged),
                    "total_count": len(schools)
                })
            
            # Sort by average_cost_per_km descending
            categories.sort(key=lambda x: x.get('average_cost_per_km') or 0, reverse=True)
            
            return JSONResponse({
                "success": True,
                "year": year,
                "categories": categories
            })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"success": False, "error": f"Error processing category statistics: {str(e)}"}, status_code=500)

@app.get("/api/budget/roads-cost-analysis-all-years")
async def budget_roads_cost_analysis_all_years_api():
    """Get aggregated road infrastructure projects cost analysis for all years (2020-2026)"""
    try:
        from collections import defaultdict
        
        all_years = ['2020', '2021', '2022', '2023', '2024', '2025', '2026']
        aggregated_stats = defaultdict(lambda: {
            'total_projects': 0,
            'total_distance_km': 0.0,
            'total_amount': 0.0
        })
        
        # Helper function to process roads data (reuse logic from budget_roads_cost_analysis_api)
        def _process_roads_data(all_items):
            """Process items and categorize into national_roads, secondary_roads, bridges, traffic_signs"""
            import re
            
            def extract_all_chainage_ranges(name: str):
                """Extract all chainage ranges from name and return list of (start_km, start_m, end_km, end_m)"""
                if not name:
                    return []

                ranges = []
                seen = set()

                def parse_number(value):
                    if value is None:
                        return 0.0
                    if isinstance(value, (int, float)):
                        return float(value)
                    cleaned = str(value).replace(',', '')
                    try:
                        return float(cleaned)
                    except ValueError:
                        cleaned = re.sub(r'[^\d\.\-]', '', cleaned)
                        return float(cleaned) if cleaned else 0.0

                def add_range(start_km, start_m, end_km, end_m):
                    key = (
                        float(parse_number(start_km)),
                        float(parse_number(start_m)),
                        float(parse_number(end_km)),
                        float(parse_number(end_m))
                    )
                    if key not in seen:
                        ranges.append(key)
                        seen.add(key)

                dash = r'[-–—]'
                number = r'\d+(?:[.,]\d+)?'

                pattern_k = rf'K({number})\s*\+\s*\(?(-?{number})\)?\s*{dash}\s*K({number})\s*\+\s*\(?(-?{number})\)?'
                for match in re.finditer(pattern_k, name, re.IGNORECASE):
                    add_range(match.group(1), match.group(2), match.group(3), match.group(4))

                pattern_chainage = rf'Chainage\s+({number})\s*{dash}\s*Chainage\s+({number})'
                for match in re.finditer(pattern_chainage, name, re.IGNORECASE):
                    start_total = parse_number(match.group(1))
                    end_total = parse_number(match.group(2))
                    add_range(start_total // 1000, start_total % 1000, end_total // 1000, end_total % 1000)

                pattern_sta = rf'Sta\.?\s*({number})\s*\+\s*({number})\s*{dash}\s*(?:Sta\.?\s*)?({number})\s*\+\s*({number})'
                for match in re.finditer(pattern_sta, name, re.IGNORECASE):
                    add_range(match.group(1), match.group(2), match.group(3), match.group(4))

                pattern_plain = rf'(?<![A-Za-z0-9])({number})\s*\+\s*({number})\s*{dash}\s*({number})\s*\+\s*({number})'
                for match in re.finditer(pattern_plain, name):
                    add_range(match.group(1), match.group(2), match.group(3), match.group(4))

                return ranges
            
            def calculate_distance(chainage_ranges):
                """Calculate total distance in kilometers from list of chainage ranges"""
                if not chainage_ranges:
                    return 0.0
                total_distance_m = 0
                def to_meters(km, m):
                    return km * 1000 + m
                for chainage_range in chainage_ranges:
                    start_km, start_m, end_km, end_m = chainage_range
                    start_total = to_meters(start_km, start_m)
                    end_total = to_meters(end_km, end_m)
                    distance_m = abs(end_total - start_total)
                    total_distance_m += distance_m
                return total_distance_m / 1000.0
            
            national_road_projects = []
            secondary_road_projects = []
            bridge_projects = []
            traffic_signs_projects = []
            nia_projects = []
            fmr_projects = []
            
            for item in all_items:
                # Use revised_name if available, otherwise fall back to name or description
                name = item.get('revised_name') or item.get('name', '') or item.get('description', '')
                if not name:
                    continue
                
                chainage_ranges = extract_all_chainage_ranges(name)
                if not chainage_ranges:
                    continue
                
                amount = abs(item.get('final_amount', 0) or item.get('original_amount', 0))
                if amount <= 0:
                    continue
                
                distance_km = calculate_distance(chainage_ranges)
                if distance_km <= 0:
                    continue
                
                # Categorize projects
                name_lower = name.lower()
                
                # Check for FMR (Farm-to-Market Road) projects first - Annex A-1
                fmr_keywords = [' fmr', 'fmr ', 'farm to market', 'farm-to-market', 'farm to market road']
                is_fmr = any(keyword in name_lower for keyword in fmr_keywords) and 'cnia' not in name_lower
                
                # Check for NIA (National Irrigation Administration) projects - Annex A-4
                nia_keywords = [
                    'national irrigation', 'irrigation system', 'irrigation project',
                    'irrigation canal', 'communal irrigation', 'irrigation sub-program',
                    'irrigation subprogram', 'irrigation facility', 'irrigation structure',
                    'annex a-4', 'communal irrigation system', 'communal irrigation project',
                    'communal irrigation scheme', 
                    # Added keywords
                    'canal lining', 'lateral canal', 'main canal', 'diversion dam', 
                    'solar powered irrigation', 'pump irrigation'
                ]
                nia_keyword_patterns = [
                    r'\bnis\b', r'\bnia\b', r'\bcis\b', r'\bcip\b', r'\bsip\b',
                    r'\bc\.i\.s\b', r'\bc\.i\.p\b', r'\bs\.i\.p\b'
                ]
                pattern_hit = any(re.search(pattern, name_lower) for pattern in nia_keyword_patterns)
                
                # Careful with 'diversion' and 'lateral' as they can be road related. 
                # Ensure we don't pick up "Diversion Road"
                keyword_hit = False
                if any(keyword in name_lower for keyword in nia_keywords):
                    if 'diversion road' not in name_lower and 'road' not in name_lower:
                        keyword_hit = True
                
                is_nia = (keyword_hit or pattern_hit) and \
                         'cnia' not in name_lower and \
                         'xdp' not in name_lower and \
                         'dystonia' not in name_lower
                
                # Check for Rockfall Netting / Slope Protection - Annex A-6
                # Broader synonyms for Rockfall Netting. 
                # Note: "Slope Protection" is very broad. "Rockfall Netting" usually implies specific tech.
                rockfall_keywords = [
                    'rockfall', 'rock fall', 'rock netting', 'rocknetting', 
                    'active wire mesh', 'high tensile wire', 'erosion control mat',
                    'soil nailing', 'rockfall protection', 'rockfall mitigation'
                ]
                
                is_rockfall = any(k in name_lower for k in rockfall_keywords)
                
                project_data = {
                    'name': name,
                    'distance_km': distance_km,
                    'amount': amount
                }
                
                if is_fmr:
                    fmr_projects.append(project_data)
                    continue  # Skip further categorization for FMR
                elif is_nia:
                    nia_projects.append(project_data)
                    continue  # Skip further categorization for NIA
                
                # Road Safety Facilities: Only categorize those WITH chainage (already filtered above)
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
                    # Categorize road safety facilities into subcategories (only those with chainage)
                    subcategories = _categorize_road_safety_facilities(name, name_lower)
                    # Defensive check: ensure subcategories is never empty
                    if not subcategories or len(subcategories) == 0:
                        subcategories = ['Road Safety Facilities']
                    project_data['road_safety_subcategories'] = subcategories
                    project_data['is_new'] = _is_new_installation(name, name_lower)
                    traffic_signs_projects.append(project_data)
                elif is_bridge:
                    bridge_projects.append(project_data)
                elif is_road_term or not is_bridge:
                    # Categorize road work type (if found)
                    work_types = _categorize_road_work_type(name, name_lower)
                    if work_types:
                        # Store as list for composite work types
                        project_data['work_type'] = work_types[0] if len(work_types) == 1 else work_types
                        project_data['work_types'] = work_types  # Always store full list
                    else:
                        project_data['work_type'] = None
                        project_data['work_types'] = []
                    
                    # Determine if it's new construction or maintenance
                    # If no work type, it's automatically new construction
                    project_data['is_new_construction'] = _is_new_construction(work_types, name, name_lower)
                    
                    # Determine if it's a major road using classification rules
                    is_major_road = _is_major_road(name, chainage_ranges)
                    if is_major_road:
                        national_road_projects.append(project_data)
                    else:
                        secondary_road_projects.append(project_data)
                else:
                    secondary_road_projects.append(project_data)
            
            return {
                'national_roads': national_road_projects,
                'secondary_roads': secondary_road_projects,
                'bridges': bridge_projects,
                'traffic_signs': traffic_signs_projects,
                'nia': nia_projects,
                'fmr': fmr_projects
            }
        
        # Load historical data for 2020-2025
        historical_path = Path('static/data/historical_roads_2020_2025.json')
        historical_data = {}
        if historical_path.exists():
            with open(historical_path, 'r', encoding='utf-8') as f:
                historical_data = json.load(f)
                print(f"✅ [All Years API] Loaded historical data with years: {list(historical_data.get('data', {}).keys())}")
        else:
            print(f"⚠️ [All Years API] Historical data file not found: {historical_path}")
        
        # Process each year
        for year in all_years:
            if year == '2026':
                # Use budget_amendments_2026.json for 2026
                json_path = Path(f'static/data/budget_amendments_{year}.json')
                if not json_path.exists():
                    print(f"⚠️ [All Years API] 2026 data file not found: {json_path}")
                    continue
                
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                all_items = data.get('line_items', []) + data.get('projects', [])
                processed_data = _process_roads_data(all_items)
                print(f"✅ [All Years API] Processed 2026: {sum(len(projects) for projects in processed_data.values())} total projects")
            else:
                # Use historical_roads_2020_2025.json for 2020-2025
                # Historical data is already processed, so we can use it directly
                year_data = historical_data.get('data', {}).get(year, {})
                if not year_data:
                    print(f"⚠️ [All Years API] No data found for year {year}")
                    continue
                
                # Historical data already has processed projects by category
                processed_data = {
                    'national_roads': year_data.get('national_roads', []),
                    'secondary_roads': year_data.get('secondary_roads', []),
                    'bridges': year_data.get('bridges', []),
                    'traffic_signs': year_data.get('traffic_signs', []),
                    'multi_purpose_buildings': year_data.get('multi_purpose_buildings', []),
                    'rockfall_netting': year_data.get('rockfall_netting', []),
                    'schools': year_data.get('schools', [])
                }
                total_projects_year = sum(len(projects) for projects in processed_data.values())
                print(f"✅ [All Years API] Processed {year}: {total_projects_year} total projects")
            
            # Aggregate statistics for each category
            for category, projects in processed_data.items():
                aggregated_stats[category]['total_projects'] += len(projects)
                aggregated_stats[category]['total_distance_km'] += sum(p.get('distance_km', 0) for p in projects)
                aggregated_stats[category]['total_amount'] += sum(p.get('amount', 0) for p in projects)
        
        # Log final aggregated stats
        print(f"📊 [All Years API] Final aggregated stats:")
        for category, stats in aggregated_stats.items():
            print(f"  {category}: {stats['total_projects']} projects, {stats['total_distance_km']:.2f} km, ₱{stats['total_amount']/1e9:.2f}B")
        
        # Convert defaultdict to regular dict for JSONResponse
        result = {category: dict(stats) for category, stats in aggregated_stats.items()}
        
        # Ensure all categories are present even if empty
        for category in ['national_roads', 'secondary_roads', 'bridges', 'traffic_signs', 'nia', 'fmr', 'multi_purpose_buildings', 'rockfall_netting', 'schools']:
            if category not in result:
                result[category] = {
                    'total_projects': 0,
                    'total_distance_km': 0.0,
                    'total_amount': 0.0
                }
        
        print(f"📊 [All Years API] Returning result with categories: {list(result.keys())}")
        for category, stats in result.items():
            print(f"  {category}: {stats['total_projects']} projects, {stats['total_distance_km']:.2f} km, ₱{stats['total_amount']/1e9:.2f}B")
        
        return JSONResponse({"success": True, **result})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/budget/roads-statistics-all-years")
async def budget_roads_statistics_all_years_api():
    """Get road infrastructure statistics for all years (2020-2026) including historical data"""
    try:
        import statistics
        from collections import Counter
        
        # Load 2026 data
        json_path_2026 = Path('static/data/budget_amendments_2026.json')
        historical_path = Path('static/data/historical_roads_2020_2025.json')
        
        if not json_path_2026.exists():
            return JSONResponse({"success": False, "error": "2026 budget amendments data not available"}, status_code=404)
        
        if not historical_path.exists():
            return JSONResponse({"success": False, "error": "Historical roads data not available. Please run: python3 scripts/extract_historical_roads.py"}, status_code=404)
        
        # Load 2026 data
        with open(json_path_2026, 'r', encoding='utf-8') as f:
            data_2026 = json.load(f)
        
        # Load historical data
        with open(historical_path, 'r', encoding='utf-8') as f:
            historical_data = json.load(f)
        
        # Process 2026 data (same logic as roads-cost-analysis)
        import re
        all_items_2026 = data_2026.get('line_items', []) + data_2026.get('projects', [])
        
        def extract_all_chainage_ranges(name: str):
            if not name:
                return []

            ranges = []
            seen = set()

            def add_range(start_km, start_m, end_km, end_m):
                key = (int(start_km), int(start_m), int(end_km), int(end_m))
                if key not in seen:
                    seen.add(key)
                    ranges.append(key)

            pattern_k = r'K(\d+)\s*\+\s*\(?(-?\d+)\)?\s*-\s*K(\d+)\s*\+\s*\(?(-?\d+)\)?'
            for match in re.finditer(pattern_k, name, re.IGNORECASE):
                add_range(match.group(1), match.group(2), match.group(3), match.group(4))

            pattern_chainage = r'Chainage\s+(\d+)\s*-\s*Chainage\s+(\d+)'
            for match in re.finditer(pattern_chainage, name, re.IGNORECASE):
                start_total = int(match.group(1))
                end_total = int(match.group(2))
                add_range(start_total // 1000, start_total % 1000, end_total // 1000, end_total % 1000)

            pattern_sta = r'Sta\.?\s*(\d+)\+(\d+)\s*-\s*(?:Sta\.?\s*)?(\d+)\+(\d+)'
            for match in re.finditer(pattern_sta, name, re.IGNORECASE):
                add_range(match.group(1), match.group(2), match.group(3), match.group(4))

            pattern_plain = r'(?<![A-Za-z0-9])(\d+)\s*\+\s*(\d+)\s*-\s*(\d+)\s*\+\s*(\d+)'
            for match in re.finditer(pattern_plain, name):
                add_range(match.group(1), match.group(2), match.group(3), match.group(4))

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
            if len(individual_distances_m) > 1:
                breakdown = ' + '.join([f'{int(d)}m' for d in individual_distances_m]) + f' = {int(total_distance_m)}m'
            else:
                breakdown = None
            return distance_km, breakdown, individual_distances_m
        
        def calculate_statistics(projects):
            if not projects:
                return {
                    "min": None, "max": None, "mean": None, "median": None,
                    "mode": None, "std_dev": None, "mad": None, "threshold": None, "count": 0
                }
            costs = [p['cost_per_km'] for p in projects if p.get('cost_per_km', 0) > 0]
            if not costs:
                return {
                    "min": None, "max": None, "mean": None, "median": None,
                    "mode": None, "std_dev": None, "mad": None, "threshold": None, "count": 0
                }
            costs_sorted = sorted(costs)
            mean = statistics.mean(costs)
            median_val = statistics.median(costs_sorted)
            deviations = [abs(c - median_val) for c in costs_sorted]
            mad = statistics.median(deviations) if deviations else 0
            threshold = median_val + (MAD_SCALE * mad) if mad else None

            rounded_costs = [round(c / 1000000) * 1000000 for c in costs]
            cost_counter = Counter(rounded_costs)
            mode_value = cost_counter.most_common(1)[0][0] if cost_counter else None
            try:
                std_dev = statistics.stdev(costs) if len(costs) > 1 else 0
            except statistics.StatisticsError:
                std_dev = 0
            return {
                "min": min(costs), "max": max(costs), "mean": mean,
                "median": median_val, "mode": mode_value,
                "std_dev": std_dev, "mad": mad, "threshold": threshold, "count": len(costs)
            }
        
        # Process 2026 projects
        projects_2026 = {'roads': [], 'national_roads': [], 'secondary_roads': [], 'bridges': [], 'traffic_signs': [], 'nia': [], 'fmr': []}
        for item in all_items_2026:
            # Use revised_name if available, otherwise fall back to name or description
            name = item.get('revised_name') or item.get('name', '') or item.get('description', '')
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
            name_lower = name.lower()
            
            # Check for FMR (Farm-to-Market Road) projects first - Annex A-1
            fmr_keywords = [' fmr', 'fmr ', 'farm to market', 'farm-to-market', 'farm to market road']
            is_fmr = any(keyword in name_lower for keyword in fmr_keywords) and 'cnia' not in name_lower
            
            # Check for NIA (National Irrigation Administration) projects - Annex A-4
            nia_keywords = [
                'national irrigation', 'irrigation system', 'irrigation project', 
                'irrigation canal', 'communal irrigation', 'irrigation sub-program',
                'irrigation subprogram', 'irrigation facility', 'irrigation structure'
            ]
            is_nia = any(keyword in name_lower for keyword in nia_keywords) and \
                     'cnia' not in name_lower and \
                     'xdp' not in name_lower and \
                     'dystonia' not in name_lower
            
            project_data = {'cost_per_km': cost_per_km, 'amount': amount, 'distance_km': distance_km}
            
            if is_fmr:
                projects_2026['fmr'].append(project_data)
            elif is_nia:
                projects_2026['nia'].append(project_data)
            else:
                # Road Safety Facilities: Only categorize those WITH chainage (already filtered above)
                road_safety_keywords = [
                    'installation', 'road safety', 'guardrail', 'traffic facilities', 'traffic facility',
                    'lighting', 'streetlight', 'street light', 'led', 'solar', 'roadway lighting',
                    'road sign', 'pavement marking', 'barrier', 'pedestrian overpass'
                ]
                is_road_safety = any(keyword in name_lower for keyword in road_safety_keywords)
                
                # Bridges: projects with bridge-related keywords ONLY (no distance heuristic to avoid false positives)
                bridge_keywords = ['bridge', 'viaduct', 'flyover', 'overpass', 'underpass', 'footbridge', 'pedestrian bridge']
                is_bridge = any(keyword in name_lower for keyword in bridge_keywords)
                
                # Road-related terms (these indicate roads, not bridges)
                road_terms = [
                    ' road', ' rd', ' highway', ' hiway', ' hway', ' h-way',
                    'boulevard', ' blvd', ' avenue', ' ave', ' ave.',
                    'junction', ' jct', ' old route', ' diversion',
                    'extension', ' ext', ' street', ' st', ' st.',
                    'expressway'
                ]
                is_road_term = any(term in name_lower for term in road_terms)
                
                if is_road_safety:
                    projects_2026['traffic_signs'].append(project_data)
                elif is_bridge:
                    projects_2026['bridges'].append(project_data)
                else:
                    # Categorize road work type (if found)
                    work_type = _categorize_road_work_type(name, name_lower)
                    if work_type:
                        project_data['work_type'] = work_type
                    
                    # Separate into national and secondary roads
                    is_major = _is_major_road(name, chainage_ranges)
                    if is_major:
                        projects_2026['national_roads'].append(project_data)
                    else:
                        projects_2026['secondary_roads'].append(project_data)
                projects_2026['roads'].append(project_data)  # Combined for backward compatibility
        
        # Combine historical data (2020-2025) with 2026
        all_years_data = {}
        years = [2020, 2021, 2022, 2023, 2024, 2025, 2026]
        
        # Process historical years (handle both string and int keys)
        for year in years[:-1]:  # 2020-2025
            year_key = str(year)  # Historical data uses string keys
            if year_key in historical_data.get('data', {}):
                year_data = historical_data['data'][year_key]
                all_years_data[year] = {
                    'roads': [{'cost_per_km': p['cost_per_km'], 'amount': p['amount'], 'distance_km': p['distance_km']} for p in year_data.get('roads', [])],
                    'national_roads': [{'cost_per_km': p['cost_per_km'], 'amount': p['amount'], 'distance_km': p['distance_km']} for p in year_data.get('national_roads', [])],
                    'secondary_roads': [{'cost_per_km': p['cost_per_km'], 'amount': p['amount'], 'distance_km': p['distance_km']} for p in year_data.get('secondary_roads', [])],
                    'bridges': [{'cost_per_km': p['cost_per_km'], 'amount': p['amount'], 'distance_km': p['distance_km']} for p in year_data.get('bridges', [])],
                    'traffic_signs': [{'cost_per_km': p['cost_per_km'], 'amount': p['amount'], 'distance_km': p['distance_km']} for p in year_data.get('traffic_signs', [])],
                    'nia': [{'cost_per_km': p['cost_per_km'], 'amount': p['amount'], 'distance_km': p['distance_km']} for p in year_data.get('nia', [])],
                    'fmr': [{'cost_per_km': p['cost_per_km'], 'amount': p['amount'], 'distance_km': p['distance_km']} for p in year_data.get('fmr', [])]
                }
        
        # Add 2026
        all_years_data[2026] = projects_2026
        
        # Calculate statistics for each year and category
        result = {}
        for year in years:
            result[year] = {
                'roads': calculate_statistics(all_years_data.get(year, {}).get('roads', [])),
                'national_roads': calculate_statistics(all_years_data.get(year, {}).get('national_roads', [])),
                'secondary_roads': calculate_statistics(all_years_data.get(year, {}).get('secondary_roads', [])),
                'bridges': calculate_statistics(all_years_data.get(year, {}).get('bridges', [])),
                'traffic_signs': calculate_statistics(all_years_data.get(year, {}).get('traffic_signs', [])),
                'nia': calculate_statistics(all_years_data.get(year, {}).get('nia', [])),
                'fmr': calculate_statistics(all_years_data.get(year, {}).get('fmr', []))
            }
        
        # Calculate totals (aggregate all years)
        total_roads = []
        total_national_roads = []
        total_secondary_roads = []
        total_bridges = []
        total_traffic_signs = []
        total_nia = []
        total_fmr = []
        for year in years:
            total_roads.extend(all_years_data.get(year, {}).get('roads', []))
            total_national_roads.extend(all_years_data.get(year, {}).get('national_roads', []))
            total_secondary_roads.extend(all_years_data.get(year, {}).get('secondary_roads', []))
            total_bridges.extend(all_years_data.get(year, {}).get('bridges', []))
            total_traffic_signs.extend(all_years_data.get(year, {}).get('traffic_signs', []))
            total_nia.extend(all_years_data.get(year, {}).get('nia', []))
            total_fmr.extend(all_years_data.get(year, {}).get('fmr', []))
        
        result['total'] = {
            'roads': calculate_statistics(total_roads),
            'national_roads': calculate_statistics(total_national_roads),
            'secondary_roads': calculate_statistics(total_secondary_roads),
            'bridges': calculate_statistics(total_bridges),
            'traffic_signs': calculate_statistics(total_traffic_signs),
            'nia': calculate_statistics(total_nia),
            'fmr': calculate_statistics(total_fmr)
        }
        
        return JSONResponse({"success": True, "statistics": result})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

_reblocking_cache_by_year = {}
_reblocking_cache_mtime_by_year = {}

def _load_reblocking_cache(year: str = "2026"):
    """Load reblocking analysis cache for a specific year (cached in memory with file modification time check)"""
    global _reblocking_cache_by_year, _reblocking_cache_mtime_by_year
    
    # Try year-specific cache file first
    json_path = Path(f'static/data/reblocking_analysis_{year}.json')
    
    # Fallback to old format for 2026 only if year-specific doesn't exist
    if not json_path.exists() and year == "2026":
        old_path = Path('static/data/reblocking_analysis.json')
        if old_path.exists():
            json_path = old_path
    
    if not json_path.exists():
        print(f"⚠️ Reblocking cache file not found for year {year}: {json_path}")
        return None
    
    # Check if file was modified
    try:
        current_mtime = json_path.stat().st_mtime
        cache_key = f"{year}_{json_path}"
        
        if cache_key not in _reblocking_cache_by_year or _reblocking_cache_mtime_by_year.get(cache_key) != current_mtime:
            print(f"📂 Loading reblocking cache for year {year} from {json_path}")
            with open(json_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                _reblocking_cache_by_year[cache_key] = cache_data
                _reblocking_cache_mtime_by_year[cache_key] = current_mtime
            print(f"✅ Loaded {cache_data.get('total_highways', 0)} highways for year {year}")
        
        return _reblocking_cache_by_year[cache_key]
    except Exception as e:
        print(f"❌ Error loading reblocking cache for year {year}: {e}")
        import traceback
        traceback.print_exc()
        return None

@app.get("/api/budget/reblocking-analysis")
async def budget_reblocking_analysis_api(year: str = Query("2026", description="Year to filter by (2020-2026 or 'total' for all years)")):
    """Get highway reblocking analysis - major highways with chainage data, cost per km, and anomaly detection"""
    try:
        # Handle "total" or "all" to combine all years
        if year.lower() in ['total', 'all', 'combined']:
            from collections import defaultdict
            
            all_years = ['2020', '2021', '2022', '2023', '2024', '2025', '2026']
            combined_highways = defaultdict(lambda: {
                'highway': None,
                'estimated_length_km': 0,
                'main_project': None,
                'total_segments': 0,
                'total_distance_km': 0,
                'total_amount': 0,
                'segments': [],
                'years': []
            })
            
            total_highways = 0
            total_segments = 0
            total_distance_km = 0
            total_amount = 0
            total_anomalies = 0
            
            # Load and combine data from all years
            for year_str in all_years:
                year_data = _load_reblocking_cache(year_str)
                if year_data and year_data.get('highways'):
                    for highway_data in year_data['highways']:
                        highway_name = highway_data.get('highway')
                        if not highway_name:
                            continue
                        
                        hw = combined_highways[highway_name]
                        if hw['highway'] is None:
                            hw['highway'] = highway_name
                            hw['estimated_length_km'] = highway_data.get('estimated_length_km', 0)
                            hw['main_project'] = highway_data.get('main_project')
                            total_highways += 1
                        
                        # Add segments from this year
                        segments = highway_data.get('segments', [])
                        for segment in segments:
                            # Add year info to segment
                            segment_with_year = segment.copy()
                            segment_with_year['year'] = year_str
                            hw['segments'].append(segment_with_year)
                        
                        # Aggregate totals
                        hw['total_segments'] += highway_data.get('total_segments', 0)
                        hw['total_distance_km'] += highway_data.get('total_distance_km', 0)
                        hw['total_amount'] += highway_data.get('total_amount', 0)
                        
                        # Track which years this highway appears in
                        if year_str not in hw['years']:
                            hw['years'].append(year_str)
                        
                        # Count anomalies
                        for segment in segments:
                            if segment.get('is_anomaly', False):
                                total_anomalies += 1
                    
                    # Update overall totals
                    total_segments += year_data.get('total_segments', 0)
                    total_distance_km += year_data.get('total_distance_km', 0)
                    total_amount += year_data.get('total_amount', 0)
            
            # Convert to list and sort by highway name
            highways_list = list(combined_highways.values())
            highways_list.sort(key=lambda x: x['highway'] or '')
            
            # Update main_project to be the one with highest amount
            for hw in highways_list:
                if hw['segments']:
                    hw['main_project'] = max(hw['segments'], key=lambda s: s.get('amount', 0))
            
            return JSONResponse({
                "success": True,
                "year": "total",
                "highways": highways_list,
                "total_highways": total_highways,
                "total_segments": total_segments,
                "total_distance_km": total_distance_km,
                "total_amount": total_amount,
                "total_anomalies": total_anomalies
            })
        
        # Handle individual year
        data = _load_reblocking_cache(year)
        if data is None:
            return JSONResponse({
                "success": False, 
                "error": f"Reblocking analysis data for {year} not available. Please run: python3 scripts/generate_reblocking_cache.py {year}",
                "year": year,
                "highways": [],
                "total_highways": 0,
                "total_segments": 0,
                "total_distance_km": 0,
                "total_anomalies": 0
            }, status_code=404)
        
        # Ensure year is set in response
        if "year" not in data:
            data["year"] = year
        
        return JSONResponse({"success": True, **data})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/budget/reblocking-statistics-all-years")
async def budget_reblocking_statistics_all_years_api():
    """Get reblocking statistics for all years (2020-2026) for year-on-year trend analysis"""
    try:
        all_years = ['2020', '2021', '2022', '2023', '2024', '2025', '2026']
        statistics = {}
        
        for year in all_years:
            data = _load_reblocking_cache(year)
            if data:
                statistics[year] = {
                    'total_highways': data.get('total_highways', 0),
                    'total_segments': data.get('total_segments', 0),
                    'total_distance_km': data.get('total_distance_km', 0),
                    'total_anomalies': data.get('total_anomalies', 0)
                }
            else:
                statistics[year] = {
                    'total_highways': 0,
                    'total_segments': 0,
                    'total_distance_km': 0,
                    'total_anomalies': 0
                }
        
        return JSONResponse({
            "success": True,
            "statistics": statistics
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/budget/anti-zero-analysis")
async def budget_anti_zero_analysis_api():
    """Get analysis of uniform decrease patterns in Annex A-5 projects (Column O to Column S)"""
    try:
        from collections import defaultdict
        
        # Load uniform decreases data (all patterns)
        uniform_path = Path('static/data/annex_a5_uniform_decreases.json')
        if uniform_path.exists():
            with open(uniform_path, 'r', encoding='utf-8') as f:
                uniform_data = json.load(f)
            
            patterns = uniform_data.get('patterns', [])
            metadata = uniform_data.get('metadata', {})
            
            # Group by decrease percentage for chart
            by_percentage = []
            for pattern in patterns:
                by_percentage.append({
                    'decrease_percentage': pattern['decrease_percentage'],
                    'match_count': pattern['match_count'],
                    'total_column_o_amount': pattern['total_column_o_amount'],
                    'total_column_s_amount': pattern['total_column_s_amount'],
                    'total_decrease': pattern['total_decrease']
                })
            
            # Sort by percentage for chart
            by_percentage.sort(key=lambda x: x['decrease_percentage'])
            
            total_projects = metadata.get('total_projects', 0)
            total_matches = sum(p['match_count'] for p in patterns)
            percentage = (total_matches / total_projects * 100) if total_projects > 0 else 0.0
            
            summary = {
                "total_matches": total_matches,
                "total_projects": total_projects,
                "percentage": percentage,
                "unique_patterns": len(patterns),
                "total_column_o_amount": sum(p['total_column_o_amount'] for p in patterns),
                "total_column_s_amount": sum(p['total_column_s_amount'] for p in patterns),
                "total_decrease": sum(p['total_decrease'] for p in patterns)
            }
            
            return JSONResponse({
                "success": True,
                "summary": summary,
                "by_percentage": by_percentage,
                "top_patterns": sorted(patterns, key=lambda x: x['match_count'], reverse=True)[:20]
            })
        
        # Fallback to old 3.1906% data if uniform decreases not available
        json_path = Path('static/data/annex_a5_decreased_31pct.json')
        if not json_path.exists():
            return JSONResponse({"success": False, "error": "Anti-zero analysis data not available. Please run scripts/find_uniform_decreases.py first."}, status_code=404)
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        matches = data.get('matches', [])
        metadata = data.get('metadata', {})
        
        if not matches:
            return JSONResponse({
                "success": True,
                "summary": {
                    "total_matches": 0,
                    "total_projects": metadata.get('total_items', 0),
                    "percentage": 0.0,
                    "unique_patterns": 0,
                    "total_column_o_amount": 0,
                    "total_column_s_amount": 0,
                    "total_decrease": 0
                },
                "by_percentage": [],
                "top_patterns": []
            })
        
        # For single pattern, create by_percentage array
        total_projects = metadata.get('total_items', 0)
        percentage = (len(matches) / total_projects * 100) if total_projects > 0 else 0.0
        
        total_o = sum(m['project']['column_o_amount'] for m in matches)
        total_s = sum(m['project']['column_s_amount'] for m in matches)
        
        summary = {
            "total_matches": len(matches),
            "total_projects": total_projects,
            "percentage": percentage,
            "unique_patterns": 1,
            "total_column_o_amount": total_o,
            "total_column_s_amount": total_s,
            "total_decrease": total_o - total_s
        }
        
        # Get the decrease percentage from first match
        first_decrease = matches[0]['decrease']['percentage'] if matches else 0
        
        return JSONResponse({
            "success": True,
            "summary": summary,
            "by_percentage": [{
                'decrease_percentage': first_decrease,
                'match_count': len(matches),
                'total_column_o_amount': total_o,
                'total_column_s_amount': total_s,
                'total_decrease': total_o - total_s
            }],
            "top_patterns": []
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/budget/anomalies/count")
async def budget_anomalies_count_api(year: str = "2025"):
    """Get count of budget anomalies for a specific year - no authentication required"""
    try:
        from budget_postgres_client import get_budget_anomalies_count
        result = await get_budget_anomalies_count(year)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/data-browser")
async def budget_data_browser_api(
    year: str = "2025",
    page: int = 1,
    limit: int = 50,
    sort_by: str = "amt",
    sort_order: str = "DESC",
    department: str = None,
    uacs_dpt_dsc: str = None,
    agency: str = None,
    uacs_agy_dsc: str = None,
    dsc: str = None,
    uacs_fundsubcat_dsc: str = None,
    uacs_exp_dsc: str = None,
    uacs_sobj_dsc: str = None,
    uacs_div_dsc: str = None,
    uacs_reg_id: str = None,
    amt_min: float = None,
    amt_max: float = None,
):
    """Get paginated budget data browser from PostgreSQL with filtering - no authentication required"""
    try:
        # Build filters dictionary
        filters = {}
        if department:
            filters['department'] = department
        if uacs_dpt_dsc:
            filters['uacs_dpt_dsc'] = uacs_dpt_dsc
        if agency:
            filters['agency'] = agency
        if uacs_agy_dsc:
            filters['uacs_agy_dsc'] = uacs_agy_dsc
        if dsc:
            filters['dsc'] = dsc
        if uacs_fundsubcat_dsc:
            filters['uacs_fundsubcat_dsc'] = uacs_fundsubcat_dsc
        if uacs_exp_dsc:
            filters['uacs_exp_dsc'] = uacs_exp_dsc
        if uacs_sobj_dsc:
            filters['uacs_sobj_dsc'] = uacs_sobj_dsc
        if uacs_div_dsc:
            filters['uacs_div_dsc'] = uacs_div_dsc
        if uacs_reg_id:
            filters['uacs_reg_id'] = uacs_reg_id
        if amt_min is not None:
            filters['amt_min'] = amt_min
        if amt_max is not None:
            filters['amt_max'] = amt_max

        from budget_postgres_client import get_budget_data_browser
        result = await get_budget_data_browser(year, page, limit, sort_by, sort_order, filters)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/nep/anomalies/count")
async def nep_anomalies_count_api(year: str = "2026"):
    """Get NEP anomalies count - no authentication required"""
    try:
        result = await get_nep_anomalies_count(year)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/nep/data-browser")
async def nep_data_browser_api(year: str = "2025", page: int = 1, limit: int = 1):
    """Get NEP data browser - no authentication required"""
    try:
        result = await get_nep_data_browser(year, page, limit)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/nep/year-over-year")
async def nep_year_over_year_api():
    """Get NEP year-over-year data - no authentication required"""
    try:
        # Check for pre-generated cache first
        cache_file = Path(__file__).parent / "static" / "data" / "api_cache" / "nep_year_over_year_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                if cache_data.get('success'):
                    print(f"✅ [/api/budget/nep/year-over-year] Using cached data from {cache_file.name}")
                    return JSONResponse(cache_data)
            except Exception as cache_err:
                print(f"⚠️ [/api/budget/nep/year-over-year] Error reading cache, falling back to processing: {cache_err}")
        
        from nep_client import get_nep_year_over_year
        result = await get_nep_year_over_year()
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/nep/top-programs")
async def nep_top_programs_api(year: str = "2025", limit: int = 10):
    """Get top NEP programs - no authentication required"""
    try:
        # Check for pre-generated cache first
        cache_file = Path(__file__).parent / "static" / "data" / "api_cache" / "nep_top_programs_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                if cache_data.get('success'):
                    # Check if year-specific data exists
                    year_data = cache_data.get('data', {}).get(year)
                    if year_data:
                        print(f"✅ [/api/budget/nep/top-programs] Using cached data for year {year}")
                        # Apply limit if needed
                        if limit < 20 and year_data.get('programs'):
                            year_data = year_data.copy()
                            year_data['programs'] = year_data['programs'][:limit]
                        return JSONResponse(year_data)
            except Exception as cache_err:
                print(f"⚠️ [/api/budget/nep/top-programs] Error reading cache, falling back to processing: {cache_err}")
        
        from nep_client import get_nep_top_programs
        result = await get_nep_top_programs(year, limit)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/nep/overview/stats")
async def nep_overview_stats_api(year: str = Query("2026", description="Year to filter by")):
    """Get NEP overview statistics - no authentication required"""
    try:
        result = await get_nep_overview_stats(year)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/nep/departments")
async def nep_departments_api(year: str = "2026", limit: int = 8):
    """Get NEP departments - no authentication required"""
    try:
        result = await get_nep_departments(year, limit)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/nep/expense-categories")
async def nep_expense_categories_api(year: str = "2026", limit: int = 8):
    """Get NEP expense categories - no authentication required"""
    try:
        result = await get_nep_expense_categories(year, limit)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/nep/regions")
async def nep_regions_api(year: str = "2026", limit: int = 8):
    """Get NEP regions - no authentication required"""
    try:
        result = await get_nep_regions(year, limit)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/nep/agencies")
async def nep_agencies_api(year: str = "2026", limit: int = 10):
    """Get NEP agencies - no authentication required"""
    try:
        result = await get_nep_agencies(year, limit)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/nep/columns")
async def nep_columns_api(year: str = "2024"):
    """Get NEP columns - no authentication required"""
    try:
        result = await get_nep_columns(year)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/nep/duplicates/count")
async def nep_duplicates_count_api(year: str = "2026"):
    """Get NEP duplicates count - no authentication required"""
    try:
        result = await get_nep_duplicates_count(year)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/nep/total-items/count")
async def nep_total_items_count_api(year: str = "2026"):
    """Get NEP total items count - no authentication required"""
    try:
        result = await get_nep_total_items_count(year)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/columns")
async def budget_columns_api(year: str = "2024"):
    """Get budget columns - no authentication required"""
    try:
        result = await get_budget_columns(year)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/overview/stats")
async def budget_overview_stats_api(year: str = Query(None, description="Year to filter by (optional)")):
    """Get budget overview statistics - no authentication required"""
    try:
        result = await get_budget_overview_stats(year)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/departments")
async def budget_departments_api(year: str = "2025", limit: int = 10):
    """Get budget departments - no authentication required"""
    try:
        result = await get_budget_departments(year, limit)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/expense-categories")
async def budget_expense_categories_api(year: str = "2025", limit: int = 8):
    """Get budget expense categories - no authentication required"""
    try:
        result = await get_budget_expense_categories(year, limit)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/regions")
async def budget_regions_api(year: str = "2025", limit: int = 8):
    """Get budget regions - no authentication required"""
    try:
        # Check for pre-generated cache first
        cache_file = Path(__file__).parent / "static" / "data" / "api_cache" / "budget_regions_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                if cache_data.get('success'):
                    year_data = cache_data.get('data', {}).get(year)
                    if year_data:
                        print(f"✅ [/api/budget/regions] Using cached data for year {year}")
                        # Apply limit if needed
                        if limit < 1000 and year_data.get('regions'):
                            year_data = year_data.copy()
                            year_data['regions'] = year_data['regions'][:limit]
                        return JSONResponse(year_data)
            except Exception as cache_err:
                print(f"⚠️ [/api/budget/regions] Error reading cache, falling back to processing: {cache_err}")
        
        result = await get_budget_regions(year, limit)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/agencies")
async def budget_agencies_api(year: str = "2025", limit: int = 10):
    """Get budget agencies - no authentication required"""
    try:
        result = await get_budget_agencies(year, limit)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/department-trends")
async def budget_department_trends_api():
    """Get department spending trends for 2020-2025 with percent changes - no authentication required"""
    try:
        # Check for pre-generated cache first
        cache_file = Path(__file__).parent / "static" / "data" / "api_cache" / "budget_department_trends_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                if cache_data.get('success'):
                    print(f"✅ [/api/budget/department-trends] Using cached data from {cache_file.name}")
                    return JSONResponse(cache_data)
            except Exception as cache_err:
                print(f"⚠️ [/api/budget/department-trends] Error reading cache, falling back to processing: {cache_err}")
        
        from budget_postgres_client import get_budget_department_trends
        result = await get_budget_department_trends()
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e), "departments": []})

@app.get("/api/budget/columns/issues")
async def budget_columns_issues_api(year: str = "2025", page: int = 1, limit: int = 10):
    """Get budget column issues for a specific year with pagination - no authentication required"""
    try:
        from budget_postgres_client import get_budget_columns_issues, get_budget_column_issues_count
        result = await get_budget_columns_issues(year, limit, (page - 1) * limit)
        count_result = await get_budget_column_issues_count(year)
        total_items = count_result.get("count", 0) if count_result.get("success") else 0
        total_pages = max(1, (total_items + limit - 1) // limit)
        if result.get("success"):
            result["pagination"] = {
                "current_page": page,
                "total_pages": total_pages,
                "total_items": total_items,
                "limit": limit
            }
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e), "issues": []})

@app.get("/api/budget/columns/differences")
async def budget_columns_differences_api():
    """Get column differences between years - no authentication required"""
    try:
        from budget_postgres_client import get_budget_columns_differences
        result = await get_budget_columns_differences()
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e), "differences": []})

@app.get("/api/budget/column-mapping")
async def budget_column_mapping_api():
    """Get 2020-2021 column mapping information - no authentication required"""
    try:
        from budget_postgres_client import get_column_mapping_2020_2021
        result = await get_column_mapping_2020_2021()
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

# ===== BUDGET AMENDMENTS (FY 2026) ENDPOINTS =====
_amendments_cache = None

def load_amendments_data():
    """Load FY 2026 budget amendments data from JSON"""
    global _amendments_cache
    json_path = DATA_ROOT / "budget_amendments_2026.json"
    if not json_path.exists():
        print(f"⚠️ [Budget Amendments] JSON file not found at: {json_path}")
        return None
    try:
        # Check file modification time to reload if file has changed
        import os
        file_mtime = os.path.getmtime(json_path)
        cache_mtime = getattr(load_amendments_data, '_cache_mtime', None)
        
        # Reload if cache is empty or file has been modified
        if _amendments_cache is None or cache_mtime != file_mtime:
            with open(json_path, 'r', encoding='utf-8') as f:
                _amendments_cache = json.load(f)
            load_amendments_data._cache_mtime = file_mtime
            print(f"✅ [Budget Amendments] Loaded {len(_amendments_cache.get('departments', []))} departments from {json_path}")
        
        return _amendments_cache
    except Exception as e:
        print(f"❌ [Budget Amendments] Error loading JSON from {json_path}: {e}")
        import traceback
        traceback.print_exc()
        return None

@app.get("/api/budget/amendments/summary")
async def budget_amendments_summary():
    """Get FY 2026 budget amendments summary statistics"""
    try:
        data = load_amendments_data()
        if not data:
            return JSONResponse({"success": False, "error": "Data not available"}, status_code=404)
        return JSONResponse({"success": True, **data['metadata']})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/budget/amendments/departments")
async def budget_amendments_departments():
    """Get all top-level departments (excluding agencies) with budget amendment summary"""
    try:
        # Check for pre-generated cache first
        cache_file = Path(__file__).parent / "static" / "data" / "api_cache" / "budget_amendments_departments_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                if cache_data.get('success'):
                    print(f"✅ [/api/budget/amendments/departments] Using cached data from {cache_file.name}")
                    return JSONResponse(cache_data)
            except Exception as cache_err:
                print(f"⚠️ [/api/budget/amendments/departments] Error reading cache, falling back to processing: {cache_err}")
        
        data = load_amendments_data()
        if not data:
            return JSONResponse({"success": False, "error": "Data not available"}, status_code=404)
        # Filter out agencies - only return top-level departments
        departments = [
            d for d in data['departments'] 
            if not d.get('is_agency', False)  # Exclude agencies
        ]
        departments = sorted(departments, key=lambda d: d.get('original_amount', 0), reverse=True)
        return JSONResponse({"success": True, "departments": departments, "metadata": data['metadata']})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/budget/amendments/department/{dept_id}")
async def budget_amendments_department_details(dept_id: str):
    """Get programs within a department with enriched descriptions from budget database"""
    try:
        # URL decode the department ID in case it contains special characters
        from urllib.parse import unquote
        dept_id = unquote(dept_id)
        
        data = load_amendments_data()
        if not data:
            return JSONResponse({"success": False, "error": "Data not available"}, status_code=404)
        
        # Try exact match first
        department = next((d for d in data['departments'] if d['id'] == dept_id), None)
        
        # If not found, try matching without any colon suffix (e.g., "DIC:1" -> "DIC")
        if not department and ':' in dept_id:
            dept_id_base = dept_id.split(':')[0]
            department = next((d for d in data['departments'] if d['id'] == dept_id_base), None)
            if department:
                dept_id = dept_id_base  # Use the base ID for subsequent lookups
        
        if not department:
            return JSONResponse({"success": False, "error": f"Department not found: {dept_id}"}, status_code=404)
        
        # Match programs by department_id - use EXACT match only to avoid false positives
        # The department_id should already be correctly set during parsing
        programs = []
        for p in data.get('programs', []):
            prog_dept_id = p.get('department_id', '')
            # Use exact match only - this is the most reliable
            if prog_dept_id == dept_id:
                programs.append(p)
        
        # Also get line items for this department - use exact match only
        line_items = [li for li in data.get('line_items', []) 
                     if li.get('department_id') == dept_id]
        
        # Get agencies for this department
        agencies = []
        # Check if department has agencies in its structure
        if department.get('agencies'):
            agencies = department.get('agencies', [])
        else:
            # Find agencies by parent_department_id or parent_department_name
            # Only if 'agencies' key exists in data (it might not if parser hasn't been run with agency separation)
            if 'agencies' in data:
                dept_name = (department.get('name') or '').upper()
                for agency in data.get('agencies', []):
                    agency_parent_id = agency.get('parent_department_id')
                    agency_parent_name = agency.get('parent_department_name')
                    # Safely handle None values
                    agency_parent_name_upper = (agency_parent_name or '').upper() if agency_parent_name else ''
                    if agency_parent_id == dept_id or (agency_parent_name_upper and dept_name and dept_name in agency_parent_name_upper):
                        agencies.append(agency)
        
        # Try to enrich descriptions from budget database
        try:
            import asyncpg
            budget_conn = await asyncpg.connect(
                host=os.getenv('POSTGRES_HOST', 'localhost'),
                port=int(os.getenv('POSTGRES_PORT', 5432)),
                user=os.getenv('POSTGRES_USER', 'budget_admin'),
                password=os.getenv('POSTGRES_PASSWORD', ''),
                database='budget_analysis'
            )
            
            # Look up department description - try exact match first, then partial
            dept_desc = None
            # Try exact department code match (use uacs_dpt_dsc pattern matching instead)
            # Note: budget_2025 doesn't have a 'department' column, use uacs_dpt_dsc instead
            dept_desc_query = """
                SELECT DISTINCT uacs_dpt_dsc 
                FROM budget_2025 
                WHERE uacs_dpt_dsc ILIKE $1 
                AND uacs_dpt_dsc IS NOT NULL 
                AND uacs_dpt_dsc != ''
                LIMIT 1
            """
            # Try matching by department name pattern
            dept_name_for_search = (department.get('name') or '').strip()
            if dept_name_for_search:
                # Remove prefixes and search
                cleaned = dept_name_for_search
                if '.' in cleaned:
                    parts = cleaned.split('.', 1)
                    if len(parts) > 1:
                        cleaned = parts[1].strip()
                dept_desc = await budget_conn.fetchval(dept_desc_query, f"%{cleaned}%")
            
            # If no exact match, try to find by department name pattern
            if not dept_desc:
                dept_name_pattern = (department.get('name') or '').strip()
                if dept_name_pattern:
                    # Remove common prefixes like "A.", "B.", "38.", "XLIII."
                    cleaned_name = dept_name_pattern
                    if '.' in cleaned_name:
                        parts = cleaned_name.split('.', 1)
                        if len(parts) > 1 and len(parts[0].strip()) < 5:
                            cleaned_name = parts[1].strip()
                    
                    if cleaned_name and len(cleaned_name) > 3:
                        dept_desc_query2 = """
                            SELECT DISTINCT uacs_dpt_dsc 
                            FROM budget_2025 
                            WHERE uacs_dpt_dsc ILIKE $1
                            AND uacs_dpt_dsc IS NOT NULL 
                            AND uacs_dpt_dsc != ''
                            LIMIT 1
                        """
                        dept_desc = await budget_conn.fetchval(dept_desc_query2, f"%{cleaned_name}%")
            
            if dept_desc and len(dept_desc.strip()) > len(department.get('name', '').strip()):
                department['full_description'] = dept_desc.strip()
            
            # Look up program descriptions
            for program in programs:
                program_name = (program.get('name') or '').strip()
                # Skip if name is too short or looks like just a prefix/number
                if len(program_name) < 5 or program_name in ['X', '38.', 'XLIII.'] or (program_name.count('.') > 0 and len(program_name.split('.')[0]) < 3):
                    # Try to find program description by matching partial name
                    # Use department name pattern instead of department code
                    dept_name_for_prog_search = (department.get('name') or '').strip()
                    if dept_name_for_prog_search:
                        # Clean department name for search
                        cleaned_dept = dept_name_for_prog_search
                        if '.' in cleaned_dept:
                            parts = cleaned_dept.split('.', 1)
                            if len(parts) > 1:
                                cleaned_dept = parts[1].strip()
                        
                        # Remove parenthetical text for cleaner search
                        if '(' in cleaned_dept:
                            cleaned_dept = cleaned_dept.split('(')[0].strip()
                        
                        prog_desc_query = """
                            SELECT DISTINCT uacs_prog_dsc 
                            FROM budget_2025 
                            WHERE uacs_dpt_dsc ILIKE $1 
                            AND uacs_prog_dsc IS NOT NULL 
                            AND uacs_prog_dsc != ''
                            AND (
                                uacs_prog_dsc ILIKE $2 
                                OR uacs_prog_dsc ILIKE $3
                            )
                            LIMIT 1
                        """
                        # Try matching with the prefix or look for any program in this department
                        search_pattern1 = f"%{program_name}%"
                        search_pattern2 = "%"  # Fallback to any program if prefix doesn't match
                        prog_desc = await budget_conn.fetchval(prog_desc_query, f"%{cleaned_dept}%", search_pattern1, search_pattern2)
                        
                        if not prog_desc and len(programs) == 1:
                            # If only one program, get the most common program description for this department
                            prog_desc_query2 = """
                                SELECT uacs_prog_dsc, COUNT(*) as cnt
                                FROM budget_2025 
                                WHERE uacs_dpt_dsc ILIKE $1 
                                AND uacs_prog_dsc IS NOT NULL 
                                AND uacs_prog_dsc != ''
                                GROUP BY uacs_prog_dsc
                                ORDER BY cnt DESC
                                LIMIT 1
                            """
                            prog_desc = await budget_conn.fetchval(prog_desc_query2, f"%{cleaned_dept}%")
                    
                    if prog_desc and len(prog_desc.strip()) > len(program_name):
                        program['full_description'] = prog_desc.strip()
                        # Update the name if it's significantly better
                        if len(prog_desc.strip()) > len(program_name) + 10:
                            program['name'] = prog_desc.strip()
            
            await budget_conn.close()
        except Exception as db_error:
            # If database lookup fails, continue with original data
            print(f"⚠️ Could not enrich descriptions from database: {db_error}")
        
        return JSONResponse({"success": True, "department": department, "programs": programs, "agencies": agencies, "line_items": line_items[:100]})  # Limit to 100 for performance
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/budget/amendments/search")
async def budget_amendments_search(q: str = Query("")):
    """Full-text search across departments, programs, and projects"""
    try:
        data = load_amendments_data()
        if not data:
            return JSONResponse({"success": False, "error": "Data not available"}, status_code=404)
        query = q.lower()
        if not query:
            return JSONResponse({"success": True, "query": q, "results": []})
        results = []
        for dept in data['departments']:
            if query in dept['name'].lower() or query in dept['code'].lower():
                results.append({
                    "type": "department",
                    "id": dept['id'],
                    "name": dept['name'],
                    "code": dept['code'],
                    "amount": dept['final_amount']
                })
        return JSONResponse({"success": True, "query": q, "results": results[:50]})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/budget/amendments/duplicates")
async def budget_amendments_duplicates():
    """Get duplicate detection results for budget amendments"""
    try:
        json_path = Path('static/data/duplicates_2026.json')
        
        if not json_path.exists():
            return JSONResponse({
                "success": False,
                "error": "Duplicate data not available. Please run scripts/detect_duplicates.py first."
            }, status_code=404)
        
        with open(json_path, 'r', encoding='utf-8') as f:
            duplicates_data = json.load(f)
        
        return JSONResponse({
            "success": True,
            **duplicates_data
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/budget/amendments/annex-a1-amounts")
async def budget_amendments_annex_a1_amounts():
    """Get just the amounts from Annex A-1 projects for histogram (lightweight)"""
    try:
        # Check for pre-generated cache first
        cache_file = Path(__file__).parent / "static" / "data" / "api_cache" / "annex_a1_amounts_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                if cache_data.get('success'):
                    print(f"✅ [/api/budget/amendments/annex-a1-amounts] Using cached data from {cache_file.name}")
                    return JSONResponse(cache_data)
            except Exception as cache_err:
                print(f"⚠️ [/api/budget/amendments/annex-a1-amounts] Error reading cache, falling back to processing: {cache_err}")
        
        json_path = Path('static/data/budget_amendments_2026.json')
        
        if not json_path.exists():
            return JSONResponse({
                "success": False,
                "error": "Budget amendments data not available"
            }, status_code=404)
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extract only Annex A-1 project amounts (much smaller payload)
        annex_a1_projects = [
            p for p in data.get('projects', [])
            if p.get('source_sheet') == 'Annex A-1'
        ]
        
        amounts = [
            p.get('final_amount') or p.get('original_amount') or 0
            for p in annex_a1_projects
            if (p.get('final_amount') or p.get('original_amount') or 0) > 0
        ]
        
        return JSONResponse({
            "success": True,
            "amounts": amounts,
            "total_projects": len(amounts)
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/budget/amendments/annex-a5-amounts")
async def budget_amendments_annex_a5_amounts():
    """Get just the amounts from Annex A-5 (DPWH) projects for histogram (lightweight)"""
    try:
        # Check for pre-generated cache first
        cache_file = Path(__file__).parent / "static" / "data" / "api_cache" / "annex_a5_amounts_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                if cache_data.get('success'):
                    print(f"✅ [/api/budget/amendments/annex-a5-amounts] Using cached data from {cache_file.name}")
                    return JSONResponse(cache_data)
            except Exception as cache_err:
                print(f"⚠️ [/api/budget/amendments/annex-a5-amounts] Error reading cache, falling back to processing: {cache_err}")
        
        json_path = Path('static/data/budget_amendments_2026.json')
        
        if not json_path.exists():
            return JSONResponse({
                "success": False,
                "error": "Budget amendments data not available"
            }, status_code=404)
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extract only Annex A-5 project amounts (much smaller payload)
        annex_a5_projects = [
            p for p in data.get('projects', [])
            if p.get('source_sheet') == 'Annex A-5'
        ]
        
        amounts = [
            p.get('final_amount') or p.get('original_amount') or 0
            for p in annex_a5_projects
            if (p.get('final_amount') or p.get('original_amount') or 0) > 0
        ]
        
        return JSONResponse({
            "success": True,
            "amounts": amounts,
            "total_projects": len(amounts)
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/budget/amendments/annex-a5-duplicates")
async def budget_amendments_annex_a5_duplicates():
    """Get duplicate detection results for Annex A-5 (DPWH) projects"""
    try:
        # Check for pre-generated cache first
        cache_file = Path(__file__).parent / "static" / "data" / "api_cache" / "annex_a5_duplicates_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                if cache_data.get('success'):
                    print(f"✅ [/api/budget/amendments/annex-a5-duplicates] Using cached data from {cache_file.name}")
                    return JSONResponse(cache_data)
            except Exception as cache_err:
                print(f"⚠️ [/api/budget/amendments/annex-a5-duplicates] Error reading cache, falling back to processing: {cache_err}")
        
        json_path = Path('static/data/duplicates_a5_2026.json')
        
        if not json_path.exists():
            return JSONResponse({
                "success": False,
                "error": "Annex A-5 duplicate data not available. Please run duplicate detection for Annex A-5 first."
            }, status_code=404)
        
        with open(json_path, 'r', encoding='utf-8') as f:
            duplicates_data = json.load(f)
        
        return JSONResponse({
            "success": True,
            **duplicates_data
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/budget/amendments/annex-a4-amounts")
async def budget_amendments_annex_a4_amounts():
    """Get just the amounts from Annex A-4 (NIA) projects for histogram (lightweight)"""
    try:
        # Check for pre-generated cache first
        cache_file = Path(__file__).parent / "static" / "data" / "api_cache" / "annex_a4_amounts_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                if cache_data.get('success'):
                    print(f"✅ [/api/budget/amendments/annex-a4-amounts] Using cached data from {cache_file.name}")
                    return JSONResponse(cache_data)
            except Exception as cache_err:
                print(f"⚠️ [/api/budget/amendments/annex-a4-amounts] Error reading cache, falling back to processing: {cache_err}")
        
        json_path = Path('static/data/budget_amendments_2026.json')
        
        if not json_path.exists():
            return JSONResponse({
                "success": False,
                "error": "Budget amendments data not available"
            }, status_code=404)
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extract only Annex A-4 project amounts (much smaller payload)
        annex_a4_projects = [
            p for p in data.get('projects', [])
            if p.get('source_sheet') == 'Annex A-4'
        ]
        
        amounts = [
            p.get('final_amount') or p.get('original_amount') or 0
            for p in annex_a4_projects
            if (p.get('final_amount') or p.get('original_amount') or 0) > 0
        ]
        
        return JSONResponse({
            "success": True,
            "amounts": amounts,
            "total_projects": len(amounts)
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/budget/amendments/annex-a4-duplicates")
async def budget_amendments_annex_a4_duplicates():
    """Get duplicate detection results for Annex A-4 (NIA) projects"""
    try:
        # Check for pre-generated cache first
        cache_file = Path(__file__).parent / "static" / "data" / "api_cache" / "annex_a4_duplicates_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                if cache_data.get('success'):
                    print(f"✅ [/api/budget/amendments/annex-a4-duplicates] Using cached data from {cache_file.name}")
                    return JSONResponse(cache_data)
            except Exception as cache_err:
                print(f"⚠️ [/api/budget/amendments/annex-a4-duplicates] Error reading cache, falling back to processing: {cache_err}")
        
        json_path = Path('static/data/duplicates_a4_2026.json')
        
        if not json_path.exists():
            return JSONResponse({
                "success": False,
                "error": "Annex A-4 duplicate data not available. Please run duplicate detection for Annex A-4 first."
            }, status_code=404)
        
        with open(json_path, 'r', encoding='utf-8') as f:
            duplicates_data = json.load(f)
        
        return JSONResponse({
            "success": True,
            **duplicates_data
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/budget/amendments/department/{dept_id}/line-items")
async def budget_amendments_department_line_items(dept_id: str):
    """Get detailed line items (Annex A) for a department"""
    try:
        # URL decode the department ID in case it contains special characters
        from urllib.parse import unquote
        dept_id = unquote(dept_id)
        
        data = load_amendments_data()
        if not data:
            return JSONResponse({"success": False, "error": "Data not available"}, status_code=404)
        
        # Try exact match first
        department = next((d for d in data['departments'] if d['id'] == dept_id), None)
        
        # If not found, try matching without any colon suffix (e.g., "OP:1" -> "OP")
        if not department and ':' in dept_id:
            dept_id_base = dept_id.split(':')[0]
            department = next((d for d in data['departments'] if d['id'] == dept_id_base), None)
            if department:
                dept_id = dept_id_base  # Use the base ID for subsequent lookups
        
        if not department:
            return JSONResponse({"success": False, "error": f"Department not found: {dept_id}"}, status_code=404)
        
        dept_code = department.get('code', '').upper()
        dept_name = department.get('name', '').upper()
        
        # Get line items matching this department - be more flexible
        line_items = []
        for li in data.get('line_items', []):
            li_dept_id = str(li.get('department_id', '')).upper()
            li_sheet = str(li.get('excel_sheet', '')).upper()
            
            # Match by department ID, code, or sheet name
            if (li_dept_id == dept_id.upper() or 
                li_dept_id == dept_code or
                dept_code in li_dept_id or
                dept_id.upper() in li_dept_id or
                any(word in li_dept_id for word in dept_name.split() if len(word) > 3) or
                # Also match by sheet name if it contains department keywords
                (li_sheet and any(word in li_sheet for word in dept_name.split() if len(word) > 3))):
                line_items.append(li)
        
        return JSONResponse({
            "success": True, 
            "department": department,
            "line_items": line_items,
            "total": len(line_items)
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/budget/amendments/program/{program_id}/line-items")
async def budget_amendments_program_line_items(program_id: str):
    """Get detailed line-by-line amendments for a specific program"""
    try:
        data = load_amendments_data()
        if not data:
            return JSONResponse({"success": False, "error": "Data not available"}, status_code=404)
        
        # Find program
        program = next((p for p in data.get('programs', []) if p.get('id') == program_id), None)
        if not program:
            return JSONResponse({"success": False, "error": "Program not found"}, status_code=404)
        
        # Get line items for this program
        line_items = [
            item for item in data.get('line_items', [])
            if item.get('program_id') == program_id
        ]
        
        # If program has line_items embedded, use those
        if program.get('line_items'):
            line_items = program['line_items']
        
        return JSONResponse({
            "success": True,
            "program": program,
            "line_items": line_items,
            "total_line_items": len(line_items)
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/budget/analysis/comparison-chart")
async def budget_analysis_comparison_chart_api():
    """Get data for Budget vs NEP comparison chart - no authentication required"""
    try:
        # Check for pre-generated cache first
        cache_file = Path(__file__).parent / "static" / "data" / "api_cache" / "budget_comparison_chart_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                if cache_data.get('success'):
                    print(f"✅ [/api/budget/analysis/comparison-chart] Using cached data from {cache_file.name}")
                    return JSONResponse(cache_data)
            except Exception as cache_err:
                print(f"⚠️ [/api/budget/analysis/comparison-chart] Error reading cache, falling back to processing: {cache_err}")
        
        print(f"📊 [API] DEBUG: Fetching Budget vs NEP comparison data")

        # Direct database queries to get yearly totals
        import asyncpg

        # Connect to budget_analysis database
        budget_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database='budget_analysis'
        )

        # Connect to nep database
        nep_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database='nep'
        )

        try:
            # Years to compare (overlapping years)
            years = [2020, 2021, 2022, 2023, 2024, 2025]
            budget_amounts = []
            nep_amounts = []

            for year in years:
                # Get budget data for this year
                budget_table = f"budget_{year}"
                try:
                    budget_result = await budget_conn.fetchrow(f"""
                        SELECT COALESCE(SUM(amt), 0) as total_amount
                        FROM {budget_table}
                        WHERE amt IS NOT NULL AND amt > 0
                    """)
                    budget_amount = float(budget_result['total_amount']) if budget_result else 0
                except Exception as e:
                    print(f"⚠️ [API] DEBUG: Error fetching budget data for {year}: {e}")
                    budget_amount = 0

                # Get NEP data for this year
                nep_table = f"budget_{year}"
                try:
                    nep_result = await nep_conn.fetchrow(f"""
                        SELECT COALESCE(SUM(amount), 0) as total_amount
                        FROM {nep_table}
                        WHERE amount IS NOT NULL AND amount > 0
                    """)
                    nep_amount = float(nep_result['total_amount']) if nep_result else 0
                except Exception as e:
                    print(f"⚠️ [API] DEBUG: Error fetching NEP data for {year}: {e}")
                    nep_amount = 0

                budget_amounts.append(budget_amount)
                nep_amounts.append(nep_amount)

                print(f"📊 [API] DEBUG: Year {year} - Budget: ₱{budget_amount:,.0f}, NEP: ₱{nep_amount:,.0f}")

            chart_data = {
                "years": years,
                "budget_amounts": budget_amounts,
                "nep_amounts": nep_amounts
            }

            print(f"📊 [API] DEBUG: Comparison chart data prepared: {len(chart_data['years'])} years")
            return JSONResponse(chart_data)

        finally:
            await budget_conn.close()
            await nep_conn.close()

    except Exception as e:
        print(f"💥 [API] ERROR: Failed to fetch comparison chart data: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e),
            "years": [],
            "budget_amounts": [],
            "nep_amounts": []
        })

@app.get("/api/budget/programs/comparison")
async def budget_programs_comparison_api():
    """Get program comparison data between Budget and NEP databases - no authentication required"""
    try:
        # Check for pre-generated cache first
        cache_file = Path(__file__).parent / "static" / "data" / "api_cache" / "budget_programs_comparison_cache.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                if cache_data.get('success'):
                    print(f"✅ [/api/budget/programs/comparison] Using cached data from {cache_file.name}")
                    return JSONResponse(cache_data)
            except Exception as cache_err:
                print(f"⚠️ [/api/budget/programs/comparison] Error reading cache, falling back to processing: {cache_err}")
        
        print(f"📊 [API] DEBUG: Fetching program comparison data")

        # Direct database queries to get program data
        import asyncpg

        # Connect to budget_analysis database
        budget_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database='budget_analysis'
        )

        # Connect to nep database
        nep_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database='nep'
        )

        try:
            # Define the programs we're looking for
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
                # Get budget data for this program by year
                budget_yearly = {}
                budget_total = 0
                budget_count = 0
                
                # Check budget tables (2020-2025) - earlier tables don't have dsc column
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
                        print(f"⚠️ [API] DEBUG: Error fetching budget data for {program} in {year}: {e}")
                        budget_yearly[str(year)] = 0

                # Get NEP data for this program by year
                nep_yearly = {}
                nep_total = 0
                nep_count = 0
                
                # Check all NEP tables (2020-2026)
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
                        print(f"⚠️ [API] DEBUG: Error fetching NEP data for {program} in {year}: {e}")
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

                print(f"📊 [API] DEBUG: Program {program} - Budget: ₱{budget_total:,.0f} ({budget_count} entries), NEP: ₱{nep_total:,.0f} ({nep_count} entries)")

            return JSONResponse({
                "success": True,
                "programs": program_data,
                "total_programs": len(programs),
                "generated_at": datetime.now().isoformat()
            })

        finally:
            await budget_conn.close()
            await nep_conn.close()

    except Exception as e:
        print(f"💥 [API] ERROR: Failed to fetch program comparison data: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e),
            "programs": []
        })

@app.get("/api/budget/programs/raw-comparison")
async def budget_programs_raw_comparison_api():
    """Get program comparison data from raw NEP files - no authentication required"""
    try:
        print(f"📊 [API] DEBUG: Fetching raw program comparison data")

        # Import the raw NEP processor
        import sys
        import os
        sys.path.append(os.path.dirname(__file__))
        
        from process_raw_nep_programs import RawNEPProgramProcessor
        
        processor = RawNEPProgramProcessor()
        
        # Process all available years
        years = [2020, 2021, 2022, 2023, 2024, 2025, 2026]
        raw_data = processor.process_all_years(years)
        
        # Convert to the format expected by the frontend
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
            nep_yearly = {}
            
            # Get NEP data from raw files
            for year_str, year_data in raw_data.items():
                if program in year_data:
                    nep_yearly[year_str] = year_data[program]['total_amount']
                else:
                    nep_yearly[year_str] = 0
            
            # For now, set budget data to 0 since we're focusing on raw NEP data
            # TODO: Process raw budget files similarly
            for year_str in nep_yearly.keys():
                budget_yearly[year_str] = 0
            
            program_data.append({
                'program': program,
                'budget_total': sum(budget_yearly.values()),
                'budget_count': 0,  # TODO: Count from raw budget files
                'budget_yearly': budget_yearly,
                'nep_total': sum(nep_yearly.values()),
                'nep_count': sum(year_data.get(program, {}).get('entry_count', 0) for year_data in raw_data.values()),
                'nep_yearly': nep_yearly
            })
        
        return JSONResponse({
            "success": True,
            "programs": program_data,
            "total_programs": len(programs),
            "data_source": "raw_nep_files",
            "generated_at": datetime.now().isoformat()
        })

    except Exception as e:
        print(f"💥 [API] ERROR: Failed to fetch raw program comparison data: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e),
            "programs": []
        })

@app.get("/api/budget/programs/excel-comparison")
async def budget_programs_excel_comparison_api():
    """Get program comparison data from cached Excel JSON - no authentication required"""
    try:
        print(f"📊 [API] DEBUG: Fetching cached Excel program comparison data")

        import json
        import os
        
        # Path to the cached JSON file
        cache_file = os.path.join(os.path.dirname(__file__), "static", "data", "excel_programs_cache.json")
        
        if not os.path.exists(cache_file):
            return JSONResponse({
                "success": False,
                "error": "Cached Excel data not found. Please run generate_excel_programs_cache.py",
                "programs": []
            })
        
        # Load cached data
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        if not cache_data.get('success', False):
            return JSONResponse({
                "success": False,
                "error": "Cached data indicates failure",
                "programs": []
            })
        
        print(f"📊 [API] DEBUG: Loaded cached data with {len(cache_data['programs'])} programs")
        
        return JSONResponse(cache_data)

    except Exception as e:
        print(f"💥 [API] ERROR: Failed to fetch cached Excel program comparison data: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e),
            "programs": []
        })

from flood_client import FloodControlClient, FloodControlProject, build_filter_string

# Create global flood client instance
_flood_client = None

def get_flood_client():
    """Get or create flood client instance"""
    global _flood_client
    if _flood_client is None:
        _flood_client = FloodControlClient()
    return _flood_client

@app.get("/api/flood/health")
async def flood_health_check():
    """Check if flood control API is healthy - no authentication required"""
    try:
        client = get_flood_client()
        is_healthy = await client.health_check()
        return JSONResponse({
            "status": "healthy" if is_healthy else "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "meilisearch_connected": is_healthy
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/flood/projects")
async def flood_projects_api(
    q: str = Query(default="", description="Search query"),
    region: str = Query(default=None, description="Filter by region"),
    province: str = Query(default=None, description="Filter by province"),
    year: str = Query(default=None, description="Filter by infrastructure year"),
    type_of_work: str = Query(default=None, description="Filter by type of work"),
    contractor: str = Query(default=None, description="Filter by contractor"),
    district_office: str = Query(default=None, description="Filter by district engineering office"),
    legislative_district: str = Query(default=None, description="Filter by legislative district"),
    limit: int = Query(default=20, ge=1, le=20000, description="Number of results"),
    offset: int = Query(default=0, ge=0, description="Number to skip")
):
    """Search flood control projects with optional filters - backed by PostgreSQL."""
    try:
        start_time = time.perf_counter()
        projects, total_hits = await search_flood_projects(
            query=q,
            region=region,
            province=province,
            year=year,
            type_of_work=type_of_work,
            contractor=contractor,
            district_office=district_office,
            legislative_district=legislative_district,
            limit=limit,
            offset=offset,
        )
        duration_ms = int((time.perf_counter() - start_time) * 1000)

        return JSONResponse({
            "success": True,
            "projects": projects,
            "totalHits": total_hits,
            "processingTimeMs": duration_ms,
            "query": q or "",
            "facetsDistribution": {}
        })

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e), "projects": []})

@app.get("/api/flood/projects/{project_id}")
async def flood_project_by_id(project_id: str):
    """Get a specific flood control project by GlobalID - no authentication required"""
    try:
        client = get_flood_client()
        project = await client.get_project_by_id(project_id)
        
        if not project:
            return JSONResponse({"success": False, "error": "Project not found"}, status_code=404)
        
        return JSONResponse({
            "success": True,
            "project": {
                "GlobalID": project.GlobalID,
                "ProjectDescription": project.ProjectDescription,
                "InfraYear": project.InfraYear,
                "Region": project.Region,
                "Province": project.Province,
                "Municipality": project.Municipality,
                "TypeofWork": project.TypeofWork,
                "Contractor": project.Contractor,
                "ContractCost": project.ContractCost,
                "DistrictEngineeringOffice": project.DistrictEngineeringOffice,
                "LegislativeDistrict": project.LegislativeDistrict,
                "ContractID": project.ContractID,
                "ProjectID": project.ProjectID,
                "Latitude": project.Latitude,
                "Longitude": project.Longitude
            }
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/flood/statistics")
async def flood_statistics_api(
    region: str = Query(default=None, description="Filter by region"),
    province: str = Query(default=None, description="Filter by province"),
    year: str = Query(default=None, description="Filter by infrastructure year"),
    type_of_work: str = Query(default=None, description="Filter by type of work"),
    contractor: str = Query(default=None, description="Filter by contractor"),
    district_office: str = Query(default=None, description="Filter by district engineering office"),
    legislative_district: str = Query(default=None, description="Filter by legislative district")
):
    """Get comprehensive statistics for flood control projects - no authentication required"""
    try:
        client = get_flood_client()
        
        # Build filters dictionary
        filters = {}
        if region:
            filters["Region"] = region
        if province:
            filters["Province"] = province
        if year:
            filters["InfraYear"] = year
        if type_of_work:
            filters["TypeofWork"] = type_of_work
        if contractor:
            filters["Contractor"] = contractor
        if district_office:
            filters["DistrictEngineeringOffice"] = district_office
        if legislative_district:
            filters["LegislativeDistrict"] = legislative_district
        
        filter_string = build_filter_string(filters) if filters else None
        stats = await client.get_statistics(filter_string)
        
        # Get most expensive projects for the chart
        most_expensive_projects = await client.get_most_expensive_projects(filter_string, limit=10)
        
        return JSONResponse({
            "success": True,
            "totalProjects": stats.totalProjects,
            "totalCost": stats.totalCost,
            "uniqueContractors": stats.uniqueContractors,
            "regions": stats.regions,
            "years": stats.years,
            "typesOfWork": stats.typesOfWork,
            "topContractors": stats.topContractors,
            "mostExpensiveProjects": most_expensive_projects
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/flood/districts")
async def flood_districts_api():
    """Get district statistics for flood control projects - no authentication required"""
    try:
        # Try to load from cached JSON file first
        cache_file = os.path.join(os.path.dirname(__file__), "static", "data", "flood_districts_cache.json")
        if os.path.exists(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
                if cached_data.get('success'):
                    print(f"✅ Using cached district data from {cache_file}")
                    return JSONResponse(cached_data)
        
        print("⚠️ No cached district data found, fetching from MeiliSearch...")
        client = get_flood_client()
        
        # Get all projects to count by district
        projects, metadata = await client.search_projects(query="", limit=10000, offset=0)
        
        # Count projects by DistrictEngineeringOffice
        districts_data = {}
        for project in projects:
            district = project.DistrictEngineeringOffice or "Unknown District"
            districts_data[district] = districts_data.get(district, 0) + 1
        
        # Convert to array format for consistency
        districts_array = [
            {"district": district, "count": count}
            for district, count in districts_data.items()
        ]
        
        # Sort by count descending
        districts_array.sort(key=lambda x: x["count"], reverse=True)
        
        return JSONResponse({
            "success": True,
            "districts": districts_array,
            "totalDistricts": len(districts_array),
            "totalProjects": sum(count for _, count in districts_data.items())
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/flood/provinces")
async def flood_provinces_api():
    """Get province statistics for flood control projects - no authentication required"""
    try:
        # Import the district to province mapper
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(__file__), 'sec_scraper'))
        from district_to_province_mapper import DistrictToProvinceMapper
        
        # Try to load from cached JSON file first
        cache_file = os.path.join(os.path.dirname(__file__), "static", "data", "province_heatmap_cache.json")
        if os.path.exists(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
                if cached_data.get('success'):
                    print(f"✅ Using cached province heat map data from {cache_file}")
                    return JSONResponse(cached_data)
                else:
                    print(f"⚠️ Cached province data has errors: {cached_data.get('error')}")
        else:
            print(f"⚠️ Province heat map cache not found at {cache_file}")
        
        # Fallback: generate from MeiliSearch if cache not available
        print("⚠️ Cache not found, generating province data from MeiliSearch...")
        client = get_flood_client()
        projects, metadata = await client.search_projects(limit=10000)  # Get all projects
        
        # Group by DistrictEngineeringOffice
        district_counts = {}
        for project in projects:
            district = project.DistrictEngineeringOffice or "Unknown District"
            if district not in district_counts:
                district_counts[district] = 0
            district_counts[district] += 1
        
        # Convert to districts format for processing
        districts_data = [{"district": district, "count": count} for district, count in district_counts.items()]
        
        # Process districts data and aggregate by province
        mapper = DistrictToProvinceMapper()
        province_aggregates = mapper.process_districts_data(districts_data)
        
        # Convert to list format for API response
        provinces_list = []
        for province_name, province_data in province_aggregates.items():
            provinces_list.append({
                'province': province_name,
                'geojson_name': province_data['geojson_name'],
                'total_projects': province_data['total_projects'],
                'districts_count': len(province_data['districts']),
                'districts': province_data['districts']
            })
        
        # Sort by project count descending
        provinces_list.sort(key=lambda x: x['total_projects'], reverse=True)
        
        return JSONResponse({
            "success": True,
            "provinces": provinces_list,
            "total_provinces": len(provinces_list),
            "total_projects": sum(p['total_projects'] for p in provinces_list),
            "generated_at": datetime.now().isoformat(),
            "description": "Province-level aggregation of flood control projects from MeiliSearch data"
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/flood/lookup/regions")
async def flood_regions_lookup():
    """Get list of all regions - no authentication required"""
    try:
        client = get_flood_client()
        regions = await client.get_facets("Region")
        return JSONResponse({
            "success": True,
            "regions": list(regions.keys()),
            "counts": regions
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/flood/lookup/provinces")
async def flood_provinces_lookup(region: str = Query(default=None, description="Filter by region")):
    """Get list of provinces, optionally filtered by region - no authentication required"""
    try:
        client = get_flood_client()
        filters = {"Region": region} if region else None
        filter_string = build_filter_string(filters) if filters else None
        
        provinces = await client.get_facets("Province", filter_string)
        return JSONResponse({
            "success": True,
            "provinces": list(provinces.keys()),
            "counts": provinces
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/flood/lookup/years")
async def flood_years_lookup():
    """Get list of all infrastructure years - no authentication required"""
    try:
        client = get_flood_client()
        years = await client.get_facets("InfraYear")
        return JSONResponse({
            "success": True,
            "years": list(years.keys()),
            "counts": years
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/flood/lookup/types-of-work")
async def flood_types_of_work_lookup():
    """Get list of all types of work - no authentication required"""
    try:
        client = get_flood_client()
        types = await client.get_facets("TypeofWork")
        return JSONResponse({
            "success": True,
            "types_of_work": list(types.keys()),
            "counts": types
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/flood/lookup/contractors")
async def flood_contractors_lookup():
    """Get list of all contractors - no authentication required"""
    try:
        client = get_flood_client()
        contractors = await client.get_facets("Contractor")
        return JSONResponse({
            "success": True,
            "contractors": list(contractors.keys()) if contractors else [],
            "counts": contractors if contractors else {},
            "total": len(contractors) if contractors else 0
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/flood/contractors")
async def flood_contractors_paginated(
    page: int = Query(default=1, description="Page number (1-based)"),
    limit: int = Query(default=50, description="Number of contractors per page"),
    search: str = Query(default="", description="Search query for contractor names")
):
    """Get paginated contractors with costs and suspicion scores - no authentication required"""
    try:
        # Try to load from generated contractor data with costs
        try:
            import json
            with open('static/data/contractors_with_costs.json', 'r') as f:
                data = json.load(f)
                contractor_list = data.get('contractors', [])
        except FileNotFoundError:
            # Fallback to MeiliSearch facets if file not found
            client = get_flood_client()
            contractors = await client.get_facets("Contractor")
            
            if not contractors:
                return JSONResponse({
                    "success": True,
                    "contractors": [],
                    "pagination": {
                        "page": page,
                        "limit": limit,
                        "total": 0,
                        "total_pages": 0
                    }
                })
            
            # Convert to list of contractor objects
            contractor_list = []
            for name, count in contractors.items():
                contractor_list.append({
                    "name": name,
                    "projects": count,
                    "totalCost": 0,  # Not available from facets
                    "avgCostPerProject": 0,  # Not available from facets
                    "suspicionScore": 0,  # No SEC data in MeiliSearch
                    "performance": "Normal"  # Default
                })
        
        # Apply search filter if provided
        if search:
            search_lower = search.lower()
            contractor_list = [c for c in contractor_list if search_lower in c["name"].lower()]
        
        # Sort by project count (descending)
        contractor_list.sort(key=lambda x: x["projects"], reverse=True)
        
        # Calculate pagination
        total = len(contractor_list)
        total_pages = (total + limit - 1) // limit
        offset = (page - 1) * limit
        
        # Get page data
        page_contractors = contractor_list[offset:offset + limit]
        
        return JSONResponse({
            "success": True,
            "contractors": page_contractors,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "total_pages": total_pages
            }
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

# ============================================================================
# DIME Infrastructure API Endpoints
# ============================================================================

from dime_client import (
    get_dime_statistics,
    get_dime_filter_options,
    get_dime_barangay_aggregates,
    get_dime_barangay_aggregates_by_count,
    get_dime_projects,
    get_dime_suggestions,
    find_dime_project_coordinates
)

@app.get("/api/dime/statistics")
async def dime_statistics_api():
    """Get DIME infrastructure project statistics - no authentication required"""
    try:
        result = await get_dime_statistics()
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/dime/filter-options")
async def dime_filter_options_api():
    """Get DIME filter options - no authentication required"""
    try:
        result = await get_dime_filter_options()
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/dime/barangay-aggregates")
async def dime_barangay_aggregates_api():
    """Get DIME barangay aggregates (by total amount) - no authentication required"""
    try:
        result = await get_dime_barangay_aggregates()
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/dime/barangay-aggregates-by-count")
async def dime_barangay_aggregates_by_count_api():
    """Get DIME barangay aggregates (by project count) - no authentication required"""
    try:
        result = await get_dime_barangay_aggregates_by_count()
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/dime/projects/dime-only")
async def get_dime_only_projects():
    """Get DIME-only projects (not in flood) for map display"""
    try:
        import asyncpg
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_DIME', 'dime')
        )
        
        # Get DIME projects that are NOT in flood (no meilisearch_id)
        projects = await conn.fetch('''
            SELECT id, project_name, description, latitude, longitude, 
                   status, city, province, region, contractors, cost,
                   date_started, contract_completion_date, actual_date_started
            FROM projects
            WHERE (meilisearch_id IS NULL OR meilisearch_id = '')
              AND latitude IS NOT NULL AND longitude IS NOT NULL
              AND latitude != 0 AND longitude != 0
        ''')
        
        await conn.close()
        
        projects_list = []
        for p in projects:
            # Extract year from any available date field
            year = None
            for date_field in ['date_started', 'actual_date_started', 'contract_completion_date']:
                if p.get(date_field):
                    year = p[date_field].year if hasattr(p[date_field], 'year') else None
                    if year:
                        break
            
            projects_list.append({
                'id': p['id'],
                'project_name': p['project_name'],
                'description': p['description'],
                'latitude': float(p['latitude']) if p['latitude'] else None,
                'longitude': float(p['longitude']) if p['longitude'] else None,
                'status': p['status'],
                'city': p['city'],
                'province': p['province'],
                'region': p['region'],
                'contractors': p['contractors'],
                'cost': float(p['cost']) if p['cost'] else None,
                'year': year,
                'date_started': p['date_started'].isoformat() if p.get('date_started') else None,
                'contract_completion_date': p['contract_completion_date'].isoformat() if p.get('contract_completion_date') else None
            })
        
        return JSONResponse({
            "success": True,
            "projects": projects_list,
            "count": len(projects_list)
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/dime/projects/{project_id}/status")
async def dime_project_status_api(project_id: str):
    """Get DIME project status by MeiliSearch ID - no authentication required"""
    try:
        import asyncpg
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_DIME', 'dime')
        )
        
        # Query project by meilisearch_id (the GlobalID from flood projects)
        project = await conn.fetchrow(
            "SELECT status, project_name FROM projects WHERE meilisearch_id = $1",
            project_id
        )
        await conn.close()
        
        if project:
            return JSONResponse({
                "success": True,
                "status": project['status'],
                "project_name": project['project_name']
            })
        else:
            return JSONResponse({"success": False, "error": "Project not found"})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/philgeps/contracts/{meilisearch_id}")
async def philgeps_contracts_api(meilisearch_id: str):
    """Get PhilGEPS contracts by MeiliSearch ID - no authentication required"""
    try:
        import asyncpg
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
        )
        
        # Query contracts by meilisearch_id (the GlobalID from flood projects)
        contracts = await conn.fetch(
            """SELECT reference_id, contract_no, award_title, notice_title,
                      awardee_name, organization_name, area_of_delivery,
                      business_category, contract_amount, award_date, award_status
               FROM contracts 
               WHERE meilisearch_id = $1
               ORDER BY contract_amount DESC
               LIMIT 10""",
            meilisearch_id
        )
        await conn.close()
        
        if contracts:
            contracts_list = []
            for contract in contracts:
                contracts_list.append({
                    "reference_id": contract['reference_id'],
                    "contract_no": contract['contract_no'],
                    "award_title": contract['award_title'],
                    "notice_title": contract['notice_title'],
                    "awardee_name": contract['awardee_name'],
                    "organization_name": contract['organization_name'],
                    "area_of_delivery": contract['area_of_delivery'],
                    "business_category": contract['business_category'],
                    "contract_amount": float(contract['contract_amount']) if contract['contract_amount'] else 0,
                    "award_date": contract['award_date'].isoformat() if contract['award_date'] else None,
                    "award_status": contract['award_status']
                })
            
            return JSONResponse({
                "success": True,
                "count": len(contracts_list),
                "contracts": contracts_list
            })
        else:
            return JSONResponse({"success": False, "error": "No contracts found"})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/philgeps/sec")
async def get_sec_contractors():
    """Get all SEC contractors from cached JSON - no authentication required"""
    try:
        import json
        from pathlib import Path
        
        # Try to load from cached JSON first
        cache_file = Path("static/data/contractor_stats.json")
        if cache_file.exists():
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
            
            # Check if cache is fresh (less than 1 hour old)
            from datetime import datetime, timedelta
            cache_time = datetime.fromisoformat(cached_data.get('generated_at', '1970-01-01T00:00:00'))
            if datetime.now() - cache_time < timedelta(hours=1):
                print("📊 Using cached contractor statistics")
                return JSONResponse(cached_data)
        
        # Fallback to database if cache is missing or stale
        print("⚠️ Cache not available, falling back to database")
        import asyncpg
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_SEC', 'sec')
        )
        
        # Query all contractors
        contractors = await conn.fetch(
            """SELECT contractor_name, sec_number, date_registered, status, address, 
                      created_at, updated_at, project_count
               FROM contractors 
               ORDER BY contractor_name"""
        )
        
        # Get summary stats
        stats = await conn.fetchrow(
            """SELECT 
                COUNT(*) as total_contractors,
                COUNT(CASE WHEN sec_number IS NOT NULL AND sec_number != '' THEN 1 END) as with_sec_data,
                COUNT(CASE WHEN sec_number IS NULL OR sec_number = '' THEN 1 END) as without_sec_data,
                COUNT(CASE WHEN status = 'NO_SEC_RESULTS' THEN 1 END) as suspicious_no_results
               FROM contractors"""
        )
        
        await conn.close()
        
        contractors_list = []
        for contractor in contractors:
            contractors_list.append({
                "contractor_name": contractor['contractor_name'],
                "company_name": contractor['contractor_name'],  # For compatibility
                "original_contractor_name": contractor['contractor_name'],  # For compatibility
                "sec_number": contractor['sec_number'],
                "date_registered": contractor['date_registered'].isoformat() if contractor['date_registered'] else None,
                "status": contractor['status'] or "",
                "address": contractor['address'],
                "registered_address": contractor['address'],  # For compatibility
                "created_at": contractor['created_at'].isoformat() if contractor['created_at'] else None,
                "updated_at": contractor['updated_at'].isoformat() if contractor['updated_at'] else None,
                "project_count": contractor['project_count'] or 0
            })
        
        # Calculate processed count to match script format
        processed_count = (stats['with_sec_data'] or 0) + (stats['suspicious_no_results'] or 0)
        
        from datetime import datetime
        return JSONResponse({
            "success": True,
            "summary": {
                "total_contractors": stats['total_contractors'],
                "processed_contractors": processed_count,
                "with_sec_data": stats['with_sec_data'],
                "without_sec_data": stats['without_sec_data'],
                "suspicious_no_results": stats['suspicious_no_results'],
                "last_updated": datetime.now().isoformat(),
                "processing_batch": "database_generated",
                "source": "PostgreSQL sec.contractors table"
            },
            "contractors": contractors_list,
            "generated_at": datetime.now().isoformat(),
            "description": "Contractor statistics for /philgeps page",
            "cache_version": "1.0"
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/philgeps/top")
async def get_top_contractors(limit: int = 100):
    """Get top contractors by project count from sec database"""
    try:
        import asyncpg
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_SEC', 'sec')
        )
        
        # Get top contractors by project count - aggregate duplicates by contractor name
        contractors = await conn.fetch(
            """SELECT contractor_name, 
                      SUM(project_count) as total_projects,
                      MAX(sec_number) as sec_number,
                      MAX(status) as status,
                      BOOL_OR(has_flood) as has_flood,
                      BOOL_OR(has_dime) as has_dime,
                      BOOL_OR(has_philgeps) as has_philgeps
               FROM contractors
               WHERE project_count IS NOT NULL AND project_count > 0
               GROUP BY contractor_name
               ORDER BY total_projects DESC
               LIMIT $1""",
            limit
        )
        
        await conn.close()
        
        contractors_list = []
        for c in contractors:
            contractors_list.append({
                'contractor': c['contractor_name'],
                'count': c['total_projects'] or 0,
                'sec_number': c['sec_number'],
                'status': c['status'],
                'has_flood': c['has_flood'],
                'has_dime': c['has_dime'],
                'has_philgeps': c['has_philgeps']
            })
        
        return JSONResponse({
            "success": True,
            "contractors": contractors_list,
            "count": len(contractors_list)
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/philgeps/venn")
async def get_contractors_venn():
    """Get Venn diagram data for contractor sources (flood, dime, philgeps)"""
    try:
        import asyncpg
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_SEC', 'sec')
        )
        
        # Get source distribution using boolean columns
        stats = await conn.fetchrow(
            """SELECT 
                COUNT(*) FILTER (WHERE has_flood AND NOT has_dime AND NOT has_philgeps) as flood_only,
                COUNT(*) FILTER (WHERE has_dime AND NOT has_flood AND NOT has_philgeps) as dime_only,
                COUNT(*) FILTER (WHERE has_philgeps AND NOT has_flood AND NOT has_dime) as philgeps_only,
                COUNT(*) FILTER (WHERE has_flood AND has_dime AND NOT has_philgeps) as flood_dime,
                COUNT(*) FILTER (WHERE has_flood AND has_philgeps AND NOT has_dime) as flood_philgeps,
                COUNT(*) FILTER (WHERE has_dime AND has_philgeps AND NOT has_flood) as dime_philgeps,
                COUNT(*) FILTER (WHERE has_flood AND has_dime AND has_philgeps) as all_three,
                COUNT(*) FILTER (WHERE has_flood) as total_flood,
                COUNT(*) FILTER (WHERE has_dime) as total_dime,
                COUNT(*) FILTER (WHERE has_philgeps) as total_philgeps,
                COUNT(*) as total_unique
               FROM contractors"""
        )
        
        await conn.close()
        
        flood_only = stats['flood_only']
        dime_only = stats['dime_only']
        philgeps_only = stats['philgeps_only']
        flood_dime = stats['flood_dime']
        flood_philgeps = stats['flood_philgeps']
        dime_philgeps = stats['dime_philgeps']
        all_three = stats['all_three']
        
        return JSONResponse({
            "success": True,
            "flood_only": flood_only,
            "dime_only": dime_only,
            "philgeps_only": philgeps_only,
            "flood_dime": flood_dime,
            "flood_philgeps": flood_philgeps,
            "dime_philgeps": dime_philgeps,
            "all_three": all_three,
            "flood_total": stats['total_flood'],
            "dime_total": stats['total_dime'],
            "philgeps_total": stats['total_philgeps'],
            "total_unique": stats['total_unique']
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/philgeps/standard-deviation")
async def get_contractor_standard_deviation():
    """Get contractor project distribution standard deviation analysis - no authentication required"""
    try:
        import json
        from pathlib import Path
        
        # Load standard deviation analysis data
        data_file = Path("static/data/contractor_standard_deviation.json")
        if not data_file.exists():
            return JSONResponse({
                "success": False, 
                "error": "Standard deviation analysis not available. Run the analysis script first."
            })
        
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return JSONResponse({
            "success": True,
            "analysis": data.get('analysis', {}),
            "chart_data": data.get('chart_data', {}),
            "metadata": data.get('metadata', {})
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/philgeps/sec-standard-deviation")
async def get_sec_contractor_standard_deviation():
    """Get SEC contractor project distribution standard deviation analysis - no authentication required"""
    try:
        import json
        from pathlib import Path
        
        # Load SEC standard deviation analysis data
        data_file = Path("static/data/sec_contractor_standard_deviation.json")
        if not data_file.exists():
            return JSONResponse({
                "success": False, 
                "error": "SEC standard deviation analysis not available. Run the SEC analysis script first."
            })
        
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return JSONResponse({
            "success": True,
            "analysis": data.get('analysis', {}),
            "chart_data": data.get('chart_data', {}),
            "metadata": data.get('metadata', {})
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

# ============================================================================
# Flood-DIME Correlation API Endpoints
# ============================================================================

@app.get("/api/flood/dime/correlation")
async def flood_dime_correlation_api():
    """Get flood-DIME contractor correlation data - no authentication required"""
    try:
        import json
        from pathlib import Path
        
        # Load correlation data
        data_file = Path("static/data/flood_dime_contractor_correlation.json")
        if not data_file.exists():
            return JSONResponse({
                "success": False,
                "error": "Flood-DIME correlation data not available"
            })
        
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Check if it's an error response
        if data.get('status') == 'error':
            return JSONResponse({
                "success": False,
                "error": data.get('error', 'Unknown error'),
                "contractors": []
            })
        
        return JSONResponse({
            "success": True,
            "contractors": data.get('contractors', []),
            "summary": data.get('summary', {}),
            "generated_at": data.get('generated_at'),
            "cache_version": data.get('cache_version', '1.0')
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e), "contractors": []})

@app.get("/api/flood/dime/correlation/{year}")
async def flood_dime_correlation_year_api(year: str):
    """Get flood-DIME contractor correlation data for specific year - no authentication required"""
    try:
        import json
        from pathlib import Path
        
        # Load correlation data for specific year
        data_file = Path(f"static/data/flood_dime_contractor_correlation_{year}.json")
        if not data_file.exists():
            return JSONResponse({
                "success": False,
                "error": f"Flood-DIME correlation data for {year} not available"
            })
        
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Check if it's an error response
        if data.get('status') == 'error':
            return JSONResponse({
                "success": False,
                "error": data.get('error', 'Unknown error'),
                "contractors": []
            })
        
        return JSONResponse({
            "success": True,
            "contractors": data.get('contractors', []),
            "summary": data.get('summary', {}),
            "year": year,
            "generated_at": data.get('generated_at'),
            "cache_version": data.get('cache_version', '1.0')
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e), "contractors": []})

@app.get("/api/flood/dime/correlation/all")
async def flood_dime_correlation_all_api():
    """Get flood-DIME contractor correlation data for all years - no authentication required"""
    print("🔍 DEBUG: flood_dime_correlation_all_api called")
    try:
        import json
        from pathlib import Path
        
        # Load correlation data for all years
        data_file = Path("static/data/flood_dime_contractor_correlation_all_years.json")
        if not data_file.exists():
            return JSONResponse({
                "success": False,
                "error": "Flood-DIME correlation data for all years not available"
            })
        
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Check if it's an error response
        if data.get('status') == 'error':
            return JSONResponse({
                "success": False,
                "error": data.get('error', 'Unknown error'),
                "contractors": []
            })
        
        return JSONResponse({
            "success": True,
            "contractors": data.get('contractors', []),
            "summary": data.get('summary', {}),
            "generated_at": data.get('generated_at'),
            "cache_version": data.get('cache_version', '1.0')
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e), "contractors": []})

@app.get("/api/philgeps/merchants")
async def get_philgeps_merchants(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    search: str = Query(None, description="Search merchant name")
):
    """Get paginated PhilGEPS merchant data from parquet file"""
    try:
        import pandas as pd
        from pathlib import Path
        
        # Resolve path relative to script location (more reliable in production)
        parquet_file = Path(__file__).parent / 'database' / 'philgeps_merchant_info.parquet'
        
        if not parquet_file.exists():
            return JSONResponse({
                "success": False,
                "error": "Merchant parquet file not found",
                "data": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "total_pages": 0
            })
        
        # Read parquet (explicitly use pyarrow engine)
        try:
            df = pd.read_parquet(parquet_file, engine='pyarrow')
        except ImportError as e:
            # Fallback to fastparquet if pyarrow is not available
            try:
                df = pd.read_parquet(parquet_file, engine='fastparquet')
            except ImportError:
                return JSONResponse({
                    "success": False,
                    "error": "Parquet support requires pyarrow or fastparquet. Please install: pip install pyarrow",
                    "data": [],
                    "total": 0,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": 0
                })
        
        # Join with contracts parquet to get PCAB license data
        contracts_parquet = Path(__file__).parent / 'data' / 'parquet' / 'philgeps_contracts.parquet'
        if contracts_parquet.exists():
            try:
                contracts_df = pd.read_parquet(contracts_parquet, engine='pyarrow', columns=['contractor_name', 'pcab_license_number', 'pcab_category'])
                # Filter out rows where PCAB data is null
                contracts_df = contracts_df[contracts_df['pcab_license_number'].notna() | contracts_df['pcab_category'].notna()]
                
                if len(contracts_df) > 0:
                    # Get unique PCAB data per contractor (take first non-null value)
                    pcab_data = contracts_df.groupby('contractor_name').agg({
                        'pcab_license_number': 'first',
                        'pcab_category': 'first'
                    }).reset_index()
                    
                    # Normalize contractor names for better matching
                    def normalize_name(name):
                        if pd.isna(name):
                            return None
                        name_str = str(name).upper().strip()
                        # Remove common suffixes
                        import re
                        name_str = re.sub(r'\s+(INC\.?|INCORPORATED|CORP\.?|CORPORATION|CO\.?|COMPANY|OPC|OPC\.?)$', '', name_str)
                        name_str = re.sub(r'[^\w\s]', '', name_str)  # Remove special chars
                        name_str = re.sub(r'\s+', ' ', name_str).strip()  # Normalize whitespace
                        return name_str
                    
                    # Create normalized name columns for matching
                    df['_normalized_contractor'] = df['contractor_name'].apply(normalize_name)
                    pcab_data['_normalized_contractor'] = pcab_data['contractor_name'].apply(normalize_name)
                    
                    # Merge on normalized names
                    df = df.merge(
                        pcab_data[['_normalized_contractor', 'pcab_license_number', 'pcab_category']],
                        left_on='_normalized_contractor',
                        right_on='_normalized_contractor',
                        how='left'
                    )
                    
                    # Drop temporary column
                    df = df.drop(columns=['_normalized_contractor'], errors='ignore')
                    
                    # Debug: Check how many matches we got
                    matched = df['pcab_license_number'].notna().sum()
                    print(f"📊 PCAB data: Matched {matched} out of {len(df)} merchants")
            except Exception as e:
                print(f"⚠️  Warning: Could not join PCAB data: {e}")
                import traceback
                traceback.print_exc()
        
        # Apply search filter if provided
        if search and search.strip():
            search_term = search.strip().upper()
            mask = (
                df['name'].str.upper().str.contains(search_term, na=False) |
                df['contractor_name'].str.upper().str.contains(search_term, na=False) |
                df['normalized_name'].str.upper().str.contains(search_term, na=False)
            )
            df = df[mask]
        
        total = len(df)
        total_pages = (total + page_size - 1) // page_size
        
        # Paginate
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        df_page = df.iloc[start_idx:end_idx]
        
        # Select columns for display (now includes PCAB and PhilGEPS expiry)
        display_columns = [
            'name',
            'company_type',
            'reg_status',
            'reg_sec',
            'reg_philgeps_number',
            'reg_philgeps_expiry',  # Already split in parquet
            'pcab_license_number',
            'pcab_category',
            'project_count'
        ]
        
        # Convert to dict
        merchants = []
        for _, row in df_page.iterrows():
            merchant = {}
            for col in display_columns:
                value = row.get(col)
                if pd.isna(value):
                    merchant[col] = None
                elif col == 'pcab_license_number' and isinstance(value, (int, float)):
                    # Convert float to int then string to remove .0
                    merchant[col] = str(int(value)) if not pd.isna(value) else None
                elif isinstance(value, (int, float)):
                    merchant[col] = str(value)
                else:
                    merchant[col] = value
            
            merchants.append(merchant)
        
        return JSONResponse({
            "success": True,
            "data": merchants,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        })
        
    except Exception as e:
        print(f"❌ Error loading merchant data: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "success": False,
            "error": str(e),
            "data": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "total_pages": 0
        })

@app.get("/api/philgeps/amo")
async def get_amo_analysis():
    """Get PCAB AMO (Authorized Managing Officer) analysis - elected politicians serving as AMOs"""
    try:
        cache_path = DATA_ROOT / "philgeps_amo_cache.json"
        
        if not cache_path.exists():
            return JSONResponse({
                "success": False,
                "error": "AMO cache file not found. Please run scripts/generate_philgeps_amo_cache.py"
            })
        
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        return JSONResponse(cache_data)
        
    except Exception as e:
        print(f"Error loading AMO cache: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "success": False,
            "error": str(e)
        })

@app.get("/api/philgeps/projects/{contractor_name}")
async def search_contractor_projects(contractor_name: str):
    """Search for contractor projects across Flood, DIME, and PhilGEPS databases"""
    try:
        import asyncpg
        
        # Search pattern for fuzzy matching
        search_pattern = f"%{contractor_name}%"
        
        # Search flood database using MeiliSearch
        flood_projects = []
        flood_total = 0
        flood_count = 0
        try:
            flood_client = get_flood_client()
            # Search for contractor in flood control using the query parameter
            # MeiliSearch will search across all fields including Contractor
            flood_response = await flood_client._make_request(
                f"indexes/{flood_client.index_name}/search",
                "POST",
                data={
                    "q": contractor_name,
                    "limit": 10000,  # Get all matches
                    "attributesToRetrieve": [
                        "ProjectDescription", "Contractor", "ContractCost",
                        "InfraYear", "Region", "Province", "TypeofWork"
                    ]
                }
            )
            
            if flood_response and 'hits' in flood_response:
                # Filter results where contractor name contains the search term
                # (MeiliSearch's full-text search might return partial matches)
                filtered_hits = [
                    hit for hit in flood_response['hits']
                    if contractor_name.lower() in hit.get('Contractor', '').lower()
                ]
                
                flood_count = len(filtered_hits)
                flood_total = sum(float(hit.get('ContractCost', 0)) for hit in filtered_hits)
                
                # Sort by contract cost descending
                sorted_hits = sorted(filtered_hits, key=lambda x: float(x.get('ContractCost', 0)), reverse=True)
                
                for proj in sorted_hits:
                    flood_projects.append({
                        "description": proj.get('ProjectDescription', ''),
                        "contractor": proj.get('Contractor', ''),
                        "contractor_raw": proj.get('Contractor', ''),  # Raw name from database
                        "amount": float(proj.get('ContractCost', 0)),
                        "year": proj.get('InfraYear', ''),
                        "region": proj.get('Region', ''),
                        "province": proj.get('Province', ''),
                        "type": proj.get('TypeofWork', '')
                    })
        except Exception as e:
            print(f"Error querying flood database: {e}")
        
        # Connect to DIME database
        dime_projects = []
        dime_total = 0
        dime_count = 0
        try:
            dime_conn = await asyncpg.connect(
                host=os.getenv('POSTGRES_HOST', 'localhost'),
                port=int(os.getenv('POSTGRES_PORT', 5432)),
                user=os.getenv('POSTGRES_USER', 'budget_admin'),
                password=os.getenv('POSTGRES_PASSWORD', ''),
                database=os.getenv('POSTGRES_DB_DIME', 'dime')
            )
            
            # DIME contractors is an array field, so we need to check if ANY element matches
            dime_results = await dime_conn.fetch(
                """SELECT project_name, contractors, cost, 
                          province, city, status
                   FROM projects 
                   WHERE EXISTS (
                       SELECT 1 FROM unnest(contractors) AS c 
                       WHERE c ILIKE $1
                   )
                   ORDER BY cost DESC""",
                search_pattern
            )
            
            dime_stats = await dime_conn.fetchrow(
                """SELECT COUNT(*) as count,
                          COALESCE(SUM(cost), 0) as total,
                          COALESCE(AVG(cost), 0) as average,
                          COALESCE(MIN(cost), 0) as minimum,
                          COALESCE(MAX(cost), 0) as maximum
                   FROM projects 
                   WHERE EXISTS (
                       SELECT 1 FROM unnest(contractors) AS c 
                       WHERE c ILIKE $1
                   )""",
                search_pattern
            )
            
            dime_count = dime_stats['count']
            dime_total = float(dime_stats['total']) if dime_stats['total'] else 0
            
            for proj in dime_results:
                # Find the matching contractor from the array
                matching_contractor = ', '.join(proj['contractors']) if proj['contractors'] else 'N/A'
                
                dime_projects.append({
                    "title": proj['project_name'],
                    "contractor": matching_contractor,
                    "contractor_raw": matching_contractor,  # Raw name from database
                    "amount": float(proj['cost']) if proj['cost'] else 0,
                    "region": 'N/A',  # Region not in this table structure
                    "province": proj['province'],
                    "city": proj['city'],
                    "status": proj['status']
                })
            
            await dime_conn.close()
        except Exception as e:
            print(f"Error querying DIME database: {e}")
        
        # Connect to PhilGEPS database
        philgeps_projects = []
        philgeps_total = 0
        philgeps_count = 0
        try:
            philgeps_conn = await asyncpg.connect(
                host=os.getenv('POSTGRES_HOST', 'localhost'),
                port=int(os.getenv('POSTGRES_PORT', 5432)),
                user=os.getenv('POSTGRES_USER', 'budget_admin'),
                password=os.getenv('POSTGRES_PASSWORD', ''),
                database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
            )
            
            philgeps_results = await philgeps_conn.fetch(
                """SELECT reference_id, notice_title, awardee_name, contract_amount, 
                          business_category, organization_name, award_date, award_status
                   FROM contracts 
                   WHERE awardee_name ILIKE $1
                   ORDER BY contract_amount DESC
                   LIMIT 100""",
                search_pattern
            )
            
            philgeps_stats = await philgeps_conn.fetchrow(
                """SELECT COUNT(*) as count,
                          COALESCE(SUM(contract_amount), 0) as total,
                          COALESCE(AVG(contract_amount), 0) as average,
                          COALESCE(MIN(contract_amount), 0) as minimum,
                          COALESCE(MAX(contract_amount), 0) as maximum
                   FROM contracts 
                   WHERE awardee_name ILIKE $1""",
                search_pattern
            )
            
            philgeps_count = philgeps_stats['count']
            philgeps_total = float(philgeps_stats['total']) if philgeps_stats['total'] else 0
            
            for proj in philgeps_results:
                philgeps_projects.append({
                    "reference": proj['reference_id'],
                    "description": proj['notice_title'],
                    "awardee": proj['awardee_name'],
                    "awardee_raw": proj['awardee_name'],  # Raw name from database
                    "amount": float(proj['contract_amount']) if proj['contract_amount'] else 0,
                    "procurement_mode": proj['business_category'],
                    "procuring_entity": proj['organization_name'],
                    "award_date": proj['award_date'].isoformat() if proj['award_date'] else None,
                    "status": proj['award_status']
                })
            
            await philgeps_conn.close()
        except Exception as e:
            print(f"Error querying PhilGEPS database: {e}")
        
        # Connect to Infrawatch database (unmatched projects only)
        infrawatch_projects = []
        infrawatch_total = 0.0
        infrawatch_count = 0
        infrawatch_conn = None
        try:
            infrawatch_conn = await get_infrawatch_connection()
            if infrawatch_conn:
                infrawatch_results = await infrawatch_conn.fetch(
                    """
                    SELECT data
                    FROM infrawatch_projects_rows
                    WHERE philgeps_contract_id IS NULL
                      AND (
                        COALESCE(data->>'Contractor', '') ILIKE $1 OR
                        COALESCE(data->>'Contractor Name', '') ILIKE $1
                      )
                    ORDER BY COALESCE((data->>'Contract Price')::numeric, 0) DESC NULLS LAST
                    LIMIT 200
                    """,
                    search_pattern
                )

                for row in infrawatch_results:
                    record = row["data"]
                    if isinstance(record, str):
                        try:
                            record = json.loads(record)
                        except json.JSONDecodeError:
                            continue
                    if not isinstance(record, dict):
                        continue

                    contractor_value = (
                        record.get("Contractor")
                        or record.get("Contractor Name")
                        or record.get("Contractor_Name")
                        or ""
                    )
                    if not contractor_value:
                        continue

                    amount_raw = (
                        record.get("Contract Price")
                        or record.get("Contract Amount")
                        or record.get("Amount")
                    )

                    amount_value = 0.0
                    if isinstance(amount_raw, (int, float)):
                        amount_value = float(amount_raw)
                    elif amount_raw:
                        try:
                            amount_value = float(str(amount_raw).replace("₱", "").replace(",", "").strip())
                        except Exception:
                            amount_value = 0.0

                    if amount_value:
                        infrawatch_total += amount_value
                    infrawatch_count += 1

                    infrawatch_projects.append({
                        "contract_id": record.get("Contract ID") or record.get("Contract No"),
                        "description": record.get("Contract Details") or record.get("Project Description") or "",
                        "contractor": contractor_value,
                        "contractor_raw": contractor_value,
                        "amount": amount_value,
                        "fund_source": record.get("Fund Source"),
                        "status": record.get("Contract Status"),
                        "implementing_agency": record.get("Implementing Agency"),
                        "effectivity_date": record.get("Contract Effectivity Date"),
                        "expiry_date": record.get("Contract Expiry Date")
                    })
        except Exception as e:
            print(f"Error querying Infrawatch database: {e}")
        finally:
            if infrawatch_conn:
                await infrawatch_conn.close()
        
        # STEP 1: Deduplicate within each database first (especially PhilGEPS)
        
        def deduplicate_by_reference_and_amount(projects_list, ref_key, amount_key):
            """Deduplicate within a single database by reference number or exact amount"""
            seen = set()
            unique = []
            for proj in projects_list:
                # Create signature using reference (if available) or exact amount
                ref = proj.get(ref_key, "")
                amount = proj.get(amount_key, 0)
                sig = f"{ref}|{amount}" if ref else f"_|{amount}"
                
                if sig not in seen:
                    seen.add(sig)
                    unique.append(proj)
            return unique
        
        # Deduplicate PhilGEPS by reference_id (contract number)
        philgeps_projects_dedup = deduplicate_by_reference_and_amount(philgeps_projects, "reference", "amount")
        philgeps_count_dedup = len(philgeps_projects_dedup)
        philgeps_total_dedup = sum(p.get("amount", 0) for p in philgeps_projects_dedup)
        
        infrawatch_projects_dedup = deduplicate_by_reference_and_amount(infrawatch_projects, "contract_id", "amount")
        infrawatch_count_dedup = len(infrawatch_projects_dedup)
        infrawatch_total_dedup = sum(p.get("amount", 0) for p in infrawatch_projects_dedup)
        
        # Deduplicate DIME (though it should already be clean)
        dime_projects_dedup = deduplicate_by_reference_and_amount(dime_projects, "title", "amount")
        dime_count_dedup = len(dime_projects_dedup)
        dime_total_dedup = sum(p.get("amount", 0) for p in dime_projects_dedup)
        
        # Deduplicate Flood (should be clean from MeiliSearch)
        flood_projects_dedup = deduplicate_by_reference_and_amount(flood_projects, "description", "amount")
        flood_count_dedup = len(flood_projects_dedup)
        flood_total_dedup = sum(p.get("amount", 0) for p in flood_projects_dedup)
        
        print(f"🔍 Deduplication within databases:")
        print(f"  Flood: {len(flood_projects)} → {flood_count_dedup} ({len(flood_projects) - flood_count_dedup} internal dupes)")
        print(f"  DIME: {len(dime_projects)} → {dime_count_dedup} ({len(dime_projects) - dime_count_dedup} internal dupes)")
        print(f"  PhilGEPS: {len(philgeps_projects)} → {philgeps_count_dedup} ({len(philgeps_projects) - philgeps_count_dedup} internal dupes)")
        print(f"  Infrawatch: {len(infrawatch_projects)} → {infrawatch_count_dedup} ({len(infrawatch_projects) - infrawatch_count_dedup} internal dupes)")
        
        # STEP 2: Deduplicate across databases using correlation logic
        
        def normalize_location(location: str) -> str:
            """Normalize location string for comparison"""
            if not location:
                return ""
            location = location.upper().strip()
            for word in ["PROVINCE", "PROVINCE OF", "CITY OF", "MUNICIPALITY OF", "BARANGAY"]:
                location = location.replace(word, "")
            return " ".join(location.split())
        
        def amount_match(amount1: float, amount2: float, tolerance_percent: float = 5.0) -> bool:
            """Check if amounts match within tolerance"""
            if amount1 == 0 or amount2 == 0:
                return False
            if amount1 == amount2:
                return True
            diff_percent = abs(amount1 - amount2) / max(amount1, amount2) * 100
            return diff_percent <= tolerance_percent
        
        def location_match(loc1: str, loc2: str) -> bool:
            """Check if locations match"""
            if not loc1 or not loc2:
                return False
            norm1 = normalize_location(loc1)
            norm2 = normalize_location(loc2)
            if not norm1 or not norm2:
                return False
            return norm1 in norm2 or norm2 in norm1
        
        # Build list with deduplicated projects
        all_projects = []
        
        for proj in flood_projects_dedup:
            all_projects.append({
                "source": "flood",
                "amount": proj.get("amount", 0),
                "province": proj.get("province", ""),
                "region": proj.get("region", "")
            })
        
        for proj in dime_projects_dedup:
            all_projects.append({
                "source": "dime",
                "amount": proj.get("amount", 0),
                "province": proj.get("province", ""),
                "region": proj.get("region", "")
            })
        
        for proj in philgeps_projects_dedup:
            all_projects.append({
                "source": "philgeps",
                "amount": proj.get("amount", 0),
                "province": "",
                "region": ""
            })

        for proj in infrawatch_projects_dedup:
            all_projects.append({
                "source": "infrawatch",
                "amount": proj.get("amount", 0),
                "province": "",
                "region": ""
            })
        
        # Cross-database deduplication
        unique_projects = []
        seen_indices = set()
        cross_db_duplicates = 0
        
        for i, proj1 in enumerate(all_projects):
            if i in seen_indices:
                continue
            
            seen_indices.add(i)
            unique_projects.append(proj1)
            
            # Check for cross-database duplicates
            for j in range(i + 1, len(all_projects)):
                if j in seen_indices:
                    continue
                
                proj2 = all_projects[j]
                
                # Only check cross-database (not within same database)
                if proj1["source"] == proj2["source"]:
                    continue

                if "infrawatch" in (proj1["source"], proj2["source"]):
                    continue
                
                is_duplicate = False
                
                # For Flood + DIME: use amount + location
                if proj1["source"] in ["flood", "dime"] and proj2["source"] in ["flood", "dime"]:
                    if amount_match(proj1["amount"], proj2["amount"]):
                        if location_match(proj1["province"], proj2["province"]) or location_match(proj1["region"], proj2["region"]):
                            is_duplicate = True
                
                # For PhilGEPS vs Flood/DIME: only exact amount (no location in PhilGEPS)
                # Be conservative - only mark as duplicate if exact same amount
                elif "philgeps" in [proj1["source"], proj2["source"]]:
                    if proj1["amount"] == proj2["amount"]:
                        is_duplicate = True
                
                if is_duplicate:
                    seen_indices.add(j)
                    cross_db_duplicates += 1
        
        # Calculate final statistics
        unique_count = len(unique_projects)
        unique_total = sum(p["amount"] for p in unique_projects)
        
        # Total duplicates = internal + cross-database
        internal_duplicates = (
            (len(flood_projects) - flood_count_dedup)
            + (len(dime_projects) - dime_count_dedup)
            + (len(philgeps_projects) - philgeps_count_dedup)
            + (len(infrawatch_projects) - infrawatch_count_dedup)
        )
        total_duplicates = internal_duplicates + cross_db_duplicates
        
        total_raw = flood_count + dime_count + philgeps_count + infrawatch_count
        simple_total = flood_total + dime_total + philgeps_total + infrawatch_total
        
        print(f"🔍 Cross-database deduplication:")
        print(f"  Internal duplicates: {internal_duplicates}")
        print(f"  Cross-DB duplicates: {cross_db_duplicates}")
        print(f"  Total duplicates: {total_duplicates}")
        print(f"  Unique projects: {unique_count}")
        print(f"  Unique total: ₱{unique_total:,.2f}")
        
        # BASIC CHECK: Ensure deduplicated total >= max single database
        max_single_db_total = max(flood_total_dedup, dime_total_dedup, philgeps_total_dedup, infrawatch_total_dedup)
        max_single_db_count = max(flood_count_dedup, dime_count_dedup, philgeps_count_dedup, infrawatch_count_dedup)
        
        validation_passed = unique_total >= max_single_db_total
        
        if not validation_passed:
            print(f"⚠️ VALIDATION WARNING: Deduplicated total (₱{unique_total:,.2f}) < max single DB (₱{max_single_db_total:,.2f})")
            print(f"   Using max single DB as baseline to ensure accuracy")
            # Use the larger value as safeguard
            unique_total = max(unique_total, max_single_db_total)
            unique_count = max(unique_count, max_single_db_count)
        
        return JSONResponse({
            "success": True,
            "contractor_name": contractor_name,
            "summary": {
                "total_projects": unique_count,  # Deduplicated count
                "total_value": unique_total,  # Deduplicated value
                "raw_total_projects": total_raw,  # Raw sum before deduplication
                "raw_total_value": simple_total,  # Raw sum before deduplication
                "duplicate_count": total_duplicates,  # Total duplicates (internal + cross-DB)
                "internal_duplicates": internal_duplicates,  # Duplicates within same database
                "cross_db_duplicates": cross_db_duplicates,  # Duplicates across databases
                "validation_passed": validation_passed,  # Basic check result
                "flood": {
                    "count": flood_count,
                    "total": flood_total,
                    "count_dedup": flood_count_dedup,
                    "total_dedup": flood_total_dedup
                },
                "dime": {
                    "count": dime_count,
                    "total": dime_total,
                    "count_dedup": dime_count_dedup,
                    "total_dedup": dime_total_dedup
                },
                "philgeps": {
                    "count": philgeps_count,
                    "total": philgeps_total,
                    "count_dedup": philgeps_count_dedup,
                    "total_dedup": philgeps_total_dedup
                },
                "infrawatch": {
                    "count": infrawatch_count,
                    "total": infrawatch_total,
                    "count_dedup": infrawatch_count_dedup,
                    "total_dedup": infrawatch_total_dedup
                }
            },
            "projects": {
                "flood": flood_projects_dedup,  # Return deduplicated lists
                "dime": dime_projects_dedup,
                "philgeps": philgeps_projects_dedup,
                "infrawatch": infrawatch_projects_dedup
            }
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/dime/projects")
async def dime_projects_api(
    page: int = 1,
    limit: int = 50,
    sort_by: str = "project_name",
    sort_order: str = "ASC",
    status: str = None,
    region: str = None,
    province: str = None,
    city: str = None,
    barangay: str = None,
    search: str = None
):
    """Get DIME projects with pagination and filtering - no authentication required"""
    try:
        filters = {}
        if status:
            filters['status'] = status
        if region:
            filters['region'] = region
        if province:
            filters['province'] = province
        if city:
            filters['city'] = city
        if barangay:
            filters['barangay'] = barangay
        if search:
            filters['search'] = search
        
        result = await get_dime_projects(page, limit, sort_by, sort_order, filters)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/dime/project-suggestions")
async def dime_project_suggestions_api(query: str, limit: int = 10):
    """Get DIME project name suggestions for autocomplete - no authentication required"""
    try:
        result = await get_dime_suggestions('project_name', query, limit)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/dime/barangay-suggestions")
async def dime_barangay_suggestions_api(query: str, limit: int = 10):
    """Get DIME barangay suggestions for autocomplete - no authentication required"""
    try:
        result = await get_dime_suggestions('barangay', query, limit)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/dime/city-suggestions")
async def dime_city_suggestions_api(query: str, limit: int = 10):
    """Get DIME city suggestions for autocomplete - no authentication required"""
    try:
        result = await get_dime_suggestions('city', query, limit)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/dime/province-suggestions")
async def dime_province_suggestions_api(query: str, limit: int = 10):
    """Get DIME province suggestions for autocomplete - no authentication required"""
    try:
        result = await get_dime_suggestions('province', query, limit)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/dime/fastest-projects")
async def dime_fastest_projects_api():
    """Get fastest completed DIME projects - no authentication required"""
    try:
        import asyncpg
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_DIME', 'dime')
        )
        
        # Get fastest completed projects (top 50)
        query = """
        SELECT 
            project_name,
            project_description,
            total_project_cost,
            start_date,
            end_date,
            project_status,
            implementing_office,
            region,
            province,
            city_municipality,
            barangay,
            project_type,
            -- Calculate completion time in days
            CASE 
                WHEN start_date IS NOT NULL AND end_date IS NOT NULL 
                THEN EXTRACT(EPOCH FROM (end_date - start_date)) / 86400
                ELSE NULL
            END as completion_days
        FROM projects 
        WHERE project_status = 'Completed'
          AND start_date IS NOT NULL 
          AND end_date IS NOT NULL
          AND start_date < end_date
        ORDER BY completion_days ASC
        LIMIT 50
        """
        
        results = await conn.fetch(query)
        await conn.close()
        
        # Process results
        projects = []
        for row in results:
            projects.append({
                'project_name': row['project_name'],
                'project_description': row['project_description'],
                'total_project_cost': float(row['total_project_cost']) if row['total_project_cost'] else 0,
                'start_date': row['start_date'].isoformat() if row['start_date'] else None,
                'end_date': row['end_date'].isoformat() if row['end_date'] else None,
                'project_status': row['project_status'],
                'implementing_office': row['implementing_office'],
                'region': row['region'],
                'province': row['province'],
                'city_municipality': row['city_municipality'],
                'barangay': row['barangay'],
                'project_type': row['project_type'],
                'completion_days': float(row['completion_days']) if row['completion_days'] else None
            })
        
        return JSONResponse({
            "success": True,
            "projects": projects,
            "count": len(projects),
            "generated_at": datetime.now().isoformat(),
            "description": "Top 50 fastest completed DIME projects"
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

# ============================================================================
# Hidden Flood Control API Endpoints
# ============================================================================

@app.get("/api/flood/hidden-projects")
async def hidden_flood_projects_api(page: int = 1, limit: int = 20):
    """Get projects that mention flood but are not in Meilisearch database - no authentication required"""
    try:
        import asyncpg
        
        # Connect to PhilGEPS database to find flood projects
        philgeps_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
        )
        
        # First, let's check what data we have in PhilGEPS
        total_contracts = await philgeps_conn.fetchval("SELECT COUNT(*) FROM contracts")
        flood_contracts = await philgeps_conn.fetchval("""
            SELECT COUNT(*) FROM contracts 
            WHERE (
                LOWER(award_title) LIKE '%flood%' 
                OR LOWER(notice_title) LIKE '%flood%'
                OR LOWER(award_title) LIKE '%drainage%'
                OR LOWER(notice_title) LIKE '%drainage%'
                OR LOWER(award_title) LIKE '%canal%'
                OR LOWER(notice_title) LIKE '%canal%'
                OR LOWER(award_title) LIKE '%water%'
                OR LOWER(notice_title) LIKE '%water%'
            )
        """)
        
        print(f"🔍 Debug PhilGEPS: {total_contracts} total contracts, {flood_contracts} flood contracts")
        
        # Calculate offset for pagination
        offset = (page - 1) * limit
        
        # Find flood contracts that cannot be correlated with Meilisearch flood database
        # These are PhilGEPS flood contracts that don't have a corresponding match in Meilisearch
        hidden_projects = await philgeps_conn.fetch("""
            SELECT reference_id as id, award_title as project_name, notice_title as description, 
                   awardee_name as contractor, contract_amount as cost, 
                   area_of_delivery as location, award_status as status, 
                   award_date as date_started, award_date as contract_completion_date
            FROM contracts 
            WHERE (
                  LOWER(award_title) LIKE '%flood%' 
                  OR LOWER(notice_title) LIKE '%flood%'
                  OR LOWER(award_title) LIKE '%drainage%'
                  OR LOWER(notice_title) LIKE '%drainage%'
                  OR LOWER(award_title) LIKE '%canal%'
                  OR LOWER(notice_title) LIKE '%canal%'
                  OR LOWER(award_title) LIKE '%water%'
                  OR LOWER(notice_title) LIKE '%water%'
              )
              AND (meilisearch_id IS NULL OR meilisearch_id = '')
            ORDER BY contract_amount DESC
            LIMIT $1 OFFSET $2
        """, limit, offset)
        
        # Get total count for pagination info
        total_count = await philgeps_conn.fetchval("""
            SELECT COUNT(*) FROM contracts 
            WHERE (
                  LOWER(award_title) LIKE '%flood%' 
                  OR LOWER(notice_title) LIKE '%flood%'
                  OR LOWER(award_title) LIKE '%drainage%'
                  OR LOWER(notice_title) LIKE '%drainage%'
                  OR LOWER(award_title) LIKE '%canal%'
                  OR LOWER(notice_title) LIKE '%canal%'
                  OR LOWER(award_title) LIKE '%water%'
                  OR LOWER(notice_title) LIKE '%water%'
              )
              AND (meilisearch_id IS NULL OR meilisearch_id = '')
        """)
        
        await philgeps_conn.close()
        
        projects_list = []
        total_value = 0
        
        for proj in hidden_projects:
            # Extract year from award_date
            year = None
            if proj.get('date_started'):
                try:
                    year = proj['date_started'].year if hasattr(proj['date_started'], 'year') else None
                except:
                    pass
            
            # Contractor is already in the data from PhilGEPS
            contractors = [proj['contractor']] if proj['contractor'] else []
            
            project_value = float(proj['cost']) if proj['cost'] else 0
            total_value += project_value
            
            projects_list.append({
                'id': proj['id'],
                'project_name': proj['project_name'],
                'description': proj['description'],
                'contractors': contractors,
                'cost': project_value,
                'province': proj['location'] or '',
                'city': proj['location'] or '',
                'region': proj['location'] or '',
                'status': proj['status'],
                'year': year,
                'date_started': proj['date_started'].isoformat() if proj.get('date_started') else None,
                'contract_completion_date': proj['contract_completion_date'].isoformat() if proj.get('contract_completion_date') else None
            })
        
        await philgeps_conn.close()
        
        # Calculate pagination info
        total_pages = (total_count + limit - 1) // limit
        start_item = offset + 1
        end_item = min(offset + limit, total_count)
        
        return JSONResponse({
            "success": True,
            "projects": projects_list,
            "count": len(projects_list),
            "total_count": total_count,
            "total_value": total_value,
            "average_value": total_value / len(projects_list) if projects_list else 0,
            "pagination": {
                "page": page,
                "limit": limit,
                "total_pages": total_pages,
                "start_item": start_item,
                "end_item": end_item,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/flood/hidden-contractors")
async def hidden_flood_contractors_api(limit: int = 20):
    """Get top contractors from PhilGEPS with flood-related projects - no authentication required"""
    try:
        import asyncpg
        
        # Connect to PhilGEPS database to get contractors with flood projects
        philgeps_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
        )
        
        # First, let's check what data we have in PhilGEPS
        total_contracts = await philgeps_conn.fetchval("SELECT COUNT(*) FROM contracts")
        flood_contracts = await philgeps_conn.fetchval("""
            SELECT COUNT(*) FROM contracts 
            WHERE (
                LOWER(award_title) LIKE '%flood%' 
                OR LOWER(notice_title) LIKE '%flood%'
                OR LOWER(award_title) LIKE '%drainage%'
                OR LOWER(notice_title) LIKE '%drainage%'
                OR LOWER(award_title) LIKE '%canal%'
                OR LOWER(notice_title) LIKE '%canal%'
                OR LOWER(award_title) LIKE '%water%'
                OR LOWER(notice_title) LIKE '%water%'
            )
        """)
        
        print(f"🔍 Debug PhilGEPS: {total_contracts} total contracts, {flood_contracts} flood-related contracts")
        
        # Get top contractors from PhilGEPS with flood-related projects that cannot be correlated with Meilisearch
        contractors = await philgeps_conn.fetch(f"""
            SELECT 
                awardee_name as contractor_name,
                COUNT(*) as project_count,
                SUM(contract_amount) as total_value,
                AVG(contract_amount) as avg_value,
                MAX(contract_amount) as max_value,
                MIN(contract_amount) as min_value,
                array_agg(DISTINCT area_of_delivery) as areas,
                array_agg(DISTINCT business_category) as categories
            FROM contracts 
            WHERE awardee_name IS NOT NULL 
              AND awardee_name != ''
              AND (
                  LOWER(award_title) LIKE '%flood%' 
                  OR LOWER(notice_title) LIKE '%flood%'
                  OR LOWER(award_title) LIKE '%drainage%'
                  OR LOWER(notice_title) LIKE '%drainage%'
                  OR LOWER(award_title) LIKE '%canal%'
                  OR LOWER(notice_title) LIKE '%canal%'
                  OR LOWER(award_title) LIKE '%water%'
                  OR LOWER(notice_title) LIKE '%water%'
              )
              AND (meilisearch_id IS NULL OR meilisearch_id = '')
            GROUP BY awardee_name
            HAVING awardee_name IS NOT NULL AND awardee_name != ''
            ORDER BY project_count DESC, total_value DESC
            LIMIT $1
        """, limit)
        
        await philgeps_conn.close()
        
        contractors_list = []
        for contractor in contractors:
            contractors_list.append({
                'contractor_name': contractor['contractor_name'],
                'project_count': contractor['project_count'],
                'total_value': float(contractor['total_value']) if contractor['total_value'] else 0,
                'avg_value': float(contractor['avg_value']) if contractor['avg_value'] else 0,
                'max_value': float(contractor['max_value']) if contractor['max_value'] else 0,
                'min_value': float(contractor['min_value']) if contractor['min_value'] else 0,
                'areas': contractor.get('areas', []),
                'categories': contractor.get('categories', [])
            })
        
        return JSONResponse({
            "success": True,
            "contractors": contractors_list,
            "count": len(contractors_list),
            "total_contracts": total_contracts,
            "flood_contracts": flood_contracts,
            "debug": {
                "total_contracts": total_contracts,
                "flood_contracts": flood_contracts,
                "contractors_found": len(contractors_list)
            }
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/flood/hidden-contractors-cached")
async def hidden_flood_contractors_cached_api():
    """Get cached excluded flood contractors data for fast loading"""
    try:
        import json
        from pathlib import Path
        
        # Try to load from cache file
        cache_file = Path("static/data/excluded_flood_contractors_cache.json")
        
        if cache_file.exists():
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Check if cache is recent (less than 1 hour old)
            if 'generated_at' in cache_data:
                from datetime import datetime, timedelta
                cache_time = datetime.fromisoformat(cache_data['generated_at'])
                if datetime.now() - cache_time < timedelta(hours=1):
                    return JSONResponse({
                        "success": True,
                        "contractors": cache_data.get('contractors', []),
                        "count": cache_data.get('count', 0),
                        "cached": True,
                        "generated_at": cache_data.get('generated_at'),
                        "cache_version": cache_data.get('cache_version', '1.0')
                    })
        
        # If no cache or cache is old, return empty result
        return JSONResponse({
            "success": True,
            "contractors": [],
            "count": 0,
            "cached": False,
            "message": "Cache not available or expired"
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/flood/hidden-statistics")
async def hidden_flood_statistics_api():
    """Get comprehensive statistics for hidden flood projects - no authentication required"""
    try:
        # Try to load from cached JSON file first
        cache_file = "static/data/hidden_flood_statistics_cache.json"
        if os.path.exists(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
                if cached_data.get('success'):
                    return JSONResponse(cached_data)
        
        # Fallback to database calculation if cache not available
        import asyncpg
        
        # Connect to PhilGEPS database
        philgeps_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
        )
        
        # Get total flood projects from the flood control database directly
        try:
            # Connect to the flood control database to get the actual count
            flood_conn = await asyncpg.connect(
                host=os.getenv('POSTGRES_HOST', 'localhost'),
                port=int(os.getenv('POSTGRES_PORT', 5432)),
                user=os.getenv('POSTGRES_USER', 'budget_admin'),
                password=os.getenv('POSTGRES_PASSWORD', ''),
                database=os.getenv('POSTGRES_DB_FLOOD', 'flood')
            )
            
            # Get the total count of flood control projects
            result = await flood_conn.fetchrow("SELECT COUNT(*) as total FROM flood_control_projects")
            total_meilisearch_projects = result['total'] if result else 0
            
            await flood_conn.close()
        except Exception as e:
            print(f"Error getting flood statistics from database: {e}")
            # Fallback: try to get from MeiliSearch stats
            try:
                client = get_flood_client()
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{client.base_url}/stats") as response:
                        if response.status == 200:
                            stats_data = await response.json()
                            total_meilisearch_projects = stats_data.get('numberOfDocuments', 0)
                        else:
                            total_meilisearch_projects = 0
            except Exception as e2:
                print(f"Error getting flood statistics from MeiliSearch: {e2}")
                total_meilisearch_projects = 0
        
        # Get comprehensive statistics from PhilGEPS
        stats = await philgeps_conn.fetchrow("""
            WITH hidden_flood_contracts AS (
                SELECT reference_id as id, award_title as project_name, awardee_name as contractor, 
                       contract_amount as cost, area_of_delivery as location
                FROM contracts 
                WHERE (
                      LOWER(award_title) LIKE '%flood%' 
                      OR LOWER(notice_title) LIKE '%flood%'
                      OR LOWER(award_title) LIKE '%drainage%'
                      OR LOWER(notice_title) LIKE '%drainage%'
                      OR LOWER(award_title) LIKE '%canal%'
                      OR LOWER(notice_title) LIKE '%canal%'
                      OR LOWER(award_title) LIKE '%water%'
                      OR LOWER(notice_title) LIKE '%water%'
                  )
                  AND (meilisearch_id IS NULL OR meilisearch_id = '')
            ),
            contractor_stats AS (
                SELECT 
                    contractor as contractor_name,
                    COUNT(*) as project_count,
                    SUM(cost) as total_value
                FROM hidden_flood_contracts
                WHERE contractor IS NOT NULL AND contractor != ''
                GROUP BY contractor
                HAVING contractor IS NOT NULL AND contractor != ''
            )
            SELECT 
                COUNT(*) as total_projects,
                COALESCE(SUM(cost), 0) as total_value,
                COALESCE(AVG(cost), 0) as avg_value,
                COALESCE(MAX(cost), 0) as max_value,
                COALESCE(MIN(cost), 0) as min_value,
                COUNT(DISTINCT contractor) as unique_contractors,
                (SELECT contractor_name FROM contractor_stats ORDER BY project_count DESC LIMIT 1) as top_contractor,
                (SELECT project_count FROM contractor_stats ORDER BY project_count DESC LIMIT 1) as top_contractor_projects,
                (SELECT total_value FROM contractor_stats ORDER BY total_value DESC LIMIT 1) as top_contractor_value
            FROM hidden_flood_contracts
        """)
        
        # Calculate omission rate: excluded / (total_flood + excluded)
        hidden_projects_count = stats['total_projects']
        total_flood_projects = total_meilisearch_projects + hidden_projects_count
        
        await philgeps_conn.close()
        
        # Debug logging
        print(f"DEBUG: total_meilisearch_projects = {total_meilisearch_projects}")
        print(f"DEBUG: hidden_projects_count = {hidden_projects_count}")
        print(f"DEBUG: total_flood_projects = {total_flood_projects}")
        
        if total_flood_projects > 0:
            omission_rate = (hidden_projects_count / total_flood_projects) * 100
        else:
            omission_rate = 0
            
        print(f"DEBUG: omission_rate = {omission_rate}%")
        
        return JSONResponse({
            "success": True,
            "total_projects": stats['total_projects'],
            "total_value": float(stats['total_value']) if stats['total_value'] else 0,
            "avg_value": float(stats['avg_value']) if stats['avg_value'] else 0,
            "max_value": float(stats['max_value']) if stats['max_value'] else 0,
            "min_value": float(stats['min_value']) if stats['min_value'] else 0,
            "unique_contractors": stats['unique_contractors'],
            "top_contractor": {
                "name": stats['top_contractor'],
                "project_count": stats['top_contractor_projects'],
                "total_value": float(stats['top_contractor_value']) if stats['top_contractor_value'] else 0
            },
            "omission_rate": round(omission_rate, 1),
            "total_meilisearch_projects": total_meilisearch_projects,
            "total_flood_projects": total_flood_projects
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/dynasty")
async def dynasty_data_api(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=1000, description="Number of records per page"),
    search: str = Query("", description="Search term for filtering"),
    position: str = Query("", description="Filter by position"),
    region: str = Query("", description="Filter by region"),
    dynasty: str = Query("", description="Filter by dynasty status (dynasty/non-dynasty)"),
    first_name: str = Query("", description="Filter by first name"),
    last_name: str = Query("", description="Filter by last name")
):
    """Get paginated political dynasty data with search and filtering"""
    try:
        import asyncpg
        
        # Connect to dynasty database
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
        )
        
        # Filter positions: elected positions only (President, Vice President, Senator, Mayor, Congressmen, Councilor, Governor) with max 2 words
        # OR BAC positions (any word count)
        # OR ENGINEER positions (max 2 words)
        where_conditions = [
            "position IS NOT NULL AND position != ''",
            # Position must match elected positions (max 2 words) OR BAC positions (any word count) OR ENGINEER positions (max 2 words)
            """(
                (
                    UPPER(position) ILIKE ANY(ARRAY['%PRESIDENT%', '%VICE PRESIDENT%', '%SENATOR%', '%MAYOR%', 
                                                      '%CONGRESSMEN%', '%CONGRESSMAN%', '%COUNCILOR%', '%GOVERNOR%'])
                    AND 
                    LENGTH(position) - LENGTH(REPLACE(position, ' ', '')) + 1 <= 2
                )
                OR
                (
                    UPPER(position) LIKE '%BAC%'
                )
                OR
                (
                    UPPER(position) LIKE '%ENGINEER%'
                    AND 
                    LENGTH(position) - LENGTH(REPLACE(position, ' ', '')) + 1 <= 2
                )
            )"""
        ]
        params = []
        param_count = 0
        
        # Precise name filters (additional refinement on top of top 500 filter)
        if first_name:
            param_count += 1
            where_conditions.append(f"first_name ILIKE ${param_count}")
            params.append(f"%{first_name}%")
        if last_name:
            param_count += 1
            where_conditions.append(f"last_name ILIKE ${param_count}")
            params.append(f"%{last_name}%")

        # Generic search filter (fallback)
        if search and not (first_name or last_name):
            param_count += 1
            where_conditions.append(f"""
                (first_name ILIKE ${param_count} OR 
                 last_name ILIKE ${param_count} OR 
                 party ILIKE ${param_count} OR 
                 region ILIKE ${param_count} OR 
                 province ILIKE ${param_count} OR 
                 municipality_city ILIKE ${param_count} OR 
                 position ILIKE ${param_count})
            """)
            params.append(f"%{search}%")
        
        # Position filter
        if position:
            param_count += 1
            where_conditions.append(f"position ILIKE ${param_count}")
            params.append(f"%{position}%")
        
        # Region filter
        if region:
            param_count += 1
            where_conditions.append(f"region ILIKE ${param_count}")
            params.append(f"%{region}%")
        
        # Dynasty filter
        if dynasty.lower() == "dynasty":
            where_conditions.append("fat = 1")
        elif dynasty.lower() == "non-dynasty":
            where_conditions.append("fat = 0")
        
        # Note: Do not force winners-only so appointed roles (e.g., BAC) can be returned
        
        # Build complete WHERE clause
        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)
        
        # Do not short-circuit when there are no winners; allow appointed/non-winner records
        
        # Get total count
        count_query = f"SELECT COUNT(*) FROM political_dynasties {where_clause}"
        total_count = await conn.fetchval(count_query, *params)
        
        # Calculate pagination
        total_pages = (total_count + limit - 1) // limit
        offset = (page - 1) * limit
        
        # Get paginated data
        data_query = f"""
            SELECT 
                id,
                first_name,
                last_name,
                party,
                region,
                province,
                municipality_city,
                position,
                year,
                fat,
                government_branch,
                organization
            FROM political_dynasties 
            {where_clause}
            ORDER BY year DESC, last_name ASC, first_name ASC
            LIMIT ${param_count + 1} OFFSET ${param_count + 2}
        """
        
        # Add limit and offset to params
        params.extend([limit, offset])
        
        records = await conn.fetch(data_query, *params)
        
        # Convert records to dictionaries
        data = []
        for record in records:
            data.append({
                "id": record['id'],
                "first_name": record['first_name'],
                "last_name": record['last_name'],
                "party": record['party'],
                "region": record['region'],
                "province": record['province'],
                "municipality_city": record['municipality_city'],
                "position": record['position'],
                "year": record['year'],
                "fat": record['fat'],
                "organization": record['organization']
            })
        
        await conn.close()
        
        return JSONResponse({
            "success": True,
            "data": data,
            "pagination": {
                "page": page,
                "limit": limit,
                "total_count": total_count,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/dynasty/positions")
async def dynasty_positions_api(
    q: str = Query("", description="Optional prefix filter for positions"),
    limit: int = Query(500, ge=1, le=2000),
    first_name: str = Query("", description="Optional first name filter to align suggestions"),
    last_name: str = Query("", description="Optional last name filter to align suggestions"),
    region: str = Query("", description="Optional region filter to align suggestions"),
    dynasty: str = Query("", description="Optional dynasty filter (dynasty/non-dynasty) to align suggestions")
):
    """Return distinct positions (elected positions, BAC positions, or ENGINEER positions)
    with max 2 words, filtered by prefix, sorted alphabetically."""
    conn = None
    try:
        import asyncpg

        connect_timeout = float(os.getenv("DYNASTY_DB_CONNECT_TIMEOUT", "2"))
        query_timeout = float(os.getenv("DYNASTY_DB_QUERY_TIMEOUT", "5"))

        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty'),
            timeout=connect_timeout,
        )
        
        params = []
        where_conditions = [
            "position IS NOT NULL AND position != ''",
            # Position must match elected positions (max 2 words) OR BAC positions (any word count) OR ENGINEER positions (max 2 words)
            """(
                (
                    UPPER(position) ILIKE ANY(ARRAY['%PRESIDENT%', '%VICE PRESIDENT%', '%SENATOR%', '%MAYOR%', 
                                                      '%CONGRESSMEN%', '%CONGRESSMAN%', '%COUNCILOR%', '%GOVERNOR%'])
                    AND 
                    LENGTH(position) - LENGTH(REPLACE(position, ' ', '')) + 1 <= 2
                )
                OR
                (
                    UPPER(position) LIKE '%BAC%'
                )
                OR
                (
                    UPPER(position) LIKE '%ENGINEER%'
                    AND 
                    LENGTH(position) - LENGTH(REPLACE(position, ' ', '')) + 1 <= 2
                )
            )"""
        ]
        
        param_idx = 0
        if q:
            param_idx += 1
            where_conditions.append(f"position ILIKE ${param_idx}")
            params.append(f"{q}%")
        if first_name:
            param_idx += 1
            where_conditions.append(f"first_name ILIKE ${param_idx}")
            params.append(f"%{first_name}%")
        if last_name:
            param_idx += 1
            where_conditions.append(f"last_name ILIKE ${param_idx}")
            params.append(f"%{last_name}%")
        if region:
            param_idx += 1
            where_conditions.append(f"region ILIKE ${param_idx}")
            params.append(f"%{region}%")
        if dynasty.lower() == 'dynasty':
            where_conditions.append("fat = 1")
        elif dynasty.lower() == 'non-dynasty':
            where_conditions.append("fat = 0")

        where_clause = "WHERE " + " AND ".join(where_conditions)
        query = f"""
            SELECT DISTINCT position
            FROM political_dynasties
            {where_clause}
            ORDER BY position ASC
            LIMIT {limit}
        """
        rows = await conn.fetch(query, *params, timeout=query_timeout)
        return JSONResponse({
            "success": True,
            "data": [r['position'] for r in rows]
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})
    finally:
        if conn is not None:
            try:
                await conn.close()
            except Exception:
                pass

@app.get("/api/dynasty/autocomplete/first-names")
async def dynasty_first_names_autocomplete(q: str = Query("", description="Optional prefix for first name"), limit: int = Query(200, ge=1, le=1000)):
    """Autocomplete for first names among winners."""
    try:
        import asyncpg
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
        )
        params = []
        where_clause = "WHERE winner = true AND first_name IS NOT NULL AND first_name != ''"
        if q:
            where_clause += " AND first_name ILIKE $1"
            params.append(f"{q}%")
        query = f"""
            SELECT first_name, COUNT(*) as cnt
            FROM political_dynasties
            {where_clause}
            GROUP BY first_name
            ORDER BY cnt DESC, first_name ASC
            LIMIT {limit}
        """
        rows = await conn.fetch(query, *params)
        await conn.close()
        return JSONResponse({
            "success": True,
            "data": [r['first_name'] for r in rows]
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/dynasty/autocomplete/last-names")
async def dynasty_last_names_autocomplete(q: str = Query("", description="Optional prefix for last name"), limit: int = Query(200, ge=1, le=1000)):
    """Autocomplete for last names among winners."""
    try:
        import asyncpg
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
        )
        params = []
        where_clause = "WHERE winner = true AND last_name IS NOT NULL AND last_name != ''"
        if q:
            where_clause += " AND last_name ILIKE $1"
            params.append(f"{q}%")
        query = f"""
            SELECT last_name, COUNT(*) as cnt
            FROM political_dynasties
            {where_clause}
            GROUP BY last_name
            ORDER BY cnt DESC, last_name ASC
            LIMIT {limit}
        """
        rows = await conn.fetch(query, *params)
        await conn.close()
        return JSONResponse({
            "success": True,
            "data": [r['last_name'] for r in rows]
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/dynasty/top-surnames")
async def dynasty_top_surnames_api(
    limit: int = Query(100, ge=1, le=100, description="Number of top surnames to return"),
    province: str = Query("", description="Filter by specific province")
):
    """Get top surnames by province for political dynasty data from cached JSON"""
    try:
        import json
        
        # Load cached JSON data
        cache_file = "static/data/dynasty_surnames_cache.json"
        
        if not os.path.exists(cache_file):
            return JSONResponse({"success": False, "error": "Dynasty surnames cache not found. Please run the cache generation script."})
        
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        # Filter data based on parameters
        surnames = cache_data.get('surnames', [])
        
        # Only include surnames with actual dynasty members (dynasty_count > 0)
        surnames = [s for s in surnames if s.get('dynasty_count', 0) > 0]
        
        # Apply province filter if specified
        if province:
            surnames = [s for s in surnames if s['province'].upper() == province.upper()]
        
        # Apply limit
        surnames = surnames[:limit]
        
        return JSONResponse({
            "success": True,
            "data": surnames,
            "total_surnames": len(surnames),
            "cache_info": {
                "last_updated": cache_data.get('summary', {}).get('last_updated'),
                "total_cached": cache_data.get('summary', {}).get('total_surnames', 0)
            }
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/dynasty/stats")
async def dynasty_stats_api():
    """Get dynasty dashboard statistics filtered by elected positions, BAC positions, or ENGINEER positions"""
    conn = None
    try:
        import asyncpg
        import os
        
        connect_timeout = float(os.getenv("DYNASTY_DB_CONNECT_TIMEOUT", "2"))
        query_timeout = float(os.getenv("DYNASTY_DB_QUERY_TIMEOUT", "15"))

        # Database connection
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty'),
            timeout=connect_timeout,
        )
        
        # Position filter: elected positions only (President, Vice President, Senator, Mayor, Congressmen, Councilor, Governor) with max 2 words
        # OR BAC positions (any word count)
        # OR ENGINEER positions (max 2 words)
        position_filter = """(
            position IS NOT NULL AND position != ''
            AND (
                (
                    UPPER(position) ILIKE ANY(ARRAY['%PRESIDENT%', '%VICE PRESIDENT%', '%SENATOR%', '%MAYOR%', 
                                                      '%CONGRESSMEN%', '%CONGRESSMAN%', '%COUNCILOR%', '%GOVERNOR%'])
                    AND 
                    LENGTH(position) - LENGTH(REPLACE(position, ' ', '')) + 1 <= 2
                )
                OR
                (
                    UPPER(position) LIKE '%BAC%'
                )
                OR
                (
                    UPPER(position) LIKE '%ENGINEER%'
                    AND 
                    LENGTH(position) - LENGTH(REPLACE(position, ' ', '')) + 1 <= 2
                )
            )
        )"""
        
        row = await conn.fetchrow(
            f"""
            SELECT
                COUNT(*) FILTER (WHERE {position_filter}) AS total_records,
                COUNT(*) FILTER (WHERE fat = 1 AND {position_filter}) AS dynasty_members,
                COUNT(*) FILTER (WHERE fat = 0 AND {position_filter}) AS non_dynasty_members,
                COUNT(DISTINCT (first_name, last_name)) FILTER (WHERE {position_filter}) AS unique_politicians
            FROM political_dynasties
            """,
            timeout=query_timeout,
        )
        
        return JSONResponse({
            "success": True,
            "data": {
                "total_records": int(row["total_records"] or 0),
                "dynasty_members": int(row["dynasty_members"] or 0),
                "non_dynasty_members": int(row["non_dynasty_members"] or 0),
                "unique_politicians": int(row["unique_politicians"] or 0),
            }
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})
    finally:
        if conn is not None:
            try:
                await conn.close()
            except Exception:
                pass

@app.get("/api/dynasty/family")
async def dynasty_family_api(
    surname: str = Query("", description="Family surname to search for"),
    province: str = Query("", description="Filter by specific province")
):
    """Get family members by surname, optionally filtered by province"""
    try:
        import asyncpg
        import os
        
        if not surname:
            return JSONResponse({"success": False, "error": "Surname parameter is required"})
        
        # Convert parameters to uppercase for database matching
        surname = surname.upper()
        province = province.upper() if province else province
        
        # Database connection
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
        )
        
        # Check if there are any winners first
        winners_count = await conn.fetchval("SELECT COUNT(*) FROM political_dynasties WHERE winner = true")
        if winners_count == 0:
            await conn.close()
            return JSONResponse({
                "success": True,
                "data": [],
                "message": "No winning candidates found yet. The election data import is still in progress."
            })
        
        # Build query based on whether province filter is provided
        if province:
            # First try exact match on province column
            family_members = await conn.fetch("""
                SELECT 
                    id,
                    first_name,
                    last_name,
                    position,
                    province,
                    municipality_city,
                    year,
                    fat,
                    nickname
                FROM political_dynasties 
                WHERE UPPER(last_name) = UPPER($1) AND province = $2 AND winner = true
                ORDER BY year DESC, first_name
            """, surname, province)
            
            # If no results, try province-level mapping from JSON cache
            if not family_members:
                try:
                    import json
                    import os
                    
                    # Load province-cities mapping from JSON cache
                    mapping_file = os.path.join(os.path.dirname(__file__), 'static', 'data', 'province_cities_mapping_hybrid.json')
                    with open(mapping_file, 'r') as f:
                        province_mappings = json.load(f)
                    
                    if province in province_mappings:
                        cities = province_mappings[province]
                        placeholders = ','.join([f'${i+2}' for i in range(len(cities))])
                        family_members = await conn.fetch(f"""
                            SELECT 
                                first_name,
                                last_name,
                                position,
                                province,
                                municipality_city,
                                year,
                                fat
                            FROM political_dynasties 
                            WHERE UPPER(last_name) = UPPER($1) AND municipality_city IN ({placeholders})
                            ORDER BY year DESC, first_name
                        """, surname, *cities)
                except Exception as e:
                    print(f"Error loading province mapping: {e}")
                    pass
        else:
            family_members = await conn.fetch("""
                SELECT 
                    first_name,
                    last_name,
                    position,
                    province,
                    municipality_city,
                    year,
                    fat,
                    nickname
                FROM political_dynasties 
                WHERE UPPER(last_name) = UPPER($1) AND winner = true
                ORDER BY year DESC, first_name
            """, surname)
        
        await conn.close()
        
        # Convert to list of dictionaries
        family_data = []
        for member in family_members:
            family_data.append({
                "id": member["id"],
                "first_name": member["first_name"],
                "last_name": member["last_name"],
                "position": member["position"],
                "province": member["province"],
                "municipality_city": member["municipality_city"],
                "year": member["year"],
                "fat": member["fat"],
                "nickname": member["nickname"]
            })
        
        # Find connected family members (people connected to this family)
        connected_members = []
        if family_data:
            # Get all unique IDs from the current family members
            family_member_ids = []
            for member in family_members:
                if member.get("id"):  # If we have the database ID
                    family_member_ids.append(member["id"])
            
            # Use only the family member IDs
            all_family_ids = family_member_ids
            
            if all_family_ids:
                # Reconnect to database for the connected members query
                conn2 = await asyncpg.connect(
                    host=os.getenv('POSTGRES_HOST', 'localhost'),
                    port=int(os.getenv('POSTGRES_PORT', 5432)),
                    user=os.getenv('POSTGRES_USER', 'postgres'),
                    password=os.getenv('POSTGRES_PASSWORD', ''),
                    database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
                )
                
                try:
                    # Find people who are connected to this family using the relationships table
                    # This includes people connected through the normalized relationships table
                    connected_query = """
                        WITH RECURSIVE connected_people AS (
                            -- Base case: people directly connected to family members via relationships table
                            SELECT DISTINCT
                                p.id,
                                p.first_name,
                                p.last_name,
                                p.position,
                                p.province,
                                p.municipality_city,
                                p.year,
                                p.fat,
                                p.nickname,
                                1 as level
                            FROM political_dynasties p
                            JOIN relationships r ON p.id = r.person_id
                            WHERE r.related_person_id = ANY($1)
                            
                            UNION ALL
                            
                            -- Recursive case: people connected to already found connected people
                            SELECT DISTINCT
                                p.id,
                                p.first_name,
                                p.last_name,
                                p.position,
                                p.province,
                                p.municipality_city,
                                p.year,
                                p.fat,
                                p.nickname,
                                cp.level + 1
                            FROM political_dynasties p
                            JOIN relationships r ON p.id = r.person_id
                            INNER JOIN connected_people cp ON r.related_person_id = cp.id
                            WHERE cp.level < 3  -- Limit to 3 levels of connections
                        )
                        SELECT DISTINCT
                            id,
                            first_name,
                            last_name,
                            position,
                            province,
                            municipality_city,
                            year,
                            fat,
                            nickname
                        FROM connected_people
                        WHERE CONCAT(first_name, ' ', last_name) NOT IN (
                            SELECT CONCAT(first_name, ' ', last_name) 
                            FROM political_dynasties 
                            WHERE UPPER(last_name) = UPPER($2) AND province = $3
                        )
                        ORDER BY year DESC, first_name
                    """
                    
                    connected_results = await conn2.fetch(connected_query, all_family_ids, surname, province)
                    
                    for connected_member in connected_results:
                        connected_members.append({
                            "id": connected_member["id"],
                            "first_name": connected_member["first_name"],
                            "last_name": connected_member["last_name"],
                            "position": connected_member["position"],
                            "province": connected_member["province"],
                            "municipality_city": connected_member["municipality_city"],
                            "year": connected_member["year"],
                            "fat": connected_member["fat"],
                            "nickname": connected_member["nickname"],
                            "is_connected_member": True  # Flag to identify connected members
                        })
                finally:
                    await conn2.close()
        
        # Get relationships for all members using a fresh connection
        all_member_ids = [member["id"] for member in family_data + connected_members if member.get("id")]
        
        relationships = []
        if all_member_ids:
            # Use a fresh connection for the relationships query
            conn3 = await asyncpg.connect(
                host=os.getenv('POSTGRES_HOST', 'localhost'),
                port=int(os.getenv('POSTGRES_PORT', 5432)),
                user=os.getenv('POSTGRES_USER', 'postgres'),
                password=os.getenv('POSTGRES_PASSWORD', ''),
                database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
            )
            
            try:
                relationships = await conn3.fetch("""
                    SELECT 
                        r.person_id,
                        r.related_person_id,
                        r.relationship_type,
                        r.relationship_description,
                        p1.first_name as person_first_name,
                        p1.last_name as person_last_name,
                        p2.first_name as related_first_name,
                        p2.last_name as related_last_name
                    FROM relationships r
                    JOIN political_dynasties p1 ON r.person_id = p1.id
                    JOIN political_dynasties p2 ON r.related_person_id = p2.id
                    WHERE r.person_id = ANY($1) OR r.related_person_id = ANY($1)
                """, all_member_ids)
            finally:
                await conn3.close()
        
        # Add relationship data to each member
        for member in family_data + connected_members:
            member_relationships = []
            for rel in relationships:
                if rel["person_id"] == member.get("id"):
                    member_relationships.append({
                        "related_person_id": rel["related_person_id"],
                        "relationship_type": rel["relationship_type"],
                        "relationship_description": rel["relationship_description"],
                        "related_person_name": f"{rel['related_first_name']} {rel['related_last_name']}"
                    })
                elif rel["related_person_id"] == member.get("id"):
                    member_relationships.append({
                        "related_person_id": rel["person_id"],
                        "relationship_type": rel["relationship_type"],
                        "relationship_description": rel["relationship_description"],
                        "related_person_name": f"{rel['person_first_name']} {rel['person_last_name']}"
                    })
            
            member["relationships"] = member_relationships
        
        # Combine family members and connected members
        all_members = family_data + connected_members
        
        return JSONResponse({
            "success": True,
            "data": all_members,
            "family_count": len(family_data),
            "connected_count": len(connected_members),
            "total_count": len(all_members)
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/dynasty/family/advanced-search")
async def dynasty_family_advanced_search_api(
    name: str = Query("", description="Full name to search for"),
    province: str = Query("", description="Filter by specific province")
):
    """Advanced family search using improved name matching"""
    try:
        import asyncpg
        import os
        from advanced_name_matcher import AdvancedNameMatcher
        
        if not name:
            return JSONResponse({"success": False, "error": "Name parameter is required"})
        
        # Convert parameters to uppercase for database matching
        name = name.upper()
        province = province.upper() if province else province
        
        # Database connection
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
        )
        
        try:
            # Use advanced name matcher
            name_matcher = AdvancedNameMatcher(conn)
            suggestions = await name_matcher.suggest_name_connections(name, province)
            
            return JSONResponse({
                "success": True,
                "data": suggestions
            })
            
        finally:
            await conn.close()
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/dynasty/projection")
async def dynasty_projection_api(
    group_by: str = Query("region", description="Group by field (region, position, province)"),
    position: str = Query(None, description="Optional filter by position"),
    province: str = Query(None, description="Optional filter by province"),
    year: int = Query(None, description="Election year (defaults to latest year with winners)"),
    use_cache: bool = Query(True, description="Use precomputed cache when available"),
    refresh_cache: bool = Query(False, description="Ignore cache and compute live"),
):
    """
    Get aggregated projection of officials 'removed' by anti-dynasty law.
    Returns counts for HB 6771 (Simultaneous) and HB 5905 (Broad/Succession).
    """
    conn = None
    try:
        import asyncpg
        import os
        import json

        cache_path = Path("static/data/dynasty_projection_cache.json")
        if (
            use_cache
            and not refresh_cache
            and not position
            and not province
            and cache_path.exists()
        ):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    cache = json.load(f)

                available_years = cache.get("available_years") or []
                by_year = cache.get("by_year") or {}

                selected_year = year
                if selected_year is None and available_years:
                    selected_year = available_years[0]

                year_key = str(selected_year) if selected_year is not None else None
                bucket = by_year.get(year_key, {}).get(group_by) if year_key else None

                if bucket and isinstance(bucket, dict) and isinstance(bucket.get("data"), list) and isinstance(bucket.get("summary"), dict):
                    summary = dict(bucket["summary"])
                    summary["available_years"] = available_years
                    summary["year"] = int(selected_year) if selected_year is not None else summary.get("year")
                    return JSONResponse({"success": True, "data": bucket["data"], "summary": summary})
            except Exception:
                pass

        connect_timeout = float(os.getenv("DYNASTY_DB_CONNECT_TIMEOUT", "2"))
        query_timeout = float(os.getenv("DYNASTY_DB_QUERY_TIMEOUT", "30"))
        
        # Validate group_by
        valid_groups = ["region", "position", "province", "party"]
        if group_by not in valid_groups:
            return JSONResponse({"success": False, "error": f"Invalid group_by parameter. Must be one of: {', '.join(valid_groups)}"})
            
        # Database connection
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty'),
            timeout=connect_timeout,
        )
        
        # Determine available years and default to latest year with winners
        years_rows = await conn.fetch(
            "SELECT DISTINCT year FROM political_dynasties WHERE winner = true AND year IS NOT NULL ORDER BY year DESC",
            timeout=query_timeout,
        )
        available_years = [r["year"] for r in years_rows if r.get("year") is not None]

        selected_year = year
        if selected_year is None and available_years:
            selected_year = available_years[0]
        if selected_year is None:
            return JSONResponse({"success": False, "error": "No election years available in political_dynasties (winner=true)."})

        # Build query
        where_conditions = ["winner = true"]  # Only consider winners for projection
        params = []
        param_idx = 0

        if selected_year is not None:
            param_idx += 1
            where_conditions.append(f"year = ${param_idx}")
            params.append(int(selected_year))
        
        if position:
            param_idx += 1
            where_conditions.append(f"position ILIKE ${param_idx}")
            params.append(f"%{position}%")
            
        if province:
            param_idx += 1
            where_conditions.append(f"province ILIKE ${param_idx}")
            params.append(f"%{province}%")
            
        where_clause = "WHERE " + " AND ".join(where_conditions)
        
        # Handle group field select - use CASE/COALESCE to handle NULLs nicely
        group_select = f"COALESCE(p.{group_by}, 'Unknown') as group_name"
        
        query = f"""
            WITH current AS (
                SELECT p.*
                FROM political_dynasties p
                {where_clause}
            ),
            current_keys AS (
                SELECT DISTINCT province, last_name
                FROM current
                WHERE province IS NOT NULL AND last_name IS NOT NULL
            ),
            same_year AS (
                SELECT p.province, p.last_name, COUNT(*) AS same_year_count
                FROM political_dynasties p
                JOIN current_keys k
                  ON k.province = p.province AND k.last_name = p.last_name
                WHERE p.winner = true AND p.year = $1
                GROUP BY p.province, p.last_name
            ),
            prior AS (
                SELECT p.province, p.last_name, 1 AS has_prior
                FROM political_dynasties p
                JOIN current_keys k
                  ON k.province = p.province AND k.last_name = p.last_name
                WHERE p.winner = true AND p.year >= ($1 - 9) AND p.year < $1
                GROUP BY p.province, p.last_name
            )
            SELECT
                COALESCE(current.{group_by}, 'Unknown') AS group_name,
                COUNT(*) AS total_count,
                SUM(
                    CASE
                        WHEN COALESCE(same_year.same_year_count, 0) > 1
                         AND NOT (
                             COALESCE(current.position_category, '') ILIKE '%party%list%'
                             OR COALESCE(current.position, '') ILIKE '%party%list%'
                         )
                        THEN 1
                        ELSE 0
                    END
                ) AS hb6771_count,
                SUM(
                    CASE
                        WHEN COALESCE(same_year.same_year_count, 0) > 1
                          OR prior.has_prior = 1
                        THEN 1
                        ELSE 0
                    END
                ) AS hb5905_count
            FROM current
            LEFT JOIN same_year
              ON same_year.province = current.province AND same_year.last_name = current.last_name
            LEFT JOIN prior
              ON prior.province = current.province AND prior.last_name = current.last_name
            GROUP BY current.{group_by}
            ORDER BY hb5905_count DESC, total_count DESC
        """
        
        rows = await conn.fetch(query, *params, timeout=query_timeout)
        
        data = []
        for row in rows:
            total = row['total_count']
            hb6771 = row['hb6771_count']
            hb5905 = row['hb5905_count']
            non_dynasty = total - hb5905
            remaining_6771 = total - hb6771
            
            impact_6771 = (hb6771 / total * 100) if total > 0 else 0
            impact_5905 = (hb5905 / total * 100) if total > 0 else 0
            
            data.append({
                "group": row['group_name'],
                "total_count": total,
                "hb6771_count": hb6771,
                "hb5905_count": hb5905,
                "remaining_6771": remaining_6771,
                "remaining_count": non_dynasty,
                "impact_percentage": round(impact_5905, 1),
                "impact_6771": round(impact_6771, 1),
                "impact_5905": round(impact_5905, 1)
            })
            
        # Calculate summary totals
        summary = {
            "year": selected_year,
            "available_years": available_years,
            "total_officials": sum(d['total_count'] for d in data),
            "total_hb6771": sum(d['hb6771_count'] for d in data),
            "total_hb5905": sum(d['hb5905_count'] for d in data),
            "total_remaining_6771": sum(d['remaining_6771'] for d in data),
            "total_remaining": sum(d['remaining_count'] for d in data)
        }
        summary["hb6771_pct_of_total"] = (summary["total_hb6771"] / summary["total_officials"] * 100) if summary["total_officials"] > 0 else 0
        summary["hb5905_pct_of_total"] = (summary["total_hb5905"] / summary["total_officials"] * 100) if summary["total_officials"] > 0 else 0
        summary["hb5905_additional"] = max(summary["total_hb5905"] - summary["total_hb6771"], 0)
        summary["hb6771_pct_of_hb5905"] = (summary["total_hb6771"] / summary["total_hb5905"] * 100) if summary["total_hb5905"] > 0 else 0

        summary["hb6771_pct_of_total"] = round(summary["hb6771_pct_of_total"], 1)
        summary["hb5905_pct_of_total"] = round(summary["hb5905_pct_of_total"], 1)
        summary["hb6771_pct_of_hb5905"] = round(summary["hb6771_pct_of_hb5905"], 1)

        return JSONResponse({
            "success": True,
            "data": data,
            "summary": summary
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})
    finally:
        if conn is not None:
            try:
                await conn.close()
            except Exception:
                pass


@app.get("/api/dynasty/projection/people")
async def dynasty_projection_people_api(
    hb: str = Query("hb5905", description="Which HB rule to list (hb6771 or hb5905)"),
    group_by: str = Query("province", description="Group by field (region, position, province, party)"),
    group: str = Query(..., description="Group value to drill into (exact match, case-insensitive)"),
    position: str = Query(None, description="Optional filter by position"),
    province: str = Query(None, description="Optional filter by province (useful when group_by is not province)"),
    year: int = Query(None, description="Election year (defaults to latest year with winners)"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(200, ge=1, le=1000, description="Page size"),
):
    """List winner records removed under HB 6771 or HB 5905 for a specific group (region/province/position/party)."""
    conn = None
    try:
        import asyncpg
        import os

        hb = (hb or "").lower().strip()
        hb_field = hb.replace("-", "").replace("_", "")
        if hb_field not in {"hb6771", "hb5905"}:
            return JSONResponse({"success": False, "error": "Invalid hb. Must be hb6771 or hb5905."})

        valid_groups = ["region", "position", "province", "party"]
        if group_by not in valid_groups:
            return JSONResponse({"success": False, "error": f"Invalid group_by parameter. Must be one of: {', '.join(valid_groups)}"})

        connect_timeout = float(os.getenv("DYNASTY_DB_CONNECT_TIMEOUT", "2"))
        query_timeout = float(os.getenv("DYNASTY_DB_QUERY_TIMEOUT", "30"))

        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty'),
            timeout=connect_timeout,
        )

        years_rows = await conn.fetch(
            "SELECT DISTINCT year FROM political_dynasties WHERE winner = true AND year IS NOT NULL ORDER BY year DESC",
            timeout=query_timeout,
        )
        available_years = [r["year"] for r in years_rows if r.get("year") is not None]

        selected_year = year
        if selected_year is None and available_years:
            selected_year = available_years[0]
        if selected_year is None:
            return JSONResponse({"success": False, "error": "No election years available in political_dynasties (winner=true)."})

        params = []
        param_idx = 0
        where_conditions = ["winner = true"]

        param_idx += 1
        where_conditions.append(f"year = ${param_idx}")
        params.append(int(selected_year))

        param_idx += 1
        where_conditions.append(f"COALESCE({group_by}, '') ILIKE ${param_idx}")
        params.append(str(group))

        if position:
            param_idx += 1
            where_conditions.append(f"position ILIKE ${param_idx}")
            params.append(f"%{position}%")

        if province:
            param_idx += 1
            where_conditions.append(f"province ILIKE ${param_idx}")
            params.append(f"%{province}%")

        where_clause = "WHERE " + " AND ".join(where_conditions)
        offset = (page - 1) * limit

        removed_predicate = {
            "hb6771": "removed_hb6771 = true",
            "hb5905": "removed_hb5905 = true",
        }[hb_field]

        query = f"""
            WITH current AS (
                SELECT *
                FROM political_dynasties
                {where_clause}
            ),
            current_keys AS (
                SELECT DISTINCT province, last_name
                FROM current
                WHERE province IS NOT NULL AND last_name IS NOT NULL
            ),
            same_year AS (
                SELECT p.province, p.last_name, COUNT(*) AS same_year_count
                FROM political_dynasties p
                JOIN current_keys k
                  ON k.province = p.province AND k.last_name = p.last_name
                WHERE p.winner = true AND p.year = $1
                GROUP BY p.province, p.last_name
            ),
            prior AS (
                SELECT p.province, p.last_name, 1 AS has_prior
                FROM political_dynasties p
                JOIN current_keys k
                  ON k.province = p.province AND k.last_name = p.last_name
                WHERE p.winner = true AND p.year >= ($1 - 9) AND p.year < $1
                GROUP BY p.province, p.last_name
            ),
            flagged AS (
                SELECT
                    current.*,
                    COALESCE(same_year.same_year_count, 0) AS same_year_count,
                    COALESCE(prior.has_prior, 0) AS has_prior,
                    (
                        COALESCE(same_year.same_year_count, 0) > 1
                        AND NOT (
                            COALESCE(current.position_category, '') ILIKE '%party%list%'
                            OR COALESCE(current.position, '') ILIKE '%party%list%'
                        )
                    ) AS removed_hb6771,
                    (
                        COALESCE(same_year.same_year_count, 0) > 1
                        OR prior.has_prior = 1
                    ) AS removed_hb5905
                FROM current
                LEFT JOIN same_year
                  ON same_year.province = current.province AND same_year.last_name = current.last_name
                LEFT JOIN prior
                  ON prior.province = current.province AND prior.last_name = current.last_name
            )
            SELECT
                *,
                COUNT(*) OVER() AS total_matching
            FROM flagged
            WHERE {removed_predicate}
            ORDER BY COALESCE(position, '') ASC, COALESCE(last_name, '') ASC, COALESCE(first_name, '') ASC
            LIMIT {int(limit)} OFFSET {int(offset)}
        """

        rows = await conn.fetch(query, *params, timeout=query_timeout)

        people = []
        total_matching = 0
        for row in rows:
            total_matching = int(row.get("total_matching") or 0)

            reasons = []
            if int(row.get("same_year_count") or 0) > 1:
                reasons.append("family-member same-year")
            if int(row.get("has_prior") or 0) == 1:
                reasons.append("family-member prior-year (<=9y)")

            people.append({
                "first_name": row.get("first_name"),
                "last_name": row.get("last_name"),
                "full_name": " ".join([v for v in [row.get("first_name"), row.get("last_name")] if v]),
                "position": row.get("position"),
                "position_category": row.get("position_category"),
                "party": row.get("party"),
                "region": row.get("region"),
                "province": row.get("province"),
                "municipality_city": row.get("municipality_city"),
                "year": row.get("year"),
                "removed_hb6771": bool(row.get("removed_hb6771")),
                "removed_hb5905": bool(row.get("removed_hb5905")),
                "same_year_count": int(row.get("same_year_count") or 0),
                "has_prior": bool(row.get("has_prior")),
                "reason": ", ".join(reasons) if reasons else None,
            })

        return JSONResponse({
            "success": True,
            "meta": {
                "hb": hb_field,
                "group_by": group_by,
                "group": group,
                "year": selected_year,
                "available_years": available_years,
                "page": page,
                "limit": limit,
                "total_matching": total_matching,
            },
            "data": people,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})
    finally:
        if conn is not None:
            try:
                await conn.close()
            except Exception:
                pass


@app.get("/api/dynasty/province/roster")
async def dynasty_province_roster_api(
    province: str = Query(..., description="Province to list winners for"),
    year: int = Query(None, description="Election year (defaults to latest year with winners in province)"),
    position: str = Query(None, description="Optional filter by position (ILIKE contains)"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(500, ge=1, le=5000, description="Page size"),
):
    """Province-wide winners list with HB 6771 / HB 5905 flags and simple term-streak indicators."""
    conn = None
    try:
        import asyncpg
        import os

        connect_timeout = float(os.getenv("DYNASTY_DB_CONNECT_TIMEOUT", "2"))
        query_timeout = float(os.getenv("DYNASTY_DB_QUERY_TIMEOUT", "30"))

        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty'),
            timeout=connect_timeout,
        )

        years_rows = await conn.fetch(
            "SELECT DISTINCT year FROM political_dynasties WHERE winner = true AND year IS NOT NULL AND province ILIKE $1 ORDER BY year DESC",
            f"%{province}%",
            timeout=query_timeout,
        )
        available_years = [r["year"] for r in years_rows if r.get("year") is not None]

        selected_year = year
        if selected_year is None and available_years:
            selected_year = available_years[0]
        if selected_year is None:
            return JSONResponse({"success": False, "error": "No election years available for this province (winner=true)."})

        params = []
        param_idx = 0
        where_conditions = ["p.winner = true"]

        param_idx += 1
        where_conditions.append(f"p.province ILIKE ${param_idx}")
        params.append(f"%{province}%")

        param_idx += 1
        where_conditions.append(f"p.year = ${param_idx}")
        params.append(int(selected_year))

        if position:
            param_idx += 1
            where_conditions.append(f"p.position ILIKE ${param_idx}")
            params.append(f"%{position}%")

        where_clause = "WHERE " + " AND ".join(where_conditions)
        offset = (page - 1) * limit

        query = f"""
            WITH current AS (
                SELECT p.*
                FROM political_dynasties p
                {where_clause}
            ),
            same_year AS (
                SELECT province, last_name, COUNT(*) AS same_year_count
                FROM current
                WHERE province IS NOT NULL AND last_name IS NOT NULL
                GROUP BY province, last_name
            ),
            prior AS (
                SELECT p.province, p.last_name, 1 AS has_prior
                FROM political_dynasties p
                JOIN (SELECT DISTINCT province, last_name FROM current WHERE province IS NOT NULL AND last_name IS NOT NULL) k
                  ON k.province = p.province AND k.last_name = p.last_name
                WHERE p.winner = true AND p.year >= ($2 - 9) AND p.year < $2
                GROUP BY p.province, p.last_name
            ),
            history AS (
                SELECT
                    first_name,
                    last_name,
                    position,
                    province,
                    year,
                    (year - 3 * ROW_NUMBER() OVER (
                        PARTITION BY first_name, last_name, position, province
                        ORDER BY year
                    )) AS grp
                FROM political_dynasties
                WHERE winner = true
                  AND province ILIKE $1
                  AND first_name IS NOT NULL AND first_name != ''
                  AND last_name IS NOT NULL AND last_name != ''
                  AND position IS NOT NULL AND position != ''
                  AND year IS NOT NULL
            ),
            streaks AS (
                SELECT
                    first_name,
                    last_name,
                    position,
                    province,
                    MAX(year) AS end_year,
                    COUNT(*) AS streak_len
                FROM history
                GROUP BY first_name, last_name, position, province, grp
            ),
            flagged AS (
                SELECT
                    current.*,
                    COALESCE(same_year.same_year_count, 0) AS same_year_count,
                    COALESCE(prior.has_prior, 0) AS has_prior,
                    COALESCE(streaks.streak_len, 1) AS term_streak,
                    (COALESCE(streaks.streak_len, 1) >= 3) AS term_limited,
                    (
                        COALESCE(same_year.same_year_count, 0) > 1
                        AND NOT (
                            COALESCE(current.position_category, '') ILIKE '%party%list%'
                            OR COALESCE(current.position, '') ILIKE '%party%list%'
                        )
                    ) AS removed_hb6771,
                    (
                        COALESCE(same_year.same_year_count, 0) > 1
                        OR prior.has_prior = 1
                    ) AS removed_hb5905
                FROM current
                LEFT JOIN same_year
                  ON same_year.province = current.province AND same_year.last_name = current.last_name
                LEFT JOIN prior
                  ON prior.province = current.province AND prior.last_name = current.last_name
                LEFT JOIN streaks
                  ON streaks.first_name = current.first_name
                 AND streaks.last_name = current.last_name
                 AND streaks.position = current.position
                 AND streaks.province = current.province
                 AND streaks.end_year = current.year
            )
            SELECT
                *,
                COUNT(*) OVER() AS total_matching
            FROM flagged
            ORDER BY COALESCE(position, '') ASC, COALESCE(last_name, '') ASC, COALESCE(first_name, '') ASC
            LIMIT {int(limit)} OFFSET {int(offset)}
        """

        rows = await conn.fetch(query, *params, timeout=query_timeout)

        total_matching = 0
        people = []
        removed_6771 = 0
        removed_5905 = 0
        term_limited = 0

        for row in rows:
            total_matching = int(row.get("total_matching") or 0)

            removed_hb6771 = bool(row.get("removed_hb6771"))
            removed_hb5905 = bool(row.get("removed_hb5905"))
            if removed_hb6771:
                removed_6771 += 1
            if removed_hb5905:
                removed_5905 += 1
            if bool(row.get("term_limited")):
                term_limited += 1

            reasons_5905 = []
            if int(row.get("same_year_count") or 0) > 1:
                reasons_5905.append("family-member same-year")
            if int(row.get("has_prior") or 0) == 1:
                reasons_5905.append("family-member prior-year (<=9y)")

            people.append({
                "first_name": row.get("first_name"),
                "last_name": row.get("last_name"),
                "full_name": " ".join([v for v in [row.get("first_name"), row.get("last_name")] if v]),
                "position": row.get("position"),
                "position_category": row.get("position_category"),
                "party": row.get("party"),
                "region": row.get("region"),
                "province": row.get("province"),
                "municipality_city": row.get("municipality_city"),
                "year": row.get("year"),
                "removed_hb6771": removed_hb6771,
                "removed_hb5905": removed_hb5905,
                "same_year_count": int(row.get("same_year_count") or 0),
                "has_prior": bool(row.get("has_prior")),
                "term_streak": int(row.get("term_streak") or 1),
                "term_limited": bool(row.get("term_limited")),
                "reason_hb5905": ", ".join(reasons_5905) if reasons_5905 else None,
            })

        total_current = total_matching if total_matching else len(people)
        summary = {
            "province": province,
            "year": selected_year,
            "available_years": available_years,
            "total_winners": total_current,
            "removed_hb6771": removed_6771,
            "removed_hb5905": removed_5905,
            "remaining_hb6771": max(total_current - removed_6771, 0),
            "remaining_hb5905": max(total_current - removed_5905, 0),
            "term_limited": term_limited,
        }

        return JSONResponse({
            "success": True,
            "summary": summary,
            "page": page,
            "limit": limit,
            "total": total_current,
            "data": people,
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})
    finally:
        if conn is not None:
            try:
                await conn.close()
            except Exception:
                pass

@app.get("/api/dynasty/provinces")
async def dynasty_provinces_api():
    """Get dynasty data aggregated by province"""
    try:
        import json
        
        # Load cached JSON data
        cache_file = "static/data/dynasty_surnames_cache.json"
        
        if not os.path.exists(cache_file):
            return JSONResponse({"success": False, "error": "Dynasty surnames cache not found. Please run the cache generation script."})
        
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        # Aggregate data by province
        province_data = {}
        for surname in cache_data.get('surnames', []):
            province = surname['province']
            if province not in province_data:
                province_data[province] = {
                    'province': province,
                    'dynasty_count': 0,
                    'total_count': 0,
                    'surnames': []
                }
            
            province_data[province]['dynasty_count'] += surname['dynasty_count']
            province_data[province]['total_count'] += surname['total_count']
            province_data[province]['surnames'].append({
                'surname': surname['surname'],
                'dynasty_count': surname['dynasty_count']
            })
        
        # Convert to list and sort by dynasty count
        data = list(province_data.values())
        data.sort(key=lambda x: x['dynasty_count'], reverse=True)
        
        return JSONResponse({
            "success": True,
            "data": data,
            "total_provinces": len(data),
            "cache_info": {
                "last_updated": cache_data.get('summary', {}).get('last_updated'),
                "total_cached": cache_data.get('summary', {}).get('total_surnames', 0)
            }
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/dynasty/conflicts")
async def dynasty_conflicts_api(
    conflict_type: str = Query("", description="Filter by conflict type"),
    risk_level: str = Query("", description="Filter by risk level"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=1000, description="Number of records per page")
):
    """Get relationship data for government officials"""
    try:
        import asyncpg
        
        # Connect to dynasty database
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
        )
        
        # Build WHERE clause for filtering
        where_conditions = []
        params = []
        param_count = 0
        
        # Conflict type filter
        if conflict_type:
            param_count += 1
            where_conditions.append(f"conflict_type ILIKE ${param_count}")
            params.append(f"%{conflict_type}%")
        
        # Risk level filter
        if risk_level:
            param_count += 1
            where_conditions.append(f"risk_level ILIKE ${param_count}")
            params.append(f"%{risk_level}%")
        
        # Build complete WHERE clause
        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)
        
        # For now, we'll create mock conflicts data based on existing officials
        # In the future, this would query a conflicts table
        
        # Get high-level officials for conflicts analysis
        officials_query = f"""
            SELECT 
                first_name,
                last_name,
                position,
                government_branch,
                position_category,
                appointment_type
            FROM political_dynasties 
            WHERE year = 2025 
            AND (position IN ('PRESIDENT', 'VICE PRESIDENT', 'EXECUTIVE SECRETARY', 'SECRETARY OF BUDGET AND MANAGEMENT', 'SECRETARY OF EDUCATION', 'SECRETARY OF HEALTH', 'SECRETARY OF FINANCE')
                 OR position LIKE '%SECRETARY%'
                 OR position LIKE '%CHAIRMAN%'
                 OR position LIKE '%COMMISSIONER%')
            ORDER BY 
                CASE 
                    WHEN position = 'PRESIDENT' THEN 1
                    WHEN position = 'VICE PRESIDENT' THEN 2
                    WHEN position = 'EXECUTIVE SECRETARY' THEN 3
                    WHEN position LIKE 'SECRETARY%' THEN 4
                    ELSE 5
                END,
                last_name, first_name
            LIMIT ${param_count + 1} OFFSET ${param_count + 2}
        """
        
        # Add limit and offset to params
        params.extend([limit, (page - 1) * limit])
        
        officials = await conn.fetch(officials_query, *params)
        
        # Generate mock conflicts data based on officials
        conflicts_data = []
        conflict_types = ['Family Business', 'Business Interest', 'Political Appointment', 'Government Contract', 'Financial Interest']
        risk_levels = ['High', 'Medium', 'Low']
        
        for i, official in enumerate(officials):
            # Generate conflicts for some officials
            if i % 3 == 0:  # Every 3rd official has a conflict
                conflict_type = conflict_types[i % len(conflict_types)]
                risk_level = risk_levels[i % len(risk_levels)]
                
                # Generate details based on conflict type
                details_map = {
                    'Family Business': f"Family members own businesses that may benefit from government decisions",
                    'Business Interest': f"Previous business connections in {official['government_branch'] or 'government'} sector",
                    'Political Appointment': f"Family members in key government positions",
                    'Government Contract': f"Potential for awarding contracts to family businesses",
                    'Financial Interest': f"Financial investments that may conflict with official duties"
                }
                
                conflicts_data.append({
                    'official': f"{official['first_name']} {official['last_name']}",
                    'position': official['position'],
                    'conflict_type': conflict_type,
                    'risk_level': risk_level,
                    'details': details_map[conflict_type]
                })
        
        # Apply filters to mock data
        if conflict_type:
            conflicts_data = [c for c in conflicts_data if conflict_type.lower() in c['conflict_type'].lower()]
        
        if risk_level:
            conflicts_data = [c for c in conflicts_data if risk_level.lower() in c['risk_level'].lower()]
        
        # Calculate statistics
        stats = {
            'high_risk': len([c for c in conflicts_data if c['risk_level'] == 'High']),
            'business_connections': len([c for c in conflicts_data if 'Business' in c['conflict_type']]),
            'family_businesses': len([c for c in conflicts_data if 'Family' in c['conflict_type']]),
            'contract_awards': len([c for c in conflicts_data if 'Contract' in c['conflict_type']])
        }
        
        await conn.close()
        
        return JSONResponse({
            "success": True,
            "data": conflicts_data,
            "stats": stats,
            "pagination": {
                "page": page,
                "limit": limit,
                "total_count": len(conflicts_data),
                "total_pages": (len(conflicts_data) + limit - 1) // limit,
                "has_next": page < (len(conflicts_data) + limit - 1) // limit,
                "has_prev": page > 1
            }
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

# EOGO CRI Analysis API Endpoints
@app.get("/api/eogo/political-hhi")
async def political_hhi_api():
    """Get Political HHI analysis from cache"""
    try:
        import json
        
        cache_file = "static/data/political_hhi_cache.json"
        if not os.path.exists(cache_file):
            return JSONResponse({"success": False, "error": "Political HHI cache not found. Please run the CRI analysis script."})
        
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        return JSONResponse(cache_data)
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/eogo/contractor-hhi")
async def contractor_hhi_api():
    """Get Contractor HHI analysis from cache"""
    try:
        import json
        
        cache_file = "static/data/contractor_hhi_cache.json"
        if not os.path.exists(cache_file):
            return JSONResponse({"success": False, "error": "Contractor HHI cache not found. Please run the CRI analysis script."})
        
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        return JSONResponse(cache_data)
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/eogo/poverty-correlation")
async def poverty_correlation_api():
    """Get Poverty Correlation analysis from cache"""
    try:
        import json
        
        cache_file = "static/data/poverty_correlation_cache.json"
        if not os.path.exists(cache_file):
            return JSONResponse({"success": False, "error": "Poverty correlation cache not found. Please run the CRI analysis script."})
        
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        return JSONResponse(cache_data)
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/eogo/cri-analysis")
async def cri_analysis_api():
    """Get Comprehensive CRI Analysis from cache"""
    try:
        import json
        
        cache_file = "static/data/cri_analysis_cache.json"
        if not os.path.exists(cache_file):
            return JSONResponse({"success": False, "error": "CRI analysis cache not found. Please run the CRI analysis script."})
        
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        return JSONResponse(cache_data)
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

# Contractor endpoints that frontend expects
@app.get("/api/contractors/top")
async def get_contractors_top(limit: int = 100):
    """Get top contractors by project count - frontend endpoint"""
    try:
        # Redirect to the existing philgeps endpoint
        return await get_top_contractors(limit)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/contractors/venn")
async def get_contractors_venn_frontend():
    """Get Venn diagram data for contractor sources - frontend endpoint"""
    try:
        # Redirect to the existing philgeps endpoint
        return await get_contractors_venn()
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/contractors/sec-standard-deviation")
async def get_contractors_sec_std_frontend():
    """Get SEC contractor standard deviation analysis - frontend endpoint"""
    try:
        # Redirect to the existing philgeps endpoint
        return await get_sec_contractor_standard_deviation()
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/contractors/projects/{contractor_name}")
async def get_contractor_projects_frontend(contractor_name: str):
    """Get contractor projects - frontend endpoint"""
    try:
        # Redirect to the existing philgeps endpoint
        return await search_contractor_projects(contractor_name)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/dynasty/relationship-chains")
async def dynasty_relationship_chains_api(
    chain_length_min: int = Query(2, ge=2, le=10, description="Minimum chain length to find"),
    chain_length_max: int = Query(10, ge=2, le=10, description="Maximum chain length to find (10 means 10+)"),
    max_constellations: str = Query("10", description="Maximum number of unique constellations to return (number or 'ALL')"),
    contractor_only: bool = Query(False, description="Only return constellations with contractor connections"),
    party_list_only: bool = Query(False, description="Only return constellations with party-list connections")
):
    """Get relationship chains from JSON cache"""
    try:
        import json
        
        # Load cached JSON data
        cache_file = "static/data/relationship_chains_cache.json"
        
        if not os.path.exists(cache_file):
            return JSONResponse({"success": False, "error": "Relationship chains cache not found. Please run the cache generation script."})
        
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        # Validate min <= max
        if chain_length_min > chain_length_max:
            return JSONResponse({"success": False, "error": "chain_length_min must be <= chain_length_max"})
        
        # Parse max_constellations - can be a number or "ALL"
        max_constellations_int = None
        if max_constellations.upper() == "ALL":
            max_constellations_int = None  # No limit
        else:
            try:
                max_constellations_int = int(max_constellations)
                if max_constellations_int < 1:
                    max_constellations_int = None
            except (ValueError, TypeError):
                return JSONResponse({"success": False, "error": f"Invalid max_constellations value: {max_constellations}. Must be a number or 'ALL'."})
        
        # Filter chains by length range
        # Note: chain_length_max >= 10 means no upper limit (treat as 10+)
        all_chains = cache_data.get('chains', [])
        if chain_length_max >= 10:
            # No upper limit - only filter by minimum
            filtered_chains = [chain for chain in all_chains 
                              if chain_length_min <= chain.get('length', 0)]
        else:
            # Filter by both min and max
            filtered_chains = [chain for chain in all_chains 
                              if chain_length_min <= chain.get('length', 0) <= chain_length_max]
        
        # Filter by connection type if requested
        if contractor_only:
            filtered_chains = [chain for chain in filtered_chains 
                             if chain.get('contractor_connection') and chain.get('contractor_connection', {}).get('contractor_name')]
        elif party_list_only:
            filtered_chains = [chain for chain in filtered_chains 
                             if chain.get('party_list_connection') and chain.get('party_list_connection', {}).get('party_name')]
        
        # Group chains by unique constellation (family pairs)
        # A constellation is a unique connection between two families (regardless of path direction or length)
        # Include single-person chains (Person → Contractor/Party-list node) where start_family == end_family
        from collections import defaultdict
        chains_by_constellation = defaultdict(list)
        single_person_chains = []  # Store single-person chains separately (Person → Contractor/Party-list node)
        
        for chain in filtered_chains:
            start_family = chain.get('start_surname', '').upper().strip()
            end_family = chain.get('end_surname', '').upper().strip()
            chain_length = chain.get('length', 0)
            
            # Single-person chains: same family with length 2 = Person → Contractor/Party-list node
            if start_family and end_family and start_family == end_family and chain_length == 2:
                single_person_chains.append(chain)
            elif start_family and end_family and start_family != end_family:
                # Normalize: use sorted tuple so A->B and B->A are the same constellation
                constellation_key = tuple(sorted([start_family, end_family]))
                chains_by_constellation[constellation_key].append(chain)
            else:
                # Other edge cases (e.g., same family but length > 2)
                single_person_chains.append(chain)
        
        # Sort constellations by number of chains (more paths = more interesting)
        sorted_constellations = sorted(chains_by_constellation.items(), key=lambda x: len(x[1]), reverse=True)
        
        # Take up to max_constellations unique constellations, including all chains for each
        limited_chains = []
        if max_constellations_int is None:
            # "ALL" - return all constellations
            for constellation_key, constellation_chains in sorted_constellations:
                limited_chains.extend(constellation_chains)
            # Add all single-person chains
            limited_chains.extend(single_person_chains)
        else:
            # Limit to requested number of constellations
            for constellation_key, constellation_chains in sorted_constellations[:max_constellations_int]:
                limited_chains.extend(constellation_chains)
        
        filtered_chains = limited_chains
        
        # Count unique constellations in the filtered result
        result_constellations = set()
        for chain in filtered_chains:
            start_family = chain.get('start_surname', '').upper().strip()
            end_family = chain.get('end_surname', '').upper().strip()
            if start_family and end_family and start_family != end_family:
                constellation_key = tuple(sorted([start_family, end_family]))
                result_constellations.add(constellation_key)
        
        return JSONResponse({
            "success": True,
            "data": filtered_chains,
            "people": cache_data.get('people', {}),  # Include people dictionary for reconstruction
            "total_constellations": len(result_constellations),
            "total_chains": len(filtered_chains),
            "min_constellation_stars": chain_length_min,
            "max_constellation_stars": chain_length_max,
            "max_constellations_requested": max_constellations,
            "cache_info": {
                "last_updated": cache_data.get('summary', {}).get('last_updated'),
                "total_cached_chains": cache_data.get('summary', {}).get('total_chains', 0),
                "total_cached_constellations": cache_data.get('summary', {}).get('total_constellations', 0),
                "constellation_mapping": cache_data.get('summary', {}).get('constellation_mapping', {})
            }
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/dynasty/relationship-chains/person")
async def dynasty_relationship_chains_person_api(
    normalized_name: str = Query(..., description="Normalized person name (e.g., 'FRANCIS ESCUDERO')")
):
    """Get relationship chains for a specific person from their JSON file"""
    try:
        import json
        from pathlib import Path
        
        # Create safe filename from normalized name
        safe_filename = normalized_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
        safe_filename = ''.join(c for c in safe_filename if c.isalnum() or c in ('_', '-', '.'))
        
        # Load person-specific JSON file
        person_file = Path("static/data/relationship_chains_by_person") / f"{safe_filename}.json"
        
        if not person_file.exists():
            return JSONResponse({
                "success": False, 
                "error": f"Person file not found for: {normalized_name}",
                "suggestions": "Make sure the normalized name matches exactly (e.g., 'FRANCIS ESCUDERO')"
            }, status_code=404)
        
        with open(person_file, 'r', encoding='utf-8') as f:
            person_data = json.load(f)
        
        return JSONResponse({
            "success": True,
            "person": person_data.get("person", {}),
            "chains": person_data.get("chains", []),
            "people": person_data.get("people", {}),
            "chain_count": len(person_data.get("chains", []))
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/dynasty-projects/all")
async def dynasty_projects_all_api(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=10000, description="Number of records per page"),
    congressman: str = Query(None, description="Filter by congressman name (optional)")
):
    """Get all projects from cached JSON, loading from all individual congressman caches"""
    try:
        import json
        from pathlib import Path
        import glob
        
        # If congressman filter is provided, try to load from individual cache
        if congressman and congressman.strip() and congressman.strip() != 'all' and congressman.strip() != 'All Congressmen':
            congressman_normalized = congressman.strip().lower().replace(" ", "-").replace(".", "").replace(",", "").replace("'", "")
            congressman_cache_dir = Path(__file__).parent / 'static' / 'data' / f'congressman-projects-{congressman_normalized}'
            congressman_cache_file = congressman_cache_dir / 'all-projects-cache.json'
            
            if congressman_cache_file.exists():
                # Load from individual congressman cache
                with open(congressman_cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                
                if cache_data.get('success', False):
                    unique_projects = cache_data.get('projects', [])
                    
                    # Paginate
                    total_pages = (len(unique_projects) + limit - 1) // limit
                    offset = (page - 1) * limit
                    paginated_projects = unique_projects[offset:offset + limit]
                    
                    return JSONResponse({
                        "success": True,
                        "projects": paginated_projects,
                        "summary": cache_data.get('summary', {}),
                        "chart_data": cache_data.get('chart_data', []),
                        "dashboard_stats": cache_data.get('dashboard_stats', {}),
                        "page": page,
                        "total": len(unique_projects),
                        "total_pages": total_pages,
                        "congressman": congressman.strip(),
                        "generated_at": cache_data.get('generated_at'),
                        "cache_version": cache_data.get('cache_version', '1.0')
                    })
        
        # Load from ALL individual congressman caches
        data_dir = Path(__file__).parent / 'static' / 'data'
        all_projects = []
        total_summary = {
            "total": 0,
            "dime": 0,
            "philgeps": 0,
            "ssp": 0,
            "district_projects": 0,
            "contractor_projects": 0
        }
        
        # Find all congressman cache directories
        congressman_cache_pattern = str(data_dir / 'congressman-projects-*' / 'all-projects-cache.json')
        cache_files = glob.glob(congressman_cache_pattern)
        
        print(f"Loading from {len(cache_files)} congressman caches...")
        
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
            except Exception as e:
                print(f"Error loading cache {cache_file_path}: {e}")
                continue
        
        print(f"Loaded {len(all_projects)} total projects from all caches")
        
        # Load pre-generated top-200 stats from cache
        top_cache_file = data_dir / 'top-200-congressmen.json'
        chart_data = []
        dashboard_stats = {}
        
        if top_cache_file.exists():
            try:
                with open(top_cache_file, 'r', encoding='utf-8') as f:
                    top_cache_data = json.load(f)
                    chart_data = top_cache_data.get('chart_data', [])
                    dashboard_stats = top_cache_data.get('dashboard_stats', {})
                    print("✅ Loaded pre-generated top-200 stats from cache")
            except Exception as e:
                print(f"⚠️  Error loading top-200 cache: {e}")
        
        # Fallback: calculate if cache doesn't exist
        if not chart_data or not dashboard_stats:
            print("⚠️  Top-200 cache not found, calculating on-the-fly...")
            congressman_stats = {}
            for proj in all_projects:
                congressman = proj.get('congressman', 'Unknown')
                if congressman not in congressman_stats:
                    congressman_stats[congressman] = {
                        "name": congressman,
                        "count": 0,
                        "total_cost": 0
                    }
                
                congressman_stats[congressman]["count"] += 1
                
                amount = proj.get('amount', 0)
                if isinstance(amount, str):
                    amount_str = amount.replace('₱', '').replace(',', '').strip()
                    try:
                        amount = float(amount_str) if amount_str else 0
                    except (ValueError, AttributeError):
                        amount = 0
                else:
                    amount = float(amount) if amount else 0
                
                congressman_stats[congressman]["total_cost"] += amount
            
            chart_data = sorted(
                list(congressman_stats.values()),
                key=lambda x: x["count"],
                reverse=True
            )[:10]
            
            total_cost_all = sum(stat["total_cost"] for stat in chart_data)
            district_count = total_summary['district_projects']
            contractor_count = total_summary['contractor_projects']
            
            district_cost = sum(
                float(proj.get('amount', 0)) if isinstance(proj.get('amount', 0), (int, float)) else 0
                for proj in all_projects if proj.get('match_type') == 'district'
            )
            contractor_cost = sum(
                float(proj.get('amount', 0)) if isinstance(proj.get('amount', 0), (int, float)) else 0
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
        
        # Paginate
        total_pages = (len(all_projects) + limit - 1) // limit
        offset = (page - 1) * limit
        paginated_projects = all_projects[offset:offset + limit]
        
        return JSONResponse({
            "success": True,
            "projects": paginated_projects,
            "summary": total_summary,
            "chart_data": chart_data,
            "dashboard_stats": dashboard_stats,
            "page": page,
            "total": len(all_projects),
            "total_pages": total_pages,
            "generated_at": datetime.utcnow().isoformat(),
            "cache_version": "2.0",
            "source": "individual_caches"
        })
        
    except Exception as e:
        print(f"Error in dynasty_projects_all_api: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "success": False,
            "error": str(e),
            "projects": [],
            "summary": {"total": 0, "ssp": 0, "dime": 0, "philgeps": 0, "district_projects": 0, "contractor_projects": 0}
        })

@app.get("/api/dynasty-projects/congressmen")
async def dynasty_projects_congressmen_api():
    """Get list of all congressmen from JSON config with cache metadata."""
    try:
        config_data = _load_dynasty_config()
        target_congressmen = config_data.get("target_congressmen", [])

        congressmen_list = []
        seen_names: Set[str] = set()

        for entry in target_congressmen:
            display_name = entry.get("display_name") or entry.get("name")
            if not display_name:
                continue

            normalized_key = _normalize_cache_name(display_name)
            if normalized_key in seen_names:
                continue
            seen_names.add(normalized_key)

            cache_dir = _find_congressman_cache(display_name)
            has_cache = cache_dir is not None
            slug = (
                cache_dir.name.replace("congressman-projects-", "", 1)
                if has_cache
                else _normalize_congressman_slug(display_name)
            )

            summary_data = {}
            total_cost = None
            generated_at = None
            dashboard_stats = {}

            if has_cache:
                summary_path = cache_dir / "summary.json"
                summary_file = _read_json_file(summary_path)
                if isinstance(summary_file, dict):
                    summary_data = summary_file.get("summary") or {}
                    total_cost = summary_file.get("total_cost")
                    generated_at = summary_file.get("generated_at")
                else:
                    all_cache_data = _read_json_file(cache_dir / "all-projects-cache.json")
                    if isinstance(all_cache_data, dict):
                        summary_data = all_cache_data.get("summary") or {}
                        dashboard_stats = all_cache_data.get("dashboard_stats") or {}
                        generated_at = all_cache_data.get("generated_at")
                        total_cost = dashboard_stats.get("total_cost_all")

            province = entry.get("province") or ""
            district_number = entry.get("district_number") or ""
            is_partylist = entry.get("is_partylist")
            if is_partylist is None:
                is_partylist = not province and not district_number

            congressmen_list.append(
                {
                    "display_name": display_name,
                    "name": display_name,
                    "province": province,
                    "district_number": district_number,
                    "is_city_district": bool(entry.get("is_city_district")),
                    "is_partylist": bool(is_partylist),
                    "slug": slug,
                    "cache_available": has_cache,
                    "summary": summary_data,
                    "dashboard_stats": dashboard_stats,
                    "total_projects": summary_data.get("total"),
                    "total_cost": total_cost,
                    "generated_at": generated_at,
                    "terms": entry.get("terms"),
                    "barangays": entry.get("barangays", []),
                    "id": entry.get("id"),
                    "raw_entry": entry,
                }
            )

        congressmen_list.sort(key=lambda item: item["display_name"])

        return JSONResponse(
            {
                "success": True,
                "source": "json_config",
                "congressmen": congressmen_list,
                "count": len(congressmen_list),
                "generated_at": datetime.utcnow().isoformat(),
            }
        )

    except Exception as exc:
        print(f"Error in dynasty_projects_congressmen_api: {exc}")
        import traceback

        traceback.print_exc()
        return JSONResponse(
            {
                "success": False,
                "error": str(exc),
                "congressmen": [],
            }
        )


@app.get("/api/dynasty-projects/congressman")
async def dynasty_projects_congressman_detail_api(
    name: Optional[str] = Query(None, description="Display name of the congressman"),
    slug: Optional[str] = Query(None, description="Slug of the congressman cache directory"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(2500, ge=1, le=25000, description="Number of records per page"),
    include_projects: bool = Query(True, description="Include project list in response"),
):
    """Load cached projects for a specific congressman."""
    identifier = slug or name
    if not identifier:
        raise HTTPException(status_code=400, detail="name or slug query parameter is required")

    cache_data = _load_congressman_cache(identifier)
    if not cache_data:
        raise HTTPException(status_code=404, detail=f"No cached projects found for '{identifier}'")

    projects = cache_data.get("projects") or []
    total_projects = len(projects)
    total_pages = max(1, (total_projects + limit - 1) // limit)
    offset = (page - 1) * limit
    paginated_projects = projects[offset : offset + limit] if include_projects else []

    summary = cache_data.get("summary") or {}
    dashboard_stats = cache_data.get("dashboard_stats") or {}
    generated_at = cache_data.get("generated_at")
    congressman_name = cache_data.get("congressman") or name or slug
    slug_value = cache_data.get("slug") or _normalize_congressman_slug(congressman_name)

    config_data = _load_dynasty_config()
    config_entry = None
    normalized_target = _normalize_cache_name(congressman_name)
    for entry in config_data.get("target_congressmen", []):
        display_name = entry.get("display_name") or entry.get("name") or ""
        if display_name and _normalize_cache_name(display_name) == normalized_target:
            config_entry = entry
            break

    return JSONResponse(
        {
            "success": True,
            "congressman": {
                "name": congressman_name,
                "slug": slug_value,
                "summary": summary,
                "dashboard_stats": dashboard_stats,
                "generated_at": generated_at,
                "total_projects": total_projects,
                "config": config_entry,
            },
            "projects": paginated_projects,
            "page": page,
            "limit": limit,
            "total": total_projects,
            "total_pages": total_pages,
            "cache_version": cache_data.get("cache_version", "1.0"),
        }
    )


@app.get("/api/dynasty-projects/overview")
async def dynasty_projects_overview_api():
    """Return pre-computed overview statistics and chart data."""
    ranking_path = DATA_ROOT / "congressman-ranking.json"
    cache_data = _read_json_file(ranking_path)

    if not isinstance(cache_data, dict):
        return JSONResponse(
            {
                "success": False,
                "error": "congressman-ranking cache not found; run cache generator first",
            },
            status_code=503,
        )

    ranking_by_count = cache_data.get("ranking_by_count") or []
    ranking_by_cost = cache_data.get("ranking_by_cost") or ranking_by_count
    top_10_by_cost = cache_data.get("top_10_by_cost") or ranking_by_cost[:10]
    top_10_by_count = cache_data.get("top_10_by_count") or ranking_by_count[:10]

    response = {
        "success": True,
        "summary": cache_data.get("summary") or {},
        "dashboard_stats": cache_data.get("dashboard_stats") or {},
        "chart_data": top_10_by_cost,
        "chart_data_top_10_by_cost": top_10_by_cost,
        "chart_data_top_10_by_count": top_10_by_count,
        "chart_data_by_count": ranking_by_count,
        "chart_data_by_cost": ranking_by_cost,
        "total_congressmen": cache_data.get("total_congressmen"),
        "generated_at": cache_data.get("generated_at"),
        "cache_version": cache_data.get("cache_version", "3.0"),
        "source": "congressman-ranking.json",
    }

    return JSONResponse(response)


@app.get("/api/dynasty-projects/search")
async def dynasty_projects_search_api(
    congressman: str = Query(..., description="Congressman name to search"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=100, description="Number of records per page")
):
    """Search projects by congressman name across MeiliSearch, DIME, and PhilGEPS
    Includes district projects AND contractor projects (direct + party-list contractors)"""
    try:
        import asyncpg
        from flood_client import FloodControlClient
        
        # Connect to dynasty database to find congressman
        dynasty_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
        )
        
        # Search for congressman in dynasty database - get full person info
        congressman_query = """
            SELECT id, first_name, last_name, province, municipality_city, region, party
            FROM political_dynasties
            WHERE (UPPER(position) LIKE '%CONGRESSMAN%' OR UPPER(position) LIKE '%CONGRESSMEN%' OR UPPER(position) LIKE '%MEMBER, HOUSE OF REPRESENTATIVES%')
              AND (UPPER(first_name || ' ' || last_name) LIKE $1 OR UPPER(last_name || ', ' || first_name) LIKE $1)
            LIMIT 1
        """
        search_pattern = f"%{congressman.upper()}%"
        person = await dynasty_conn.fetchrow(congressman_query, search_pattern)
        
        if not person:
            await dynasty_conn.close()
            return JSONResponse({
                "success": False,
                "error": f"No congressman found matching '{congressman}'",
                "congressman_info": None,
                "projects": [],
                "summary": {"total": 0, "ssp": 0, "dime": 0, "philgeps": 0}
            })
        
        # Get district info
        provinces = [person['province']] if person['province'] else []
        municipalities = [person['municipality_city']] if person['municipality_city'] else []
        
        # Get direct contractor connections
        direct_contractors = await dynasty_conn.fetch('''
            SELECT DISTINCT company_name, role
            FROM contractor_dynasty_matches
            WHERE dynasty_first_name = $1 AND dynasty_last_name = $2
        ''', person['first_name'], person['last_name'])
        contractor_names = [c['company_name'] for c in direct_contractors]
        
        # Get party-list connections and their contractors
        party_lists = await dynasty_conn.fetch('''
            SELECT pl.party_list_number, pl.party_name
            FROM party_list_members plm
            JOIN party_list pl ON plm.party_list_number = pl.party_list_number
            WHERE plm.person_id = $1
        ''', person['id'])
        
        party_list_info = []
        for pl in party_lists:
            # Get all contractors for this party-list (all members' contractors)
            pl_contractors = await dynasty_conn.fetch('''
                SELECT DISTINCT cdm.company_name, cdm.role
                FROM party_list_members plm2
                JOIN political_dynasties pd ON plm2.person_id = pd.id
                JOIN contractor_dynasty_matches cdm ON cdm.dynasty_first_name = pd.first_name 
                                                       AND cdm.dynasty_last_name = pd.last_name
                WHERE plm2.party_list_number = $1
            ''', pl['party_list_number'])
            pl_contractor_names = [c['company_name'] for c in pl_contractors]
            contractor_names.extend(pl_contractor_names)
            party_list_info.append({
                "number": pl['party_list_number'],
                "name": pl['party_name'],
                "contractors": pl_contractor_names
            })
        
        contractor_names = list(set(contractor_names))
        
        await dynasty_conn.close()
        
        # Now query projects from all 3 databases
        # This is a simplified version - in production, you'd want to use the cached JSON
        # For now, we'll use the search endpoint which queries the cache
        # But this endpoint should redirect to the cached data filtered by congressman
        
        return JSONResponse({
            "success": True,
            "congressman_info": {
                "name": f"{person['first_name']} {person['last_name']}",
                "province": person['province'],
                "municipality": person['municipality_city'],
                "region": person['region'],
                "party": person['party'],
                "contractors": contractor_names,
                "party_lists": party_list_info
            },
            "projects": [],
            "summary": {"total": 0, "ssp": 0, "dime": 0, "philgeps": 0},
            "message": "This endpoint is deprecated. Use /api/dynasty-projects/all and filter by congressman client-side."
        })
        
    except Exception as e:
        print(f"Error in dynasty_projects_search_api: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "success": False,
            "error": str(e),
            "congressman_info": None,
            "projects": [],
            "summary": {"total": 0, "ssp": 0, "dime": 0, "philgeps": 0}
        })

@app.get("/api/province-projects/all")
async def province_projects_all_api(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=10000, description="Number of records per page"),
    province: str = Query("Cebu", description="Province name"),
    contractor: str = Query(None, description="Contractor name (optional)")
):
    """Get all projects for a specific province from cached JSON (per contractor cache files)"""
    try:
        import json
        from pathlib import Path
        
        # Normalize province name
        province_normalized = province.strip()
        # Fix common typos/normalization issues
        if province_normalized.lower() == 'iloil':
            province_normalized = 'Iloilo'
        elif province_normalized.lower() == 'compostela valley':
            province_normalized = 'Davao de Oro'
        
        # Load summary file first
        cache_dir = Path(__file__).parent / 'static' / 'data' / f'province-projects-{province_normalized.lower().replace(" ", "-")}'
        summary_file = cache_dir / 'summary.json'
        
        # Fallback to old cache file structure if new structure doesn't exist
        old_cache_file = Path(__file__).parent / 'static' / 'data' / f'province-projects-{province_normalized.lower().replace(" ", "-")}-cache.json'
        
        if summary_file.exists():
            # New structure: load from per-contractor cache files
            with open(summary_file, 'r', encoding='utf-8') as f:
                summary_data = json.load(f)
            
            unique_projects = []
            province_cache_filter_options = None  # Initialize for filter_options
            
            if contractor and contractor != 'all' and contractor != 'All Contractors':
                # Load specific contractor cache file
                contractor_normalized = contractor.lower().replace(" ", "-").replace("/", "-")
                contractor_cache_file = cache_dir / f'{contractor_normalized}-cache.json'
                
                if contractor_cache_file.exists():
                    with open(contractor_cache_file, 'r', encoding='utf-8') as f:
                        contractor_data = json.load(f)
                    unique_projects = contractor_data.get('projects', [])
                else:
                    # Check if contractor is in small contractors cache
                    small_contractors_cache_file = cache_dir / 'small-contractors-cache.json'
                    if small_contractors_cache_file.exists():
                        with open(small_contractors_cache_file, 'r', encoding='utf-8') as f:
                            small_contractors_data = json.load(f)
                        projects_by_contractor = small_contractors_data.get('projects_by_contractor', {})
                        if contractor in projects_by_contractor:
                            unique_projects = projects_by_contractor[contractor]
                        else:
                            # Contractor not found
                            return JSONResponse({
                                "success": False,
                                "error": f"Contractor '{contractor}' not found for {province}",
                                "projects": [],
                                "summary": summary_data.get('summary', {"total": 0, "ssp": 0, "dime": 0, "philgeps": 0}),
                                "total_cost": 0
                            })
                    else:
                        # Contractor not found
                        return JSONResponse({
                            "success": False,
                            "error": f"Contractor '{contractor}' not found for {province}",
                            "projects": [],
                            "summary": summary_data.get('summary', {"total": 0, "ssp": 0, "dime": 0, "philgeps": 0}),
                            "total_cost": 0
                        })
            else:
                # Load all projects - use province-level cache if available (more efficient)
                province_cache_file = cache_dir / 'all-projects-cache.json'
                if province_cache_file.exists():
                    with open(province_cache_file, 'r', encoding='utf-8') as f:
                        province_cache_data = json.load(f)
                    unique_projects = province_cache_data.get('projects', [])
                    province_cache_filter_options = province_cache_data.get('filter_options')
                else:
                    # Fallback: Load all contractor cache files
                    contractors = summary_data.get('contractors', {})
                    small_contractors_loaded = False
                    
                    for contractor_name, contractor_info in contractors.items():
                        # Check if this is a small contractor (already loaded from combined cache)
                        if contractor_info.get('is_small_contractor', False) and not small_contractors_loaded:
                            # Load small contractors cache once
                            small_contractors_cache_file = cache_dir / 'small-contractors-cache.json'
                            if small_contractors_cache_file.exists():
                                with open(small_contractors_cache_file, 'r', encoding='utf-8') as f:
                                    small_contractors_data = json.load(f)
                                projects_by_contractor = small_contractors_data.get('projects_by_contractor', {})
                                for small_contractor, small_projects in projects_by_contractor.items():
                                    unique_projects.extend(small_projects)
                                small_contractors_loaded = True
                            continue
                        elif contractor_info.get('is_small_contractor', False):
                            # Skip small contractors as they're already loaded
                            continue
                        
                        # Load individual contractor cache file
                        cache_file_path = Path(__file__).parent / 'static' / 'data' / contractor_info['cache_file']
                        if cache_file_path.exists():
                            with open(cache_file_path, 'r', encoding='utf-8') as f:
                                contractor_data = json.load(f)
                            unique_projects.extend(contractor_data.get('projects', []))
            
            # Sort by cost descending
            unique_projects.sort(key=lambda x: float(x.get('amount', 0) or 0), reverse=True)
            
            # Paginate
            total_pages = (len(unique_projects) + limit - 1) // limit
            offset = (page - 1) * limit
            paginated_projects = unique_projects[offset:offset + limit]
            
            # Use filter_options from province cache if available, otherwise from summary
            filter_options = province_cache_filter_options if province_cache_filter_options else summary_data.get('filter_options', {"contractors": [], "municipalities": []})
            
            return JSONResponse({
                "success": True,
                "province": summary_data.get('province', province),
                "projects": paginated_projects,
                "summary": summary_data.get('summary', {}),
                "total_cost": summary_data.get('total_cost', 0),
                "filter_options": filter_options,
                "page": page,
                "total": len(unique_projects),
                "total_pages": total_pages,
                "generated_at": summary_data.get('generated_at'),
                "cache_version": summary_data.get('cache_version', '1.0')
            })
        
        elif old_cache_file.exists():
            # Old structure: single cache file (backward compatibility)
            with open(old_cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            if not cache_data.get('success', False):
                return JSONResponse({
                    "success": False,
                    "error": cache_data.get('error', 'Unknown error'),
                    "projects": [],
                    "summary": cache_data.get('summary', {"total": 0, "ssp": 0, "dime": 0, "philgeps": 0}),
                    "total_cost": 0
                })
            
            unique_projects = cache_data.get('projects', [])
            
            # Filter by contractor if specified
            if contractor and contractor != 'all' and contractor != 'All Contractors':
                unique_projects = [
                    p for p in unique_projects 
                    if (p.get('contractor', '').strip() or 'Unknown') == contractor
                ]
            
            # Paginate
            total_pages = (len(unique_projects) + limit - 1) // limit
            offset = (page - 1) * limit
            paginated_projects = unique_projects[offset:offset + limit]
            
            return JSONResponse({
                "success": True,
                "province": cache_data.get('province', province),
                "projects": paginated_projects,
                "summary": cache_data.get('summary', {}),
                "total_cost": cache_data.get('total_cost', 0),
                "filter_options": cache_data.get('filter_options', {"contractors": [], "municipalities": []}),
                "page": page,
                "total": len(unique_projects),
                "total_pages": total_pages,
                "generated_at": cache_data.get('generated_at'),
                "cache_version": cache_data.get('cache_version', '1.0')
            })
        
        else:
            return JSONResponse({
                "success": False,
                "error": f"Cached data not found for {province_normalized}. Please run scripts/generate_province_projects_cache.py \"{province_normalized}\"",
                "projects": [],
                "summary": {"total": 0, "ssp": 0, "dime": 0, "philgeps": 0},
                "total_cost": 0
            })
        
    except Exception as e:
        print(f"Error in province_projects_all_api: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "success": False,
            "error": str(e),
            "projects": [],
            "summary": {"total": 0, "ssp": 0, "dime": 0, "philgeps": 0},
            "total_cost": 0
        })

@app.get("/api/province-projects/top-provinces")
async def top_provinces_api(all: bool = Query(default=False, description="Return all provinces instead of top 10")):
    """Get top 10 provinces by project count and total cost, or all provinces if all=true"""
    try:
        import json
        from pathlib import Path
        
        cache_base_dir = Path(__file__).parent / 'static' / 'data'
        province_stats = []
        
        # Iterate through all province cache directories
        for province_dir in cache_base_dir.glob('province-projects-*/summary.json'):
            try:
                with open(province_dir, 'r', encoding='utf-8') as f:
                    summary_data = json.load(f)
                
                province_name = province_dir.parent.name.replace('province-projects-', '').replace('-', ' ').title()
                # Fix common province name issues
                province_name = province_name.replace('Iloil', 'Iloilo').replace('Compostela Valley', 'Davao de Oro')
                summary = summary_data.get('summary', {})
                total_projects = summary.get('total', 0)
                total_cost = summary_data.get('total_cost', 0)
                
                if total_projects > 0:
                    province_stats.append({
                        'name': province_name,
                        'count': total_projects,
                        'total_cost': total_cost,
                        'sources': {
                            'ssp': summary.get('ssp', 0),
                            'dime': summary.get('dime', 0),
                            'philgeps': summary.get('philgeps', 0),
                            'microsite': summary.get('microsite', 0)
                        }
                    })
            except Exception as e:
                print(f"Error reading {province_dir}: {e}")
                continue
        
        # Sort by project count descending
        province_stats.sort(key=lambda x: x['count'], reverse=True)
        
        # Return all provinces if requested, otherwise top 10
        if all:
            result = province_stats
        else:
            result = province_stats[:10]
        
        return JSONResponse({
            "success": True,
            "provinces": result
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e),
            "provinces": []
        })

@app.get("/api/province-projects/all-provinces-totals")
async def all_provinces_totals_api():
    """Get overall totals across all provinces (pre-computed)"""
    try:
        import json
        from pathlib import Path
        
        cache_file = Path(__file__).parent / 'static' / 'data' / 'province-overall-totals.json'
        
        if cache_file.exists():
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            return JSONResponse(cache_data)
        else:
            # Fallback: calculate on the fly if cache doesn't exist
            cache_base_dir = Path(__file__).parent / 'static' / 'data'
            total_projects = 0
            total_cost = 0
            province_count = 0
            
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
                except Exception as e:
                    print(f"Error reading {province_dir}: {e}")
                    continue
            
            return JSONResponse({
                "success": True,
                "total_projects": total_projects,
                "total_cost": total_cost,
                "province_count": province_count,
                "cache_version": "1.0"
            })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e),
            "total_projects": 0,
            "total_cost": 0
        })

@app.get("/api/dynasty-projects/search")
async def dynasty_projects_search_api(
    congressman: str = Query(..., description="Congressman name to search"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=100, description="Number of records per page")
):
    """Search projects by congressman name - DEPRECATED: Use /api/dynasty-projects/all and filter client-side"""
    try:
        import asyncpg
        from flood_client import FloodControlClient
        
        # Connect to dynasty database to find congressman
        dynasty_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
        )
        
        # Search for congressman in dynasty database - get full person info
        congressman_query = """
            SELECT id, first_name, last_name, province, municipality_city, region, party
            FROM political_dynasties
            WHERE (UPPER(position) LIKE '%CONGRESSMAN%' OR UPPER(position) LIKE '%CONGRESSMEN%' OR UPPER(position) LIKE '%MEMBER, HOUSE OF REPRESENTATIVES%')
              AND (UPPER(first_name || ' ' || last_name) LIKE $1 OR UPPER(last_name || ', ' || first_name) LIKE $1)
            LIMIT 1
        """
        search_pattern = f"%{congressman.upper()}%"
        person = await dynasty_conn.fetchrow(congressman_query, search_pattern)
        
        if not person:
            await dynasty_conn.close()
            return JSONResponse({
                "success": False,
                "error": f"No congressman found matching '{congressman}'",
                "congressman_info": None,
                "projects": [],
                "summary": {"total": 0, "ssp": 0, "dime": 0, "philgeps": 0}
            })
        
        # Get district info
        provinces = [person['province']] if person['province'] else []
        municipalities = [person['municipality_city']] if person['municipality_city'] else []
        
        # Get direct contractor connections
        direct_contractors = await dynasty_conn.fetch('''
            SELECT DISTINCT company_name, role
            FROM contractor_dynasty_matches
            WHERE dynasty_first_name = $1 AND dynasty_last_name = $2
        ''', person['first_name'], person['last_name'])
        contractor_names = [c['company_name'] for c in direct_contractors]
        
        # Get party-list connections and their contractors
        party_lists = await dynasty_conn.fetch('''
            SELECT pl.party_list_number, pl.party_name
            FROM party_list_members plm
            JOIN party_list pl ON plm.party_list_number = pl.party_list_number
            WHERE plm.person_id = $1
        ''', person['id'])
        
        party_list_info = []
        for pl in party_lists:
            # Get all contractors for this party-list (all members' contractors)
            pl_contractors = await dynasty_conn.fetch('''
                SELECT DISTINCT cdm.company_name, cdm.role
                FROM party_list_members plm2
                JOIN political_dynasties pd ON plm2.person_id = pd.id
                JOIN contractor_dynasty_matches cdm ON cdm.dynasty_first_name = pd.first_name 
                                                       AND cdm.dynasty_last_name = pd.last_name
                WHERE plm2.party_list_number = $1
            ''', pl['party_list_number'])
            pl_contractor_names = [c['company_name'] for c in pl_contractors]
            contractor_names.extend(pl_contractor_names)
            party_list_info.append({
                "number": pl['party_list_number'],
                "name": pl['party_name'],
                "contractors": pl_contractor_names
            })
        
        contractor_names = list(set(contractor_names))
        
        await dynasty_conn.close()
        
        # Now query projects from all 3 databases
        # This is a simplified version - in production, you'd want to use the cached JSON
        # For now, we'll use the search endpoint which queries the cache
        # But this endpoint should redirect to the cached data filtered by congressman
        
        return JSONResponse({
            "success": True,
            "congressman_info": {
                "name": f"{person['first_name']} {person['last_name']}",
                "province": person['province'],
                "municipality": person['municipality_city'],
                "region": person['region'],
                "party": person['party'],
                "contractors": contractor_names,
                "party_lists": party_list_info
            },
            "projects": [],
            "summary": {"total": 0, "ssp": 0, "dime": 0, "philgeps": 0},
            "message": "This endpoint is deprecated. Use /api/dynasty-projects/all and filter by congressman client-side."
        })
        
    except Exception as e:
        print(f"Error in dynasty_projects_search_api: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "success": False,
            "error": str(e),
            "congressman_info": None,
            "projects": [],
            "summary": {"total": 0, "ssp": 0, "dime": 0, "philgeps": 0}
        })

@app.get("/api/sources")
async def get_sources_api():
    """Get all sources from database/sources.csv grouped by source name"""
    try:
        csv_path = Path(__file__).parent / 'database' / 'sources.csv'
        domain_mapping = {
            'rappler.com': 'Rappler',
            'newsinfo.inquirer.net': 'Philippine Daily Inquirer',
            'business.inquirer.net': 'Philippine Daily Inquirer',
            'inquirer.net': 'Philippine Daily Inquirer',
            'manilastandard.net': 'Manila Standard',
            'manilatimes.net': 'Manila Times',
            'philstar.com': 'Philippine STAR',
            'wikipedia.org': 'Wikipedia',
            'wikiwand.com': 'Wikiwand',
            'peoplaid.com': 'PeoPlaid',
            'kwebanibarok.com': 'Kwebanibarok',
            'dof.gov.ph': 'DOF Philippines',
            'pdplaban.org.ph': 'PDP Laban',
            'reddit.com': 'Reddit',
            'philatlas.com': 'PhilAtlas',
            'bilyonaryo.com': 'Bilyonaryo',
            'abs-cbn.com': 'ABS-CBN',
            'pcij.org': 'PCIJ Flood Control'
        }
        
        name_normalization = {
            'Inquirer': 'Philippine Daily Inquirer',
            'Philippine Daily Inquirer': 'Philippine Daily Inquirer',
            'Philippine Daily Inquirer News': 'Philippine Daily Inquirer',
            'Philippine Inquirer': 'Philippine Daily Inquirer',
            'The Philippine Daily Inquirer': 'Philippine Daily Inquirer',
            'Manila Standard': 'Manila Standard',
            'The Manila Times': 'Manila Times',
            'Manila Times': 'Manila Times',
            'Rappler': 'Rappler',
            'Wikipedia': 'Wikipedia',
            'PhilAtlas': 'PhilAtlas'
        }
        
        def get_domain(url: str) -> str:
            if not url:
                return ''
            parsed = urlparse(url)
            domain = (parsed.netloc or '').lower()
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain
        
        def get_source_key(source_name: str, url: str) -> str:
            domain = get_domain(url)
            # Special handling for Facebook/Social Media to extract source from name
            if domain in ['facebook.com', 'm.facebook.com', 'web.facebook.com']:
                if 'VOV Philippines' in source_name:
                    return 'VOV Philippines'
                if 'Aviso Zamboanga' in source_name:
                    return 'Aviso Zamboanga'
                # Check for other known social media sources if needed

            if domain:
                if domain in domain_mapping:
                    return domain_mapping[domain]
                for known_domain, mapped in domain_mapping.items():
                    if domain.endswith(known_domain):
                        return mapped
            
            normalized_name = (source_name or '').strip()
            if normalized_name:
                normalized_name = name_normalization.get(normalized_name, normalized_name)
                return normalized_name
            if domain:
                return domain
            return 'Unknown'
        
        sources_by_name = defaultdict(list)
        seen_urls = set()
        
        def add_entry(source_key: str, title: str, url: str, date: str) -> None:
            if not source_key or not url:
                return
            key = (source_key, url)
            if key in seen_urls:
                return
            seen_urls.add(key)
            sources_by_name[source_key].append({
                "title": title or url,
                "url": url,
                "date": date or ''
            })
        try:
            relationship_articles = await fetch_relationship_articles()
            for source_key, articles in relationship_articles.items():
                for article in articles:
                    add_entry(
                        source_key,
                        (article.get("title") or article.get("url") or "").strip(),
                        (article.get("url") or "").strip(),
                        (article.get("date") or "").strip()
                    )
        except Exception as rel_error:
            print(f"⚠️  Failed to supplement relationship sources: {rel_error}")
        
        if csv_path.exists():
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if not row:
                        continue
                    source_name = (row.get('Source_Name') or '').strip()
                    url = (row.get('URL') or '').strip()
                    if not url:
                        continue
                    title = (row.get('Source_Name') or '').strip() or url
                    date = (row.get('Publish_Date') or '').strip() or ''
                    source_key = get_source_key(source_name, url)
                    if source_key == 'Unknown' and source_name:
                        source_key = source_name
                    add_entry(source_key, title, url, date)
        else:
            print("⚠️  Sources CSV file not found; proceeding with dynasty database sources only.")
        
        # Pull additional sources from dynasty database tables
        conn = None
        try:
            conn = await asyncpg.connect(
                host=os.getenv('POSTGRES_HOST', 'localhost'),
                port=int(os.getenv('POSTGRES_PORT', 5432)),
                user=os.getenv('POSTGRES_USER', 'budget_admin'),
                password=os.getenv('POSTGRES_PASSWORD', ''),
                database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
            )
            
            dynasty_queries = [
                """
                SELECT 
                    COALESCE(NULLIF(relationship_description, ''), 'Dynasty relationship coverage') AS title,
                    source_url AS url,
                    TO_CHAR(created_at, 'YYYY-MM-DD') AS date
                FROM all_names_politician_relationships
                WHERE source_url IS NOT NULL AND source_url <> ''
                """,
                """
                SELECT 
                    COALESCE(NULLIF(relationship_description, ''), 'BAC relationship coverage') AS title,
                    source_url AS url,
                    TO_CHAR(created_at, 'YYYY-MM-DD') AS date
                FROM bac_politician_relationships
                WHERE source_url IS NOT NULL AND source_url <> ''
                """,
                """
                SELECT 
                    COALESCE(NULLIF(relationship_description, ''), 'Engineer relationship coverage') AS title,
                    source_url AS url,
                    TO_CHAR(created_at, 'YYYY-MM-DD') AS date
                FROM engineer_politician_relationships
                WHERE source_url IS NOT NULL AND source_url <> ''
                """,
                """
                SELECT 
                    COALESCE(CONCAT_WS(' - ', NULLIF(company_name, ''), NULLIF(role, '')), 'Company affiliation reference') AS title,
                    source_url AS url,
                    TO_CHAR(created_at, 'YYYY-MM-DD') AS date
                FROM company_affiliations
                WHERE source_url IS NOT NULL AND source_url <> ''
                """
            ]
            
            for query in dynasty_queries:
                rows = await conn.fetch(query)
                for row in rows:
                    url = (row.get('url') or '').strip()
                    if not url:
                        continue
                    title = (row.get('title') or '').strip() or url
                    date = (row.get('date') or '').strip()
                    source_key = get_source_key('', url)
                    add_entry(source_key, title, url, date)
        except Exception as db_error:
            print(f"⚠️  Failed to load dynasty sources: {db_error}")
        finally:
            if conn:
                await conn.close()
        
        # Ensure required investigative sources have at least one entry
        required_defaults = {
            "Rappler": [{
                "title": "Rappler Investigative Coverage",
                "url": "https://www.rappler.com/newsbreak/investigative/",
                "date": ""
            }],
            "Philippine Daily Inquirer": [{
                "title": "Philippine Daily Inquirer News",
                "url": "https://www.inquirer.net/",
                "date": ""
            }],
            "Manila Standard": [{
                "title": "Manila Standard - News",
                "url": "https://manilastandard.net/",
                "date": ""
            }],
            "Manila Times": [{
                "title": "The Manila Times",
                "url": "https://www.manilatimes.net/",
                "date": ""
            }],
            "Wikipedia": [{
                "title": "Wikipedia: Politics of the Philippines",
                "url": "https://en.wikipedia.org/wiki/Politics_of_the_Philippines",
                "date": ""
            }],
            "PhilAtlas": [{
                "title": "PhilAtlas Province Profiles",
                "url": "https://www.philatlas.com/",
                "date": ""
            }]
        }
        
        for source_key, default_articles in required_defaults.items():
            if not sources_by_name.get(source_key):
                for article in default_articles:
                    add_entry(source_key, article["title"], article["url"], article.get("date", ""))
        
        # Sort articles by date (if available) descending within each source
        for entries in sources_by_name.values():
            entries.sort(key=lambda item: (item.get("date") or "", item.get("title") or ""), reverse=True)
        
        result = {source_name: articles for source_name, articles in sorted(sources_by_name.items())}
        
        return JSONResponse({
            "success": True,
            "sources": result,
            "total_sources": len(result),
            "total_articles": sum(len(articles) for articles in result.values())
        })
        
    except Exception as e:
        print(f"❌ Error loading sources: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e),
            "sources": {}
        })


@app.get("/api/relationship-sources/checklist")
async def relationship_sources_checklist_api():
    """Return checklist report for relationship entries and their source URLs."""
    try:
        report = await fetch_relationship_checklist()
        return JSONResponse({
            "success": True,
            **report,
        })
    except Exception as exc:
        print(f"❌ Error generating relationship checklist: {exc}")
        return JSONResponse(
            {"success": False, "error": str(exc)},
            status_code=500,
        )

async def fetch_flood_flag_metadata(global_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    valid_ids = {gid for gid in global_ids if gid}
    if not valid_ids:
        return {}

    conn = None
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_FLOOD', 'flood')
        )

        id_list = list(valid_ids)

        summary_rows = await conn.fetch(
            """
            SELECT project_global_id,
                   COALESCE(is_green_flag, FALSE) AS is_green_flag,
                   COALESCE(has_red_flags, FALSE) AS has_red_flags
            FROM flagged_flood_projects
            WHERE project_global_id = ANY($1::text[])
            """,
            id_list
        )

        classification_rows = await conn.fetch(
            """
            SELECT project_global_id,
                   classification,
                   classification_type,
                   reason
            FROM flood_project_flag_links
            WHERE project_global_id = ANY($1::text[])
            """,
            id_list
        )

        metadata: Dict[str, Dict[str, Any]] = {}
        for row in summary_rows:
            metadata[row['project_global_id']] = {
                "is_green_flag": bool(row['is_green_flag']),
                "has_red_flags": bool(row['has_red_flags']),
                "red_flags": [],
                "green_flags": [],
            }

        for row in classification_rows:
            entry = metadata.setdefault(
                row['project_global_id'],
                {
                    "is_green_flag": False,
                    "has_red_flags": False,
                    "red_flags": [],
                    "green_flags": [],
                },
            )
            flag_record = {
                "classification": row['classification'],
                "reason": row['reason'],
            }
            if row['classification_type'] == 'red':
                entry["red_flags"].append(flag_record)
                entry["has_red_flags"] = True
            elif row['classification_type'] == 'green':
                entry["green_flags"].append(flag_record)
                entry["is_green_flag"] = True

        return metadata
    except Exception as exc:
        print(f"⚠️ [API] Failed to fetch flood flag metadata: {exc}")
        return {}
    finally:
        if conn:
            await conn.close()

@app.post("/api/province-projects/coordinates")
async def province_project_coordinates_api(request: Request):
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {exc}") from exc

    province = payload.get("province")
    project_inputs = payload.get("projects") or []
    coordinates: List[Dict[str, Any]] = []

    for project in project_inputs:
        project_name = project.get("project_name") or ""
        if not project_name:
            continue

        primary_source = (project.get("source") or "").lower()
        candidate_sources: List[str] = []
        if primary_source:
            candidate_sources.append(primary_source)

        for src in project.get("sources") or []:
            lower = (src or "").lower()
            if lower and lower not in candidate_sources:
                candidate_sources.append(lower)

        province_hint = project.get("province") or province
        city_hint = project.get("municipality") or project.get("city")

        found = False
        for candidate in candidate_sources:
            try:
                if candidate == "ssp":
                    matches, _ = await search_flood_projects(
                        query=project_name,
                        province=province_hint,
                        limit=1,
                        offset=0,
                    )
                    if matches:
                        match = matches[0]
                        lat = match.get("Latitude")
                        lng = match.get("Longitude")
                        try:
                            lat_val = float(lat)
                            lng_val = float(lng)
                        except (TypeError, ValueError):
                            lat_val = lng_val = None
                        if lat_val is not None and lng_val is not None:
                            coordinates.append({
                                "project_name": project_name,
                                "source": candidate,
                                "original_source": primary_source,
                                "latitude": lat_val,
                                "longitude": lng_val,
                                "status": match.get("Status") or match.get("status"),
                                "matched_source": "ssp",
                                "flags": match.get("flags")
                            })
                            found = True
                            break
                elif candidate == "dime":
                    dime_match = await find_dime_project_coordinates(project_name, province_hint, city_hint)
                    if dime_match:
                        coordinates.append({
                            "project_name": project_name,
                            "source": candidate,
                            "original_source": primary_source,
                            "latitude": dime_match["latitude"],
                            "longitude": dime_match["longitude"],
                            "status": dime_match.get("status"),
                            "matched_source": "dime"
                        })
                        found = True
                        break
                elif candidate == "philgeps":
                    province_hint = project.get("province") or province
                    city_hint = project.get("municipality") or project.get("city")
                    philgeps_match = await find_philgeps_project_coordinates(
                        project_name,
                        province_hint=province_hint,
                        city_hint=city_hint,
                        amount_hint=project.get("amount")
                    )
                    if philgeps_match and philgeps_match.get("latitude") is not None and philgeps_match.get("longitude") is not None:
                        coordinates.append({
                            "project_name": project_name,
                            "source": candidate,
                            "original_source": primary_source,
                            "latitude": float(philgeps_match["latitude"]),
                            "longitude": float(philgeps_match["longitude"]),
                            "status": None,
                            "matched_source": "philgeps",
                            "metadata": {k: philgeps_match.get(k) for k in ("reference_id", "contract_no", "award_title", "area_of_delivery") if philgeps_match.get(k) is not None}
                        })
                        found = True
                        break
                elif candidate in ("microsite", "infrawatch"):
                    province_hint = project.get("province") or province
                    city_hint = project.get("municipality") or project.get("city")
                    infrawatch_match = await find_infrawatch_project_coordinates(
                        project_name,
                        province_hint=province_hint,
                        city_hint=city_hint,
                        amount_hint=project.get("amount")
                    )
                    if infrawatch_match and infrawatch_match.get("latitude") is not None and infrawatch_match.get("longitude") is not None:
                        coordinates.append({
                            "project_name": project_name,
                            "source": candidate,
                            "original_source": primary_source,
                            "latitude": float(infrawatch_match["latitude"]),
                            "longitude": float(infrawatch_match["longitude"]),
                            "status": None,
                            "matched_source": "microsite",
                            "metadata": infrawatch_match.get("raw_record")
                        })
                        found = True
                        break
                # PhilGEPS and Microsite coordinate lookups are not yet implemented
            except Exception as exc:
                print(f"⚠️ Coordinate lookup failed for {project_name} ({candidate}): {exc}")

        if found:
            continue

    return JSONResponse({
        "success": True,
        "province": province,
        "coordinates": coordinates
    })

def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if value != value:  # NaN check
            return None
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    match = re.findall(r"-?\d+(?:\.\d+)?", text.replace(",", " "))
    if not match:
        return None
    try:
        return float(match[0])
    except ValueError:
        return None


def _amounts_close(amount_hint: Optional[Any], candidate: Optional[Any]) -> bool:
    hint = _coerce_float(amount_hint)
    candidate_val = _coerce_float(candidate)
    if hint is None or candidate_val is None:
        return True
    tolerance = max(500000.0, hint * 0.1)
    return abs(hint - candidate_val) <= tolerance


def _coordinate_cache_key(*parts: Optional[str]) -> str:
    normalized = [part.lower().strip() for part in parts if isinstance(part, str) and part.strip()]
    return "|".join(normalized)


def _extract_coordinate_pair_from_record(record: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    for lat_key in _INFRAWATCH_LAT_KEYS:
        lat = _coerce_float(record.get(lat_key))
        if lat is None:
            continue
        for lng_key in _INFRAWATCH_LNG_KEYS:
            lng = _coerce_float(record.get(lng_key))
            if lng is not None:
                return lat, lng
    for coord_key in _INFRAWATCH_COORDINATE_FALLBACK_KEYS:
        raw = record.get(coord_key)
        if not raw:
            continue
        text = str(raw)
        numeric = re.findall(r"-?\d+(?:\.\d+)?", text.replace(",", " "))
        if len(numeric) >= 2:
            lat = _coerce_float(numeric[0])
            lng = _coerce_float(numeric[1])
            if lat is not None and lng is not None:
                return lat, lng
    return None

async def _get_philgeps_coordinate_columns(conn: asyncpg.Connection) -> Optional[Tuple[str, str]]:
    global _PHILGEPS_COORD_COLUMNS
    if _PHILGEPS_COORD_COLUMNS:
        return _PHILGEPS_COORD_COLUMNS
    try:
        rows = await conn.fetch(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'contracts'
            """
        )
    except Exception as exc:
        print(f"⚠️ Failed to inspect PhilGEPS columns: {exc}")
        _PHILGEPS_COORD_COLUMNS = None
        return None

    lat_column = None
    lng_column = None
    for row in rows:
        column_name = row.get("column_name")
        if not column_name:
            continue
        lowered = column_name.lower()
        if lat_column is None and "lat" in lowered:
            lat_column = column_name
        elif lng_column is None and ("long" in lowered or "lng" in lowered):
            lng_column = column_name
        if lat_column and lng_column:
            break

    if lat_column and lng_column:
        _PHILGEPS_COORD_COLUMNS = (lat_column, lng_column)
    else:
        _PHILGEPS_COORD_COLUMNS = None
    return _PHILGEPS_COORD_COLUMNS


async def find_philgeps_project_coordinates(
    project_name: Optional[str],
    province_hint: Optional[str] = None,
    city_hint: Optional[str] = None,
    amount_hint: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    cache_key = _coordinate_cache_key(project_name, province_hint, city_hint)
    if cache_key in _PHILGEPS_COORD_CACHE:
        return _PHILGEPS_COORD_CACHE[cache_key]

    if not project_name:
        _PHILGEPS_COORD_CACHE[cache_key] = None
        return None

    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
        )
    except Exception as exc:
        print(f"⚠️ PhilGEPS connection failed: {exc}")
        _PHILGEPS_COORD_CACHE[cache_key] = None
        return None

    try:
        columns = await _get_philgeps_coordinate_columns(conn)
        if not columns:
            _PHILGEPS_COORD_CACHE[cache_key] = None
            return None
        lat_column, lng_column = columns
        conditions = ["award_title ILIKE $1"]
        params: List[Any] = [f"%{project_name}%"]
        param_index = 2

        if city_hint:
            conditions.append(f"(area_of_delivery ILIKE ${param_index} OR organization_name ILIKE ${param_index})")
            params.append(f"%{city_hint}%")
            param_index += 1
        if province_hint:
            conditions.append(f"(area_of_delivery ILIKE ${param_index} OR organization_name ILIKE ${param_index})")
            params.append(f"%{province_hint}%")
            param_index += 1

        where_clause = " AND ".join(conditions)
        sql = f"""
            SELECT "{lat_column}" AS lat_value,
                   "{lng_column}" AS lng_value,
                   award_title,
                   area_of_delivery,
                   contract_amount,
                   reference_id,
                   contract_no
            FROM contracts
            WHERE {where_clause}
            ORDER BY contract_amount DESC NULLS LAST
            LIMIT 40
        """
        try:
            rows = await conn.fetch(sql, *params)
        except Exception as exc:
            print(f"⚠️ PhilGEPS coordinate query failed: {exc}")
            _PHILGEPS_COORD_CACHE[cache_key] = None
            return None

        for row in rows:
            lat = _coerce_float(row.get("lat_value"))
            lng = _coerce_float(row.get("lng_value"))
            if lat is None or lng is None:
                continue
            if not _amounts_close(amount_hint, row.get("contract_amount")):
                continue
            result = {
                "latitude": lat,
                "longitude": lng,
                "matched_source": "philgeps",
                "reference_id": row.get("reference_id"),
                "contract_no": row.get("contract_no"),
                "award_title": row.get("award_title"),
                "area_of_delivery": row.get("area_of_delivery")
            }
            _PHILGEPS_COORD_CACHE[cache_key] = result
            return result

        _PHILGEPS_COORD_CACHE[cache_key] = None
        return None
    finally:
        await conn.close()


async def find_infrawatch_project_coordinates(
    project_name: Optional[str],
    province_hint: Optional[str] = None,
    city_hint: Optional[str] = None,
    amount_hint: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    cache_key = _coordinate_cache_key("infrawatch", project_name, province_hint, city_hint)
    if cache_key in _INFRAWATCH_COORD_CACHE:
        return _INFRAWATCH_COORD_CACHE[cache_key]

    if not project_name:
        _INFRAWATCH_COORD_CACHE[cache_key] = None
        return None

    conn = await get_infrawatch_connection()
    if not conn:
        _INFRAWATCH_COORD_CACHE[cache_key] = None
        return None

    try:
        meta = await _get_infrawatch_table_meta(conn)
        if not meta or meta.get("table") is None:
            _INFRAWATCH_COORD_CACHE[cache_key] = None
            return None

        if meta.get("mode") == "structured":
            params: List[Any] = []
            conditions: List[str] = []
            param_index = 1

            title_cols = meta.get("title_cols") or []
            if title_cols:
                title_predicates = [f"\"{col}\" ILIKE ${param_index}" for col in title_cols]
                params.append(f"%{project_name}%")
                conditions.append("(" + " OR ".join(title_predicates) + ")")
                param_index += 1
            else:
                conditions.append("TRUE")

            if city_hint and meta.get("city_cols"):
                city_predicates = [f"\"{col}\" ILIKE ${param_index}" for col in meta.get("city_cols", [])]
                params.append(f"%{city_hint}%")
                conditions.append("(" + " OR ".join(city_predicates) + ")")
                param_index += 1

            if province_hint and meta.get("province_cols"):
                province_predicates = [f"\"{col}\" ILIKE ${param_index}" for col in meta.get("province_cols", [])]
                params.append(f"%{province_hint}%")
                conditions.append("(" + " OR ".join(province_predicates) + ")")
                param_index += 1

            if not conditions:
                conditions.append("TRUE")

            amount_cols = meta.get("amount_cols") or []
            amount_column = amount_cols[0] if amount_cols else None

            select_parts: List[str] = [
                f"\"{meta['lat_col']}\" AS lat_value",
                f"\"{meta['lng_col']}\" AS lng_value",
            ]
            if amount_column:
                select_parts.append(f"\"{amount_column}\" AS amount_value")
            metadata_cols: List[str] = []
            for col in meta.get("metadata_cols", []):
                if col in (meta['lat_col'], meta['lng_col'], amount_column):
                    continue
                select_parts.append(f"\"{col}\"")
                metadata_cols.append(col)

            order_clause = ""
            if amount_column:
                order_clause = f" ORDER BY \"{amount_column}\" DESC NULLS LAST"

            sql = f"""
                SELECT {", ".join(select_parts)}
                FROM {meta['table']}
                WHERE {' AND '.join(conditions)}
                {order_clause}
                LIMIT 60
            """
            try:
                rows = await conn.fetch(sql, *params)
            except Exception as exc:
                print(f"⚠️ Infrawatch structured coordinate query failed: {exc}")
                rows = []

            for row in rows:
                lat = _coerce_float(row.get("lat_value"))
                lng = _coerce_float(row.get("lng_value"))
                if lat is None or lng is None:
                    continue
                if amount_column and not _amounts_close(amount_hint, row.get("amount_value")):
                    continue
                raw_record = {col: row.get(col) for col in metadata_cols if col in row.keys()}
                for identifier in meta.get("id_cols", []):
                    if identifier not in raw_record and identifier in row.keys():
                        raw_record[identifier] = row.get(identifier)
                result = {
                    "latitude": lat,
                    "longitude": lng,
                    "matched_source": "microsite",
                    "record_id": raw_record.get("contract_id") or raw_record.get("project_id"),
                    "raw_record": raw_record,
                }
                _INFRAWATCH_COORD_CACHE[cache_key] = result
                return result

        # Fallback to JSON rows model when structured lookup misses
        params = []
        conditions = []
        param_index = 1

        title_predicates = []
        for key in _INFRAWATCH_TITLE_KEYS:
            title_predicates.append(f"data->>'{key}' ILIKE ${param_index}")
        params.append(f"%{project_name}%")
        conditions.append("(" + " OR ".join(title_predicates) + ")")
        param_index += 1

        if city_hint:
            city_predicates = [f"data->>'{key}' ILIKE ${param_index}" for key in _INFRAWATCH_CITY_KEYS]
            params.append(f"%{city_hint}%")
            conditions.append("(" + " OR ".join(city_predicates) + ")")
            param_index += 1

        if province_hint:
            province_predicates = [f"data->>'{key}' ILIKE ${param_index}" for key in _INFRAWATCH_PROVINCE_KEYS]
            params.append(f"%{province_hint}%")
            conditions.append("(" + " OR ".join(province_predicates) + ")")
            param_index += 1

        table_name = meta.get("table", "infrawatch_projects_rows")
        where_clause = " AND ".join(conditions)
        sql = f"""
            SELECT data
            FROM {table_name}
            WHERE {where_clause}
            LIMIT 60
        """
        try:
            rows = await conn.fetch(sql, *params)
        except Exception as exc:
            print(f"⚠️ Infrawatch coordinate query failed: {exc}")
            _INFRAWATCH_COORD_CACHE[cache_key] = None
            return None

        for row in rows:
            raw_record = row.get("data")
            if isinstance(raw_record, str):
                try:
                    record = json.loads(raw_record)
                except json.JSONDecodeError:
                    continue
            else:
                record = raw_record
            if not isinstance(record, dict):
                continue

            coords = _extract_coordinate_pair_from_record(record)
            if not coords:
                continue
            lat, lng = coords
            if province_hint:
                province_text = " ".join(str(record.get(key, "")) for key in _INFRAWATCH_PROVINCE_KEYS)
                if province_hint.lower() not in province_text.lower():
                    continue
            if city_hint:
                city_text = " ".join(str(record.get(key, "")) for key in _INFRAWATCH_CITY_KEYS)
                if city_hint.lower() not in city_text.lower():
                    continue
            if not _amounts_close(amount_hint, record.get("Contract Amount")):
                continue
            result = {
                "latitude": lat,
                "longitude": lng,
                "matched_source": "microsite",
                "record_id": record.get("Contract ID") or record.get("Reference Number"),
                "raw_record": {k: record.get(k) for k in ("Project Name", "Project", "Project Description", "City/Municipality", "Municipality", "Province")}
            }
            _INFRAWATCH_COORD_CACHE[cache_key] = result
            return result

        _INFRAWATCH_COORD_CACHE[cache_key] = None
        return None
    finally:
        await conn.close()

async def _get_infrawatch_table_meta(conn: asyncpg.Connection) -> Dict[str, Any]:
    global _INFRAWATCH_TABLE_META
    if _INFRAWATCH_TABLE_META is not None:
        return _INFRAWATCH_TABLE_META

    async def inspect_table(table_name: str) -> Optional[List[str]]:
        exists = await conn.fetchval("SELECT to_regclass($1)", f"public.{table_name}")
        if not exists:
            return None
        rows = await conn.fetch(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = $1
            """,
            table_name,
        )
        columns = [row.get("column_name") for row in rows if row.get("column_name")]
        return columns or None

    structured_columns = await inspect_table("infrawatch_projects")
    if structured_columns:
        lowered = {col: col.lower() for col in structured_columns}

        def find_column(priority_keywords: List[str]) -> Optional[str]:
            for keywords in priority_keywords:
                if isinstance(keywords, str):
                    keywords = [keywords]
                for col, lower in lowered.items():
                    if all(keyword in lower for keyword in keywords):
                        return col
            return None

        def collect_columns(keywords: List[str]) -> List[str]:
            result: List[str] = []
            seen: Set[str] = set()
            for col, lower in lowered.items():
                if any(keyword in lower for keyword in keywords):
                    if col not in seen:
                        seen.add(col)
                        result.append(col)
            return result

        lat_col = find_column([["lat"]])
        lng_col = find_column([["long"], ["lng"]])

        if lat_col and lng_col:
            title_cols = collect_columns(["project_name", "project title", "project", "name", "description"])
            if not title_cols and "title" in lowered.values():
                title_cols = collect_columns(["title"])
            city_cols = collect_columns(["municipality", "city"])
            province_cols = collect_columns(["province"])
            amount_cols = collect_columns(["contract_amount", "project_cost", "amount", "cost", "value"]) or []
            id_cols = collect_columns(["contract_id", "project_id", "id"]) or []
            metadata_cols = list(dict.fromkeys(title_cols + city_cols + province_cols + id_cols))

            _INFRAWATCH_TABLE_META = {
                "mode": "structured",
                "table": "infrawatch_projects",
                "lat_col": lat_col,
                "lng_col": lng_col,
                "title_cols": title_cols,
                "city_cols": city_cols,
                "province_cols": province_cols,
                "amount_cols": amount_cols,
                "metadata_cols": metadata_cols,
                "id_cols": id_cols,
            }
            return _INFRAWATCH_TABLE_META

    rows_columns = await inspect_table("infrawatch_projects_rows")
    if rows_columns:
        _INFRAWATCH_TABLE_META = {
            "mode": "json",
            "table": "infrawatch_projects_rows",
        }
        return _INFRAWATCH_TABLE_META

    _INFRAWATCH_TABLE_META = {"mode": "none", "table": None}
    return _INFRAWATCH_TABLE_META

@app.get("/api/zaldy/dpwh-projects")
async def zaldy_dpwh_projects_api():
    """Get DPWH projects with database tags (flood, DIME, PhilGEPS, Infrawatch) - no authentication required"""
    try:
        from pathlib import Path
        import json
        
        # Try to load from cache first
        script_dir = Path(__file__).resolve().parent
        cache_path = script_dir / "static" / "data" / "zaldy_dpwh_projects_cache.json"
        
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                
                # Return cached data if it's valid
                if cached_data.get("success") and "projects" in cached_data:
                    return JSONResponse(cached_data)
            except Exception as e:
                print(f"⚠️  Error reading cache file: {e}")
                # Fall through to generate fresh data
        
        # If cache doesn't exist or is invalid, return error suggesting to run the cache script
        return JSONResponse({
            "success": False,
            "error": "Cache file not found. Please run: python scripts/generate_zaldy_dpwh_cache.py",
            "cache_path": str(cache_path)
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "success": False,
            "error": str(e)
        })

@app.get("/api/integrated/projects")
async def integrated_projects_api(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=10000, description="Number of records per page"),
    project_name: str = Query(None, description="Filter by project name"),
    contractor: str = Query(None, description="Filter by contractor name"),
    source: str = Query(None, description="Filter by source"),
    green: bool = Query(False, description="Filter for lower-cost projects (excludes resurrected/flagged)"),
    dpwh_all: bool = Query(False, description="Return ALL Annex A-5 (2026) projects (with flags)"),
    group_by: Optional[str] = Query(None, description="Group results (e.g., 'district') for dpwh_all"),
    view: Optional[str] = Query(None, description="Special views for dpwh_all (e.g., 'aggregates')"),
    order_by: Optional[str] = Query(None, description="Sort key for dpwh_all (e.g., amount, delta_amount, delta_pct, flag)"),
    order_dir: str = Query("desc", description="Sort direction: asc|desc"),
):
    """Get unique integrated projects from classified parquet with sources_list"""
    import inspect
    current_file = inspect.getfile(inspect.currentframe())
    print(f"🔵 [DEBUG] /api/integrated/projects endpoint called - page={page}, limit={limit}")
    print(f"🔵 [DEBUG] Executing from file: {current_file}")
    print(f"🔵 [DEBUG] This is the NEW version without DuckDB - timestamp check")
    try:
        import pandas as pd
        from pathlib import Path
        # CRITICAL: Ensure we're NOT using DuckDB - check if it's imported
        import sys
        duckdb_imported = 'duckdb' in sys.modules
        print(f"🔵 [DEBUG] DuckDB imported: {duckdb_imported}")
        # --- GREEN / DPWH ALL PROJECTS LOGIC (2026 Annex A-5) ---
        if green or dpwh_all:
            import json
            import re
            try:
                def _coerce_amount(raw_amount: Any) -> Optional[float]:
                    if raw_amount is None:
                        return None
                    try:
                        return float(raw_amount)
                    except (TypeError, ValueError):
                        return None

                # 1. Load 2026 Data (Annex A-5)
                json_path = Path(__file__).parent / "static" / "data" / "budget_amendments_2026.json"
                if not json_path.exists():
                    return JSONResponse({"error": "2026 Data not found"}, status_code=404)
                
                with open(json_path, 'r', encoding='utf-8') as f:
                    data_2026 = json.load(f)
                
                # Combine projects and line_items, filter for Annex A-5
                raw_items = data_2026.get('projects', []) + data_2026.get('line_items', [])
                annex_a5_items = [
                    item for item in raw_items 
                    if item.get('source_sheet') == 'Annex A-5'
                ]
                
                # 2. Load Bad IDs (Resurrected & Flagged)
                resurrected_ids = set()
                flagged_ids = set()
                historical_amounts_by_pid: Dict[str, List[float]] = {}
                flagged_meta_by_pid: Dict[str, Dict[str, Any]] = {}
                
                # Resurrected
                res_path = Path(__file__).parent / "static" / "data" / "resurrected_projects_dpwh.json"
                if res_path.exists():
                    with open(res_path, 'r', encoding='utf-8') as f:
                        res_data = json.load(f)
                        for match in res_data.get('matches', []):
                            y2026 = match.get('year_2026') or {}
                            pid = y2026.get('id')
                            if pid:
                                pid_str = str(pid)
                                resurrected_ids.add(pid_str)
                                hist = match.get('historical')
                                if isinstance(hist, dict):
                                    amt = _coerce_amount(hist.get('amount'))
                                    if amt:
                                        historical_amounts_by_pid.setdefault(pid_str, []).append(amt)
                                elif isinstance(hist, list):
                                    for entry in hist:
                                        if isinstance(entry, dict):
                                            amt = _coerce_amount(entry.get('amount'))
                                            if amt:
                                                historical_amounts_by_pid.setdefault(pid_str, []).append(amt)
                            
                # Flagged
                flagged_path = Path(__file__).parent / "static" / "data" / "flagged_amount_projects_2026.json"
                if flagged_path.exists():
                    with open(flagged_path, 'r', encoding='utf-8') as f:
                        flagged_list = json.load(f)
                        for item in flagged_list:
                            if not isinstance(item, dict):
                                continue
                            # This file can contain multiple years; only use Annex A-5 2026
                            if str(item.get('source_sheet') or '').strip() != 'Annex A-5':
                                continue
                            if str(item.get('year') or '').strip() != '2026':
                                continue
                            pid = item.get('id')
                            if not pid:
                                continue
                            pid_str = str(pid)
                            if item.get('is_flagged') is True:
                                flagged_ids.add(pid_str)
                            flagged_meta_by_pid[pid_str] = item
                
                # Aggregate lines are typically headers or broad rollups (often very high amount).
                # Includes geographic headers (regions) and financing headers (Loan Proceeds, GOP).
                aggregate_pattern = re.compile(
                    r'^(?:[a-zA-Z0-9]+\.)?\s*(?:'
                    r'National Capital Region|Region\s+[IVX]+|Cordillera Administrative Region|Bangsamoro Autonomous Region|'
                    r'MIMAROPA|CALABARZON|SOCCSKSARGEN|Zamboanga Peninsula|Northern Mindanao|Davao Region|Caraga|'
                    r'Eastern Visayas|Central Visayas|Western Visayas|Bicol Region|Central Luzon|Cagayan Valley|Ilocos Region|'
                    r'Loan Proceeds|GOP'
                    r').*$',
                    re.IGNORECASE
                )

                def _is_aggregate_row(title: str, amount: Optional[float]) -> bool:
                    title = (title or "").strip()
                    if not title:
                        return True
                    if aggregate_pattern.match(title):
                        return True
                    if amount is not None and amount >= 300_000_000:
                        if len(title) <= 80 and len(title.split()) <= 10:
                            return True
                    return False
                
                # 3. Filter Projects
                final_projects = []
                program_rollup: Dict[str, Dict[str, Any]] = {}
                for item in annex_a5_items:
                    pid = str(item.get('id'))
                    p_name = item.get('name') or item.get('description') or ''
                    amount = _coerce_amount(item.get('final_amount') or item.get('original_amount') or 0)

                    baseline_amounts = historical_amounts_by_pid.get(pid) or []
                    baseline_avg = (sum(baseline_amounts) / len(baseline_amounts)) if baseline_amounts else None
                    baseline_samples = len(baseline_amounts)
                    flagged_meta = flagged_meta_by_pid.get(pid) or {}
                    cost_per_km = _coerce_amount(flagged_meta.get('cost_per_km'))
                    threshold = _coerce_amount((flagged_meta.get('subcategory_stats') or {}).get('threshold'))
                    distance_km = _coerce_amount(flagged_meta.get('distance_km'))
                    flag_reason = flagged_meta.get('flag_reason')
                    subcategory = flagged_meta.get('subcategory')
                    # For Annex A-5, "region" is typically a program bucket (not geographic region)
                    program_name = (item.get('location') or {}).get('region') or (item.get('hierarchy') or {}).get('region') or None

                    # Check status
                    is_resurrected = pid in resurrected_ids
                    is_flagged = pid in flagged_ids
                    is_aggregate = _is_aggregate_row(p_name, amount)

                    # For Green: Exclude bad IDs AND aggregates
                    if green and (is_resurrected or is_flagged or is_aggregate):
                        continue
                    
                    # For DPWH All: skip aggregate headers in the projects list
                    if dpwh_all and is_aggregate:
                        continue

                    status_labels = []
                    if is_resurrected:
                        status_labels.append("Resurrected")
                    if is_flagged:
                        status_labels.append("Flagged Amount")
                    if not status_labels:
                        status_labels.append("Lower Cost")
                    
                    final_projects.append({
                        'project_name': p_name,
                        'amount': amount,
                        'contractor_name': item.get('contractor') or 'N/A',
                        'source': 'Annex A-5 (2026)',
                        'sources_list': ['Annex A-5 (2026)'],
                        'contract_id': pid,
                        'program': program_name,
                        'location': program_name or 'Unknown',
                        'status': ', '.join(status_labels),
                        'is_resurrected': is_resurrected,
                        'is_flagged': is_flagged,
                        'flag_reason': flag_reason,
                        'subcategory': subcategory,
                        'cost_per_km': cost_per_km,
                        'threshold_cost_per_km': threshold,
                        'distance_km': distance_km,
                        'baseline_amount': baseline_avg,
                        'baseline_samples': baseline_samples,
                    })

                    # Program rollup (no green/red; just totals)
                    program_key = program_name or 'Unknown'
                    bucket = program_rollup.setdefault(program_key, {
                        'program': program_key,
                        'project_count': 0,
                        'total_amount': 0.0,
                    })
                    bucket['project_count'] += 1
                    if amount:
                        bucket['total_amount'] += float(amount)

                # Add derived pricing fields (over/under) after baseline is available
                for proj in final_projects:
                    baseline = proj.get('baseline_amount')
                    amt = proj.get('amount')
                    if baseline and amt is not None:
                        delta = amt - baseline
                        proj['over_under_amount'] = delta
                        proj['over_under_pct'] = delta / baseline
                        proj['baseline_kind'] = 'historical_amount'
                        continue

                    # Fallback for flagged/non-flagged items with cost/km metadata: compare against threshold * distance
                    distance_km = proj.get('distance_km')
                    threshold = proj.get('threshold_cost_per_km')
                    if amt is not None and distance_km and threshold:
                        baseline_amt = float(distance_km) * float(threshold)
                        if baseline_amt > 0:
                            delta = float(amt) - baseline_amt
                            proj['baseline_amount'] = baseline_amt
                            proj['baseline_kind'] = 'cost_per_km_threshold'
                            proj['over_under_amount'] = delta
                            proj['over_under_pct'] = delta / baseline_amt
                            continue

                    proj['baseline_kind'] = None
                    proj['over_under_amount'] = None
                    proj['over_under_pct'] = None

                if dpwh_all and (group_by or '').lower() in {'program', 'region'}:
                    rows = list(program_rollup.values())
                    rows.sort(key=lambda r: (r.get('total_amount') or 0.0, r.get('project_count') or 0), reverse=True)
                    return JSONResponse({
                        "success": True,
                        "group_by": "program",
                        "rows": rows,
                        "total_groups": len(rows),
                    })

                if dpwh_all and order_by:
                    key = (order_by or "").strip().lower()
                    reverse = (order_dir or "desc").strip().lower() != "asc"

                    def sort_value(project: Dict[str, Any]):
                        if key in {"amount"}:
                            return project.get("amount") if project.get("amount") is not None else -1.0
                        if key in {"delta_amount", "over_under_amount"}:
                            val = project.get("over_under_amount")
                            return val if val is not None else -1.0
                        if key in {"delta_pct", "over_under_pct"}:
                            val = project.get("over_under_pct")
                            return val if val is not None else -1.0
                        if key in {"flag", "status"}:
                            # Red first in desc: 1=red, 0=green
                            is_red = bool(project.get("is_resurrected") or project.get("is_flagged"))
                            return 1 if is_red else 0
                        return 0

                    final_projects.sort(key=sort_value, reverse=reverse)
                
                # 4. Search Filter
                if project_name:
                   final_projects = [p for p in final_projects if project_name.lower() in str(p['project_name']).lower()]
                
                # 5. Pagination + headline stats
                total = len(final_projects)
                total_amount = sum((p.get('amount') or 0.0) for p in final_projects)

                # Prefer real district counts (via district cache). Do not fall back to region/program counts.
                total_districts: Optional[int] = None
                districts_available = False
                try:
                    district_cache_path = Path(__file__).parent / "static" / "data" / "dpwh_annex_a5_district_cache.json"
                    if district_cache_path.exists():
                        district_cache = json.loads(district_cache_path.read_text(encoding="utf-8"))
                        by_id = district_cache.get("by_id") or {}
                        districts = set()
                        for p in final_projects:
                            pid = p.get("contract_id")
                            if not pid:
                                continue
                            entry = by_id.get(str(pid)) or {}
                            district = (entry.get("district") or "").strip()
                            province = (entry.get("province") or "").strip()
                            if not district or district.lower() in {"unknown", "n/a", "na"}:
                                continue
                            if province and province.lower() not in {"unknown", "n/a", "na"}:
                                districts.add(f"{province} - {district}")
                            else:
                                districts.add(district)
                        total_districts = len(districts)
                        districts_available = True
                except Exception:
                    total_districts = None
                    districts_available = False
                
                total_pages = max(1, (total + limit - 1) // limit)
                start = (page - 1) * limit
                end = start + limit
                paginated = final_projects[start:end]
                
                return JSONResponse({
                    "success": True,
                    "projects": paginated,
                    "total": total,
                    "total_amount": total_amount,
                    "total_districts": total_districts,
                    "districts_available": districts_available,
                    "page": page,
                    "limit": limit,
                    "total_pages": total_pages
                })
                
            except Exception as e:
                print(f"Error loading Projects: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)
        # ---------------------------------------------------
        
        # CRITICAL: Use classified parquet (deduplicated) - this is the correct file for the API
        # The classified parquet contains deduplicated projects with sources_list showing all databases
        classified_path = Path(__file__).parent / "data" / "parquet" / "integrated_projects_classified.parquet"
        integrated_path = Path(__file__).parent / "data" / "parquet" / "integrated_projects.parquet"
        
        # ALWAYS prefer classified (deduplicated) - this is the correct output from the script
        if classified_path.exists():
            parquet_path = classified_path
            print(f"📊 Using classified parquet (deduplicated, includes all 5 sources): {parquet_path.name}")
            # Count will be determined after reading the file with pandas
        elif integrated_path.exists():
            # Fallback to integrated if classified doesn't exist (shouldn't happen after script runs)
            parquet_path = integrated_path
            print(f"⚠️  WARNING: Using integrated parquet (all projects, not deduplicated): {integrated_path.name}")
            print(f"   Please regenerate cache with --force to create classified parquet")
        else:
            parquet_path = None
        
        if not parquet_path or not parquet_path.exists():
            return JSONResponse({
                "success": False,
                "error": "Integrated projects parquet file not found. Please run the cache generation script first.",
                "projects": [],
                "total": 0
            })
        
        # Calculate pagination first
        offset = (page - 1) * limit
        
        # Read parquet file with pandas (handles list columns and all column types)
        # CRITICAL: We are NOT using DuckDB - using pandas only
        print(f"📖 Reading parquet file: {parquet_path}")
        print(f"🔵 [DEBUG] Confirming: use_duckdb = False, using pandas only")
        use_duckdb = False
        # Double-check: ensure no DuckDB connection is created
        assert use_duckdb == False, "DuckDB should NOT be used in this endpoint"
        
        try:
            # Read with pyarrow first (faster)
            print(f"   Reading data with pandas/PyArrow (this may take a moment for large files)...")
            df = pd.read_parquet(parquet_path, engine='pyarrow')
            print(f"   ✅ Successfully read {len(df)} rows")
        except Exception as pyarrow_err:
            print(f"⚠️ PyArrow failed: {pyarrow_err}")
            print(f"   Trying default engine...")
            try:
                df = pd.read_parquet(parquet_path)
                print(f"   ✅ Successfully read {len(df)} rows with default engine")
            except Exception as final_err:
                print(f"❌ All parquet read methods failed: {final_err}")
                import traceback
                traceback.print_exc()
                raise final_err
        
        # Get total count from dataframe
        total = len(df)
        
        # Check if dataframe is empty
        if len(df) == 0:
            print(f"⚠️  Parquet file is empty or has no rows")
            return JSONResponse({
                "success": True,
                "projects": [],
                "total": 0,
                "page": page,
                "limit": limit,
                "total_pages": 0
            })
        
        print(f"   DataFrame shape: {df.shape}, Columns: {list(df.columns)[:10]}...")

        # Filter by Green Status (No Flags, No Resurrection)
        if green:
            print("🟢 Filtering for Green Projects (Clean)")
            # Ensure columns exist before filtering to avoid errors
            if 'flag_reason' in df.columns:
                df = df[df['flag_reason'].isna() | (df['flag_reason'] == '')]
            if 'historical_match' in df.columns:
                df = df[df['historical_match'].isna() | (df['historical_match'] == '')]
        
        # Ensure sources_list is a list (it might be stored as string or other format)
        # Handle this more efficiently for large datasets
        if 'sources_list' in df.columns:
            # Check if it's already a list type
            try:
                sample_val = df['sources_list'].iloc[0] if len(df) > 0 else None
                if not isinstance(sample_val, list):
                    # Only convert if needed
                    print(f"   Converting sources_list to list format...")
                    df['sources_list'] = df['sources_list'].apply(
                        lambda x: x if isinstance(x, list) else ([x] if pd.notna(x) and x else [])
                    )
            except Exception as sources_err:
                print(f"⚠️  Error processing sources_list: {sources_err}")
                # Create empty list if conversion fails
                df['sources_list'] = [[]] * len(df)
        else:
            # If sources_list doesn't exist, create it from source field
            if 'source' in df.columns:
                df['sources_list'] = df['source'].apply(
                    lambda x: [x] if pd.notna(x) and x else []
                )
            else:
                df['sources_list'] = [[]] * len(df)
        
        # CRITICAL: Ensure project_name is properly set for PhilGEPS projects
        # For PhilGEPS, we MUST use award_title, NOT contract_id
        if 'project_name' not in df.columns:
            df['project_name'] = ''
        
        # CRITICAL: First, detect and fix contract IDs (e.g., "19Z00043") BEFORE other logic
        # Contract IDs follow pattern: 2 digits, 1 letter, 5 digits
        import re
        contract_id_pattern = r'^\d{2}[A-Z]\d{5}$'
        is_contract_id = df['project_name'].astype(str).str.match(contract_id_pattern, na=False)
        
        if is_contract_id.any():
            contract_id_count = is_contract_id.sum()
            print(f"🔧 Fixing {contract_id_count} projects with contract ID pattern in project_name...")
            
            # For rows where project_name is a contract ID, replace with award_title
            # Note: The parquet file has 'award_title' not 'philgeps_award_title'
            # If still contract ID, try award_title
            still_contract_id = df['project_name'].astype(str).str.match(contract_id_pattern, na=False)
            if still_contract_id.any() and 'award_title' in df.columns:
                mask = still_contract_id & df['award_title'].notna() & (df['award_title'].astype(str).str.strip() != '')
                fixed_count = mask.sum()
                if fixed_count > 0:
                    df.loc[mask, 'project_name'] = df.loc[mask, 'award_title']
                    print(f"   ✅ Fixed {fixed_count} using award_title")
            
            # If still contract ID, try notice_title
            still_contract_id = df['project_name'].astype(str).str.match(contract_id_pattern, na=False)
            if still_contract_id.any() and 'notice_title' in df.columns:
                mask = still_contract_id & df['notice_title'].notna() & (df['notice_title'].astype(str).str.strip() != '')
                fixed_count = mask.sum()
                if fixed_count > 0:
                    df.loc[mask, 'project_name'] = df.loc[mask, 'notice_title']
                    print(f"   ✅ Fixed {fixed_count} using notice_title")
            
            # Log remaining contract IDs that couldn't be fixed
            still_contract_id = df['project_name'].astype(str).str.match(contract_id_pattern, na=False)
            if still_contract_id.any():
                remaining = still_contract_id.sum()
                print(f"   ⚠️  {remaining} projects still have contract ID (no award_title/notice_title available)")
        
        # For PhilGEPS projects, ALWAYS prefer award_title over contract_id (if not already fixed above)
        # Note: The parquet file has 'award_title' not 'philgeps_award_title'
        if 'award_title' in df.columns:
            # Check if project has PhilGEPS in sources_list or source field
            has_philgeps = False
            if 'sources_list' in df.columns:
                has_philgeps = df['sources_list'].apply(
                    lambda x: any('PhilGEPS' in str(s) for s in (x if isinstance(x, list) else [x]) if pd.notna(s))
                )
            elif 'source' in df.columns:
                has_philgeps = df['source'].astype(str).str.contains('PhilGEPS', case=False, na=False)
            
            # For PhilGEPS projects, use award_title if project_name is empty or still looks like contract ID
            if has_philgeps.any():
                empty_or_contract = (df['project_name'].isna() | (df['project_name'] == '') | 
                                   df['project_name'].astype(str).str.match(contract_id_pattern, na=False))
                philgeps_mask = has_philgeps & empty_or_contract & df['award_title'].notna()
                df.loc[philgeps_mask, 'project_name'] = df.loc[philgeps_mask, 'award_title']
        
        # Fallback: if project_name is still empty or looks like a contract ID, try other fields
        empty_or_contract_id = (df['project_name'].isna() | (df['project_name'] == '') | 
                               df['project_name'].astype(str).str.match(contract_id_pattern, na=False))
        if empty_or_contract_id.any():
            # Try project_description
            if 'project_description' in df.columns:
                df.loc[empty_or_contract_id & df['project_description'].notna(), 'project_name'] = \
                    df.loc[empty_or_contract_id & df['project_description'].notna(), 'project_description']
            # Try notice_title for PhilGEPS
            if 'notice_title' in df.columns:
                still_empty = empty_or_contract_id & (df['project_name'].isna() | (df['project_name'] == ''))
                df.loc[still_empty & df['notice_title'].notna(), 'project_name'] = \
                    df.loc[still_empty & df['notice_title'].notna(), 'notice_title']
        
        # Apply filters using pandas (since we're not using DuckDB)
        if project_name:
            if 'project_name' in df.columns:
                mask = df['project_name'].astype(str).str.contains(project_name, case=False, na=False)
                df = df[mask]
        
        if contractor:
            contractor_cols = ['contractor_name', 'philgeps_awardee_name', 'organization_name', 'contractor']
            contractor_mask = pd.Series([False] * len(df))
            for col in contractor_cols:
                if col in df.columns:
                    contractor_mask |= df[col].astype(str).str.contains(contractor, case=False, na=False)
            df = df[contractor_mask]
        
        # Apply source filter
        if source:
            # Filter by sources_list containing the source
            if 'sources_list' in df.columns:
                df = df[df['sources_list'].apply(
                    lambda x: any(source.lower() in str(s).lower() for s in (x if isinstance(x, list) else [x]) if pd.notna(s))
                )]
            elif 'source' in df.columns:
                df = df[df['source'].astype(str).str.contains(source, case=False, na=False)]
        
        # Calculate total and paginate
        # total is already set from dataframe length above
        total_pages = (total + limit - 1) // limit
        
        # Apply pagination
        try:
            df_page = df.iloc[offset:offset + limit]
            print(f"   Paginated: showing rows {offset} to {offset + limit} of {total}")
        except Exception as pagination_err:
            print(f"⚠️ Pagination error: {pagination_err}")
            # Return empty if pagination fails
            df_page = pd.DataFrame()
        
        # Convert to dict more efficiently
        projects = []
        for idx, row in df_page.iterrows():
            project = {}
            
            # Project name - CRITICAL: For PhilGEPS, use award_title, NOT contract_id
            # Note: project_name should already be fixed in the DataFrame above, but double-check here
            project_name = row.get('project_name', '')
            project_name_str = str(project_name) if project_name else ''
            
            # CRITICAL: If project_name still looks like a contract ID (e.g., "19Z00043"), replace with award_title
            # Contract IDs follow pattern: 2 digits, 1 letter, 5 digits (e.g., "19Z00043", "23Z00041")
            # Note: The parquet file has 'award_title' not 'philgeps_award_title'
            if project_name_str and re.match(r'^\d{2}[A-Z]\d{5}$', project_name_str):
                # This is a contract ID, get the actual project name from award_title
                award_title = row.get('award_title')
                if award_title and str(award_title).strip() and str(award_title).strip() != 'nan':
                    project_name = award_title
                else:
                    # Try notice_title as fallback
                    notice_title = row.get('notice_title')
                    if notice_title and str(notice_title).strip() and str(notice_title).strip() != 'nan':
                        project_name = notice_title
                    # Otherwise keep contract_id (better than nothing)
            elif not project_name or project_name == '' or project_name == 'N/A' or project_name == 'nan':
                # If project_name is empty, try to get it from other fields
                project_name = (
                    row.get('award_title') or
                    row.get('notice_title') or
                    row.get('project_description') or 
                    'N/A'
                )
            
            project['project_name'] = str(project_name) if project_name and str(project_name) != 'nan' else 'N/A'
            
            # Contractor
            project['contractor_name'] = (
                row.get('contractor_name') or 
                row.get('philgeps_awardee_name') or 
                row.get('organization_name') or 
                'N/A'
            )
            
            # Amount
            amount_cols = ['amount', 'contract_amount', 'dime_cost', 'infrawatch_contract_price']
            project['amount'] = None
            for col in amount_cols:
                if col in row.index and pd.notna(row[col]):
                    try:
                        project['amount'] = float(row[col])
                        break
                    except (ValueError, TypeError):
                        continue
            
            # Sources list - ensure it's a list
            val_sources = row.get('sources_list', [])
            if hasattr(val_sources, 'tolist'):
                sources_list = val_sources.tolist()
            elif isinstance(val_sources, list):
                sources_list = val_sources
            elif pd.notna(val_sources) and val_sources:
                sources_list = [val_sources]
            else:
                sources_list = []
            
            # Ensure elements are strings
            project['sources_list'] = [str(s) for s in sources_list]
            
            # Source (for backward compatibility)
            project['source'] = row.get('source') or (sources_list[0] if sources_list else 'N/A')
            
            # CRITICAL: Include award_title, notice_title, and project_description for frontend
            # Note: The parquet file has 'award_title' not 'philgeps_award_title'
            # Frontend will concatenate these with contract_id to show more complete project information
            if 'award_title' in row.index and pd.notna(row['award_title']):
                award_title_val = str(row['award_title']).strip()
                if award_title_val and award_title_val != 'nan':
                    project['award_title'] = award_title_val
                    # Also set as philgeps_award_title for frontend compatibility
                    project['philgeps_award_title'] = award_title_val
            if 'notice_title' in row.index and pd.notna(row['notice_title']):
                notice_title_val = str(row['notice_title']).strip()
                if notice_title_val and notice_title_val != 'nan':
                    project['notice_title'] = notice_title_val
            if 'project_description' in row.index and pd.notna(row['project_description']):
                desc_val = str(row['project_description']).strip()
                if desc_val and desc_val != 'nan':
                    project['project_description'] = desc_val
            
            # Only add essential fields to reduce payload size
            essential_fields = ['contract_id', 'year', 'status', 'location', 'province', 'city']
            for col in essential_fields:
                if col in row.index and pd.notna(row[col]):
                    val = row[col]
                    if hasattr(val, 'item'):
                        project[col] = val.item()
                    else:
                        project[col] = val
        
            projects.append(project)
        
        return JSONResponse({
            "success": True,
            "projects": projects,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages
        })
        
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        print(f"❌ ERROR in /api/integrated/projects: {str(e)}")
        print(f"❌ ERROR TYPE: {type(e).__name__}")
        print(f"❌ FULL TRACEBACK:\n{error_traceback}")
        # Check if DuckDB is involved
        if 'duckdb' in str(e).lower() or 'BinderException' in str(type(e)):
            print(f"❌ ERROR IS DUCKDB-RELATED - This should NOT happen as we removed all DuckDB code!")
        return JSONResponse({
            "success": False,
            "error": f"Server error: {str(e)}",
            "error_type": type(e).__name__,
            "error_traceback": error_traceback if "duckdb" in str(e).lower() else None,  # Only include traceback for DuckDB errors
            "projects": [],
            "total": 0
        }, status_code=500)


@app.get("/integ2026")
async def integrated_dashboard():
    template_path = Path(__file__).parent / 'templates' / 'integrated_matrix.html'
    return FileResponse(template_path)


@app.get("/api/integ2026/dpwh-districts")
async def integ2026_dpwh_districts_api():
    """District rollup for DPWH Annex A-5 (2026), requires district cache."""
    try:
        import unicodedata

        def _fold_label(value: Any) -> str:
            text = str(value or "")
            text = unicodedata.normalize("NFKD", text)
            text = "".join(ch for ch in text if not unicodedata.combining(ch))
            return " ".join(text.split()).strip().upper()

        def _prefer_display(existing: str, candidate: str) -> str:
            if not existing:
                return candidate
            if not candidate:
                return existing
            existing_non_ascii = sum(1 for ch in existing if ord(ch) > 127)
            candidate_non_ascii = sum(1 for ch in candidate if ord(ch) > 127)
            return candidate if candidate_non_ascii > existing_non_ascii else existing

        cache_path = DATA_ROOT / "dpwh_annex_a5_district_cache.json"
        if not cache_path.exists():
            return JSONResponse({
                "success": False,
                "error": "District cache not found. Run: python scripts/generate_dpwh_annex_a5_district_cache.py",
                "cache_path": str(cache_path),
            }, status_code=404)

        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        by_id = cache.get("by_id") or {}

        json_path = DATA_ROOT / "budget_amendments_2026.json"
        if not json_path.exists():
            return JSONResponse({"success": False, "error": "2026 Data not found"}, status_code=404)

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        items = (payload.get("projects") or []) + (payload.get("line_items") or [])
        a5 = [it for it in items if (it.get("source_sheet") == "Annex A-5")]

        import re
        header_pattern = re.compile(
            r'^(?:[a-zA-Z0-9]+\.)?\s*(?:'
            r'National Capital Region|Region\s+[IVX]+|Cordillera Administrative Region|Bangsamoro Autonomous Region|'
            r'MIMAROPA|CALABARZON|SOCCSKSARGEN|Zamboanga Peninsula|Northern Mindanao|Davao Region|Caraga|'
            r'Eastern Visayas|Central Visayas|Western Visayas|Bicol Region|Central Luzon|Cagayan Valley|Ilocos Region|'
            r'Loan Proceeds|GOP'
            r')\s*$',
            re.IGNORECASE
        )

        def is_header_row(item: Dict[str, Any]) -> bool:
            title = (item.get("name") or item.get("description") or "").strip()
            if not title:
                return False
            loc = item.get("location") or {}
            if isinstance(loc, dict):
                if loc.get("province") is None and loc.get("municipality") is None and loc.get("barangay") is None:
                    if header_pattern.match(title):
                        return True
            return False

        def coerce_amount(v):
            try:
                return float(v)
            except Exception:
                return None

        rollup: Dict[str, Dict[str, Any]] = {}
        for it in a5:
            if is_header_row(it):
                continue
            pid = str(it.get("id"))
            meta = by_id.get(pid) or {}
            province = meta.get("province") or None
            municipality = meta.get("municipality") or None
            dist = meta.get("district") or "Unknown"
            congressman = meta.get("congressman") or None
            if province and dist and dist != "Unknown":
                label = f"{province} - {dist}"
            elif municipality and dist and dist != "Unknown":
                label = f"{municipality} - {dist}"
            else:
                label = dist if dist else "Unknown"

            label_key = _fold_label(label)
            bucket = rollup.setdefault(label_key, {
                "district": label,
                "congressman": None,
                "_congressman_counts": {},
                "project_count": 0,
                "total_amount": 0.0,
                "top_projects": [],
            })
            bucket["district"] = _prefer_display(bucket.get("district") or "", label)
            bucket["project_count"] += 1
            amt = coerce_amount(it.get("final_amount") or it.get("original_amount") or 0)
            if amt:
                bucket["total_amount"] += amt
            name = it.get("name") or it.get("description") or ""
            if name:
                bucket["top_projects"].append({"name": name, "amount": amt or 0.0, "id": pid})

            if congressman and congressman != "Unknown":
                counts = bucket.get("_congressman_counts") or {}
                counts[congressman] = counts.get(congressman, 0) + 1
                bucket["_congressman_counts"] = counts

        rows = list(rollup.values())
        for row in rows:
            row["top_projects"] = sorted(row["top_projects"], key=lambda p: p.get("amount", 0.0), reverse=True)[:3]
            counts = row.pop("_congressman_counts", {}) or {}
            if counts:
                row["congressman"] = max(counts.items(), key=lambda kv: kv[1])[0]
        rows.sort(key=lambda r: (r.get("total_amount") or 0.0, r.get("project_count") or 0), reverse=True)

        return JSONResponse({
            "success": True,
            "generated_at": cache.get("generated_at"),
            "total_districts": len(rows),
            "rows": rows,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)


@app.get("/api/integ2026/dpwh-district-projects")
async def integ2026_dpwh_district_projects_api(
    district: str = Query(..., description="District label from /api/integ2026/dpwh-districts"),
):
    """All DPWH Annex A-5 (2026) projects for a district label."""
    try:
        import unicodedata

        def _fold_label(value: Any) -> str:
            text = str(value or "")
            text = unicodedata.normalize("NFKD", text)
            text = "".join(ch for ch in text if not unicodedata.combining(ch))
            return " ".join(text.split()).strip().upper()

        cache_path = DATA_ROOT / "dpwh_annex_a5_district_cache.json"
        if not cache_path.exists():
            return JSONResponse({
                "success": False,
                "error": "District cache not found. Run: python scripts/generate_dpwh_annex_a5_district_cache.py",
                "cache_path": str(cache_path),
            }, status_code=404)

        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        by_id = cache.get("by_id") or {}

        json_path = DATA_ROOT / "budget_amendments_2026.json"
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        items = (payload.get("projects") or []) + (payload.get("line_items") or [])
        a5 = [it for it in items if (it.get("source_sheet") == "Annex A-5")]

        import re
        header_pattern = re.compile(
            r'^(?:[a-zA-Z0-9]+\.)?\s*(?:'
            r'National Capital Region|Region\s+[IVX]+|Cordillera Administrative Region|Bangsamoro Autonomous Region|'
            r'MIMAROPA|CALABARZON|SOCCSKSARGEN|Zamboanga Peninsula|Northern Mindanao|Davao Region|Caraga|'
            r'Eastern Visayas|Central Visayas|Western Visayas|Bicol Region|Central Luzon|Cagayan Valley|Ilocos Region|'
            r'Loan Proceeds|GOP'
            r')\s*$',
            re.IGNORECASE
        )

        def is_header_row(item: Dict[str, Any]) -> bool:
            title = (item.get("name") or item.get("description") or "").strip()
            if not title:
                return False
            loc = item.get("location") or {}
            if isinstance(loc, dict):
                if loc.get("province") is None and loc.get("municipality") is None and loc.get("barangay") is None:
                    if header_pattern.match(title):
                        return True
            return False

        # Pull flagged meta for tooltips
        flagged_meta_by_pid: Dict[str, Dict[str, Any]] = {}
        flagged_path = DATA_ROOT / "flagged_amount_projects_2026.json"
        if flagged_path.exists():
            flagged_list = json.loads(flagged_path.read_text(encoding="utf-8"))
            for item in flagged_list:
                if not isinstance(item, dict):
                    continue
                if str(item.get("source_sheet") or "").strip() != "Annex A-5":
                    continue
                if str(item.get("year") or "").strip() != "2026":
                    continue
                pid = item.get("id")
                if pid is None:
                    continue
                flagged_meta_by_pid[str(pid)] = item

        def coerce_amount(v):
            try:
                return float(v)
            except Exception:
                return None

        results: List[Dict[str, Any]] = []
        district_key = _fold_label(district)
        for it in a5:
            if is_header_row(it):
                continue
            pid = str(it.get("id"))
            meta = by_id.get(pid) or {}
            province = meta.get("province") or None
            municipality = meta.get("municipality") or None
            dist = meta.get("district") or "Unknown"
            if province and dist and dist != "Unknown":
                label = f"{province} - {dist}"
            elif municipality and dist and dist != "Unknown":
                label = f"{municipality} - {dist}"
            else:
                label = dist or "Unknown"
            if _fold_label(label) != district_key:
                continue

            name = it.get("name") or it.get("description") or ""
            amt = coerce_amount(it.get("final_amount") or it.get("original_amount") or 0) or 0.0
            flagged_meta = flagged_meta_by_pid.get(pid) or {}
            results.append({
                "name": name,
                "amount": amt,
                "flag_reason": flagged_meta.get("flag_reason"),
                "subcategory": flagged_meta.get("subcategory"),
            })

        results.sort(key=lambda r: r.get("amount", 0.0), reverse=True)
        return JSONResponse({
            "success": True,
            "district": district,
            "total": len(results),
            "projects": results,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/integrated/matrix")
async def get_integrated_matrix():
    path = DATA_ROOT / "integrated_matrix.json"
    if not path.exists():
        return {"error": "Matrix not generated yet", "metadata": {}, "ranking": []}
    
    return FileResponse(path, media_type="application/json")

@app.get("/api/integrated/matrix/strict")
async def get_integrated_matrix_strict():
    path = DATA_ROOT / "integrated_matrix_strict.json"
    if not path.exists():
        # Fallback to standard if strict not found
        return await get_integrated_matrix()
    
    return FileResponse(path, media_type="application/json")


@app.get("/api/integrated/locations")
async def get_integrated_locations():
    """Get hierarchical location data for validation"""
    parquet_path = DATA_ROOT / "unified_locations.parquet"
    if not parquet_path.exists():
        return {"error": "Unified locations DB not found"}

    import duckdb
    conn = duckdb.connect()
    
    # Read flat data
    rows = conn.execute(f"""
        SELECT 
            COALESCE(region, 'Unknown') as region,
            COALESCE(province, 'Unknown') as province,
            COALESCE(district, 'Lone District') as district,
            COALESCE(municipality, 'Unknown') as municipality,
            barangay
        FROM read_parquet('{parquet_path}')
        ORDER BY region, province, district, municipality, barangay
    """).fetchall()
    
    conn.close()
    
    # Build Tree
    tree = {}
    
    for row in rows:
        reg, prov, dist, muni, brgy = row
        
        if reg not in tree: tree[reg] = {}
        if prov not in tree[reg]: tree[reg][prov] = {}
        if dist not in tree[reg][prov]: tree[reg][prov][dist] = {}
        if muni not in tree[reg][prov][dist]: tree[reg][prov][dist][muni] = []
        
        if brgy:
            tree[reg][prov][dist][muni].append(brgy)
            
    return tree


@lru_cache(maxsize=1)
def _load_transparency_projects() -> Optional["pd.DataFrame"]:
    """
    Load and cache the Transparency projects parquet for fast keyword lookup.
    """
    try:
        import pandas as pd
    except ImportError:
        print("❌ pandas is required to search transparency projects.")
        return None

    parquet_path = Path(__file__).parent / "data" / "parquet" / "transparency_projects.parquet"
    if not parquet_path.exists():
        print(f"❌ Transparency parquet not found at {parquet_path}")
        return None

    try:
        text_cols = [
            "project_name",
            "description",
            "project_description",
            "project_title",
            "award_title",
            "notice_title",
        ]
        use_cols = [
            "contract_id",
            "contract_amount",
            "amount",
            "year",
            "contractor_name",
            "awardee_name",
        ] + text_cols

        df = pd.read_parquet(parquet_path, columns=use_cols)

        # Precompute lowercase combined text for quick substring searches
        df["combined_text"] = (
            df[text_cols]
            .fillna("")
            .astype(str)
            .agg(" ".join, axis=1)
            .str.lower()
        )
        return df
    except Exception as exc:
        print(f"❌ Failed to load transparency projects: {exc}")
        return None


@app.get("/api/transparency/search")
async def search_transparency_projects(
    q: str = Query(..., min_length=3, description="Keywords to search transparency projects"),
    limit: int = Query(5, ge=1, le=20),
):
    """
    Keyword search over local transparency_projects.parquet to surface contract IDs.
    Returns results with direct transparency URLs (Gallery tab reachable via ?project=ID).
    """
    df = _load_transparency_projects()
    if df is None:
        return JSONResponse(
            {"success": False, "error": "Transparency parquet not available on server."},
            status_code=500,
        )

    query = q.strip().lower()
    if not query:
        return JSONResponse({"success": False, "error": "Query cannot be empty."}, status_code=400)

    try:
        mask = df["combined_text"].str.contains(query, na=False)
        results_df = df.loc[mask].copy()

        # Rank by year desc then amount desc for stable ordering
        results_df = results_df.sort_values(
            by=["year", "contract_amount", "amount"], ascending=[False, False, False]
        ).head(limit)

        results = []
        for _, row in results_df.iterrows():
            contract_id = row.get("contract_id")
            if not isinstance(contract_id, str) or not contract_id.strip():
                continue
            transparency_url = f"https://transparency.dpwh.gov.ph/?project={contract_id}"
            results.append(
                {
                    "contract_id": contract_id,
                    "project_name": row.get("project_name") or row.get("description"),
                    "contract_amount": row.get("contract_amount") or row.get("amount"),
                    "year": row.get("year"),
                    "contractor": row.get("contractor_name") or row.get("awardee_name"),
                    "transparency_url": transparency_url,
                }
            )

        return {"success": True, "query": q, "count": len(results), "results": results}
    except Exception as exc:
        print(f"❌ Transparency search failed: {exc}")
        return JSONResponse(
            {"success": False, "error": f"Search failed: {exc}"},
            status_code=500,
        )


@app.get("/api/integrated/projects")
async def get_integrated_projects(
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    limit: int = Query(default=50, ge=1, le=1000, description="Number of projects per page"),
    project_name: Optional[str] = Query(default=None, description="Filter by project name/title"),
    contractor: Optional[str] = Query(default=None, description="Filter by contractor name")
) -> JSONResponse:
    """Get integrated projects from parquet file using DuckDB with filtering and pagination"""
    try:
        # Get the parquet file path (use absolute path)
        # CRITICAL: Use classified parquet (deduplicated) instead of integrated_projects.parquet
        base_dir = Path(__file__).parent.absolute()
        classified_file = base_dir / "data" / "parquet" / "integrated_projects_classified.parquet"
        integrated_file = base_dir / "data" / "parquet" / "integrated_projects.parquet"
        
        # Prefer classified (deduplicated) over integrated (all projects)
        if classified_file.exists():
            parquet_file = classified_file
            print(f"📊 Using classified parquet (deduplicated): {parquet_file.name}")
        elif integrated_file.exists():
            parquet_file = integrated_file
            print(f"⚠️  Using integrated parquet (not deduplicated): {parquet_file.name}")
        else:
            parquet_file = None
        
        if not parquet_file or not parquet_file.exists():
            return JSONResponse(
                content={
                    "success": False,
                    "error": f"Parquet file not found: {parquet_file}",
                    "projects": [],
                    "total": 0,
                    "total_pages": 0
                },
                status_code=404
            )
        
        # Connect to DuckDB
        conn = duckdb.connect()
        
        try:
            # Build WHERE clause with proper SQL escaping
            where_conditions = []
            
            def escape_sql_string(s: str) -> str:
                """Escape single quotes for SQL"""
                return s.replace("'", "''")
            
            if project_name:
                escaped_name = escape_sql_string(project_name)
                # Note: The parquet file has 'award_title' not 'philgeps_award_title'
                where_conditions.append(
                    f"(project_name ILIKE '%{escaped_name}%' OR "
                    f"award_title ILIKE '%{escaped_name}%' OR "
                    f"project_description ILIKE '%{escaped_name}%')"
                )
            
            if contractor:
                escaped_contractor = escape_sql_string(contractor)
                # Note: The parquet file has 'contractor' not 'contractor_name'
                # philgeps_awardee_name and organization_name don't exist in the parquet
                # Only search in contractor column
                where_conditions.append(
                    f"contractor ILIKE '%{escaped_contractor}%'"
                )
            
            where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
            
            # Calculate offset
            offset = (page - 1) * limit
            
            # Convert path to string and escape single quotes
            parquet_path_str = str(parquet_file).replace("'", "''")
            
            # Get total count
            count_query = f"""
                SELECT COUNT(*) as total
                FROM read_parquet('{parquet_path_str}')
                WHERE {where_clause}
            """
            
            count_result = conn.execute(count_query).fetchone()
            total = count_result[0] if count_result else 0
            total_pages = max(1, (total + limit - 1) // limit)
            
            # Get projects with pagination
            # Use SELECT * to get all columns, then filter/rename in Python
            # This avoids BinderException for columns that don't exist
            # Don't use ORDER BY in SQL - sort in Python after fetching to avoid column existence issues
            # For proper sorting, we need to fetch all matching rows, sort, then paginate
            # This is less efficient but avoids column existence errors
            # Get projects with pagination
            # Use SELECT * to get all columns, then filter/rename in Python
            # This avoids BinderException for columns that don't exist
            # Don't use ORDER BY in SQL - sort in Python after fetching to avoid column existence issues
            # For proper sorting, we need to fetch all matching rows, sort, then paginate
            # This is less efficient but avoids column existence errors
            select_query = f"""
                SELECT *
                FROM read_parquet('{parquet_path_str}')
                WHERE {where_clause}
            """
            
            # Execute query (fetch all matching rows, we'll sort and paginate in Python)
            results = conn.execute(select_query).fetchall()
            columns = [desc[0] for desc in conn.description]
            
            # Convert to list of dictionaries
            projects = []
            for row in results:
                project_dict = {}
                for i, col in enumerate(columns):
                    value = row[i]
                    # Convert timestamp and other types to string if needed
                    if value is not None:
                        if isinstance(value, datetime):
                            project_dict[col] = value.isoformat()
                        elif hasattr(value, 'isoformat'):  # Handle other datetime-like objects
                            project_dict[col] = value.isoformat()
                        elif isinstance(value, list):
                            # Handle list columns (like sources_list) - preserve as-is
                            project_dict[col] = value
                        elif col == 'sources_list':
                            # sources_list might come as a string or other format from DuckDB
                            # Try to parse it if it's a string representation of a list
                            try:
                                import ast
                                if isinstance(value, str):
                                    # Try to parse string representation of list
                                    parsed = ast.literal_eval(value)
                                    if isinstance(parsed, list):
                                        project_dict[col] = parsed
                                    else:
                                        project_dict[col] = [parsed] if parsed else []
                                else:
                                    project_dict[col] = [value] if value else []
                            except (ValueError, SyntaxError):
                                # If parsing fails, treat as single value
                                project_dict[col] = [value] if value else []
                        else:
                            project_dict[col] = value
                    else:
                        project_dict[col] = None
                
                # CRITICAL: Ensure sources_list is properly formatted as a list
                # This is essential for showing multiple DBs for each project
                if 'sources_list' in project_dict:
                    sources_list = project_dict['sources_list']
                    if not isinstance(sources_list, list):
                        # Convert to list if it's not already
                        if sources_list is not None and sources_list != '':
                            sources_list = [sources_list] if not isinstance(sources_list, list) else sources_list
                        else:
                            sources_list = []
                    project_dict['sources_list'] = sources_list
                else:
                    # If sources_list doesn't exist, try to create it from source field
                    if 'source' in project_dict and project_dict['source']:
                        project_dict['sources_list'] = [project_dict['source']]
                    else:
                        project_dict['sources_list'] = []
                
                # Source (for backward compatibility - use first source from sources_list)
                if 'source' not in project_dict or not project_dict['source']:
                    sources_list = project_dict.get('sources_list', [])
                    project_dict['source'] = sources_list[0] if sources_list else 'N/A'
                
                # Map award_title to philgeps_award_title for frontend compatibility
                if 'award_title' in project_dict and project_dict['award_title']:
                    project_dict['philgeps_award_title'] = project_dict['award_title']
                
                # Map contractor to contractor_name for frontend compatibility
                if 'contractor' in project_dict and project_dict['contractor']:
                    project_dict['contractor_name'] = project_dict['contractor']
                elif 'contractor_name' not in project_dict:
                    # Set empty if contractor column doesn't exist
                    project_dict['contractor_name'] = 'N/A'
                
                # Set philgeps_awardee_name and organization_name to N/A if not in parquet
                # These columns don't exist in the parquet file, so always set to N/A
                project_dict['philgeps_awardee_name'] = 'N/A'
                project_dict['organization_name'] = 'N/A'
                
                projects.append(project_dict)
            
            # Sort projects by amount (descending) then by project_name (ascending) in Python
            # This avoids SQL column existence issues
            def sort_key(proj):
                amount = proj.get('amount') or proj.get('dime_cost') or proj.get('infrawatch_contract_price') or 0
                try:
                    amount = float(amount) if amount else 0
                except (ValueError, TypeError):
                    amount = 0
                project_name = str(proj.get('project_name', '')).lower()
                return (-amount, project_name)  # Negative for descending amount
            
            projects.sort(key=sort_key)
            
            # Apply pagination after sorting
            paginated_projects = projects[offset:offset + limit]
            
            return JSONResponse(content={
                "success": True,
                "projects": paginated_projects,
                "total": total,
                "page": page,
                "limit": limit,
                "total_pages": total_pages
            })
            
        finally:
            conn.close()
            
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        return JSONResponse(
            content={
                "success": False,
                "error": error_msg,
                "projects": [],
                "total": 0,
                "total_pages": 0
            },
            status_code=500
        )
# End of get_integrated_projects

@app.get("/api/integrated/projects/csv")
async def export_integrated_projects_csv(
    project_name: Optional[str] = Query(default=None, description="Filter by project name/title"),
    contractor: Optional[str] = Query(default=None, description="Filter by contractor name"),
    green: bool = Query(default=False, description="Filter for green/clean projects"),
    dpwh_all: bool = Query(default=False, description="Filter for ALL Annex A-5 projects (w/ flags)")
) -> Response:
    """Export integrated projects to CSV with filtering (all pages)"""
    try:
        import csv
        import io
        
        # Get the parquet file path (use absolute path)
        base_dir = Path(__file__).parent.absolute()
        parquet_file = base_dir / "data" / "parquet" / "integrated_projects.parquet"
        
        # --- GREEN / DPWH ALL (ANNEX A-5 2026) CSV LOGIC ---
        if green or dpwh_all:
            import json
            import re
            
            # 1. Load 2026 Data (Annex A-5)
            json_path = base_dir / "static" / "data" / "budget_amendments_2026.json"
            if not json_path.exists():
                return JSONResponse({"error": "2026 Data not found"}, status_code=404)
            
            with open(json_path, 'r', encoding='utf-8') as f:
                data_2026 = json.load(f)
            
            # Combine projects and line_items, filter for Annex A-5
            raw_items = data_2026.get('projects', []) + data_2026.get('line_items', [])
            annex_a5_items = [
                item for item in raw_items 
                if item.get('source_sheet') == 'Annex A-5'
            ]
            
            def _coerce_amount(raw_amount: Any) -> Optional[float]:
                if raw_amount is None:
                    return None
                try:
                    return float(raw_amount)
                except (TypeError, ValueError):
                    return None

            # 2. Load Bad IDs (Resurrected & Flagged)
            resurrected_ids = set()
            flagged_ids = set()
            historical_amounts_by_pid: Dict[str, List[float]] = {}
            flagged_meta_by_pid: Dict[str, Dict[str, Any]] = {}
            
            # Resurrected
            res_path = base_dir / "static" / "data" / "resurrected_projects_dpwh.json"
            if res_path.exists():
                with open(res_path, 'r', encoding='utf-8') as f:
                    res_data = json.load(f)
                    for match in res_data.get('matches', []):
                        y2026 = match.get('year_2026') or {}
                        pid = y2026.get('id')
                        if pid:
                            pid_str = str(pid)
                            resurrected_ids.add(pid_str)
                            hist = match.get('historical')
                            if isinstance(hist, dict):
                                amt = _coerce_amount(hist.get('amount'))
                                if amt:
                                    historical_amounts_by_pid.setdefault(pid_str, []).append(amt)
                            elif isinstance(hist, list):
                                for entry in hist:
                                    if isinstance(entry, dict):
                                        amt = _coerce_amount(entry.get('amount'))
                                        if amt:
                                            historical_amounts_by_pid.setdefault(pid_str, []).append(amt)
                        
            # Flagged
            flagged_path = base_dir / "static" / "data" / "flagged_amount_projects_2026.json"
            if flagged_path.exists():
                try:
                    with open(flagged_path, 'r', encoding='utf-8') as f:
                        flagged_data = json.load(f)
                        for item in flagged_data:
                            # If list of dicts
                            if isinstance(item, dict):
                                pid = item.get('id')
                                if pid:
                                    pid_str = str(pid)
                                    flagged_ids.add(pid_str)
                                    flagged_meta_by_pid[pid_str] = item
                except json.JSONDecodeError:
                    pass

            # 3. Filter items
            filtered_items = []
            for item in annex_a5_items:
                pid = str(item.get('id', ''))
                
                is_res = pid in resurrected_ids
                is_flag = pid in flagged_ids
                
                # Logic:
                # If GREEN: Include ONLY if NOT resurrected AND NOT flagged
                # If DPWH_ALL: Include EVERYTHING (just mark columns appropriately)
                
                if green:
                    if not is_res and not is_flag:
                        filtered_items.append(item)
                else:
                    # dpwh_all = True
                    filtered_items.append(item)
            
            # 4. Generate CSV
            output = io.StringIO()
            writer = csv.writer(output)
            
            # CSV Headers
            headers = [
                'ID', 'Project Name', 'Amount', 'Location', 'Status', 
                'Resurrected?', 'Flagged?', 'Historical Amounts'
            ]
            writer.writerow(headers)
            
            for item in filtered_items:
                pid = str(item.get('id', ''))
                is_res = "Yes" if pid in resurrected_ids else "No"
                is_flag = "Yes" if pid in flagged_ids else "No"
                
                hist_amts = historical_amounts_by_pid.get(pid, [])
                hist_str = "; ".join([f"{a:,.2f}" for a in hist_amts])
                
                row = [
                    item.get('id', ''),
                    item.get('project_name', ''),
                    item.get('amount', ''),
                    item.get('location', ''),
                    item.get('status', ''),
                    is_res,
                    is_flag,
                    hist_str
                ]
                writer.writerow(row)
                
            output.seek(0)
            filename = f"projects_{'green' if green else 'all'}_annex_a5_2026.csv"
            return Response(
                content=output.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename={filename}"}
            )

        # --- STANDARD INTEGRATED PROJECTS CSV LOGIC (EXISTING) ---
        
        if not parquet_file.exists():
             return JSONResponse(
                content={"success": False, "error": f"Parquet file not found: {parquet_file}"},
                status_code=404
            )
            
        # Connect to DuckDB
        conn = duckdb.connect()
        try:
             # Build WHERE clause
            where_conditions = []
            def escape_sql_string(s: str) -> str:
                return s.replace("'", "''")

            if project_name:
                escaped_name = escape_sql_string(project_name)
                where_conditions.append(
                    f"(project_name ILIKE '%{escaped_name}%' OR "
                    f"award_title ILIKE '%{escaped_name}%' OR "
                    f"project_description ILIKE '%{escaped_name}%')"
                )
            
            if contractor:
                escaped_contractor = escape_sql_string(contractor)
                where_conditions.append(f"contractor ILIKE '%{escaped_contractor}%'")
            
            where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
            parquet_path_str = str(parquet_file).replace("'", "''")
            
            # Select all matching rows
            query = f"SELECT * FROM read_parquet('{parquet_path_str}') WHERE {where_clause}"
            results = conn.execute(query).fetchall()
            columns = [desc[0] for desc in conn.description]
            
            # Generate CSV
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(columns)
            writer.writerows(results)
            
            output.seek(0)
            return Response(
                content=output.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=integrated_projects.csv"}
            )
            
        finally:
            conn.close()
            
    except Exception as e:
        return JSONResponse(
            content={"success": False, "error": str(e)},
            status_code=500
        )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

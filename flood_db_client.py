import os
import json
import asyncpg
from typing import Any, Dict, List, Optional, Tuple

_POOL: Optional[asyncpg.pool.Pool] = None


async def _get_pool() -> asyncpg.pool.Pool:
    """Return a shared asyncpg connection pool for the flood database."""
    global _POOL
    if _POOL is None:
        _POOL = await asyncpg.create_pool(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
            user=os.getenv("POSTGRES_USER", "budget_admin"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            database=os.getenv("POSTGRES_DB_FLOOD", "flood"),
            min_size=1,
            max_size=int(os.getenv("FLOOD_DB_POOL_MAX", "5")),
        )
    return _POOL


def _coerce_contract_cost(raw_cost: Any) -> float:
    """Convert contract cost values (numeric or string) to float."""
    if raw_cost is None:
        return 0.0
    if isinstance(raw_cost, (int, float)):
        return float(raw_cost)
    if isinstance(raw_cost, str):
        cleaned = raw_cost.replace("₱", "").replace(",", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    return 0.0


def _normalise_row(row: asyncpg.Record) -> Dict[str, Any]:
    """Transform a database row into the JSON structure expected by the UI."""
    raw_data = row.get("raw_data")
    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except json.JSONDecodeError:
            raw_data = {}
    elif raw_data is None:
        raw_data = {}

    project_description = (
        raw_data.get("ProjectDescription")
        or raw_data.get("ProjectComponentDescription")
        or row.get("project_name")
    )

    contract_cost = _coerce_contract_cost(
        raw_data.get("ContractCost", row.get("contract_amount"))
    )

    red_flags = row.get("red_flags")
    green_flags = row.get("green_flags")
    if isinstance(red_flags, str):
        try:
            red_flags = json.loads(red_flags)
        except json.JSONDecodeError:
            red_flags = []
    elif isinstance(red_flags, list):
        red_flags = [
            dict(item) if hasattr(item, "items") else item
            for item in red_flags
        ]
    if isinstance(green_flags, str):
        try:
            green_flags = json.loads(green_flags)
        except json.JSONDecodeError:
            green_flags = []
    elif isinstance(green_flags, list):
        green_flags = [
            dict(item) if hasattr(item, "items") else item
            for item in green_flags
        ]
    flags = {
        "isGreenFlag": bool(row.get("is_green_flag")),
        "hasRedFlags": bool(row.get("has_red_flags")),
        "redFlags": red_flags or [],
        "greenFlags": green_flags or [],
    }

    return {
        "GlobalID": row.get("project_global_id"),
        "ProjectDescription": project_description,
        "ProjectComponentDescription": raw_data.get("ProjectComponentDescription"),
        "InfraYear": raw_data.get("InfraYear"),
        "Region": raw_data.get("Region"),
        "Province": raw_data.get("Province") or row.get("province"),
        "Municipality": raw_data.get("Municipality") or row.get("municipality"),
        "TypeofWork": raw_data.get("TypeofWork"),
        "Contractor": row.get("contractor"),
        "ContractCost": contract_cost,
        "DistrictEngineeringOffice": raw_data.get("DistrictEngineeringOffice"),
        "LegislativeDistrict": raw_data.get("LegislativeDistrict"),
        "ContractID": raw_data.get("ContractID"),
        "ProjectID": raw_data.get("ProjectID"),
        "FundingYear": raw_data.get("FundingYear"),
        "Latitude": raw_data.get("Latitude"),
        "Longitude": raw_data.get("Longitude"),
        "flags": flags,
    }


async def search_flood_projects(
    query: str = "",
    region: Optional[str] = None,
    province: Optional[str] = None,
    year: Optional[str] = None,
    type_of_work: Optional[str] = None,
    contractor: Optional[str] = None,
    district_office: Optional[str] = None,
    legislative_district: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Fetch flood control projects from PostgreSQL with optional filters.

    Returns a tuple of (projects, total_count).
    """
    pool = await _get_pool()
    clauses: List[str] = []
    params: List[Any] = []
    idx = 1

    def add_clause(condition: str, value: Any) -> None:
        nonlocal idx
        clauses.append(condition.format(idx=idx))
        params.append(value)
        idx += 1

    if query:
        like_term = f"%{query}%"
        add_clause(
            "(project_name ILIKE ${idx} OR raw_data->>'ProjectDescription' ILIKE ${idx} OR raw_data->>'ProjectComponentDescription' ILIKE ${idx})",
            like_term,
        )
    if region:
        add_clause("raw_data->>'Region' = ${idx}", region)
    if province:
        add_clause("(province = ${idx} OR raw_data->>'Province' = ${idx})", province)
    if year:
        add_clause("raw_data->>'InfraYear' = ${idx}", str(year))
    if type_of_work:
        add_clause("raw_data->>'TypeofWork' = ${idx}", type_of_work)
    if contractor:
        add_clause("contractor ILIKE ${idx}", f"%{contractor}%")
    if district_office:
        add_clause("raw_data->>'DistrictEngineeringOffice' = ${idx}", district_office)
    if legislative_district:
        add_clause("raw_data->>'LegislativeDistrict' = ${idx}", legislative_district)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    async with pool.acquire() as conn:
        total_sql = f"SELECT COUNT(*) FROM flagged_flood_projects {where_sql}"
        total_count = await conn.fetchval(total_sql, *params)

        select_sql = f"""
            WITH flag_summary AS (
                SELECT project_global_id,
                       COALESCE(jsonb_agg(jsonb_build_object('classification', classification, 'reason', reason))
                                FILTER (WHERE classification_type = 'red'), '[]'::jsonb) AS red_flags,
                       COALESCE(jsonb_agg(jsonb_build_object('classification', classification, 'reason', reason))
                                FILTER (WHERE classification_type = 'green'), '[]'::jsonb) AS green_flags
                FROM flood_project_flag_links
                GROUP BY project_global_id
            )
            SELECT
                p.project_global_id,
                p.project_name,
                p.contractor,
                p.contract_amount,
                p.province,
                p.municipality,
                p.raw_data,
                p.is_green_flag,
                p.has_red_flags,
                COALESCE(f.red_flags, '[]'::jsonb) AS red_flags,
                COALESCE(f.green_flags, '[]'::jsonb) AS green_flags
            FROM flagged_flood_projects p
            LEFT JOIN flag_summary f ON f.project_global_id = p.project_global_id
            {where_sql}
            ORDER BY p.contract_amount DESC NULLS LAST
        """

        params_with_pagination = params.copy()
        if limit is not None and limit > 0:
            select_sql += f" LIMIT ${idx}"
            params_with_pagination.append(limit)
            idx += 1
        if offset:
            select_sql += f" OFFSET ${idx}"
            params_with_pagination.append(offset)
            idx += 1

        rows = await conn.fetch(select_sql, *params_with_pagination)

    projects = [_normalise_row(row) for row in rows]
    return projects, total_count

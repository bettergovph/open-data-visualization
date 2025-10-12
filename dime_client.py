"""
DIME (Development Impact and Effectiveness) Projects PostgreSQL Client
Handles all DIME queries using PostgreSQL
"""

import os
import asyncpg
from typing import List, Dict, Any, Optional
import json
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': 'dime',
    'user': os.getenv('POSTGRES_USER', 'budget_admin'),
    'password': os.getenv('POSTGRES_PASSWORD', '')
}

async def get_db_connection():
    """Get PostgreSQL database connection"""
    try:
        conn = await asyncpg.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"💥 [DIME PostgreSQL] Error connecting to database: {e}")
        return None


async def get_dime_statistics():
    """Get DIME statistics from views"""
    conn = await get_db_connection()
    if not conn:
        return {"success": False, "error": "Database connection failed"}
    
    try:
        # Get basic stats
        basic_stats = await conn.fetchrow("SELECT * FROM dime_basic_stats")
        
        # Get status distribution
        status_rows = await conn.fetch("SELECT * FROM dime_status_distribution")
        status_distribution = {
            "labels": [row['status'] for row in status_rows],
            "data": [row['count'] for row in status_rows]
        }
        
        # Get budget by region
        region_rows = await conn.fetch("SELECT * FROM dime_budget_by_region")
        budget_by_region = {
            "labels": [row['region'] for row in region_rows],
            "data": [round(float(row['total_budget']) / 1e9, 2) for row in region_rows]
        }
        
        # Get top offices
        office_rows = await conn.fetch("SELECT * FROM dime_top_offices")
        top_offices = {
            "labels": [row['office'] for row in office_rows],
            "data": [row['project_count'] for row in office_rows]
        }
        
        # Get project types
        type_rows = await conn.fetch("SELECT * FROM dime_project_types")
        project_types = {
            "labels": [row['type'] for row in type_rows],
            "data": [row['count'] for row in type_rows]
        }
        
        # Get expensive projects
        expensive_rows = await conn.fetch("SELECT * FROM dime_expensive_projects")
        expensive_projects = {
            "labels": [row['name'][:50] + '...' if len(row['name']) > 50 else row['name'] 
                      for row in expensive_rows],
            "data": [round(float(row['cost']) / 1e9, 2) for row in expensive_rows]
        }
        
        # Get projects by year
        year_rows = await conn.fetch("SELECT * FROM dime_projects_by_year")
        projects_by_year = {
            "labels": [str(int(row['year'])) for row in year_rows],
            "data": [row['count'] for row in year_rows]
        }
        
        # Get source of funds
        funds_rows = await conn.fetch("SELECT * FROM dime_source_of_funds")
        source_of_funds = {
            "labels": [row['source'] for row in funds_rows],
            "data": [float(row['percentage']) for row in funds_rows]
        }
        
        # Get progress distribution
        progress_rows = await conn.fetch("SELECT * FROM dime_progress_distribution")
        progress_distribution = {
            "labels": [row['range'] for row in progress_rows],
            "data": [row['count'] for row in progress_rows]
        }
        
        return {
            "success": True,
            "statistics": {
                "total_projects": basic_stats['total_projects'],
                "total_budget": float(basic_stats['total_budget']),
                "avg_cost": float(basic_stats['avg_cost']),
                "active_projects": basic_stats['active_projects']
            },
            "status_distribution": status_distribution,
            "budget_by_region": budget_by_region,
            "top_offices": top_offices,
            "project_types": project_types,
            "expensive_projects": expensive_projects,
            "projects_by_year": projects_by_year,
            "source_of_funds": source_of_funds,
            "progress_distribution": progress_distribution
        }
        
    except Exception as e:
        print(f"❌ Error getting DIME statistics: {e}")
        return {"success": False, "error": str(e)}
    finally:
        await conn.close()


async def get_dime_filter_options():
    """Get unique values for filters"""
    conn = await get_db_connection()
    if not conn:
        return {"success": False, "error": "Database connection failed"}
    
    try:
        # Get unique statuses
        statuses = await conn.fetch("SELECT DISTINCT status FROM projects WHERE status IS NOT NULL ORDER BY status")
        
        # Get unique regions
        regions = await conn.fetch("SELECT DISTINCT region FROM projects WHERE region IS NOT NULL ORDER BY region")
        
        # Get unique provinces
        provinces = await conn.fetch("SELECT DISTINCT province FROM projects WHERE province IS NOT NULL ORDER BY province")
        
        # Get unique cities
        cities = await conn.fetch("SELECT DISTINCT city FROM projects WHERE city IS NOT NULL ORDER BY city")
        
        # Get unique barangays
        barangays = await conn.fetch("SELECT DISTINCT barangay FROM projects WHERE barangay IS NOT NULL AND barangay != '' ORDER BY barangay LIMIT 1000")
        
        return {
            "success": True,
            "statuses": [row['status'] for row in statuses],
            "regions": [row['region'] for row in regions],
            "provinces": [row['province'] for row in provinces],
            "cities": [row['city'] for row in cities],
            "barangays": [row['barangay'] for row in barangays]
        }
        
    except Exception as e:
        print(f"❌ Error getting filter options: {e}")
        return {"success": False, "error": str(e)}
    finally:
        await conn.close()


async def get_dime_barangay_aggregates():
    """Get barangay aggregates by total amount"""
    conn = await get_db_connection()
    if not conn:
        return {"success": False, "error": "Database connection failed"}
    
    try:
        rows = await conn.fetch("SELECT * FROM dime_barangay_aggregates")
        
        barangays = []
        for idx, row in enumerate(rows):
            barangays.append({
                "rank": idx + 1,
                "barangay": row['barangay'],
                "region": row['region'],
                "province": row['province'],
                "city": row['city'],
                "project_count": row['project_count'],
                "total_amount": float(row['total_amount']),
                "avg_amount": float(row['avg_amount']),
                "percentage_of_total": float(row['percentage_of_total']) if row['percentage_of_total'] else 0
            })
        
        return {
            "success": True,
            "barangays": barangays
        }
        
    except Exception as e:
        print(f"❌ Error getting barangay aggregates: {e}")
        return {"success": False, "error": str(e)}
    finally:
        await conn.close()


async def get_dime_barangay_aggregates_by_count():
    """Get barangay aggregates by project count"""
    conn = await get_db_connection()
    if not conn:
        return {"success": False, "error": "Database connection failed"}
    
    try:
        rows = await conn.fetch("SELECT * FROM dime_barangay_aggregates_by_count")
        
        barangays = []
        for idx, row in enumerate(rows):
            barangays.append({
                "rank": idx + 1,
                "barangay": row['barangay'],
                "region": row['region'],
                "province": row['province'],
                "city": row['city'],
                "project_count": row['project_count'],
                "total_amount": float(row['total_amount']),
                "avg_amount": float(row['avg_amount']),
                "percentage_of_total": float(row['percentage_of_total']) if row['percentage_of_total'] else 0
            })
        
        return {
            "success": True,
            "barangays": barangays
        }
        
    except Exception as e:
        print(f"❌ Error getting barangay aggregates by count: {e}")
        return {"success": False, "error": str(e)}
    finally:
        await conn.close()


async def get_dime_projects(
    page: int = 1,
    limit: int = 50,
    sort_by: str = "project_name",
    sort_order: str = "ASC",
    filters: Dict[str, Any] = None
):
    """Get DIME projects with pagination and filtering"""
    conn = await get_db_connection()
    if not conn:
        return {"success": False, "error": "Database connection failed"}
    
    try:
        filters = filters or {}
        offset = (page - 1) * limit
        
        # Build WHERE clause
        where_conditions = []
        params = []
        param_counter = 1
        
        if filters.get('status'):
            where_conditions.append(f"status = ${param_counter}")
            params.append(filters['status'])
            param_counter += 1
        
        if filters.get('region'):
            where_conditions.append(f"region = ${param_counter}")
            params.append(filters['region'])
            param_counter += 1
        
        if filters.get('province'):
            where_conditions.append(f"province = ${param_counter}")
            params.append(filters['province'])
            param_counter += 1
        
        if filters.get('city'):
            where_conditions.append(f"city = ${param_counter}")
            params.append(filters['city'])
            param_counter += 1
        
        if filters.get('barangay'):
            where_conditions.append(f"barangay = ${param_counter}")
            params.append(filters['barangay'])
            param_counter += 1
        
        if filters.get('search'):
            where_conditions.append(f"project_name ILIKE ${param_counter}")
            params.append(f"%{filters['search']}%")
            param_counter += 1
        
        where_clause = " AND ".join(where_conditions) if where_conditions else "TRUE"
        
        # Validate sort column
        valid_columns = ['project_name', 'cost', 'status', 'region', 'date_started']
        if sort_by not in valid_columns:
            sort_by = 'project_name'
        
        # Validate sort order
        sort_order = sort_order.upper() if sort_order.upper() in ['ASC', 'DESC'] else 'ASC'
        
        # Get total count
        count_query = f"SELECT COUNT(*) FROM projects WHERE {where_clause}"
        total_items = await conn.fetchval(count_query, *params)
        total_pages = max(1, (total_items + limit - 1) // limit)
        
        # Validate and fix sort column if needed
        if sort_by == 'implementing_office':
            sort_by = 'implementing_offices'
        
        # Get projects
        query = f"""
            SELECT 
                id, project_code, project_name, status, cost, region, province, city, barangay,
                date_started, contract_completion_date, implementing_offices, contractors
            FROM projects
            WHERE {where_clause}
            ORDER BY {sort_by} {sort_order}
            LIMIT ${param_counter} OFFSET ${param_counter + 1}
        """
        params.extend([limit, offset])
        
        rows = await conn.fetch(query, *params)
        
        projects = []
        for row in rows:
            projects.append({
                "id": row['id'],
                "project_code": row['project_code'],
                "project_name": row['project_name'],
                "status": row['status'],
                "cost": float(row['cost']) if row['cost'] else 0,
                "region": row['region'],
                "province": row['province'],
                "city": row['city'],
                "barangay": row['barangay'],
                "date_started": row['date_started'].isoformat() if row['date_started'] else None,
                "contract_completion_date": row['contract_completion_date'].isoformat() if row['contract_completion_date'] else None,
                "implementing_offices": row['implementing_offices'],
                "contractors": row['contractors']
            })
        
        return {
            "success": True,
            "projects": projects,
            "pagination": {
                "current_page": page,
                "total_pages": total_pages,
                "total_items": total_items,
                "limit": limit
            }
        }
        
    except Exception as e:
        print(f"❌ Error getting projects: {e}")
        return {"success": False, "error": str(e)}
    finally:
        await conn.close()


async def get_dime_suggestions(field: str, query: str, limit: int = 10):
    """Get autocomplete suggestions for a field"""
    conn = await get_db_connection()
    if not conn:
        return {"success": False, "error": "Database connection failed"}
    
    try:
        valid_fields = {
            'project_name': 'project_name',
            'barangay': 'barangay',
            'city': 'city',
            'province': 'province'
        }
        
        if field not in valid_fields:
            return {"success": False, "error": "Invalid field"}
        
        db_field = valid_fields[field]
        
        sql = f"""
            SELECT DISTINCT {db_field} as value
            FROM projects
            WHERE {db_field} ILIKE $1
            AND {db_field} IS NOT NULL
            ORDER BY {db_field}
            LIMIT $2
        """
        
        rows = await conn.fetch(sql, f"{query}%", limit)
        suggestions = [row['value'] for row in rows]
        
        return {
            "success": True,
            "suggestions": suggestions
        }
        
    except Exception as e:
        print(f"❌ Error getting suggestions: {e}")
        return {"success": False, "error": str(e)}
    finally:
        await conn.close()


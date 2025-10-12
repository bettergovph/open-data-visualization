import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
from dotenv import load_dotenv

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

app = FastAPI(title="BetterGovPH API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "BetterGovPH API", "status": "running"}

@app.get("/api/budget/files")
async def budget_list_files_api():
    """List uploaded Budget documents"""
    try:
        result = await get_budget_files()
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/total-items/count")
async def budget_total_items_count_api():
    """Get total items count - no authentication required"""
    try:
        result = await get_budget_total_items_count()
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/duplicates")
async def budget_duplicates_api(year: str = "2026", page: int = 1, limit: int = 10):
    """Get budget duplicates - no authentication required"""
    try:
        result = await get_budget_scored_duplicates(year, limit, (page - 1) * limit)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/duplicates/count")
async def budget_duplicates_count_api(year: str = "2026"):
    """Get budget duplicates count - no authentication required"""
    try:
        result = await get_budget_duplicates_count(year)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

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

# ============================================================================
# Flood Control API Endpoints (MeiliSearch)
# ============================================================================

@app.get("/api/flood/projects")
async def flood_projects_api(limit: int = 10, offset: int = 0, query: str = "", filters: str = None):
    """Get flood control projects from MeiliSearch - no authentication required"""
    try:
        from flood_client import FloodControlClient
        client = FloodControlClient()
        projects, metadata = await client.search_projects(query=query, filters=filters, limit=limit, offset=offset)
        return JSONResponse({
            "success": True,
            "projects": [proj.__dict__ for proj in projects],
            "metadata": metadata
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e), "projects": []})

# ============================================================================
# DIME Infrastructure API Endpoints
# ============================================================================

from dime_client import (
    get_dime_statistics,
    get_dime_filter_options,
    get_dime_barangay_aggregates,
    get_dime_barangay_aggregates_by_count,
    get_dime_projects,
    get_dime_suggestions
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

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

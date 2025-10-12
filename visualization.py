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

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

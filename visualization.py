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

@app.get("/api/budget/nep/year-over-year")
async def nep_year_over_year_api():
    """Get NEP year-over-year data - no authentication required"""
    try:
        from nep_client import get_nep_year_over_year
        result = await get_nep_year_over_year()
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/budget/nep/top-programs")
async def nep_top_programs_api(year: str = "2025", limit: int = 10):
    """Get top NEP programs - no authentication required"""
    try:
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

@app.get("/api/budget/analysis/comparison-chart")
async def budget_analysis_comparison_chart_api():
    """Get data for Budget vs NEP comparison chart - no authentication required"""
    try:
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

# ============================================================================
# Flood Control API Endpoints (MeiliSearch)
# ============================================================================

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
    limit: int = Query(default=20, ge=1, le=1000, description="Number of results"),
    offset: int = Query(default=0, ge=0, description="Number to skip")
):
    """Search flood control projects with optional filters - no authentication required"""
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
        
        # Build filter string for MeiliSearch
        filter_string = build_filter_string(filters) if filters else None
        
        # Search projects
        projects, metadata = await client.search_projects(
            query=q,
            filters=filter_string,
            limit=limit,
            offset=offset
        )
        
        # Convert projects to dictionaries
        project_dicts = [
            {
                "GlobalID": proj.GlobalID,
                "ProjectDescription": proj.ProjectDescription,
                "InfraYear": proj.InfraYear,
                "Region": proj.Region,
                "Province": proj.Province,
                "Municipality": proj.Municipality,
                "TypeofWork": proj.TypeofWork,
                "Contractor": proj.Contractor,
                "ContractCost": proj.ContractCost,
                "DistrictEngineeringOffice": proj.DistrictEngineeringOffice,
                "LegislativeDistrict": proj.LegislativeDistrict,
                "ContractID": proj.ContractID,
                "ProjectID": proj.ProjectID,
                "Latitude": proj.Latitude,
                "Longitude": proj.Longitude
            }
            for proj in projects
        ]
        
        return JSONResponse({
            "success": True,
            "projects": project_dicts,
            "totalHits": metadata.get("totalHits", 0),
            "processingTimeMs": metadata.get("processingTimeMs", 0),
            "query": metadata.get("query", ""),
            "facetsDistribution": metadata.get("facetsDistribution", {})
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
        
        return JSONResponse({
            "success": True,
            "totalProjects": stats.totalProjects,
            "totalCost": stats.totalCost,
            "uniqueContractors": stats.uniqueContractors,
            "regions": stats.regions,
            "years": stats.years,
            "typesOfWork": stats.typesOfWork,
            "topContractors": stats.topContractors
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

@app.get("/api/contractors/sec")
async def get_sec_contractors():
    """Get all SEC contractors from PostgreSQL - no authentication required"""
    try:
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
        
        return JSONResponse({
            "summary": {
                "total_contractors": stats['total_contractors'],
                "with_sec_data": stats['with_sec_data'],
                "without_sec_data": stats['without_sec_data'],
                "suspicious_no_results": stats['suspicious_no_results'],
                "last_updated": "database",
                "processing_batch": "database_generated",
                "source": "PostgreSQL sec.contractors table"
            },
            "contractors": contractors_list
        })
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})

@app.get("/api/contractors/top")
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
        
        # Get top contractors by project count
        contractors = await conn.fetch(
            """SELECT contractor_name, project_count, sec_number, status,
                      has_flood, has_dime, has_philgeps
               FROM contractors
               WHERE project_count IS NOT NULL AND project_count > 0
               ORDER BY project_count DESC
               LIMIT $1""",
            limit
        )
        
        await conn.close()
        
        contractors_list = []
        for c in contractors:
            contractors_list.append({
                'contractor': c['contractor_name'],
                'count': c['project_count'] or 0,
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

@app.get("/api/contractors/venn")
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

@app.get("/api/contractors/projects/{contractor_name}")
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
        internal_duplicates = (len(flood_projects) - flood_count_dedup) + (len(dime_projects) - dime_count_dedup) + (len(philgeps_projects) - philgeps_count_dedup)
        total_duplicates = internal_duplicates + cross_db_duplicates
        
        total_raw = flood_count + dime_count + philgeps_count
        simple_total = flood_total + dime_total + philgeps_total
        
        print(f"🔍 Cross-database deduplication:")
        print(f"  Internal duplicates: {internal_duplicates}")
        print(f"  Cross-DB duplicates: {cross_db_duplicates}")
        print(f"  Total duplicates: {total_duplicates}")
        print(f"  Unique projects: {unique_count}")
        print(f"  Unique total: ₱{unique_total:,.2f}")
        
        # BASIC CHECK: Ensure deduplicated total >= max single database
        max_single_db_total = max(flood_total_dedup, dime_total_dedup, philgeps_total_dedup)
        max_single_db_count = max(flood_count_dedup, dime_count_dedup, philgeps_count_dedup)
        
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
                }
            },
            "projects": {
                "flood": flood_projects_dedup,  # Return deduplicated lists
                "dime": dime_projects_dedup,
                "philgeps": philgeps_projects_dedup
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

@app.get("/api/flood/hidden-statistics")
async def hidden_flood_statistics_api():
    """Get comprehensive statistics for hidden flood projects - no authentication required"""
    try:
        import asyncpg
        
        # Connect to PhilGEPS database
        philgeps_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
        )
        
        # Get total flood projects from the flood API endpoint
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get('http://172.30.147.217:8001/api/flood/statistics') as response:
                    if response.status == 200:
                        flood_data = await response.json()
                        total_meilisearch_projects = flood_data.get('totalProjects', 0)
                    else:
                        total_meilisearch_projects = 0
        except Exception as e:
            print(f"Error getting flood statistics: {e}")
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
        
        if total_flood_projects > 0:
            omission_rate = (hidden_projects_count / total_flood_projects) * 100
        else:
            omission_rate = 0
        
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

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

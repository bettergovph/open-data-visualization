import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import asyncpg
from typing import List, Dict, Any, Optional

app = FastAPI(title="BetterGovPH API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection details from environment variables
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "budget_analysis")
POSTGRES_USER = os.getenv("POSTGRES_USER", "budget_admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "wuQ5gBYCKkZiOGb61chLcByMu")

async def get_db_connection():
    try:
        conn = await asyncpg.connect(
            host=POSTGRES_HOST,
            port=int(POSTGRES_PORT),
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            database=POSTGRES_DB
        )
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection error: {str(e)}")

@app.get("/")
async def root():
    return {"message": "BetterGovPH API", "status": "running"}

@app.get("/api/budget/files")
async def get_budget_files():
    conn = await get_db_connection()
    try:
        # Get distinct years from budget data
        years = await conn.fetch("""
            SELECT DISTINCT year FROM budget_data
            ORDER BY year DESC
        """)
        files = [{"year": row["year"], "name": f"{row['year']} Budget Data"} for row in years]
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching budget files: {str(e)}")
    finally:
        await conn.close()

@app.get("/api/budget/total-items/count")
async def get_total_items_count():
    conn = await get_db_connection()
    try:
        count = await conn.fetchval("SELECT COUNT(*) FROM budget_data")
        return {"count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching total count: {str(e)}")
    finally:
        await conn.close()

@app.get("/api/budget/duplicates")
async def get_budget_duplicates(year: int = 2026, page: int = 1, limit: int = 10):
    conn = await get_db_connection()
    try:
        offset = (page - 1) * limit
        duplicates = await conn.fetch("""
            SELECT * FROM budget_duplicates_view
            WHERE year = $1
            ORDER BY amount DESC
            LIMIT $2 OFFSET $3
        """, year, limit, offset)

        total = await conn.fetchval("""
            SELECT COUNT(*) FROM budget_duplicates_view WHERE year = $1
        """, year)

        return {
            "duplicates": [dict(row) for row in duplicates],
            "total": total,
            "page": page,
            "limit": limit
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching duplicates: {str(e)}")
    finally:
        await conn.close()

@app.get("/api/budget/nep/columns")
async def get_nep_columns(year: int = 2024):
    conn = await get_db_connection()
    try:
        # Get column names from nep_data table
        columns = await conn.fetch("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'nep_data' AND table_schema = 'public'
            ORDER BY ordinal_position
        """)
        column_names = [row["column_name"] for row in columns]
        return {"columns": column_names}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching NEP columns: {str(e)}")
    finally:
        await conn.close()

@app.get("/api/budget/duplicates/count")
async def get_duplicates_count(year: int = 2026):
    conn = await get_db_connection()
    try:
        count = await conn.fetchval("""
            SELECT COUNT(*) FROM budget_duplicates_view WHERE year = $1
        """, year)
        return {"count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching duplicates count: {str(e)}")
    finally:
        await conn.close()

@app.get("/api/budget/nep/anomalies/count")
async def get_nep_anomalies_count(year: int = 2026):
    conn = await get_db_connection()
    try:
        count = await conn.fetchval("""
            SELECT COUNT(*) FROM nep_anomalies_view WHERE year = $1
        """, year)
        return {"count": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching NEP anomalies count: {str(e)}")
    finally:
        await conn.close()

@app.get("/api/budget/nep/data-browser")
async def get_nep_data_browser(year: int = 2025, page: int = 1, limit: int = 1):
    conn = await get_db_connection()
    try:
        offset = (page - 1) * limit
        data = await conn.fetch("""
            SELECT * FROM nep_data
            WHERE year = $1
            ORDER BY id
            LIMIT $2 OFFSET $3
        """, year, limit, offset)

        total = await conn.fetchval("SELECT COUNT(*) FROM nep_data WHERE year = $1", year)

        return {
            "data": [dict(row) for row in data],
            "total": total,
            "page": page,
            "limit": limit
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching NEP data browser: {str(e)}")
    finally:
        await conn.close()

@app.get("/api/budget/nep/overview/stats")
async def get_nep_overview_stats(year: int = 2026):
    conn = await get_db_connection()
    try:
        stats = await conn.fetchrow("""
            SELECT
                COUNT(DISTINCT department) as departments,
                COUNT(DISTINCT agency) as agencies,
                SUM(amount) as total_budget
            FROM nep_data
            WHERE year = $1
        """, year)

        return {"stats": dict(stats) if stats else {"departments": 0, "agencies": 0, "total_budget": 0}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching NEP overview stats: {str(e)}")
    finally:
        await conn.close()

@app.get("/api/budget/nep/departments")
async def get_nep_departments(year: int = 2026, limit: int = 8):
    conn = await get_db_connection()
    try:
        departments = await conn.fetch("""
            SELECT department, SUM(amount) as total_amount, COUNT(*) as project_count
            FROM nep_data
            WHERE year = $1 AND department IS NOT NULL
            GROUP BY department
            ORDER BY total_amount DESC
            LIMIT $2
        """, year, limit)

        return {"departments": [dict(row) for row in departments], "limit": limit}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching NEP departments: {str(e)}")
    finally:
        await conn.close()

@app.get("/api/budget/nep/expense-categories")
async def get_nep_expense_categories(year: int = 2026, limit: int = 8):
    conn = await get_db_connection()
    try:
        categories = await conn.fetch("""
            SELECT expense_category, SUM(amount) as total_amount, COUNT(*) as project_count
            FROM nep_data
            WHERE year = $1 AND expense_category IS NOT NULL
            GROUP BY expense_category
            ORDER BY total_amount DESC
            LIMIT $2
        """, year, limit)

        return {"categories": [dict(row) for row in categories], "limit": limit}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching NEP expense categories: {str(e)}")
    finally:
        await conn.close()

@app.get("/api/budget/nep/regions")
async def get_nep_regions(year: int = 2026, limit: int = 8):
    conn = await get_db_connection()
    try:
        regions = await conn.fetch("""
            SELECT region, SUM(amount) as total_amount, COUNT(*) as project_count
            FROM nep_data
            WHERE year = $1 AND region IS NOT NULL
            GROUP BY region
            ORDER BY total_amount DESC
            LIMIT $2
        """, year, limit)

        return {"regions": [dict(row) for row in regions], "limit": limit}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching NEP regions: {str(e)}")
    finally:
        await conn.close()

@app.get("/api/budget/nep/agencies")
async def get_nep_agencies(year: int = 2026, limit: int = 10):
    conn = await get_db_connection()
    try:
        agencies = await conn.fetch("""
            SELECT agency, SUM(amount) as total_amount, COUNT(*) as project_count
            FROM nep_data
            WHERE year = $1 AND agency IS NOT NULL
            GROUP BY agency
            ORDER BY total_amount DESC
            LIMIT $2
        """, year, limit)

        return {"agencies": [dict(row) for row in agencies], "limit": limit}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching NEP agencies: {str(e)}")
    finally:
        await conn.close()

@app.get("/api/budget/columns")
async def get_budget_columns(year: int = 2024):
    conn = await get_db_connection()
    try:
        # Get column names from budget_data table
        columns = await conn.fetch("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'budget_data' AND table_schema = 'public'
            ORDER BY ordinal_position
        """)
        column_names = [row["column_name"] for row in columns]
        return {"columns": column_names}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching budget columns: {str(e)}")
    finally:
        await conn.close()

@app.get("/api/budget/overview/stats")
async def get_budget_overview_stats():
    conn = await get_db_connection()
    try:
        stats = await conn.fetchrow("""
            SELECT
                COUNT(DISTINCT year) as years,
                COUNT(*) as total_records,
                SUM(amount) as total_budget,
                COUNT(DISTINCT department) as departments
            FROM budget_data
        """)

        return {"stats": dict(stats) if stats else {
            "years": 0, "total_records": 0, "total_budget": 0, "departments": 0
        }}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching budget overview stats: {str(e)}")
    finally:
        await conn.close()

@app.get("/api/budget/departments")
async def get_budget_departments(year: int = 2025, limit: int = 8):
    conn = await get_db_connection()
    try:
        departments = await conn.fetch("""
            SELECT department, SUM(amount) as total_amount, COUNT(*) as project_count
            FROM budget_data
            WHERE year = $1 AND department IS NOT NULL
            GROUP BY department
            ORDER BY total_amount DESC
            LIMIT $2
        """, year, limit)

        return {"departments": [dict(row) for row in departments], "limit": limit}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching budget departments: {str(e)}")
    finally:
        await conn.close()

@app.get("/api/budget/expense-categories")
async def get_budget_expense_categories(year: int = 2025, limit: int = 8):
    conn = await get_db_connection()
    try:
        categories = await conn.fetch("""
            SELECT expense_category, SUM(amount) as total_amount, COUNT(*) as project_count
            FROM budget_data
            WHERE year = $1 AND expense_category IS NOT NULL
            GROUP BY expense_category
            ORDER BY total_amount DESC
            LIMIT $2
        """, year, limit)

        return {"categories": [dict(row) for row in categories], "limit": limit}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching budget expense categories: {str(e)}")
    finally:
        await conn.close()

@app.get("/api/budget/regions")
async def get_budget_regions(year: int = 2025, limit: int = 8):
    conn = await get_db_connection()
    try:
        regions = await conn.fetch("""
            SELECT region, SUM(amount) as total_amount, COUNT(*) as project_count
            FROM budget_data
            WHERE year = $1 AND region IS NOT NULL
            GROUP BY region
            ORDER BY total_amount DESC
            LIMIT $2
        """, year, limit)

        return {"regions": [dict(row) for row in regions], "limit": limit}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching budget regions: {str(e)}")
    finally:
        await conn.close()

@app.get("/api/budget/agencies")
async def get_budget_agencies(year: int = 2025, limit: int = 10):
    conn = await get_db_connection()
    try:
        agencies = await conn.fetch("""
            SELECT agency, SUM(amount) as total_amount, COUNT(*) as project_count
            FROM budget_data
            WHERE year = $1 AND agency IS NOT NULL
            GROUP BY agency
            ORDER BY total_amount DESC
            LIMIT $2
        """, year, limit)

        return {"agencies": [dict(row) for row in agencies], "limit": limit}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching budget agencies: {str(e)}")
    finally:
        await conn.close()

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)

#!/usr/bin/env python3
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

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
async def get_budget_files():
    return {"files": [{"year": 2024, "name": "2024 Budget Data"}]}

@app.get("/api/budget/total-items/count")
async def get_total_items_count():
    return {"count": 1000}

@app.get("/api/budget/duplicates")
async def get_budget_duplicates(year: int = 2026, page: int = 1, limit: int = 10):
    return {"duplicates": [], "total": 0, "page": page, "limit": limit}

@app.get("/api/budget/nep/columns")
async def get_nep_columns(year: int = 2024):
    return {"columns": ["id", "year", "department", "amount"]}

@app.get("/api/budget/duplicates/count")
async def get_duplicates_count(year: int = 2026):
    return {"count": 0}

@app.get("/api/budget/nep/anomalies/count")
async def get_nep_anomalies_count(year: int = 2026):
    return {"count": 0}

@app.get("/api/budget/nep/data-browser")
async def get_nep_data_browser(year: int = 2025, page: int = 1, limit: int = 1):
    return {"data": [], "total": 0, "page": page, "limit": limit}

@app.get("/api/budget/nep/overview/stats")
async def get_nep_overview_stats(year: int = 2026):
    return {"stats": {"total_budget": 0, "departments": 0, "agencies": 0}}

@app.get("/api/budget/nep/departments")
async def get_nep_departments(year: int = 2026, limit: int = 8):
    return {"departments": [], "limit": limit}

@app.get("/api/budget/nep/expense-categories")
async def get_nep_expense_categories(year: int = 2026, limit: int = 8):
    return {"categories": [], "limit": limit}

@app.get("/api/budget/nep/regions")
async def get_nep_regions(year: int = 2026, limit: int = 8):
    return {"regions": [], "limit": limit}

@app.get("/api/budget/nep/agencies")
async def get_nep_agencies(year: int = 2026, limit: int = 10):
    return {"agencies": [], "limit": limit}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)

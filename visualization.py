#!/usr/bin/env python3
import uvicorn
from fastapi import FastAPI
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
    return {"message": "BetterGovPH API"}

@app.get("/api/budget/files")
async def get_budget_files():
    return {"files": [{"year": 2024, "name": "2024 Budget Data"}]}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)


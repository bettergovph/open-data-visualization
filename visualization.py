#!/usr/bin/env python3
import os
import asyncpg
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
import json

app = FastAPI(title=BetterGovPH API, version=1.0.0)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[*],
    allow_methods=[*],
    allow_headers=[*],
)

# Database connection pool
pool = None

async def get_db_pool():
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            database=os.getenv('POSTGRES_DB', 'budget_analysis'),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            min_size=1,
            max_size=10,
        )
    return pool

@app.on_event(startup)
async def startup_event():
    Initialize database connection on startup
    try:
        await get_db_pool()
        print(✅ Connected to PostgreSQL database)
    except Exception as e:
        print(f❌ Failed to connect to database: {e})

@app.on_event(shutdown)
async def shutdown_event():
    Close database connection on shutdown
    global pool
    if pool:
        await pool.close()
        print(✅ Database connection closed)

@app.get(/)
async def root():
    return {message: BetterGovPH API, status: running}

@app.get(/api/budget/files)
async def get_budget_files():
    Get available budget data files/years
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # Get all budget tables
            result = await conn.fetch(

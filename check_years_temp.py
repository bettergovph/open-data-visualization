import asyncio
import asyncpg
import os

async def show_years():
    try:
        conn = await asyncpg.connect(
            host='localhost', 
            user='budget_admin', 
            database='dynasty', 
            password=os.getenv('POSTGRES_PASSWORD', 'wuQ5gBYCKkZiOGb61chLcByMu')
        )
        rows = await conn.fetch("SELECT DISTINCT year FROM political_dynasties ORDER BY year DESC")
        print([r[0] for r in rows])
        await conn.close()
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(show_years())

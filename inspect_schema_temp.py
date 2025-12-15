import asyncio
import asyncpg
import os

async def show_schema():
    try:
        conn = await asyncpg.connect(
            host='localhost', 
            user='budget_admin', 
            database='dynasty', 
            password=os.getenv('POSTGRES_PASSWORD', 'wuQ5gBYCKkZiOGb61chLcByMu')
        )
        rows = await conn.fetch("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'political_dynasties'")
        print('\n'.join([f'{r[0]}: {r[1]}' for r in rows]))
        await conn.close()
    except Exception as e:
        print(e)
asyncio.run(show_schema())

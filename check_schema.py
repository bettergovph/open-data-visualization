#!/usr/bin/env python3
import asyncio
import asyncpg

async def check_schema():
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu',
        database='dynasty'
    )
    
    try:
        # Get table schema
        result = await conn.fetch("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'political_dynasties'
        ORDER BY ordinal_position
        """)
        
        print("Political dynasties table columns:")
        for row in result:
            print(f"  {row['column_name']}: {row['data_type']}")
            
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_schema())

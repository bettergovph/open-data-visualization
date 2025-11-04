#!/usr/bin/env python3
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def verify():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD'),
        database='dynasty'
    )
    
    # Check contractor_dynasty_matches
    result = await conn.fetch('''
        SELECT company_name, person_name, role, dynasty_first_name, dynasty_last_name
        FROM contractor_dynasty_matches
        WHERE UPPER(company_name) LIKE '%CLTG%' OR UPPER(company_name) LIKE '%ALFREGO%'
        ORDER BY company_name, role
    ''')
    
    print('Contractor entries:')
    for r in result:
        print(f'  {r["company_name"]}: {r["person_name"]} ({r["role"]})')
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(verify())


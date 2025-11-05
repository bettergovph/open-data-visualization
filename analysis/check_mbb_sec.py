#!/usr/bin/env python3
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def check_mbb():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD'),
        database='sec'
    )
    
    # Check for MBB in contractors table
    mbb = await conn.fetch('''
        SELECT id, contractor_name, sec_number, date_registered, status, address
        FROM contractors
        WHERE UPPER(contractor_name) LIKE '%MBB%'
        ORDER BY contractor_name
    ''')
    
    print(f'Found {len(mbb)} MBB entries in sec.contractors:')
    for m in mbb:
        print(f'  ID: {m["id"]}, Name: {m["contractor_name"]}')
        print(f'    SEC Number: {m["sec_number"]}, Status: {m["status"]}')
        print(f'    Date Registered: {m["date_registered"]}')
        if m["address"]:
            print(f'    Address: {m["address"][:100]}')
        print()
    
    # Also check for variations
    mbb_variations = await conn.fetch('''
        SELECT id, contractor_name, sec_number
        FROM contractors
        WHERE UPPER(contractor_name) LIKE '%GLOBAL PROPERTIES%'
           OR UPPER(contractor_name) LIKE '%MBB GLOBAL%'
        ORDER BY contractor_name
    ''')
    
    if mbb_variations:
        print(f'\nFound {len(mbb_variations)} entries with "GLOBAL PROPERTIES" or "MBB GLOBAL":')
        for m in mbb_variations:
            print(f'  ID: {m["id"]}, Name: {m["contractor_name"]}, SEC: {m["sec_number"]}')
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(check_mbb())


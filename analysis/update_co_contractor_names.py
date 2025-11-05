#!/usr/bin/env python3
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def update_contractor_names():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD'),
        database='dynasty'
    )
    
    # Update contractor matches for Zaldy Co to Elizaldy S. Co
    updated = await conn.execute('''
        UPDATE contractor_dynasty_matches
        SET dynasty_first_name = 'ELIZALDY',
            dynasty_last_name = 'CO',
            dynasty_full_name = 'ELIZALDY S. CO',
            person_name = 'ELIZALDY S. CO'
        WHERE dynasty_last_name = 'CO'
          AND (dynasty_first_name LIKE '%ZALDY%' OR dynasty_first_name LIKE '%ELIZALDY%')
    ''')
    
    print(f'Updated {updated} contractor matches for Zaldy/Elizaldy Co')
    
    # Verify
    matches = await conn.fetch('''
        SELECT company_name, person_name, dynasty_full_name
        FROM contractor_dynasty_matches
        WHERE dynasty_last_name = 'CO'
          AND (dynasty_first_name LIKE '%ZALDY%' OR dynasty_first_name LIKE '%ELIZALDY%')
    ''')
    
    print('\nUpdated contractor matches:')
    for m in matches:
        print(f'  {m["company_name"]}: {m["person_name"]} (dynasty: {m["dynasty_full_name"]})')
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(update_contractor_names())


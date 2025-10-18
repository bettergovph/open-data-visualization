#!/usr/bin/env python3
"""Delete all contractors with split indicators (/, FORMERLY, FOR, parentheses)"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
import re

load_dotenv('.env')

async def main():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
    )
    
    contractors = await conn.fetch('''
        SELECT id, contractor_name, sec_number 
        FROM contractors 
        WHERE sec_number IS NULL OR sec_number = ''
    ''')
    
    deleted = 0
    for row in contractors:
        name = row['contractor_name']
        has_indicator = (
            '/' in name or 
            '(' in name or 
            ')' in name or
            re.search(r'\b(FORMERLY|FORMER|FOR|PREVIOUSLY|PREV)\b', name, re.IGNORECASE)
        )
        
        if has_indicator:
            await conn.execute('UPDATE contractors SET former_id = NULL WHERE former_id = $1', row['id'])
            await conn.execute('DELETE FROM contractors WHERE id = $1', row['id'])
            deleted += 1
    
    print(f'🗑️ Deleted {deleted} contractors with split indicators')
    total = await conn.fetchval('SELECT COUNT(*) FROM contractors')
    print(f'📊 Remaining: {total}')
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())


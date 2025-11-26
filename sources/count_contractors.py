#!/usr/bin/env python3
"""
Count total contractors in the database
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()


async def count_contractors():
    """Count contractors in the database"""
    print("📊 Counting contractors in database...")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_SEC', 'sec')
    )
    
    try:
        # Get total count
        total = await conn.fetchval("""
            SELECT COUNT(*) 
            FROM contractors
            WHERE contractor_name IS NOT NULL
            AND contractor_name != ''
        """)
        
        # Get count with SEC numbers
        with_sec = await conn.fetchval("""
            SELECT COUNT(*) 
            FROM contractors
            WHERE contractor_name IS NOT NULL
            AND contractor_name != ''
            AND sec_number IS NOT NULL
            AND sec_number != ''
        """)
        
        # Get unique contractor names
        unique = await conn.fetchval("""
            SELECT COUNT(DISTINCT contractor_name)
            FROM contractors
            WHERE contractor_name IS NOT NULL
            AND contractor_name != ''
        """)
        
        print(f"\n📊 Contractor Statistics:")
        print(f"  Total contractors: {total:,}")
        print(f"  With SEC numbers: {with_sec:,}")
        print(f"  Unique contractor names: {unique:,}")
        
        return {
            'total': total,
            'with_sec': with_sec,
            'unique': unique
        }
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(count_contractors())










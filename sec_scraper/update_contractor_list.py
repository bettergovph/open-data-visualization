#!/usr/bin/env python3
"""
Simple script to update contractor_list_top2000_unprocessed.txt with fresh data from database
"""

import asyncio
import asyncpg
import os

async def update_contractor_list():
    """Update the contractor list with fresh data from database"""
    
    try:
        # Connect to database
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', 'wuQ5gBYCKkZiOGb61chLcByMu'),
            database=os.getenv('POSTGRES_DB_DIME', 'dime')
        )
        
        # Get unique contractors from projects table
        query = """
            SELECT DISTINCT unnest(contractors) as contractor_name
            FROM projects 
            WHERE contractors IS NOT NULL 
              AND array_length(contractors, 1) > 0
            ORDER BY contractor_name
            LIMIT 2000
        """
        
        contractors = await conn.fetch(query)
        await conn.close()
        
        # Write to file
        with open('contractor_list_top2000_unprocessed.txt', 'w', encoding='utf-8') as f:
            for contractor in contractors:
                contractor_name = contractor['contractor_name'].strip()
                if contractor_name and len(contractor_name) > 2:
                    f.write(f"{contractor_name}\n")
        
        print(f"✅ Updated contractor list with {len(contractors)} contractors")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(update_contractor_list())

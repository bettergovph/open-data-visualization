#!/usr/bin/env python3
"""
Clean up contractor names in the database:
- Remove double quotes
- Remove JSON fragments
- Fix malformed names
"""

import asyncio
import asyncpg
import os
import re
from dotenv import load_dotenv

load_dotenv()

async def clean_contractor_names():
    """Clean up malformed contractor names in the database"""
    print("🧹 Starting contractor name cleanup...")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
    )
    
    try:
        # Get all contractors with problematic names
        contractors = await conn.fetch(
            """
            SELECT id, contractor_name 
            FROM contractors 
            WHERE contractor_name LIKE '%"%' 
               OR contractor_name LIKE '%{%'
               OR contractor_name LIKE '%}%'
               OR contractor_name LIKE '%nameAbbreviation%'
               OR contractor_name LIKE '%logoUrl%'
            ORDER BY id
            """
        )
        
        print(f"📊 Found {len(contractors)} contractors with malformed names")
        
        cleaned = 0
        deleted = 0
        
        for contractor in contractors:
            contractor_id = contractor['id']
            name = contractor['contractor_name']
            original_name = name
            
            # Only remove leading and trailing double quotes
            if name.startswith('"') and name.endswith('"'):
                clean_name = name.strip('"')
                
                # Update the name
                await conn.execute(
                    "UPDATE contractors SET contractor_name = $1 WHERE id = $2",
                    clean_name,
                    contractor_id
                )
                cleaned += 1
                print(f"   ✅ Cleaned ID {contractor_id}: '{original_name}' -> '{clean_name}'")
        
        print(f"\n✅ Cleanup complete:")
        print(f"   • Cleaned: {cleaned}")
        print(f"   • Deleted: {deleted}")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(clean_contractor_names())


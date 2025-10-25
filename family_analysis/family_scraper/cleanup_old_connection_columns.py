#!/usr/bin/env python3
"""
Remove old connection columns from political_dynasties table
since we're now using the normalized relationships table
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def cleanup_old_connection_columns():
    """Remove old connection columns from political_dynasties table"""
    
    # Database connection
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DYNASTY_SEC', 'dynasty')
    )
    
    try:
        print("🧹 Cleaning up old connection columns...")
        
        # Check if columns exist before dropping
        columns_to_drop = ['connection_id', 'connection_type', 'connection']
        
        for column in columns_to_drop:
            try:
                await conn.execute(f"ALTER TABLE political_dynasties DROP COLUMN IF EXISTS {column}")
                print(f"✅ Dropped column: {column}")
            except Exception as e:
                print(f"⚠️  Column {column} may not exist or already dropped: {e}")
        
        print("✅ Old connection columns cleanup completed!")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(cleanup_old_connection_columns())

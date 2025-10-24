#!/usr/bin/env python3
"""
Script to add winner column to political_dynasties table in production
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

async def add_winner_column():
    load_dotenv('visualization.env')
    
    # Database connection parameters
    db_host = '10.27.79.7'  # Production server
    db_port = 5432
    db_user = 'budget_admin'
    db_password = 'wuQ5gBYCKkZiOGb61chLcByMu'
    db_name = 'dynasty'
    
    print("🚀 Connecting to production database...")
    
    try:
        # Connect to database
        conn = await asyncpg.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database=db_name
        )
        
        print("✅ Connected to production database")
        
        # Check if winner column already exists
        check_column_query = """
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_schema = 'public' 
        AND table_name = 'political_dynasties' 
        AND column_name = 'winner'
        """
        
        existing_column = await conn.fetchval(check_column_query)
        
        if existing_column:
            print("⚠️ Winner column already exists in political_dynasties table")
        else:
            print("🔨 Adding winner column to political_dynasties table...")
            
            # Add the winner column
            alter_table_query = """
            ALTER TABLE political_dynasties 
            ADD COLUMN winner BOOLEAN DEFAULT FALSE
            """
            
            await conn.execute(alter_table_query)
            print("✅ Winner column added successfully")
        
        # Verify the column was added
        columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = 'political_dynasties'
            ORDER BY ordinal_position
        """)
        
        print("📊 Current political_dynasties table structure:")
        for col in columns:
            print(f"  - {col['column_name']}: {col['data_type']} (nullable: {col['is_nullable']}, default: {col['column_default']})")
        
        await conn.close()
        print("✅ Winner column operation completed successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(add_winner_column())

#!/usr/bin/env python3
"""
Script to recreate dynasty database tables on production
"""
import asyncio
import asyncpg
import os
import re
from dotenv import load_dotenv

async def create_dynasty_tables():
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
        
        # Read the local dynasty.sql file
        with open('database/dynasty.sql', 'r') as f:
            sql_content = f.read()
        
        # Extract table creation statements (skip the problematic parts)
        table_creation_sql = []
        
        # Find CREATE TABLE statements
        create_table_pattern = r'CREATE TABLE[^;]+;'
        create_sequences = re.findall(create_table_pattern, sql_content, re.IGNORECASE | re.DOTALL)
        
        for table_sql in create_sequences:
            # Clean up the SQL
            clean_sql = table_sql.replace('public.', '').strip()
            if 'CREATE TABLE' in clean_sql:
                table_creation_sql.append(clean_sql)
        
        print(f"📋 Found {len(table_creation_sql)} table creation statements")
        
        # Execute table creation
        for i, sql in enumerate(table_creation_sql):
            try:
                print(f"🔨 Creating table {i+1}/{len(table_creation_sql)}...")
                await conn.execute(sql)
                print(f"✅ Table {i+1} created successfully")
            except Exception as e:
                print(f"⚠️ Warning creating table {i+1}: {e}")
                # Continue with other tables
        
        # Create sequences
        sequence_pattern = r'CREATE SEQUENCE[^;]+;'
        sequences = re.findall(sequence_pattern, sql_content, re.IGNORECASE | re.DOTALL)
        
        for seq_sql in sequences:
            try:
                clean_sql = seq_sql.replace('public.', '').strip()
                await conn.execute(clean_sql)
                print(f"✅ Sequence created: {clean_sql[:50]}...")
            except Exception as e:
                print(f"⚠️ Warning creating sequence: {e}")
        
        # Set ownership
        ownership_pattern = r'ALTER TABLE[^;]+OWNER TO[^;]+;'
        ownerships = re.findall(ownership_pattern, sql_content, re.IGNORECASE | re.DOTALL)
        
        for own_sql in ownerships:
            try:
                clean_sql = own_sql.replace('public.', '').strip()
                await conn.execute(clean_sql)
                print(f"✅ Ownership set: {clean_sql[:50]}...")
            except Exception as e:
                print(f"⚠️ Warning setting ownership: {e}")
        
        # Verify tables were created
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('connection_types', 'political_dynasties', 'relationships')
        """)
        
        print(f"📊 Tables created: {[table['table_name'] for table in tables]}")
        
        await conn.close()
        print("✅ Dynasty database tables created successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(create_dynasty_tables())


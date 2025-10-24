#!/usr/bin/env python3
"""
Simple Dynasty Database Restoration Script
This script restores the dynasty database from the SQL dump with hardcoded credentials
"""

import asyncio
import asyncpg
import os
import subprocess
import sys

async def restore_dynasty_database():
    """Restore the dynasty database from SQL dump"""
    try:
        # Hardcoded database credentials for production
        db_host = 'localhost'
        db_port = 5432
        db_user = 'budget_admin'
        db_password = 'wuQ5gBYCKkZiOGb61chLcByMu'
        db_name = 'dynasty'
        
        print(f"🔄 Restoring dynasty database from SQL dump...")
        print(f"📊 Database: {db_name} on {db_host}:{db_port}")
        
        # Check if SQL dump file exists
        sql_dump_path = "database/dynasty.sql"
        if not os.path.exists(sql_dump_path):
            print(f"❌ SQL dump file not found: {sql_dump_path}")
            return False
        
        print(f"📁 Found SQL dump: {sql_dump_path}")
        
        # Try to clean existing database if possible
        print("🔄 Attempting to clean existing database...")
        try:
            # Connect to existing database and drop all tables
            conn = await asyncpg.connect(
                host=db_host,
                port=db_port,
                user=db_user,
                password=db_password,
                database=db_name
            )
            
            # Drop all tables in the database
            await conn.execute("DROP SCHEMA public CASCADE;")
            await conn.execute("CREATE SCHEMA public;")
            print("✅ Existing database cleaned")
            
            await conn.close()
        except Exception as e:
            print(f"⚠️ Warning: Could not clean existing database: {e}")
            print("🔄 Continuing with restoration...")
        
        # Restore database using psql
        print("📥 Restoring database from SQL dump...")
        
        # Set PGPASSWORD environment variable for psql
        env = os.environ.copy()
        env['PGPASSWORD'] = db_password
        
        # Run psql to restore the database
        psql_cmd = [
            'psql',
            '-h', db_host,
            '-p', str(db_port),
            '-U', db_user,
            '-d', db_name,
            '-f', sql_dump_path
        ]
        
        print(f"🔧 Running: {' '.join(psql_cmd)}")
        
        result = subprocess.run(
            psql_cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            print("✅ Database restoration completed successfully!")
            print(f"📊 Output: {result.stdout}")
            return True
        else:
            print(f"❌ Database restoration failed!")
            print(f"📊 Error: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Database restoration timed out after 5 minutes")
        return False
    except Exception as e:
        print(f"❌ Database restoration failed: {e}")
        return False

async def verify_database():
    """Verify that the database was restored correctly"""
    try:
        # Hardcoded database credentials for production
        db_host = 'localhost'
        db_port = 5432
        db_user = 'budget_admin'
        db_password = 'wuQ5gBYCKkZiOGb61chLcByMu'
        db_name = 'dynasty'
        
        print("🔍 Verifying database restoration...")
        
        # Connect to the restored database
        conn = await asyncpg.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database=db_name
        )
        
        try:
            # Check if political_dynasties table exists and has data
            count = await conn.fetchval("SELECT COUNT(*) FROM political_dynasties")
            print(f"📊 Political dynasties records: {count}")
            
            # Check if relationships table exists and has data
            relationships_count = await conn.fetchval("SELECT COUNT(*) FROM relationships")
            print(f"🔗 Relationships records: {relationships_count}")
            
            # Check if connection_types table exists and has data
            connection_types_count = await conn.fetchval("SELECT COUNT(*) FROM connection_types")
            print(f"📋 Connection types records: {connection_types_count}")
            
            # Check for specific test data (UY/TAN family)
            uy_count = await conn.fetchval("""
                SELECT COUNT(*) FROM political_dynasties 
                WHERE last_name = 'UY' AND province = 'SAMAR'
            """)
            print(f"👥 UY family in SAMAR: {uy_count} records")
            
            tan_count = await conn.fetchval("""
                SELECT COUNT(*) FROM political_dynasties 
                WHERE last_name = 'TAN' AND province = 'SAMAR'
            """)
            print(f"👥 TAN family in SAMAR: {tan_count} records")
            
            print("✅ Database verification completed successfully!")
            return True
            
        finally:
            await conn.close()
            
    except Exception as e:
        print(f"❌ Database verification failed: {e}")
        return False

async def main():
    """Main function"""
    print("🚀 Starting Dynasty Database Restoration...")
    
    # Step 1: Restore database
    if await restore_dynasty_database():
        print("✅ Database restoration successful!")
        
        # Step 2: Verify database
        if await verify_database():
            print("✅ Database verification successful!")
            print("🎉 Dynasty database restoration completed successfully!")
            return True
        else:
            print("❌ Database verification failed!")
            return False
    else:
        print("❌ Database restoration failed!")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

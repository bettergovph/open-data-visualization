#!/usr/bin/env python3
"""
Simple dynasty database restoration script
Restores the dynasty database from the SQL dump file
"""

import os
import subprocess
import sys
from pathlib import Path

def restore_dynasty_db():
    """Restore dynasty database from SQL dump"""
    try:
        # Get the project root directory
        project_root = Path(__file__).parent.parent
        sql_dump_file = project_root / "database" / "dynasty.sql"
        
        if not sql_dump_file.exists():
            print(f"❌ SQL dump file not found: {sql_dump_file}")
            return False
        
        print(f"📊 Found SQL dump: {sql_dump_file}")
        print(f"📏 File size: {sql_dump_file.stat().st_size / 1024 / 1024:.1f} MB")
        
        # Load environment variables
        from dotenv import load_dotenv
        load_dotenv(project_root / ".env")
        
        # Get database connection details
        db_host = os.getenv('POSTGRES_HOST', 'localhost')
        db_port = os.getenv('POSTGRES_PORT', '5432')
        db_user = os.getenv('POSTGRES_USER', 'postgres')
        db_password = os.getenv('POSTGRES_PASSWORD', '')
        db_name = os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
        
        print(f"🔗 Connecting to database: {db_name} on {db_host}:{db_port}")
        
        # Set PGPASSWORD environment variable for psql
        env = os.environ.copy()
        env['PGPASSWORD'] = db_password
        
        # Run psql to restore the database
        cmd = [
            'psql',
            '-h', db_host,
            '-p', db_port,
            '-U', db_user,
            '-d', db_name,
            '-f', str(sql_dump_file)
        ]
        
        print(f"🚀 Running: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            print("✅ Dynasty database restored successfully!")
            print(f"📤 Output: {result.stdout}")
            return True
        else:
            print(f"❌ Database restoration failed!")
            print(f"📤 Error: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Database restoration timed out after 5 minutes")
        return False
    except Exception as e:
        print(f"❌ Error during database restoration: {e}")
        return False

if __name__ == "__main__":
    success = restore_dynasty_db()
    sys.exit(0 if success else 1)

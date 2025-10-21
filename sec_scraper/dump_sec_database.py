#!/usr/bin/env python3
"""
Dump SEC database to database/sec_dump.sql
"""

import subprocess
import os
from dotenv import load_dotenv

# Try all tricks to read .env
# 1. Try .env first (hidden file)
if os.path.exists('.env'):
    load_dotenv('.env')
    print("📄 Loaded from .env")
# 2. Try visualization.env as fallback
elif os.path.exists('visualization.env'):
    load_dotenv('visualization.env')
    print("📄 Loaded from visualization.env")
# 3. Try absolute path to .env
else:
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"📄 Loaded from {env_path}")
    else:
        print("⚠️ No .env file found, using defaults")

def dump_database():
    host = os.getenv('POSTGRES_HOST', 'localhost')
    port = os.getenv('POSTGRES_PORT', '5432')
    user = os.getenv('POSTGRES_USER', 'budget_admin')
    password = os.getenv('POSTGRES_PASSWORD', '')
    
    # Set password in environment for pg_dump
    env = os.environ.copy()
    env['PGPASSWORD'] = password
    
    output_file = 'database/sec_dump.sql'
    
    print(f"🗄️ Dumping SEC database to {output_file}...")
    
    # Run pg_dump
    cmd = [
        'pg_dump',
        '-h', host,
        '-p', port,
        '-U', user,
        '-d', 'sec',
        '--no-owner',
        '--no-acl'
    ]
    
    try:
        with open(output_file, 'w') as f:
            result = subprocess.run(cmd, env=env, stdout=f, stderr=subprocess.PIPE, text=True)
        
        if result.returncode == 0:
            # Get file size
            size = os.path.getsize(output_file)
            size_mb = size / (1024 * 1024)
            print(f"✅ Database dump completed: {size_mb:.2f} MB")
            print(f"   File: {output_file}")
        else:
            print(f"❌ Database dump failed:")
            print(result.stderr)
            return False
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    return True

if __name__ == "__main__":
    dump_database()


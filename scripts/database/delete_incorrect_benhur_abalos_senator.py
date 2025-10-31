#!/usr/bin/env python3
"""
Delete incorrect BENHUR ABALOS SENATOR entries
Benhur Abalos never became a senator - these are data quality issues
"""

import asyncio
import asyncpg
import os
from pathlib import Path
from dotenv import load_dotenv


def load_env_from_dotenv() -> None:
    """Load environment variables from .env file"""
    root = Path(__file__).resolve().parents[2]
    env_path = root / '.env'
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


async def delete_incorrect_senator_entries():
    """Delete incorrect BENHUR ABALOS SENATOR entries"""
    load_env_from_dotenv()
    load_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        print("=" * 80)
        print("DELETE INCORRECT BENHUR ABALOS SENATOR ENTRIES")
        print("=" * 80)
        print()
        
        # Check how many SENATOR entries exist
        count = await conn.fetchval('''
            SELECT COUNT(*)
            FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%BENHUR%'
              AND UPPER(last_name) LIKE '%ABALOS%'
              AND UPPER(position) = 'SENATOR'
        ''')
        
        print(f"Found {count:,} incorrect BENHUR ABALOS SENATOR entries")
        print()
        
        # Show sample of what will be deleted
        samples = await conn.fetch('''
            SELECT id, first_name, last_name, position, province, municipality_city, year
            FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%BENHUR%'
              AND UPPER(last_name) LIKE '%ABALOS%'
              AND UPPER(position) = 'SENATOR'
            LIMIT 5
        ''')
        
        print("Sample records to be deleted:")
        print("-" * 80)
        for r in samples:
            print(f"  ID:{r['id']:8d} | {r['first_name']} {r['last_name']} | {r['position']} | {r['province']} | {r['municipality_city']} | Year:{r['year']}")
        print()
        
        # Delete the incorrect entries
        result = await conn.execute('''
            DELETE FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%BENHUR%'
              AND UPPER(last_name) LIKE '%ABALOS%'
              AND UPPER(position) = 'SENATOR'
        ''')
        
        deleted = int(result.split()[-1]) if result else 0
        print(f"✅ Deleted {deleted:,} incorrect BENHUR ABALOS SENATOR entries")
        print()
        
        # Check remaining BENHUR ABALOS records
        remaining = await conn.fetch('''
            SELECT DISTINCT position, COUNT(*) as count
            FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%BENHUR%'
              AND UPPER(last_name) LIKE '%ABALOS%'
            GROUP BY position
            ORDER BY count DESC
        ''')
        
        print("Remaining BENHUR ABALOS records by position:")
        print("-" * 80)
        for r in remaining:
            print(f"  {r['position']:50s} | {r['count']:5d} records")
        
        print()
        print("=" * 80)
        print("✅ Cleanup complete")
        print("=" * 80)
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(delete_incorrect_senator_entries())


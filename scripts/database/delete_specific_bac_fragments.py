#!/usr/bin/env python3
"""Delete specific BAC document fragments: SCHOOL, TABAC, FOR THE BAC, ALONG BAC"""

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


async def get_dynasty_conn():
    """Get connection to Dynasty database"""
    load_env_from_dotenv()
    load_dotenv()
    return await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )


async def delete_specific_fragments():
    """Delete specific BAC document fragments"""
    conn = await get_dynasty_conn()
    
    try:
        print("=" * 80)
        print("DELETE SPECIFIC BAC DOCUMENT FRAGMENTS")
        print("=" * 80)
        print()
        
        # Find records with these specific positions
        records = await conn.fetch('''
            SELECT id, first_name, last_name, position
            FROM political_dynasties
            WHERE UPPER(position) LIKE '%SCHOOL, TABAC%'
               OR UPPER(position) LIKE '%FOR THE BAC%'
               OR UPPER(position) LIKE '%ALONG BAC%'
            ORDER BY position, id
        ''')
        
        if not records:
            print("✅ No records found - all already deleted!")
            return
        
        print(f"Found {len(records)} records to delete:")
        print("-" * 80)
        
        ids_to_delete = []
        for record in records:
            print(f"ID {record['id']}: {record['first_name']:30s} | {record['last_name']:30s} | {record['position']}")
            ids_to_delete.append(record['id'])
        
        print()
        
        # Delete
        result = await conn.execute('''
            DELETE FROM political_dynasties
            WHERE id = ANY($1::int[])
        ''', ids_to_delete)
        
        deleted_num = int(str(result).split()[-1])
        print(f"✅ Deleted {deleted_num} records")
        
        # Verify
        remaining = await conn.fetch('''
            SELECT COUNT(*)
            FROM political_dynasties
            WHERE UPPER(position) LIKE '%SCHOOL, TABAC%'
               OR UPPER(position) LIKE '%FOR THE BAC%'
               OR UPPER(position) LIKE '%ALONG BAC%'
        ''')
        
        remaining_count = remaining[0]['count'] if remaining else 0
        if remaining_count == 0:
            print("✅ Verification: All deleted successfully!")
        else:
            print(f"⚠️ Warning: {remaining_count} records still remain")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(delete_specific_fragments())


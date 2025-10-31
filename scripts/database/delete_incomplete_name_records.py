#!/usr/bin/env python3
"""
Delete records with incomplete name data where suffixes are still in last_name
because first_name doesn't contain enough information to extract a real surname.
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


async def delete_incomplete_records():
    """Delete records with incomplete name data"""
    conn = await get_dynasty_conn()
    
    try:
        print("=" * 80)
        print("DELETE INCOMPLETE NAME RECORDS")
        print("=" * 80)
        print()
        
        # Get the records first to show what we're deleting
        records = await conn.fetch('''
            SELECT id, first_name, last_name, position, province, year
            FROM political_dynasties
            WHERE UPPER(TRIM(REPLACE(last_name, '.', ''))) IN ('JR', 'SR', 'II', 'III', 'IV', 'JUNIOR', 'SENIOR')
            ORDER BY id
        ''')
        
        if not records:
            print("✅ No incomplete records found!")
            return
        
        print(f"Found {len(records)} records with incomplete name data:")
        print("-" * 80)
        
        ids_to_delete = []
        for row in records:
            print(f"  ID {row['id']}:")
            print(f"    First Name: \"{row['first_name']}\"")
            print(f"    Last Name:  \"{row['last_name']}\"")
            print(f"    Position:   {row['position'] or 'N/A'}")
            print(f"    Province:   {row['province'] or 'N/A'}")
            print(f"    Year:       {row['year'] or 'N/A'}")
            print()
            ids_to_delete.append(row['id'])
        
        # Delete the records
        deleted_count = await conn.execute('''
            DELETE FROM political_dynasties
            WHERE id = ANY($1::int[])
        ''', ids_to_delete)
        
        # Extract number from result string like "DELETE 4"
        deleted_num = int(str(deleted_count).split()[-1])
        
        print(f"✅ Deleted {deleted_num} records")
        print()
        
        # Verify they're gone
        remaining = await conn.fetchval('''
            SELECT COUNT(*)
            FROM political_dynasties
            WHERE UPPER(TRIM(REPLACE(last_name, '.', ''))) IN ('JR', 'SR', 'II', 'III', 'IV', 'JUNIOR', 'SENIOR')
        ''')
        
        print(f"Remaining records with suffix in last_name: {remaining}")
        
        if remaining == 0:
            print("✅ All suffix-in-lastname issues resolved!")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(delete_incomplete_records())


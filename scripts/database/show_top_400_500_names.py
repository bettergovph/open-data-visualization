#!/usr/bin/env python3
"""
Show top 400-500 first + last name combinations from political_dynasties table
"""

import asyncio
import os
from pathlib import Path

import asyncpg


def load_env_from_dotenv() -> None:
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


async def show_top_400_500_names():
    load_env_from_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    # Get top 400-500 name combinations
    rows = await conn.fetch(
        """
        SELECT 
            UPPER(TRIM(first_name)) AS first_name, 
            UPPER(TRIM(last_name)) AS last_name, 
            COUNT(*) AS occurrences
        FROM political_dynasties
        WHERE TRIM(COALESCE(first_name,'')) <> ''
          AND TRIM(COALESCE(last_name,'')) <> ''
        GROUP BY UPPER(TRIM(first_name)), UPPER(TRIM(last_name))
        ORDER BY occurrences DESC, last_name ASC, first_name ASC
        LIMIT 500
        OFFSET 399
        """
    )
    
    print("=" * 80)
    print("TOP 400-500 FIRST + LAST NAME COMBINATIONS")
    print("=" * 80)
    print()
    
    for i, r in enumerate(rows, 400):
        print(f"{i}. {r['first_name']} {r['last_name']} ({r['occurrences']} occurrences)")
    
    await conn.close()
    print()
    print(f"Total: {len(rows)} name combinations (positions 400-500)")


if __name__ == '__main__':
    asyncio.run(show_top_400_500_names())


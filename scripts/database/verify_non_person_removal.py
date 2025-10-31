#!/usr/bin/env python3
"""
Verify non-person entities have been removed from political_dynasties table
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


async def verify_removal():
    load_env_from_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    # Check remaining non-person entities
    CLEAR_NON_PERSON_FIRST_NAMES = {
        'PCAB', 'CSEE', 'PCCP', 'ENGINEER', 'MAINTENANCE', 'REVIEWED', 'L.S.',
        'DATE', 'DPWH', 'LICENSE', 'CONSTRUCTION', 'RECOMMENDING', 'OF', 'PREPARATION',
        'MATION', 'GOV.PH', 'RTC', 'BATANGAS', 'PASIG', 'DAVAO',
        'LABS', 'CORSINE', 'COST', 'PUBLICATION', 'SUBMISSION', 'APPROVAL',
        'REQUIREMENTS', 'CATEGORY', 'BOARD', 'ERAL', 'CARRIAGEWAY', 'IMPRVT',
        'SET', 'DEO', 'OFF', 'THE'
    }
    
    CLEAR_NON_PERSON_LAST_NAMES = {
        'LICENSE', 'PUBLICATION', 'CATEGORY', 'COST', 'REQUIREMENTS', 'BOARD',
        'SUBMISSION', 'APPROVAL', 'CLASSROOMS', 'SAFETY', 'IMPRVT', 'TO',
        'OPENING'
    }
    
    # Check for remaining entries with these patterns
    rows = await conn.fetch(
        """
        SELECT 
            UPPER(TRIM(first_name)) AS first_name,
            UPPER(TRIM(last_name)) AS last_name,
            COUNT(*) AS occurrences
        FROM political_dynasties
        WHERE TRIM(COALESCE(first_name,'')) <> ''
          AND TRIM(COALESCE(last_name,'')) <> ''
          AND (
            UPPER(TRIM(first_name)) = ANY($1::text[])
            OR UPPER(TRIM(last_name)) = ANY($2::text[])
            OR UPPER(TRIM(last_name)) ~ '^(II|III|IV)$'
            OR UPPER(TRIM(first_name)) IN ('BATANGAS', 'PASIG', 'DAVAO', 'CAPIZ', 'CAMARINES', 'QUEZON', 'TANGUB', 'MANGGAHAN')
            AND UPPER(TRIM(last_name)) ~ '^(II|III)$'
          )
        GROUP BY UPPER(TRIM(first_name)), UPPER(TRIM(last_name))
        ORDER BY occurrences DESC
        LIMIT 100
        """
    , list(CLEAR_NON_PERSON_FIRST_NAMES), list(CLEAR_NON_PERSON_LAST_NAMES))
    
    print("=" * 80)
    print("REMAINING SUSPICIOUS ENTITIES (if any)")
    print("=" * 80)
    print()
    
    if rows:
        print(f"Found {len(rows)} potentially remaining non-person entities:")
        for row in rows:
            print(f"  {row['first_name']} {row['last_name']} ({row['occurrences']} occurrences)")
    else:
        print("✅ No remaining clear non-person entities found!")
    
    # Get total count
    total_count = await conn.fetchval("SELECT COUNT(*) FROM political_dynasties")
    print()
    print(f"Total records remaining: {total_count:,}")
    
    await conn.close()


if __name__ == '__main__':
    asyncio.run(verify_removal())


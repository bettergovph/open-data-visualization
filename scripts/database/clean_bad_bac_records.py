#!/usr/bin/env python3
"""Clean bad BAC records (document fragments) while preserving legitimate persons"""

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


async def clean_bad_bac_records():
    """Delete document fragments from BAC records"""
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
        print("CLEANING BAD BAC RECORDS (DOCUMENT FRAGMENTS)")
        print("=" * 80)
        print()
        
        # Bad name patterns
        bad_first_names = [
            'COMPLETE', 'MANNER', 'ENGINEERING', 'ISTANT', 'NEERING',
            'KIBUNGAN', 'TANEG', 'THIS', 'DECREASE', 'NANSASGA M',
            'NUEVA', 'PLAN', 'PROFILE', 'K GROUND BLACK WHITE',
            'WHITE BORDER UNITED', 'WHITE', 'CLASSROOM', 'SCHOOL',
            'SIDRO ANONANG TAGADTARAN CABATUAN', 'SIDRO', 'ND FLOOR LINE',
            'TYPE', 'G.I.', 'G.I. FLAT', 'I. FLAT', 'REFLECTIVE', 'GENERAL'
        ]
        
        bad_last_names = [
            'MANNER', 'SECTION', 'BUYACAOAN', 'BUGUIASLOO', 'RDE', 'S',
            'PROFILE', 'SYMBOLS', 'NATION', 'CALIPAYAN', 'DOWN', 'WITH',
            'BAR', 'THREE', 'DESCRIPTION'
        ]
        
        deleted = 0
        
        # Delete by first/last name combinations
        for first in bad_first_names:
            result = await conn.execute(
                "DELETE FROM political_dynasties WHERE UPPER(TRIM(first_name)) = $1 AND UPPER(position) LIKE '%BAC%'",
                first.upper().strip()
            )
            count = int(result.split()[-1]) if result else 0
            if count > 0:
                deleted += count
                print(f"Deleted {count} records with first_name='{first}'")
        
        for last in bad_last_names:
            result = await conn.execute(
                "DELETE FROM political_dynasties WHERE UPPER(TRIM(last_name)) = $1 AND UPPER(position) LIKE '%BAC%'",
                last.upper().strip()
            )
            count = int(result.split()[-1]) if result else 0
            if count > 0:
                deleted += count
                print(f"Deleted {count} records with last_name='{last}'")
        
        # Delete by position patterns (document fragments)
        bad_position_patterns = [
            '%ABOVE TOP OF PROPOSED PIPE INSTALL PIPE BAC%',
            '%ALONG BAC%',
            '%BADEO BAC%',
            '%BALACBAC%',
            '%BANANA ABAC%',
            '%BLACK BAC%',
            '%BLUE BAC%',
            '%TABACO NATIONAL HIGH SCHOOL%',
            '%CATAGBAC%',
            '%FACP BAC%',
            '%FILTER CLOTH BAC%',
            '%FOR THE BAC%',
            '%FRONT BAC%',
            '%GENERAL PUBLIC ADDRESS & BAC%',
            '%WASHING BAC%',
            '%SLEEVE BAC%',
        ]
        
        for pattern in bad_position_patterns:
            result = await conn.execute(
                "DELETE FROM political_dynasties WHERE UPPER(position) LIKE $1",
                pattern
            )
            count = int(result.split()[-1]) if result else 0
            if count > 0:
                deleted += count
                print(f"Deleted {count} records with position like '{pattern}'")
        
        print()
        print(f"✅ Total deleted: {deleted} bad BAC records")
        
        # Final statistics
        total_bac = await conn.fetchval(
            "SELECT COUNT(*) FROM political_dynasties WHERE UPPER(position) LIKE '%BAC%'"
        )
        unique_bac = await conn.fetchval(
            "SELECT COUNT(DISTINCT CONCAT(UPPER(TRIM(first_name)), '|', UPPER(TRIM(last_name)))) "
            "FROM political_dynasties WHERE UPPER(position) LIKE '%BAC%'"
        )
        
        print()
        print("=" * 80)
        print(f"Final BAC statistics:")
        print(f"  Total records: {total_bac}")
        print(f"  Unique persons: {unique_bac}")
        print(f"  Target: 99 unique persons")
        print("=" * 80)
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(clean_bad_bac_records())


#!/usr/bin/env python3
"""Verify restored BAC records"""

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


async def verify_restored_bac():
    """Verify restored BAC records"""
    load_env_from_dotenv()
    load_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    names_to_check = [
        ('JULIUS CEASAR', 'GALA'),
        ('JULIUS CEASAR V. DE', 'GALA'),
        ('ANGELITA', 'BASCO'),
        ('EVELYN', 'DILANGALEN'),
        ('ISMAEL', 'ALAJID'),
        ('TERESITA', 'MARQUEZ'),
        ('LILIBETH', 'CUEVAS'),
    ]
    
    print('=' * 80)
    print('VERIFYING RESTORED BAC RECORDS')
    print('=' * 80)
    print()
    
    found_count = 0
    for first, last in names_to_check:
        records = await conn.fetch(
            "SELECT first_name, last_name, position FROM political_dynasties "
            "WHERE UPPER(first_name) LIKE $1 AND UPPER(last_name) LIKE $2 "
            "AND UPPER(position) LIKE '%BAC%'",
            f'%{first}%', f'%{last}%'
        )
        
        if records:
            found_count += 1
            print(f'✅ {first} {last}:')
            for r in records:
                print(f'   - {r["first_name"]} {r["last_name"]} | {r["position"][:70]}')
        else:
            print(f'❌ {first} {last}: NOT FOUND')
        print()
    
    # Count total BAC records
    total_bac = await conn.fetchval(
        "SELECT COUNT(*) FROM political_dynasties WHERE UPPER(position) LIKE '%BAC%'"
    )
    
    print('=' * 80)
    print(f'Found {found_count}/{len(names_to_check)} deleted names restored')
    print(f'Total BAC records in database: {total_bac}')
    print('=' * 80)
    
    await conn.close()


if __name__ == '__main__':
    asyncio.run(verify_restored_bac())


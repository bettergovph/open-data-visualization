#!/usr/bin/env python3
"""Check if legitimate BAC records still exist"""

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


async def check_legitimate_bac():
    """Check if legitimate BAC records exist"""
    conn = await get_dynasty_conn()
    
    try:
        print("=" * 80)
        print("CHECKING LEGITIMATE BAC RECORDS")
        print("=" * 80)
        print()
        
        # Check for legitimate BAC positions
        legitimate_positions = [
            'Engineer III BAC',
            'Engineer IV BAC',
            'BAC Chairman Head',
            'BAC Chairman Assistant',
            'BAC Chairperson Section',
            'BAC Secretariat Head',
            'Head, BAC',
            'Head BAC',
            'Chief, Administrative Division BAC',
            'Chief, Administrative Section BAC',
            'Chief, HRAS BAC',
            'Chief, Maintenance Section BAC',
        ]
        
        print("1. Legitimate BAC positions:")
        print("-" * 80)
        total_legitimate = 0
        for pos in legitimate_positions:
            count = await conn.fetchval('''
                SELECT COUNT(*)
                FROM political_dynasties
                WHERE UPPER(position) = $1
            ''', pos.upper())
            print(f'{pos:45s}: {count} records')
            total_legitimate += count
        
        print(f'\nTotal legitimate BAC records: {total_legitimate}')
        print()
        
        # Check specific people who should have BAC positions
        print("2. Specific people who should have BAC positions:")
        print("-" * 80)
        
        people = [
            ('JULIUS CEASAR V. DE', 'GALA', 'Engineer III BAC'),
            ('ANGELITA L.', 'BASCO', 'Engineer III BAC'),
            ('EVELYN L.', 'DILANGALEN', 'Engineer III BAC'),
            ('ALBERT L.', 'CASTILLO', 'Engineer IV BAC'),
            ('ISMAEL R.', 'ALAJID', 'BAC Chairman Head'),
            ('TERESITA F.', 'MARQUEZ', 'Head, BAC'),
            ('LILIBETH M.', 'CUEVAS', 'BAC Secretariat Head'),
            ('JIM PAUL K.', 'ABRIL', 'BAC Secretariat Head'),
        ]
        
        missing_count = 0
        for first, last, expected_pos in people:
            result = await conn.fetchrow('''
                SELECT id, first_name, last_name, position
                FROM political_dynasties
                WHERE UPPER(first_name) LIKE $1
                  AND UPPER(last_name) LIKE $2
                LIMIT 1
            ''', f'%{first}%', f'%{last}%')
            
            if result:
                pos = result['position'] or 'NO POSITION'
                if expected_pos.upper() in pos.upper():
                    print(f'✅ {first} {last:20s}: {pos[:50]}')
                else:
                    print(f'⚠️  {first} {last:20s}: {pos[:50]} (expected: {expected_pos})')
            else:
                print(f'❌ {first} {last:20s}: NOT FOUND')
                missing_count += 1
        
        print()
        
        if missing_count > 0 or total_legitimate == 0:
            print("⚠️ WARNING: Some legitimate BAC records are missing!")
            print("   They may have been accidentally deleted.")
            print("   Check if there's a database backup to restore from.")
        else:
            print("✅ All legitimate BAC records are present!")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(check_legitimate_bac())


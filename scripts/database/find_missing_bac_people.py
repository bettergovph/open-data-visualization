#!/usr/bin/env python3
"""Find people who should have BAC positions but don't"""

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


async def find_people():
    """Find people who should have BAC positions"""
    conn = await get_dynasty_conn()
    
    try:
        print("=" * 80)
        print("FINDING PEOPLE WHO SHOULD HAVE BAC POSITIONS")
        print("=" * 80)
        print()
        
        people = [
            ('JULIUS CEASAR', 'GALA', 'Engineer III BAC'),
            ('ANGELITA', 'BASCO', 'Engineer III BAC'),
            ('EVELYN', 'DILANGALEN', 'Engineer III BAC'),
            ('ALBERT', 'CASTILLO', 'Engineer IV BAC'),
            ('ISMAEL', 'ALAJID', 'BAC Chairman Head'),
            ('TERESITA', 'MARQUEZ', 'Head, BAC'),
            ('LILIBETH', 'CUEVAS', 'BAC Secretariat Head'),
            ('JIM', 'ABRIL', 'BAC Secretariat Head'),
        ]
        
        print("Checking if people exist in database:")
        print("-" * 80)
        
        missing_with_position = []
        
        for first, last, expected_pos in people:
            result = await conn.fetch('''
                SELECT id, first_name, last_name, position
                FROM political_dynasties
                WHERE UPPER(first_name) LIKE $1
                  AND UPPER(last_name) LIKE $2
                LIMIT 3
            ''', f'%{first}%', f'%{last}%')
            
            if result:
                print(f'\n{first} {last}:')
                found_with_bac = False
                for row in result:
                    pos = row['position'] or 'NO POSITION'
                    print(f'  ID {row["id"]}: {row["first_name"]} {row["last_name"]} | {pos[:60]}')
                    if expected_pos.upper() in pos.upper():
                        found_with_bac = True
                
                if not found_with_bac:
                    missing_with_position.append((first, last, expected_pos, result[0]))
            else:
                print(f'\n{first} {last}: ❌ NOT FOUND AT ALL')
        
        print()
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        
        if missing_with_position:
            print(f"\n⚠️ Found {len(missing_with_position)} people who exist but are missing BAC positions:")
            for first, last, pos, record in missing_with_position:
                print(f"   {first} {last} - should have: {pos}")
                print(f"      Current record ID: {record['id']}, Position: {record['position'] or 'NONE'}")
            
            print("\n💡 These records need to have their positions restored.")
            print("   We need to restore the BAC positions from a backup or re-add them.")
        else:
            print("\n✅ All people either have BAC positions or don't exist in database")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(find_people())


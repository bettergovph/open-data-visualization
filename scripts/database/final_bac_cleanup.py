#!/usr/bin/env python3
"""Final cleanup of remaining BAC document fragments"""

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


async def final_cleanup():
    """Delete remaining BAC document fragments"""
    conn = await get_dynasty_conn()
    
    try:
        print("=" * 80)
        print("FINAL BAC DOCUMENT FRAGMENT CLEANUP")
        print("=" * 80)
        print()
        
        # Specific fragments to delete (patterns defined below in the loop)
        
        # Get all BAC positions
        all_bac = await conn.fetch('''
            SELECT id, first_name, last_name, position
            FROM political_dynasties
            WHERE UPPER(position) LIKE '%BAC%'
        ''')
        
        # Known legitimate patterns
        legitimate_keywords = [
            'BAC CHAIRMAN',
            'BAC CHAIRPERSON',
            'BAC SECRETARIAT',
            'HEAD, BAC',
            'HEAD BAC',
            'CHIEF',
            'ENGINEER',
            'BAC, CHAIRPERSON',
        ]
        
        fragment_ids = []
        
        for record in all_bac:
            pos = (record['position'] or '').upper()
            
            # Skip if it contains legitimate keywords
            is_legitimate = any(keyword in pos for keyword in legitimate_keywords)
            if is_legitimate:
                continue
            
            # Check if it matches fragment patterns
            is_fragment = False
            
            # Exact matches
            if pos in ['TO BE EXCAVATED AND BAC', 'SLEEVE BAC', 'FRONT BAC', 'FACP BAC',
                      'FILTER CLOTH BAC', 'LINE INSERTS BAC', 'INSTALL PIPE BAC',
                      'GENERAL PUBLIC ADDRESS & BAC', 'ON ITS BAC', 'WASHING BAC',
                      'ABOVE TOP OF PROPOSED PIPE INSTALL PIPE BAC',
                      'AN ELEVATION ABOVE TOP OF PIPE BAC', 'THE STRUCTURE BAC',
                      'BADEO KIBUNGAN BUYACAOAN BAC', 'NATUBLENG, BUGUIAS, BENGUET BAC',
                      'SAN ISIDRO TAYABAS BAY BAC', 'SIMLO M N A G BAC',
                      'NABUTAS BAC', 'NATALIO BAC']:
                is_fragment = True
            
            # Pattern matches
            if 'TO BE BACKFILLED' in pos:
                is_fragment = True
            if 'TO BE EXCAVATED' in pos and 'BAC' in pos:
                is_fragment = True
            if 'STONE MASONRY' in pos and 'TO BE EXCAVATED' in pos:
                is_fragment = True
            if 'EXCEPT INSOFAR' in pos:
                is_fragment = True
            if 'REFLECTIVE' in pos and 'FRONT BAC' in pos:
                is_fragment = True
            if pos == 'IN BAC' or (pos.startswith('IN BAC') and len(pos.split()) <= 3):
                is_fragment = True
            if 'MINDANAO' in pos and 'Kabac' in record['position']:
                is_fragment = True
            
            if is_fragment:
                fragment_ids.append(record['id'])
        
        if fragment_ids:
            print(f"Found {len(fragment_ids)} document fragments to delete:")
            print("-" * 80)
            
            for i, fid in enumerate(fragment_ids[:20], 1):
                record = next((r for r in all_bac if r['id'] == fid), None)
                if record:
                    print(f"{i:3d}. ID {fid}: {record['first_name']:30s} | {record['position'][:50]}")
            
            if len(fragment_ids) > 20:
                print(f"     ... and {len(fragment_ids) - 20} more")
            
            print()
            
            result = await conn.execute('''
                DELETE FROM political_dynasties
                WHERE id = ANY($1::int[])
            ''', fragment_ids)
            
            deleted_num = int(str(result).split()[-1])
            print(f"✅ Deleted {deleted_num} document fragment records")
        else:
            print("✅ No document fragments found - all cleaned!")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(final_cleanup())


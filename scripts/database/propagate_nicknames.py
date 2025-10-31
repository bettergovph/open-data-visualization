#!/usr/bin/env python3
"""
Propagate nicknames to all records for the same person.
If "Bongbong Marcos" has nickname "Bongbong", then "Ferdinand Marcos" 
should also have nickname "Bongbong" (same person).
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


async def propagate_nicknames():
    """Propagate nicknames to all records for the same person"""
    conn = await get_dynasty_conn()
    
    try:
        print("=" * 80)
        print("PROPAGATE NICKNAMES TO SAME-PERSON RECORDS")
        print("=" * 80)
        print()
        
        # Get all records with nicknames grouped by base canonical name
        print("📝 Finding nickname groups...")
        
        nickname_groups = await conn.fetch('''
            SELECT 
                canonical_first_name,
                last_name,
                nickname,
                COUNT(*) as record_count
            FROM political_dynasties
            WHERE nickname IS NOT NULL AND nickname != ''
            GROUP BY canonical_first_name, last_name, nickname
            ORDER BY canonical_first_name, last_name
        ''')
        
        print(f"   Found {len(nickname_groups)} nickname groups")
        print()
        
        updated_total = 0
        
        # For each nickname group, update all records with same base canonical name
        print("🔄 Propagating nicknames...")
        for group in nickname_groups:
            base_name = f"{group['canonical_first_name']} {group['last_name']}"
            nickname = group['nickname']
            
            # Update all records with this base canonical name (ignoring suffix)
            result = await conn.execute('''
                UPDATE political_dynasties
                SET nickname = $1
                WHERE canonical_first_name = $2
                  AND last_name = $3
                  AND (nickname IS NULL OR nickname = '' OR nickname != $1)
            ''', nickname, group['canonical_first_name'], group['last_name'])
            
            # Extract number of updated rows from result string
            if result and 'UPDATE' in result:
                updated = int(result.split()[-1])
                updated_total += updated
                if updated > 0:
                    print(f"   {base_name}: propagated '{nickname}' to {updated} records")
        
        print()
        print(f"   ✅ Total records updated: {updated_total}")
        print()
        
        # Verify results - check Marcos example
        print("🔍 Verification (Marcos family):")
        marcos = await conn.fetch('''
            SELECT first_name, canonical_first_name, canonical_name, suffix, nickname
            FROM political_dynasties
            WHERE UPPER(last_name) = 'MARCOS'
              AND (UPPER(first_name) LIKE '%BONGBONG%' OR UPPER(first_name) LIKE '%FERDINAND%')
            ORDER BY first_name, suffix
        ''')
        
        for row in marcos:
            suffix_str = f" {row['suffix']}" if row['suffix'] else ""
            print(f"   {row['first_name']:20s} -> {row['canonical_name']}{suffix_str:5s} (nickname: {row['nickname'] or 'None'})")
        
        print()
        print("✅ Nickname propagation complete!")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(propagate_nicknames())


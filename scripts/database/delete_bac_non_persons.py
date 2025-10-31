#!/usr/bin/env python3
"""
Delete BAC-related records that are clearly not persons:
1. "BAC ADVERTISEMENT" entries
2. Document fragments containing "BACK", "STRUCTURE", "BEG. OF BRIDGE" with BAC
3. Position-only entries where name fields contain document text
"""

import asyncio
import asyncpg
import os
import re
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


def is_suspicious_bac_record(first_name: str, last_name: str, position: str) -> bool:
    """Check if a record is a suspicious BAC entry (not a real person)"""
    first = (first_name or '').upper().strip()
    last = (last_name or '').upper().strip()
    pos = (position or '').upper().strip()
    
    # Pattern 1: "BAC" as first name with suspicious last name
    if first == 'BAC' and (last in ('ADVERTISEMENT', 'CHAIRPERSON', 'COMMITTEE') or 'ADVERTISEMENT' in last):
        return True
    
    # Pattern 2: "BACK" patterns (document fragments)
    if 'BACK' in first and 'BACK' in last:
        return True
    if first.startswith('BACK') or first.startswith('BACKING'):
        return True
    
    # Pattern 3: Structure/Bridge fragments
    suspicious_words = ['STRUCTURE', 'BRIDGE', 'BEG.', 'FILL', 'DIAPHRAGM', 'BACKWALL', 'DRAIN']
    if any(word in first for word in suspicious_words) and ('BAC' in pos or 'BACK' in first):
        return True
    
    # Pattern 4: Very long names with BAC positions that look like document text
    # BUT exclude legitimate multi-word names like "JULIUS CEASAR V. DE GALA"
    if len(first.split()) > 5 and 'BAC' in pos:
        # Check if it contains common name patterns (like initials, "DE", "DELA", etc.)
        name_indicators = ['DE', 'DEL', 'DELA', 'V.', 'JR', 'SR', 'II', 'III']
        if not any(indicator in first for indicator in name_indicators):
            return True
    
    # Pattern 5: Names that are clearly document fragments
    if re.search(r'\b(THE|OF|TO|FOR|AND|AT|ALONG|CROSS|SECTION|END|BEGIN|SHADE|COMBINATION)\b', first):
        if 'BAC' in pos or 'BACK' in first:
            return True
    
    return False


async def delete_bac_non_persons():
    """Delete BAC-related records that are not real persons"""
    conn = await get_dynasty_conn()
    
    try:
        print("=" * 80)
        print("DELETE BAC NON-PERSON RECORDS")
        print("=" * 80)
        print()
        
        # Get all BAC-related records
        all_bac = await conn.fetch('''
            SELECT id, first_name, last_name, position, province, year
            FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%BAC%'
               OR UPPER(last_name) LIKE '%BAC%'
               OR UPPER(position) LIKE '%BAC%'
        ''')
        
        print(f"Found {len(all_bac)} BAC-related records to analyze...")
        print()
        
        suspicious_ids = []
        suspicious_records = []
        
        for record in all_bac:
            if is_suspicious_bac_record(record['first_name'], record['last_name'], record['position']):
                suspicious_ids.append(record['id'])
                suspicious_records.append(record)
        
        print(f"Identified {len(suspicious_ids)} suspicious BAC entries to delete:")
        print("-" * 80)
        
        # Show samples
        for i, record in enumerate(suspicious_records[:30], 1):
            first = record['first_name'] or ''
            last = record['last_name'] or ''
            pos = (record['position'] or '')[:50]
            print(f"{i:3d}. ID {record['id']}: {first:30s} | {last:30s} | {pos}")
        
        if len(suspicious_records) > 30:
            print(f"     ... and {len(suspicious_records) - 30} more")
        
        print()
        
        if suspicious_ids:
            # Delete the records
            result = await conn.execute('''
                DELETE FROM political_dynasties
                WHERE id = ANY($1::int[])
            ''', suspicious_ids)
            
            deleted_num = int(str(result).split()[-1])
            
            print(f"✅ Deleted {deleted_num} suspicious BAC records")
        else:
            print("No suspicious records found to delete")
        
        print()
        
        # Show remaining legitimate BAC records (sample)
        remaining = await conn.fetch('''
            SELECT id, first_name, last_name, position
            FROM political_dynasties
            WHERE (UPPER(first_name) LIKE '%BAC%'
               OR UPPER(last_name) LIKE '%BAC%'
               OR UPPER(position) LIKE '%BAC%')
              AND id != ALL($1::int[])
            LIMIT 10
        ''', suspicious_ids if suspicious_ids else [0])
        
        if remaining:
            print(f"Sample of remaining legitimate BAC-related records ({len(remaining)} shown):")
            print("-" * 80)
            for record in remaining:
                first = record['first_name'] or ''
                last = record['last_name'] or ''
                pos = (record['position'] or '')[:50]
                print(f"   {first:30s} | {last:30s} | {pos}")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(delete_bac_non_persons())


#!/usr/bin/env python3
"""
Delete BAC-related document fragments:
1. Positions like BALACBAC, BANANA ABAC (place names, not positions)
2. BAC without proper spacing (BAC should have space before/after or be standalone with comma)
3. Document fragments where BAC is part of a word without proper spacing
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


def is_valid_bac_position(position: str) -> bool:
    """Check if BAC position has proper spacing (valid)"""
    if not position:
        return False
    
    pos_upper = position.upper()
    
    # Valid patterns: BAC with space before/after, or standalone with comma
    # Examples: "BAC Chairman", "Head, BAC", "Engineer III BAC", "BAC,"
    valid_patterns = [
        r'\sBAC\s',      # space before and after BAC
        r'\sBAC$',       # space before BAC at end
        r'^BAC\s',       # BAC at start with space after
        r'\sBAC,',       # space before BAC with comma
        r'^BAC,',        # BAC at start with comma
        r',\s*BAC',      # comma before BAC
        r'BAC$',         # BAC at end (could be valid like "HEAD BAC")
    ]
    
    # Check if it matches any valid pattern
    for pattern in valid_patterns:
        if re.search(pattern, pos_upper):
            return True
    
    return False


def is_bac_document_fragment(position: str) -> bool:
    """Check if position is a BAC document fragment"""
    if not position:
        return False
    
    pos_upper = position.upper()
    
    # Must contain BAC
    if 'BAC' not in pos_upper:
        return False
    
    # Known place names/document fragments
    place_names = [
        'BALACBAC',
        'BANANA ABAC',
        'CATAGBAC',
        'BADEO BAC',  # Place name
        'MABAC',
        'ELBAC',
        'NORABAC',
        'TENIBAC',
        'STENIBAC',
        'SETBAC',
    ]
    
    if pos_upper in place_names:
        return True
    
    # Known legitimate BAC positions (DO NOT DELETE)
    legitimate_positions = [
        'BAC CHAIRMAN',
        'BAC CHAIRPERSON',
        'BAC SECRETARIAT',
        'HEAD, BAC',
        'HEAD BAC',
        'CHIEF',
        'ENGINEER',
        'BAC, CHAIRPERSON',
        'TAYABAS BAY BAC',  # Might be legitimate location-based BAC
    ]
    
    # Check if it's a legitimate position first
    for legit in legitimate_positions:
        if legit in pos_upper:
            return False  # This is legitimate, don't delete
    
    # Fragment patterns that indicate document text (ONLY if not legitimate)
    fragment_patterns = [
        'TO BE EXCAVATED AND BAC',
        'TO BE BACKFILLED',
        'STONE MASONRY' in pos_upper and 'TO BE EXCAVATED' in pos_upper,
        'SLEEVE BAC',
        'FRONT BAC',
        'EXCEPT INSOFAR' in pos_upper,
        'FACP BAC',
        'FILTER CLOTH BAC',
        'LINE INSERTS BAC',
        'INSTALL PIPE BAC',
        'GENERAL PUBLIC ADDRESS & BAC',
        'ON ITS BAC',
        'REFLECTIVE' in pos_upper and 'FRONT BAC' in pos_upper,
        'ABOVE TOP OF PROPOSED PIPE INSTALL PIPE BAC',
        'AN ELEVATION ABOVE TOP OF PIPE BAC',
        'THE STRUCTURE BAC',
        'WASHING BAC',
        'BADEO KIBUNGAN BUYACAOAN BAC',
        'NATUBLENG, BUGUIAS, BENGUET BAC',
        'SAN ISIDRO TAYABAS BAY BAC',
        'MINDANAO' in pos_upper and 'Kabac' in pos_upper,
        'SIMLO M N A G BAC',
        'IN BAC' and len(pos_upper.split()) <= 3,
        'NABUTAS BAC',
        'NATALIO BAC',
    ]
    
    # Check fragment patterns (only if position doesn't contain legitimate keywords)
    for pattern in fragment_patterns:
        if isinstance(pattern, str):
            if pattern in pos_upper:
                return True
        elif pattern:  # For boolean patterns
            return True
    
    return False
    
    # Check if BAC is part of a word without proper spacing
    # Pattern: word contains BAC but BAC doesn't have space before/after
    # Examples: BALACBAC, CATAGBAC (BAC is embedded without spacing)
    
    # If BAC is in the position but doesn't match valid spacing patterns
    if 'BAC' in pos_upper and not is_valid_bac_position(position):
        # Check if it's clearly a document fragment
        # Look for patterns like "WORD1WORD2BAC" or "WORD BAC" where WORD+BAC might be a place name
        
        # Split by spaces and check if any word contains BAC
        words = pos_upper.split()
        for word in words:
            # If a word contains BAC but BAC isn't at start/end with proper boundaries
            if 'BAC' in word:
                # If BAC is embedded in middle of word (like BALACBAC, CATAGBAC)
                if not (word.startswith('BAC') or word.endswith('BAC') or word == 'BAC'):
                    # Check if it's a known pattern
                    if len(word) > 3 and 'BAC' in word[1:-1]:  # BAC in middle
                        return True
        
        # If the whole position doesn't have BAC as a separate word
        # and doesn't match valid patterns, it might be a fragment
        return True
    
    return False


async def delete_bac_fragments():
    """Delete BAC document fragments"""
    conn = await get_dynasty_conn()
    
    try:
        print("=" * 80)
        print("DELETE BAC DOCUMENT FRAGMENTS")
        print("=" * 80)
        print()
        
        # Get all records with BAC in position
        all_bac = await conn.fetch('''
            SELECT id, first_name, last_name, position
            FROM political_dynasties
            WHERE UPPER(position) LIKE '%BAC%'
        ''')
        
        print(f"Found {len(all_bac)} records with BAC in position")
        print()
        
        fragment_ids = []
        fragment_records = []
        
        for record in all_bac:
            position = record['position'] or ''
            if is_bac_document_fragment(position):
                fragment_ids.append(record['id'])
                fragment_records.append(record)
        
        print(f"Identified {len(fragment_ids)} document fragments to delete:")
        print("-" * 80)
        
        # Show samples
        for i, record in enumerate(fragment_records[:30], 1):
            name = f"{record['first_name']} {record['last_name']}"
            pos = record['position'] or ''
            print(f"{i:3d}. ID {record['id']}: {name:40s} | {pos[:50]}")
        
        if len(fragment_records) > 30:
            print(f"     ... and {len(fragment_records) - 30} more")
        
        print()
        
        if fragment_ids:
            # Delete the records
            result = await conn.execute('''
                DELETE FROM political_dynasties
                WHERE id = ANY($1::int[])
            ''', fragment_ids)
            
            deleted_num = int(str(result).split()[-1])
            print(f"✅ Deleted {deleted_num} BAC document fragment records")
        else:
            print("No fragments found to delete")
        
        print()
        
        # Show remaining valid BAC positions (sample)
        remaining = await conn.fetch('''
            SELECT DISTINCT position, COUNT(*) as count
            FROM political_dynasties
            WHERE UPPER(position) LIKE '%BAC%'
            GROUP BY position
            ORDER BY count DESC
            LIMIT 20
        ''')
        
        if remaining:
            print("Remaining valid BAC positions (sample):")
            print("-" * 80)
            for record in remaining:
                print(f"   {record['position']:60s} ({record['count']} records)")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(delete_bac_fragments())


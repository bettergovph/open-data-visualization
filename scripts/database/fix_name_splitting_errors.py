#!/usr/bin/env python3
"""
Fix name splitting errors where:
1. Suffixes (JR, SR, II, III) are in the last_name column instead of first_name
2. Middle names/initials (like "G.") are in the last_name column
3. Real last names are stuck in the first_name when first_name has 2+ words and last_name is a suffix
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


SUFFIXES = {'JR', 'SR', 'II', 'III', 'IV', 'JUNIOR', 'SENIOR'}


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


async def fix_suffix_in_lastname(conn):
    """
    Fix case 1: Suffix is in last_name column
    Example: first_name="FERDINAND MARCOS", last_name="JR"
    Should be: first_name="FERDINAND MARCOS JR", last_name="MARCOS"
    """
    print("🔧 Fixing suffixes in last_name column...")
    
    # Get records where last_name is a suffix (with or without trailing dot)
    records = await conn.fetch('''
        SELECT id, first_name, last_name
        FROM political_dynasties
        WHERE UPPER(TRIM(REPLACE(last_name, '.', ''))) IN ('JR', 'SR', 'II', 'III', 'IV', 'JUNIOR', 'SENIOR')
    ''')
    
    print(f"   Found {len(records)} records with suffix in last_name")
    
    fixed_count = 0
    for record in records:
        suffix_raw = record['last_name'].upper().strip()
        suffix = suffix_raw.replace('.', '').strip()
        
        # Normalize suffix
        if suffix == 'JUNIOR':
            suffix = 'JR'
        elif suffix == 'SENIOR':
            suffix = 'SR'
        
        first_name = record['first_name'] or ''
        
        # Extract real last name from first_name if it has multiple words
        first_parts = first_name.split()
        
        if len(first_parts) >= 2:
            # Last word of first_name is likely the real last name
            real_last_name = first_parts[-1]
            new_first_name = ' '.join(first_parts[:-1]) + f' {suffix}'
            
            try:
                await conn.execute('''
                    UPDATE political_dynasties
                    SET first_name = $1,
                        last_name = $2
                    WHERE id = $3
                ''', new_first_name.strip(), real_last_name, record['id'])
                
                fixed_count += 1
            except Exception as e:
                print(f"   ⚠️ Error fixing ID {record['id']}: {e}")
        elif first_name:
            # If first_name is a single word, we might need to mark this for manual review
            # For now, just move suffix to first_name and leave last_name empty (or use first_name as last_name)
            new_first_name = f"{first_name} {suffix}"
            # Use first_name as last_name if we can't extract it
            await conn.execute('''
                UPDATE political_dynasties
                SET first_name = $1,
                    last_name = $2
                WHERE id = $3
            ''', new_first_name.strip(), first_name, record['id'])
            fixed_count += 1
    
    print(f"   ✅ Fixed {fixed_count} records")
    return fixed_count


async def fix_middle_name_in_lastname(conn):
    """
    Fix case 2: Middle name/initial is in last_name column
    Example: first_name="JOSE", last_name="G. ESCUDERO"
    Should be: first_name="JOSE G.", last_name="ESCUDERO"
    
    Pattern: last_name matches "X. SURNAME" where X is a single letter
    """
    print("🔧 Fixing middle names/initials in last_name column...")
    
    # Get records where last_name has pattern like "G. ESCUDERO"
    records = await conn.fetch('''
        SELECT id, first_name, last_name
        FROM political_dynasties
        WHERE last_name ~ '^[A-Z]\. [A-Z]'
          AND last_name ~ '^[A-Z][A-Z]\. [A-Z]' = FALSE  -- Not "JR. NAME" pattern
        ORDER BY last_name
    ''')
    
    print(f"   Found {len(records)} records with middle name pattern in last_name")
    
    fixed_count = 0
    for record in records:
        last_name = record['last_name']
        first_name = record['first_name']
        
        # Pattern: "G. ESCUDERO" -> middle="G.", real_last="ESCUDERO"
        # Pattern: "G. M. ESCUDERO" -> middle="G. M.", real_last="ESCUDERO"
        
        # Split by space and find where the real last name starts
        parts = last_name.split()
        real_last_name = None
        middle_parts = []
        
        i = 0
        while i < len(parts):
            part = parts[i]
            # Check if this part looks like a middle initial (single letter + dot) or middle name
            if re.match(r'^[A-Z]\.?$', part) or (i < len(parts) - 1 and part[0].isupper()):
                middle_parts.append(part)
                i += 1
                # Check if next part is also middle (like "G. M.")
                if i < len(parts) - 1 and re.match(r'^[A-Z]\.?$', parts[i]):
                    middle_parts.append(parts[i])
                    i += 1
            else:
                # This is the start of the real last name
                real_last_name = ' '.join(parts[i:])
                break
        
        if real_last_name:
            # Move middle to first_name
            middle_str = ' '.join(middle_parts)
            new_first_name = f"{first_name} {middle_str}".strip()
            
            try:
                await conn.execute('''
                    UPDATE political_dynasties
                    SET first_name = $1,
                        last_name = $2
                    WHERE id = $3
                ''', new_first_name, real_last_name, record['id'])
                
                fixed_count += 1
            except Exception as e:
                print(f"   ⚠️ Error fixing ID {record['id']}: {e}")
    
    print(f"   ✅ Fixed {fixed_count} records")
    return fixed_count


async def fix_real_lastname_in_firstname(conn):
    """
    Fix case 3: Real last name is stuck in first_name when first_name has 2+ words
    Example: first_name="FERDINAND MARCOS", last_name="JR"
    Should be: first_name="FERDINAND", last_name="MARCOS", suffix="JR"
    
    But wait, we already handled suffixes in last_name. This is for cases where
    the first_name clearly has a surname in it but last_name is empty or wrong.
    """
    print("🔧 Fixing real last names stuck in first_name...")
    
    # Get records where first_name has 2+ words and last_name is suspiciously short or a suffix
    records = await conn.fetch('''
        SELECT id, first_name, last_name
        FROM political_dynasties
        WHERE first_name LIKE '% %'
          AND (
              last_name IS NULL
              OR last_name = ''
              OR UPPER(TRIM(last_name)) IN ('JR', 'SR', 'II', 'III', 'IV')
              OR LENGTH(last_name) <= 2
          )
    ''')
    
    print(f"   Found {len(records)} records with potential last name in first_name")
    
    fixed_count = 0
    for record in records:
        first_name = record['first_name']
        last_name = record['last_name'] or ''
        
        first_parts = first_name.split()
        
        if len(first_parts) >= 2:
            # If last_name is a suffix or empty, move the last word of first_name to last_name
            if not last_name or last_name.upper().strip() in SUFFIXES or len(last_name) <= 2:
                # Last word is likely the surname
                new_last_name = first_parts[-1]
                new_first_name = ' '.join(first_parts[:-1])
                
                # If old last_name was a suffix, append it to new_first_name
                if last_name and last_name.upper().strip() in SUFFIXES:
                    suffix = last_name.upper().strip()
                    if suffix == 'JUNIOR':
                        suffix = 'JR'
                    elif suffix == 'SENIOR':
                        suffix = 'SR'
                    new_first_name = f"{new_first_name} {suffix}"
                
                try:
                    await conn.execute('''
                        UPDATE political_dynasties
                        SET first_name = $1,
                            last_name = $2
                        WHERE id = $3
                    ''', new_first_name.strip(), new_last_name, record['id'])
                    
                    fixed_count += 1
                except Exception as e:
                    print(f"   ⚠️ Error fixing ID {record['id']}: {e}")
    
    print(f"   ✅ Fixed {fixed_count} records")
    return fixed_count


async def main():
    load_env_from_dotenv()
    load_dotenv()
    
    conn = await get_dynasty_conn()
    
    try:
        print("=" * 80)
        print("FIX NAME SPLITTING ERRORS")
        print("=" * 80)
        print()
        
        total_fixed = 0
        
        # Fix suffixes in last_name
        total_fixed += await fix_suffix_in_lastname(conn)
        print()
        
        # Fix middle names in last_name
        total_fixed += await fix_middle_name_in_lastname(conn)
        print()
        
        # Fix real last names in first_name
        total_fixed += await fix_real_lastname_in_firstname(conn)
        print()
        
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total records fixed: {total_fixed}")
        print()
        print("✅ Name splitting fixes complete!")
        print()
        print("💡 Next step: Re-run normalize_person_names.py to re-normalize")
        print("   with the corrected name splits.")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())


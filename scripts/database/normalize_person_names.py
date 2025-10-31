#!/usr/bin/env python3
"""
Normalize person names in political_dynasties table.
Handles:
1. Nickname mappings (e.g., Bongbong -> Ferdinand Marcos Jr)
2. Middle name variations (same person with/without middle names)
3. Creates canonical name mappings
"""

import asyncio
import asyncpg
import os
import re
from typing import Dict, List, Set, Tuple
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


# Common nickname mappings with suffix hints
# Format: 'NICKNAME': ('CANONICAL_FIRST_NAME', 'SUFFIX_IF_APPLICABLE')
NICKNAME_MAPPINGS = {
    # Marcos family - Bongbong is Ferdinand Marcos Jr
    'BONGBONG': ('FERDINAND', 'JR'),
    'BONG-BONG': ('FERDINAND', 'JR'),
    'BBM': ('FERDINAND', 'JR'),
    
    # Add more common nicknames as discovered
}

# Simple nickname mapping for backwards compatibility
SIMPLE_NICKNAME_MAPPINGS = {
    k: v[0] for k, v in NICKNAME_MAPPINGS.items()
}

# Suffix mappings (Jr, Sr, II, III, etc.)
SUFFIX_MAPPINGS = {
    'JR': 'JR',
    'SR': 'SR',
    'II': 'II',
    'III': 'III',
    'IV': 'IV',
    'JUNIOR': 'JR',
    'SENIOR': 'SR',
}

def normalize_first_name(first_name: str) -> Tuple[str, str]:
    """
    Normalize first name and extract suffix if any.
    Returns: (normalized_first_name, suffix)
    """
    if not first_name:
        return '', ''
    
    name = first_name.upper().strip()
    suffix = ''
    
    # Remove common prefixes
    prefixes = ['H.E.', 'HON.', 'HONORABLE', 'DR.', 'PROF.', 'ATTY.', 'ENG.', 'ARCH.']
    for prefix in prefixes:
        if name.startswith(prefix):
            name = name[len(prefix):].strip()
    
    # Extract suffix (Jr, Sr, II, III, etc.)
    name_parts = name.split()
    if len(name_parts) > 1:
        last_part = name_parts[-1]
        if last_part in SUFFIX_MAPPINGS:
            suffix = SUFFIX_MAPPINGS[last_part]
            name_parts = name_parts[:-1]
            name = ' '.join(name_parts)
    
    # Apply nickname mapping
    name_words = name.split()
    if len(name_words) > 0:
        first_word = name_words[0]
        if first_word in NICKNAME_MAPPINGS:
            canonical_info = NICKNAME_MAPPINGS[first_word]
            name_words[0] = canonical_info[0] if isinstance(canonical_info, tuple) else canonical_info
            name = ' '.join(name_words)
            # If nickname mapping provides a suffix and we don't have one, use it
            if isinstance(canonical_info, tuple) and len(canonical_info) > 1 and not suffix:
                suffix = canonical_info[1]
    
    # Remove extra spaces
    name = re.sub(r'\s+', ' ', name).strip()
    
    return name, suffix


def extract_name_parts(first_name: str) -> Dict[str, str]:
    """
    Extract first name, middle name(s), and suffix from first_name field.
    Returns dict with: first_name, middle_name, suffix
    """
    if not first_name:
        return {'first_name': '', 'middle_name': '', 'suffix': ''}
    
    normalized = first_name.upper().strip()
    name_parts = normalized.split()
    
    # Extract suffix
    suffix = ''
    if len(name_parts) > 0:
        last_part = name_parts[-1]
        if last_part in SUFFIX_MAPPINGS:
            suffix = SUFFIX_MAPPINGS[last_part]
            name_parts = name_parts[:-1]
    
    if len(name_parts) == 0:
        return {'first_name': '', 'middle_name': '', 'suffix': suffix}
    elif len(name_parts) == 1:
        # Apply nickname mapping
        first_word = name_parts[0]
        if first_word in NICKNAME_MAPPINGS:
            canonical_info = NICKNAME_MAPPINGS[first_word]
            canonical_first = canonical_info[0] if isinstance(canonical_info, tuple) else canonical_info
            # If nickname mapping provides a suffix and we don't have one, use it
            if isinstance(canonical_info, tuple) and len(canonical_info) > 1 and not suffix:
                suffix = canonical_info[1]
        else:
            canonical_first = first_word
        return {'first_name': canonical_first, 'middle_name': '', 'suffix': suffix}
    else:
        # First word is first name, rest is middle name(s)
        first_word = name_parts[0]
        if first_word in NICKNAME_MAPPINGS:
            canonical_info = NICKNAME_MAPPINGS[first_word]
            canonical_first = canonical_info[0] if isinstance(canonical_info, tuple) else canonical_info
            # If nickname mapping provides a suffix and we don't have one, use it
            if isinstance(canonical_info, tuple) and len(canonical_info) > 1 and not suffix:
                suffix = canonical_info[1]
        else:
            canonical_first = first_word
        middle = ' '.join(name_parts[1:])
        return {'first_name': canonical_first, 'middle_name': middle, 'suffix': suffix}


def create_canonical_name(first_name: str, last_name: str, force_suffix: str = None) -> str:
    """
    Create a canonical name for matching purposes.
    Uses normalized first name (no middle) + last name + suffix.
    If force_suffix is provided, use it (for cases like Bongbong -> Ferdinand Marcos Jr)
    """
    parts = extract_name_parts(first_name)
    canonical = f"{parts['first_name']} {last_name.upper().strip()}"
    
    # Use force_suffix if provided, otherwise use extracted suffix
    suffix = force_suffix or parts['suffix']
    if suffix:
        canonical += f" {suffix}"
    
    return canonical.strip()


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


async def ensure_normalization_tables(conn):
    """Create tables for name normalization tracking"""
    
    # Create name_mappings table to track canonical names
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS name_mappings (
            id SERIAL PRIMARY KEY,
            original_first_name TEXT NOT NULL,
            original_last_name TEXT NOT NULL,
            canonical_first_name TEXT NOT NULL,
            canonical_last_name TEXT NOT NULL,
            normalized_first_name TEXT NOT NULL,
            normalized_last_name TEXT NOT NULL,
            middle_name TEXT,
            suffix TEXT,
            canonical_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(original_first_name, original_last_name)
        )
    ''')
    
    # Add suffix column if it doesn't exist (middle_name already exists)
    try:
        await conn.execute('''
            ALTER TABLE political_dynasties
            ADD COLUMN IF NOT EXISTS suffix TEXT,
            ADD COLUMN IF NOT EXISTS canonical_first_name TEXT,
            ADD COLUMN IF NOT EXISTS canonical_name TEXT
        ''')
    except Exception as e:
        print(f"   Note: Some columns may already exist: {e}")


async def analyze_duplicates(conn) -> Dict[str, List[Dict]]:
    """
    Analyze potential duplicates by:
    1. Same last name
    2. Similar first names (with/without middle, nicknames)
    Returns dict mapping canonical_name -> list of records
    """
    print("🔍 Analyzing potential name duplicates...")
    
    all_records = await conn.fetch('''
        SELECT id, first_name, last_name, position, province, year
        FROM political_dynasties
        ORDER BY last_name, first_name
    ''')
    
    canonical_groups = {}
    
    for record in all_records:
        parts = extract_name_parts(record['first_name'])
        canonical = create_canonical_name(record['first_name'], record['last_name'])
        
        if canonical not in canonical_groups:
            canonical_groups[canonical] = []
        
        canonical_groups[canonical].append({
            'id': record['id'],
            'original_first': record['first_name'],
            'original_last': record['last_name'],
            'canonical_first': parts['first_name'],
            'middle': parts['middle_name'],
            'suffix': parts['suffix'],
            'canonical_name': canonical,
            'position': record['position'],
            'province': record['province'],
            'year': record['year']
        })
    
    # Filter to groups with multiple records (potential duplicates)
    duplicates = {k: v for k, v in canonical_groups.items() if len(v) > 1}
    
    print(f"   Found {len(duplicates)} canonical names with multiple records")
    print(f"   Total potential duplicates: {sum(len(v) for v in duplicates.values())} records")
    
    return duplicates


async def normalize_all_names(conn):
    """Normalize all names in political_dynasties and create mappings"""
    print("📝 Normalizing all person names...")
    
    records = await conn.fetch('''
        SELECT id, first_name, last_name
        FROM political_dynasties
        WHERE first_name IS NOT NULL AND last_name IS NOT NULL
    ''')
    
    print(f"   Processing {len(records)} records...")
    
    normalized_count = 0
    for record in records:
        parts = extract_name_parts(record['first_name'])
        
        # Special handling for known nicknames that should have suffixes
        # Bongbong Marcos should map to Ferdinand Marcos Jr
        original_upper = record['first_name'].upper().strip()
        first_word = original_upper.split()[0] if original_upper.split() else ''
        
        # Determine suffix - extract from name parts or use nickname mapping hint
        suffix = parts['suffix']
        if not suffix and first_word in NICKNAME_MAPPINGS:
            # Check if nickname mapping provides a suffix hint
            canonical_info = NICKNAME_MAPPINGS[first_word]
            if isinstance(canonical_info, tuple) and len(canonical_info) > 1:
                suffix = canonical_info[1]
        
        canonical = create_canonical_name(record['first_name'], record['last_name'], force_suffix=suffix)
        
        try:
            # Update the record with normalized values
            await conn.execute('''
                UPDATE political_dynasties
                SET middle_name = $1,
                    suffix = $2,
                    canonical_first_name = $3,
                    canonical_name = $4
                WHERE id = $5
            ''', 
                parts['middle_name'] or None,
                suffix or None,
                parts['first_name'],
                canonical,
                record['id']
            )
            
            # Update nickname - store the nickname if this is a known nickname
            # Also update other records with same canonical name to have this nickname
            if first_word in NICKNAME_MAPPINGS:
                # This IS a nickname (e.g., Bongbong), store it
                nickname_to_use = record['first_name']
                await conn.execute('''
                    UPDATE political_dynasties
                    SET nickname = $1
                    WHERE id = $2
                ''', nickname_to_use, record['id'])
                
                # Also update all other records with the same canonical name to have this nickname
                # (e.g., "Ferdinand Marcos" and "Ferdinand Marcos Jr" should also have nickname "Bongbong")
                await conn.execute('''
                    UPDATE political_dynasties
                    SET nickname = $1
                    WHERE canonical_name = $2
                      AND (nickname IS NULL OR nickname = '')
                ''', nickname_to_use, canonical)
            
            # Store mapping
            await conn.execute('''
                INSERT INTO name_mappings (
                    original_first_name, original_last_name,
                    canonical_first_name, canonical_last_name,
                    normalized_first_name, normalized_last_name,
                    middle_name, suffix, canonical_name
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (original_first_name, original_last_name) DO NOTHING
            ''',
                record['first_name'],
                record['last_name'],
                parts['first_name'],
                record['last_name'].upper().strip(),
                parts['first_name'],
                record['last_name'].upper().strip(),
                parts['middle_name'] or None,
                parts['suffix'] or None,
                canonical
            )
            
            normalized_count += 1
            
            if normalized_count % 1000 == 0:
                print(f"   Progress: {normalized_count}/{len(records)}...")
        
        except Exception as e:
            print(f"   ⚠️ Error processing {record['first_name']} {record['last_name']}: {e}")
            continue
    
    print(f"   ✅ Normalized {normalized_count} records")


async def generate_duplicate_report(duplicates: Dict[str, List[Dict]], output_file: str = 'name_normalization_report.txt'):
    """Generate a report of potential duplicates"""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("NAME NORMALIZATION REPORT\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Found {len(duplicates)} canonical names with multiple records\n\n")
        
        # Sort by number of duplicates
        sorted_duplicates = sorted(duplicates.items(), key=lambda x: len(x[1]), reverse=True)
        
        for canonical, records in sorted_duplicates[:100]:  # Top 100
            f.write(f"Canonical Name: {canonical}\n")
            f.write(f"  Records: {len(records)}\n")
            for rec in records:
                original = f"{rec['original_first']} {rec['original_last']}"
                if rec['middle']:
                    original += f" (middle: {rec['middle']})"
                if rec['suffix']:
                    original += f" {rec['suffix']}"
                f.write(f"    - {original}\n")
                f.write(f"      ID: {rec['id']}, Position: {rec['position']}, Year: {rec['year']}\n")
            f.write("\n")
    
    print(f"   📄 Report saved to: {output_file}")


async def main():
    load_env_from_dotenv()
    load_dotenv()
    
    conn = await get_dynasty_conn()
    
    try:
        print("=" * 80)
        print("PERSON NAME NORMALIZATION")
        print("=" * 80)
        print()
        
        # Ensure tables exist
        print("📋 Setting up normalization tables...")
        await ensure_normalization_tables(conn)
        print("   ✅ Tables ready")
        print()
        
        # Analyze duplicates
        duplicates = await analyze_duplicates(conn)
        print()
        
        # Generate report
        if duplicates:
            await generate_duplicate_report(duplicates)
            print()
        
        # Normalize all names
        await normalize_all_names(conn)
        print()
        
        # Summary
        stats = await conn.fetchrow('''
            SELECT 
                COUNT(*) as total,
                COUNT(canonical_name) as normalized,
                COUNT(DISTINCT canonical_name) as unique_canonical,
                COUNT(nickname) as with_nicknames
            FROM political_dynasties
        ''')
        
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total records: {stats['total']:,}")
        print(f"Normalized records: {stats['normalized']:,}")
        print(f"Unique canonical names: {stats['unique_canonical']:,}")
        print(f"Records with nicknames: {stats['with_nicknames']:,}")
        print()
        
        if duplicates:
            output_file = 'name_normalization_report.txt'
            print(f"⚠️ Found {len(duplicates)} potential duplicate groups")
            print(f"   Review {output_file} for details")
            print()
        
        print("✅ Name normalization complete!")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())


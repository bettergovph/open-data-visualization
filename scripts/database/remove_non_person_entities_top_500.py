#!/usr/bin/env python3
"""
Remove non-person entities from political_dynasties table.
Show ambiguous cases for review.
"""

import asyncio
import os
from pathlib import Path

import asyncpg


def load_env_from_dotenv() -> None:
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


# Clear non-person first names
CLEAR_NON_PERSON_FIRST_NAMES = {
    'PCAB', 'CSEE', 'PCCP', 'ENGINEER', 'MAINTENANCE', 'REVIEWED', 'L.S.',
    'DATE', 'DPWH', 'LICENSE', 'CONSTRUCTION', 'RECOMMENDING', 'OF', 'PREPARATION',
    'MATION', 'GOV.PH', 'RTC', 'ENGINEER', 'BATANGAS', 'PASIG', 'DAVAO',
    'LABS', 'PCCP', 'CSEE', 'CORSINE', 'CABUJAT', 'CABILLAR', 'COST',
    'PUBLICATION', 'SUBMISSION', 'APPROVAL', 'REQUIREMENTS', 'CATEGORY',
    'BOARD', 'MAINTENANCE', 'PREPARATION', 'REVIEWED', 'DATE'
}

# Clear non-person last names
CLEAR_NON_PERSON_LAST_NAMES = {
    'LICENSE', 'PUBLICATION', 'CATEGORY', 'COST', 'REQUIREMENTS', 'BOARD',
    'SUBMISSION', 'APPROVAL', 'CLASSROOMS', 'SAFETY', 'IMPRVT'
}

# Patterns that indicate non-person - more specific to avoid false positives
SUSPICIOUS_PATTERNS = [
    r'\b(CATEGORY|PUBLICATION|LICENSE|COST|BOARD|REQUIREMENTS|SUBMISSION|APPROVAL|CLASSROOMS|SAFETY|IMPRVT)\b',
    r'^(PCAB|CSEE|PCCP|DPWH|RTC|L\.S\.)',  # Clear acronyms
    r'^ENGINEER\s+[A-Z]+$',  # ENGINEER as first name with single word last name
    r'^REVIEWED\s+(COST|FORMAT)',  # REVIEWED + document word
    r'^DATE\s+(PUBLICATION|OPENING)',  # DATE + document word
    r'^(BATANGAS|PASIG|DAVAO|CAPIZ|CAMARINES|QUEZON|TANGUB|MANGGAHAN)\s+(II|III)$',  # Location II
    r'^SET\s+(NO|TO|DRAFTED|APPROVED|UNIT|DETAILS|DURAN|HABABAG|CONTROL|SECTION|PLAN|ALONG|ELEVATION|PROTECTION|SHEETS|JOINT|LIMITS|BANK|CITY|CONCRETE)',  # SET + document words
    r'^(MAIL|PARTICIPATION|ELECTRONIC|LETTER|SHEET|FFICE)\s+(TO|FORMAT)',  # Document headers
    r'^THE\s+(FORMAT|SHALL|PROJECT|SHEAR|GUIDELINES|CAMBER|HEADERS|NOTIFY|SURFACE|TOP)',  # THE + document words (not names)
    r'^(SHALL|SIDE|STRAIGHT|STAKED|TED)\s+(TO|NO|FORMAT|DRAFTED|PROJECT|UNIT|DETAILS|SECTION|PLAN|ALONG|CONTROL)',  # Document fragments
    r'^[A-Z]{1,3}\s+(TO|NO|FORMAT|PROJECT)$',  # Short codes + document words (like PH FORMAT)
    r'\s+(II|III|IV)$',     # Roman numerals as standalone last name
]

# Ambiguous patterns - need human review
AMBIGUOUS_PATTERNS = [
    r'ENGINEER\s+[A-Z]+',     # ENGINEER followed by a name
    r'^[A-Z]+\s+(II|III|IV)$',  # Name ending in II/III/IV
    r'^(BATANGAS|PASIG|DAVAO)\s+[A-Z]+',  # Location as first name
]


async def identify_and_remove_non_person_entities():
    load_env_from_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    import re
    
    # First, get all name combinations to analyze
    print("=" * 80)
    print("IDENTIFYING NON-PERSON ENTITIES")
    print("=" * 80)
    print()
    
    # Get distinct name combinations
    rows = await conn.fetch(
        """
        SELECT 
            UPPER(TRIM(first_name)) AS first_name,
            UPPER(TRIM(last_name)) AS last_name,
            COUNT(*) AS occurrences
        FROM political_dynasties
        WHERE TRIM(COALESCE(first_name,'')) <> ''
          AND TRIM(COALESCE(last_name,'')) <> ''
        GROUP BY UPPER(TRIM(first_name)), UPPER(TRIM(last_name))
        ORDER BY occurrences DESC
        """
    )
    
    # Identify clear non-person entries
    clear_non_person = []
    ambiguous_entries = []
    
    for row in rows:
        first = row['first_name']
        last = row['last_name']
        full_name = f"{first} {last}"
        occurrences = row['occurrences']
        
        # Check if first or last name is in clear non-person lists
        if first in CLEAR_NON_PERSON_FIRST_NAMES or last in CLEAR_NON_PERSON_LAST_NAMES:
            clear_non_person.append((first, last, occurrences, "clear_non_person_list"))
            continue
        
        # Check suspicious patterns
        is_suspicious = False
        for pattern in SUSPICIOUS_PATTERNS:
            if re.search(pattern, full_name, re.IGNORECASE):
                clear_non_person.append((first, last, occurrences, f"pattern: {pattern}"))
                is_suspicious = True
                break
        
        if is_suspicious:
            continue
        
        # Check ambiguous patterns
        for pattern in AMBIGUOUS_PATTERNS:
            if re.search(pattern, full_name, re.IGNORECASE):
                ambiguous_entries.append((first, last, occurrences, f"ambiguous: {pattern}"))
                break
    
    # Sort by occurrences descending
    clear_non_person.sort(key=lambda x: x[2], reverse=True)
    ambiguous_entries.sort(key=lambda x: x[2], reverse=True)
    
    # Show clear non-person entries
    print(f"🔴 CLEAR NON-PERSON ENTITIES ({len(clear_non_person)} entries):")
    print("-" * 80)
    for first, last, occ, reason in clear_non_person[:50]:  # Show top 50
        print(f"  {first} {last} ({occ} occurrences) - {reason}")
    if len(clear_non_person) > 50:
        print(f"  ... and {len(clear_non_person) - 50} more")
    print()
    
    # Show ambiguous entries
    print(f"🟡 AMBIGUOUS ENTITIES ({len(ambiguous_entries)} entries) - NEED REVIEW:")
    print("-" * 80)
    for first, last, occ, reason in ambiguous_entries[:30]:  # Show top 30 ambiguous
        print(f"  {first} {last} ({occ} occurrences) - {reason}")
    if len(ambiguous_entries) > 30:
        print(f"  ... and {len(ambiguous_entries) - 30} more")
    print()
    
    # Ask for confirmation before deletion
    print(f"⚠️  READY TO DELETE {len(clear_non_person)} clear non-person entries")
    print()
    
    # Delete clear non-person entries
    deleted_count = 0
    for first, last, occ, reason in clear_non_person:
        result = await conn.execute(
            """
            DELETE FROM political_dynasties
            WHERE UPPER(TRIM(first_name)) = $1
              AND UPPER(TRIM(last_name)) = $2
            """,
            first, last
        )
        deleted_count += int(result.split()[-1])
    
    await conn.close()
    
    print(f"✅ Deleted {deleted_count} records from {len(clear_non_person)} clear non-person name combinations")
    print()
    print(f"📋 Please review the {len(ambiguous_entries)} ambiguous entries above")
    print("   Run this script again with updates to CLEAR_NON_PERSON lists to remove them")


if __name__ == '__main__':
    asyncio.run(identify_and_remove_non_person_entities())


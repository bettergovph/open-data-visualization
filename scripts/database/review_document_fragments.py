#!/usr/bin/env python3
"""
Review Document Fragments - Show examples of records that would be deleted
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


async def review_fragments():
    """Review document fragments by category"""
    conn = await get_dynasty_conn()
    
    try:
        print("=" * 100)
        print("DOCUMENT FRAGMENT REVIEW - EXAMPLES OF RECORDS TO BE DELETED")
        print("=" * 100)
        print()
        
        # 1. Single-letter names
        print("1. SINGLE-LETTER NAMES (first 20 examples)")
        print("-" * 100)
        records = await conn.fetch(
            "SELECT id, first_name, last_name, position "
            "FROM political_dynasties "
            "WHERE (LENGTH(TRIM(first_name)) <= 1 OR LENGTH(TRIM(last_name)) <= 1) "
            "AND first_name IS NOT NULL AND last_name IS NOT NULL "
            "LIMIT 20"
        )
        for i, r in enumerate(records, 1):
            print(f"  {i:2d}. ID:{r['id']:8d} | '{r['first_name']}' / '{r['last_name']}' | {r['position'][:60]}")
        print(f"  Total: {await conn.fetchval('SELECT COUNT(*) FROM political_dynasties WHERE (LENGTH(TRIM(first_name)) <= 1 OR LENGTH(TRIM(last_name)) <= 1) AND first_name IS NOT NULL AND last_name IS NOT NULL')}")
        print()
        
        # 2. Empty or dot names
        print("2. EMPTY OR DOT NAMES")
        print("-" * 100)
        records = await conn.fetch(
            "SELECT id, first_name, last_name, position "
            "FROM political_dynasties "
            "WHERE first_name IN ('', '.') OR last_name IN ('', '.') "
            "OR TRIM(first_name) = '.' OR TRIM(last_name) = '.' "
            "LIMIT 20"
        )
        for i, r in enumerate(records, 1):
            print(f"  {i:2d}. ID:{r['id']:8d} | '{r['first_name']}' / '{r['last_name']}' | {r['position'][:60]}")
        print()
        
        # 3. Dictionary word pairs
        print("3. DICTIONARY WORD PAIRS (first 20 examples)")
        print("-" * 100)
        dictionary_words = {
            'THE', 'IS', 'AND', 'FOR', 'TO', 'OF', 'IN', 'ON', 'AT', 'BY',
            'WITH', 'FROM', 'AS', 'OR', 'AN', 'IT', 'BE', 'HAS', 'HAVE',
            'WAS', 'WERE', 'ARE', 'NOT', 'BUT', 'CAN', 'WILL', 'ALL',
            'HAD', 'ONE', 'TWO', 'MANY', 'MORE', 'MOST', 'SOME', 'SUCH',
            'THAT', 'THIS', 'THESE', 'THOSE', 'WHERE', 'WHEN', 'WHAT', 'WHICH',
            'WHO', 'WHOM', 'WHOSE', 'WHY', 'HOW', 'MAY', 'MIGHT', 'MUST',
            'SHOULD', 'WOULD', 'COULD', 'SHALL', 'ABOUT', 'ABOVE', 'ACROSS',
            'AFTER', 'AGAIN', 'AGAINST', 'ALONG', 'AMONG', 'AROUND', 'BECAUSE',
            'BEFORE', 'BEHIND', 'BELOW', 'BENEATH', 'BESIDE', 'BETWEEN',
            'BEYOND', 'DURING', 'EXCEPT', 'INSIDE', 'OUTSIDE', 'THROUGH',
            'THROUGHOUT', 'TOWARD', 'TOWARDS', 'UNDER', 'UNDERNEATH', 'UNTIL',
            'UPON', 'WITHIN', 'WITHOUT'
        }
        records = await conn.fetch(
            "SELECT id, first_name, last_name, position "
            "FROM political_dynasties "
            "WHERE first_name IS NOT NULL AND last_name IS NOT NULL "
            "LIMIT 10000"
        )
        dict_pairs = []
        for r in records:
            first = (r['first_name'] or '').strip().upper()
            last = (r['last_name'] or '').strip().upper()
            if first in dictionary_words and last in dictionary_words:
                dict_pairs.append(r)
                if len(dict_pairs) >= 20:
                    break
        
        for i, r in enumerate(dict_pairs, 1):
            print(f"  {i:2d}. ID:{r['id']:8d} | '{r['first_name']}' / '{r['last_name']}' | {r['position'][:60]}")
        print(f"  Total: Found {len(dict_pairs)} examples (checking all records)")
        print()
        
        # 4. Non-person entities (using heuristics)
        print("4. NON-PERSON ENTITIES (first 20 examples)")
        print("-" * 100)
        blacklist_terms = {
            'BY', 'FOLLOWING', 'CERNING', 'CONCERNING', 'REGARDING', 'PURSUANT',
            'THE', 'AND', 'OF', 'ING', 'MANUAL', 'SUBMISSION', 'BAC', 'BIDS',
            'AWARDS', 'COMMITTEE', 'CHAIRMAN', 'MEMBERS', 'SECRETARIAT',
            'REQUEST', 'FOR', 'QUOTATION', 'INVITATION', 'TO', 'BID'
        }
        records = await conn.fetch(
            "SELECT id, first_name, last_name, position "
            "FROM political_dynasties "
            "WHERE (first_name IS NOT NULL OR last_name IS NOT NULL) "
            "LIMIT 5000"
        )
        non_persons = []
        for r in records:
            first = (r['first_name'] or '').strip().upper()
            last = (r['last_name'] or '').strip().upper()
            # Simple heuristic: if both names are blacklist terms or very short
            first_is_bad = not first or first in blacklist_terms or len(first) <= 1
            last_is_bad = not last or last in blacklist_terms or len(last) <= 1
            if first_is_bad and last_is_bad:
                non_persons.append(r)
                if len(non_persons) >= 20:
                    break
        
        for i, r in enumerate(non_persons, 1):
            print(f"  {i:2d}. ID:{r['id']:8d} | '{r['first_name']}' / '{r['last_name']}' | {r['position'][:60]}")
        print(f"  Total: Found {len(non_persons)} examples (checking all records)")
        print()
        
        # 5. Very long names
        print("5. VERY LONG NAMES (>100 characters)")
        print("-" * 100)
        records = await conn.fetch(
            "SELECT id, first_name, last_name, position, "
            "LENGTH(first_name) as first_len, LENGTH(last_name) as last_len "
            "FROM political_dynasties "
            "WHERE (LENGTH(first_name) > 100 OR LENGTH(last_name) > 100) "
            "AND first_name IS NOT NULL AND last_name IS NOT NULL "
            "LIMIT 20"
        )
        for i, r in enumerate(records, 1):
            print(f"  {i:2d}. ID:{r['id']:8d} | First({r['first_len']}): '{r['first_name'][:50]}...' / Last({r['last_len']}): '{r['last_name'][:50]}...' | {r['position'][:60]}")
        print()
        
        # 6. BAC position document fragments
        print("6. BAC POSITION DOCUMENT FRAGMENTS")
        print("-" * 100)
        bac_fragments = [
            '%TO BE EXCAVATED AND BAC%',
            '%MALIMATOC II BAC%',
            '%SCHOOL, TABAC%',
            '%LINE INSERTS BAC%',
            '%INSTALL PIPE BAC%',
            '%ON ITS BAC%',
            '%SIMLO M N A G BAC%',
            '%NATALIO BAC%',
        ]
        
        for pattern in bac_fragments:
            records = await conn.fetch(
                "SELECT id, first_name, last_name, position "
                "FROM political_dynasties "
                "WHERE UPPER(position) LIKE $1 "
                "LIMIT 5",
                pattern
            )
            if records:
                print(f"  Pattern: {pattern}")
                for i, r in enumerate(records, 1):
                    print(f"    {i}. ID:{r['id']:8d} | '{r['first_name']}' / '{r['last_name']}' | {r['position']}")
                count = await conn.fetchval(
                    "SELECT COUNT(*) FROM political_dynasties WHERE UPPER(position) LIKE $1",
                    pattern
                )
                print(f"    Total: {count} records")
                print()
        
        # 7. Bad first/last names (from blacklist)
        print("7. BAD FIRST/LAST NAMES (from blacklist - first 10 examples each)")
        print("-" * 100)
        bad_names = ['FOR', 'TO', 'THE', 'ING', 'CERNING', 'MANUAL', 'BAC', 'MATION',
                    'EXCAVATION', 'CONTRACT', 'DOCUMENT', 'BID', 'SUBMISSION',
                    'RECEIVED', 'CONSTRUCTION', 'LOCATION', 'FIGURE', 'PESOS',
                    'FOLLOWING', 'ON', 'BY', 'IN', 'OF', 'AND', 'OR']
        
        print("  Bad FIRST names:")
        for bad_name in bad_names[:10]:
            records = await conn.fetch(
                "SELECT id, first_name, last_name, position "
                "FROM political_dynasties "
                "WHERE UPPER(TRIM(first_name)) = $1 "
                "LIMIT 3",
                bad_name.upper().strip()
            )
            if records:
                print(f"    '{bad_name}':")
                for r in records:
                    print(f"      ID:{r['id']:8d} | '{r['first_name']}' / '{r['last_name']}' | {r['position'][:60]}")
        
        print("\n  Bad LAST names:")
        for bad_name in bad_names[:10]:
            records = await conn.fetch(
                "SELECT id, first_name, last_name, position "
                "FROM political_dynasties "
                "WHERE UPPER(TRIM(last_name)) = $1 "
                "LIMIT 3",
                bad_name.upper().strip()
            )
            if records:
                print(f"    '{bad_name}':")
                for r in records:
                    print(f"      ID:{r['id']:8d} | '{r['first_name']}' / '{r['last_name']}' | {r['position'][:60]}")
        
        print()
        print("=" * 100)
        print("REVIEW COMPLETE")
        print("=" * 100)
        print()
        print("If these look correct, run:")
        print("  python3 scripts/database/comprehensive_document_fragment_cleanup.py --execute")
        print()
    
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(review_fragments())


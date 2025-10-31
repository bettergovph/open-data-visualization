#!/usr/bin/env python3
"""
Comprehensive Document Fragment Cleanup Script
Combines all learned patterns for identifying and removing document fragments
from the political_dynasties table.
"""

import asyncio
import asyncpg
import os
import re
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Tuple, Set


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


class DocumentFragmentCleaner:
    """Comprehensive document fragment detection and cleanup"""
    
    # Document fragment name pairs (exact matches)
    DOCUMENT_FRAGMENT_PAIRS = [
        ("IN", "WORDS"), ("NAME", "CONTRACT"), ("IN", "FIGURES"),
        ("CONTRACT", "NAME"), ("C.D.", "FUND"), ("TOTAL", "WORDS"),
        ("LOCATION", "CONTRACT"), ("C.D.", "RANGE"), ("CONTRACT", "LOCATION"),
        ("YOU", "WEBSITES"), ("PHP", "FIGURES"), ("COMMITTEE", "WORKS"),
        ("CONTRACT", "DURATION"), ("PARTMENT", "ID"), ("CONTRACT", "ID"),
        ("EMAIL", "ADDRESS"), ("DPWH.GOV.PH", "ISSUE"), ("UREMENT", "BELOW"),
        ("RECEIPT", "DEADLINE"), ("IMUM", "FOLLOWING"), ("S", "IS"),
        ("BRIEF", "DESCRIPTION"), ("THE", "IS"), ("DOCUMENTS", "BID"),
        ("FLOOD", "CONTROL"), ("SOURCE", "FUND"), ("THE", "ARE"),
        ("STA.", "WORKS"), ("ST", "OF"), ("PHILGEPS", "SUBMISSION"),
        ("ASSET", "PROGRAM"), ("WITH", "BRIDGES"), ("ROAD", "SAFETY"),
        ("BRIEF", "ROAD"), ("THE", "BELOW"), ("BARANGAY", "LOCATIONS"),
        ("LAUSE", "CLAUSE"), ("L.S.", "WORDS"), ("PLACE", "BUILDINGS"),
        ("AY", "LOCATION"), ("ELECTRONIC", "SUBMISSION"), ("MUM", "FOLLOWING"),
        ("ELECTRONIC", "EMAIL"), ("DALEN", "ADDRESS"), ("RD", "ADDRESS"),
        ("RACTORS", "S"), ("T", "ENTITY"), ("ISSUANCE", "DOCUMENTS"),
        ("NET", "LENGTH"), ("HIGHWAYS", "NAME"), ("OPENING", "BIDS"),
        ("BID", "CONFERENCE"), ("GPPB", "DOCUMENTS"), ("BELOW", "IS"),
        ("DPWH.GOV.PH", "POSTING"), ("IN", "FIGURE"), ("DROPPING", "BIDS"),
        ("IN", "OF"), ("NETWORK", "PROGRAM"), ("CLAUSE", "CLAUSE"),
        ("PART", "C"), ("IN", "DS"), ("OF", "CWR"), ("PART", "E"),
        ("LE.", "NOTE"), ("NFCC", "NOTE"), ("C.D", "RANGE"), ("ENT", "SC"),
        ("RACTOR", "SECTOR"), ("STO.", "WORKS"), ("RIEF", "ROAD"),
        ("FUND", "RANGE"), ("SIMILAR", "WORK"), ("FOR", "VISIT"), ("PART", "D"),
    ]
    
    # Single-letter or problematic first/last names
    BAD_FIRST_NAMES = [
        'FOR', 'TO', 'THE', 'ING', 'CERNING', 'MANUAL', 'BAC', 'MATION',
        'EXCAVATION', 'CONTRACT', 'DOCUMENT', 'BID', 'SUBMISSION',
        'RECEIVED', 'CONSTRUCTION', 'LOCATION', 'FIGURE', 'PESOS',
        'FOLLOWING', 'ON', 'BY', 'IN', 'OF', 'AND', 'OR', 'S', 'A',
        'COMPLETE', 'MANNER', 'ENGINEERING', 'ISTANT', 'NEERING',
        'KIBUNGAN', 'TANEG', 'THIS', 'DECREASE', 'NANSASGA M',
        'NUEVA', 'PLAN', 'PROFILE', 'K GROUND BLACK WHITE',
        'WHITE BORDER UNITED', 'WHITE', 'CLASSROOM', 'SCHOOL',
        'SIDRO ANONANG TAGADTARAN CABATUAN', 'SIDRO', 'ND FLOOR LINE',
        'TYPE', 'G.I.', 'G.I. FLAT', 'I. FLAT', 'REFLECTIVE', 'GENERAL'
    ]
    
    BAD_LAST_NAMES = [
        'TO', 'FOLLOWING', 'ON', 'BY', 'IN', 'OF', 'AND', 'OR',
        'EXCAVATION', 'CONTRACT', 'DOCUMENT', 'BID', 'SUBMISSION',
        'RECEIVED', 'CONSTRUCTION', 'LOCATION', 'FIGURE', 'PESOS',
        'MANNER', 'SECTION', 'BUYACAOAN', 'BUGUIASLOO', 'RDE', 'S',
        'PROFILE', 'SYMBOLS', 'NATION', 'CALIPAYAN', 'DOWN', 'WITH',
        'BAR', 'THREE', 'DESCRIPTION', 'A', 'AB', 'ABOVE', 'ABOVE II',
        'DISTRICT', 'ENGINEER II', 'ENGINEER', 'WORDS', 'IS'
    ]
    
    # Common English dictionary words (when both names are dictionary words)
    DICTIONARY_WORDS = {
        'THE', 'IS', 'AND', 'FOR', 'TO', 'OF', 'IN', 'ON', 'AT', 'BY',
        'WITH', 'FROM', 'AS', 'OR', 'AN', 'IT', 'BE', 'HAS', 'HAVE',
        'WAS', 'WERE', 'ARE', 'NOT', 'BUT', 'CAN', 'WILL', 'ALL', 'HAS',
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
    
    # Blacklist terms for non-person detection
    BLACKLIST_TERMS = {
        'BY', 'FOLLOWING', 'CERNING', 'CONCERNING', 'REGARDING', 'PURSUANT',
        'THE', 'AND', 'OF', 'ING', 'MANUAL', 'SUBMISSION', 'BAC', 'BIDS',
        'AWARDS', 'COMMITTEE', 'CHAIRMAN', 'MEMBERS', 'SECRETARIAT',
        'REQUEST', 'FOR', 'QUOTATION', 'INVITATION', 'TO', 'BID'
    }
    
    # BAC document fragment position patterns
    BAC_FRAGMENT_POSITIONS = [
        '%ABOVE TOP OF PROPOSED PIPE INSTALL PIPE BAC%',
        '%ALONG BAC%',
        '%BADEO BAC%',
        '%BALACBAC%',
        '%BANANA ABAC%',
        '%BLACK BAC%',
        '%BLUE BAC%',
        '%TABACO NATIONAL HIGH SCHOOL%',
        '%CATAGBAC%',
        '%FACP BAC%',
        '%FILTER CLOTH BAC%',
        '%FOR THE BAC%',
        '%FRONT BAC%',
        '%GENERAL PUBLIC ADDRESS & BAC%',
        '%WASHING BAC%',
        '%SLEEVE BAC%',
        '%TO BE EXCAVATED AND BAC%',
        '%MALIMATOC II BAC%',
        '%SCHOOL, TABAC%',
        '%BACK OF BAC%',
        '%LINE INSERTS BAC%',
        '%INSTALL PIPE BAC%',
        '%ON ITS BAC%',
        '%SIMLO M N A G BAC%',
        '%NABUTAS BAC%',
        '%NATALIO BAC%',
    ]
    
    # Pattern for legitimate person names
    NAME_PATTERN = re.compile(r"^[A-Z .'-]+$")
    
    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn
        self.deleted_count = 0
        self.deleted_records = []
    
    def looks_like_person(self, value: str) -> bool:
        """Check if a value looks like a person's name"""
        if not value:
            return False
        s = value.strip().upper()
        if not s:
            return False
        if len(s) < 2:
            return False
        if not self.NAME_PATTERN.match(s):
            return False
        if s in self.BLACKLIST_TERMS:
            return False
        tokens = [t for t in re.split(r"\s+", s) if t]
        token_set = set(tokens)
        if token_set and token_set.issubset(self.BLACKLIST_TERMS):
            return False
        if not any(len(t) >= 2 and t.isalpha() for t in tokens):
            return False
        return True
    
    async def delete_by_name_pairs(self, dry_run: bool = True) -> int:
        """Delete records matching known document fragment name pairs"""
        deleted = 0
        
        for first, last in self.DOCUMENT_FRAGMENT_PAIRS:
            if dry_run:
                count = await self.conn.fetchval(
                    "SELECT COUNT(*) FROM political_dynasties "
                    "WHERE UPPER(TRIM(first_name)) = $1 AND UPPER(TRIM(last_name)) = $2",
                    first.upper().strip(), last.upper().strip()
                )
                if count > 0:
                    deleted += count
                    print(f"  Would delete {count} records: '{first}' / '{last}'")
            else:
                result = await self.conn.execute(
                    "DELETE FROM political_dynasties "
                    "WHERE UPPER(TRIM(first_name)) = $1 AND UPPER(TRIM(last_name)) = $2",
                    first.upper().strip(), last.upper().strip()
                )
                count = int(result.split()[-1]) if result else 0
                if count > 0:
                    deleted += count
                    print(f"  Deleted {count} records: '{first}' / '{last}'")
        
        return deleted
    
    async def delete_bad_single_names(self, dry_run: bool = True) -> int:
        """Delete records with bad first or last names"""
        deleted = 0
        
        # Single letter names
        if dry_run:
            count = await self.conn.fetchval(
                "SELECT COUNT(*) FROM political_dynasties "
                "WHERE (LENGTH(TRIM(first_name)) <= 1 OR LENGTH(TRIM(last_name)) <= 1) "
                "AND first_name IS NOT NULL AND last_name IS NOT NULL"
            )
            deleted += count
            if count > 0:
                print(f"  Would delete {count} records: single-letter names")
        else:
            result = await self.conn.execute(
                "DELETE FROM political_dynasties "
                "WHERE (LENGTH(TRIM(first_name)) <= 1 OR LENGTH(TRIM(last_name)) <= 1) "
                "AND first_name IS NOT NULL AND last_name IS NOT NULL"
            )
            count = int(result.split()[-1]) if result else 0
            deleted += count
            if count > 0:
                print(f"  Deleted {count} records: single-letter names")
        
        # Empty or dot names
        if dry_run:
            count = await self.conn.fetchval(
                "SELECT COUNT(*) FROM political_dynasties "
                "WHERE first_name IN ('', '.') OR last_name IN ('', '.') "
                "OR TRIM(first_name) = '.' OR TRIM(last_name) = '.'"
            )
            deleted += count
            if count > 0:
                print(f"  Would delete {count} records: empty or dot names")
        else:
            result = await self.conn.execute(
                "DELETE FROM political_dynasties "
                "WHERE first_name IN ('', '.') OR last_name IN ('', '.') "
                "OR TRIM(first_name) = '.' OR TRIM(last_name) = '.'"
            )
            count = int(result.split()[-1]) if result else 0
            deleted += count
            if count > 0:
                print(f"  Deleted {count} records: empty or dot names")
        
        # Bad first names
        for bad_name in self.BAD_FIRST_NAMES:
            if dry_run:
                count = await self.conn.fetchval(
                    "SELECT COUNT(*) FROM political_dynasties "
                    "WHERE UPPER(TRIM(first_name)) = $1",
                    bad_name.upper().strip()
                )
                deleted += count
            else:
                result = await self.conn.execute(
                    "DELETE FROM political_dynasties WHERE UPPER(TRIM(first_name)) = $1",
                    bad_name.upper().strip()
                )
                count = int(result.split()[-1]) if result else 0
                deleted += count
        
        # Bad last names
        for bad_name in self.BAD_LAST_NAMES:
            if dry_run:
                count = await self.conn.fetchval(
                    "SELECT COUNT(*) FROM political_dynasties "
                    "WHERE UPPER(TRIM(last_name)) = $1",
                    bad_name.upper().strip()
                )
                deleted += count
            else:
                result = await self.conn.execute(
                    "DELETE FROM political_dynasties WHERE UPPER(TRIM(last_name)) = $1",
                    bad_name.upper().strip()
                )
                count = int(result.split()[-1]) if result else 0
                deleted += count
        
        return deleted
    
    async def delete_dictionary_word_pairs(self, dry_run: bool = True) -> int:
        """Delete records where both names are dictionary words"""
        if dry_run:
            # Get all records and check in Python (easier than SQL for this)
            records = await self.conn.fetch(
                "SELECT id, first_name, last_name FROM political_dynasties "
                "WHERE first_name IS NOT NULL AND last_name IS NOT NULL"
            )
            to_delete = []
            for r in records:
                first = (r['first_name'] or '').strip().upper()
                last = (r['last_name'] or '').strip().upper()
                if first in self.DICTIONARY_WORDS and last in self.DICTIONARY_WORDS:
                    to_delete.append(r['id'])
            
            if to_delete:
                print(f"  Would delete {len(to_delete)} records: dictionary word pairs")
            return len(to_delete)
        else:
            # Delete in batches
            records = await self.conn.fetch(
                "SELECT id, first_name, last_name FROM political_dynasties "
                "WHERE first_name IS NOT NULL AND last_name IS NOT NULL"
            )
            to_delete = []
            for r in records:
                first = (r['first_name'] or '').strip().upper()
                last = (r['last_name'] or '').strip().upper()
                if first in self.DICTIONARY_WORDS and last in self.DICTIONARY_WORDS:
                    to_delete.append(r['id'])
            
            if to_delete:
                BATCH = 5000
                deleted = 0
                for i in range(0, len(to_delete), BATCH):
                    batch = to_delete[i:i + BATCH]
                    result = await self.conn.execute(
                        "DELETE FROM political_dynasties WHERE id = ANY($1::int[])",
                        batch
                    )
                    deleted += len(batch)
                print(f"  Deleted {deleted} records: dictionary word pairs")
                return deleted
            return 0
    
    async def delete_non_person_entities(self, dry_run: bool = True) -> int:
        """Delete records where neither name looks like a person"""
        records = await self.conn.fetch(
            "SELECT id, first_name, last_name FROM political_dynasties "
            "WHERE (first_name IS NOT NULL OR last_name IS NOT NULL)"
        )
        
        to_delete = []
        for r in records:
            first_ok = self.looks_like_person(r['first_name'] or '')
            last_ok = self.looks_like_person(r['last_name'] or '')
            if not first_ok and not last_ok:
                to_delete.append(r['id'])
        
        if dry_run:
            if to_delete:
                print(f"  Would delete {len(to_delete)} records: non-person entities")
            return len(to_delete)
        else:
            if to_delete:
                BATCH = 5000
                deleted = 0
                for i in range(0, len(to_delete), BATCH):
                    batch = to_delete[i:i + BATCH]
                    await self.conn.execute(
                        "DELETE FROM political_dynasties WHERE id = ANY($1::int[])",
                        batch
                    )
                    deleted += len(batch)
                print(f"  Deleted {deleted} records: non-person entities")
                return deleted
            return 0
    
    async def delete_very_long_names(self, max_length: int = 100, dry_run: bool = True) -> int:
        """Delete records with suspiciously long names (likely parsing errors)"""
        if dry_run:
            count = await self.conn.fetchval(
                f"SELECT COUNT(*) FROM political_dynasties "
                f"WHERE (LENGTH(first_name) > {max_length} OR LENGTH(last_name) > {max_length}) "
                f"AND first_name IS NOT NULL AND last_name IS NOT NULL"
            )
            if count > 0:
                print(f"  Would delete {count} records: names longer than {max_length} chars")
            return count
        else:
            result = await self.conn.execute(
                f"DELETE FROM political_dynasties "
                f"WHERE (LENGTH(first_name) > {max_length} OR LENGTH(last_name) > {max_length}) "
                f"AND first_name IS NOT NULL AND last_name IS NOT NULL"
            )
            count = int(result.split()[-1]) if result else 0
            if count > 0:
                print(f"  Deleted {count} records: names longer than {max_length} chars")
            return count
    
    async def delete_bac_fragments(self, dry_run: bool = True) -> int:
        """Delete BAC position document fragments"""
        deleted = 0
        
        # Known legitimate BAC patterns (don't delete these)
        legitimate_patterns = [
            'BAC CHAIRMAN', 'BAC CHAIRPERSON', 'BAC SECRETARIAT',
            'HEAD, BAC', 'HEAD BAC', 'CHIEF', 'ENGINEER', 'BAC, CHAIRPERSON'
        ]
        
        for pattern in self.BAC_FRAGMENT_POSITIONS:
            # Check if it matches legitimate patterns first
            pattern_upper = pattern.upper().replace('%', '')
            is_legitimate = any(legit in pattern_upper for legit in legitimate_patterns)
            if is_legitimate:
                continue
            
            if dry_run:
                count = await self.conn.fetchval(
                    "SELECT COUNT(*) FROM political_dynasties WHERE UPPER(position) LIKE $1",
                    pattern
                )
                deleted += count
                if count > 0:
                    print(f"  Would delete {count} records: position like '{pattern}'")
            else:
                result = await self.conn.execute(
                    "DELETE FROM political_dynasties WHERE UPPER(position) LIKE $1",
                    pattern
                )
                count = int(result.split()[-1]) if result else 0
                deleted += count
                if count > 0:
                    print(f"  Deleted {count} records: position like '{pattern}'")
        
        return deleted
    
    async def cleanup(self, dry_run: bool = True, max_name_length: int = 100) -> dict:
        """Run comprehensive cleanup"""
        mode = "DRY RUN" if dry_run else "ACTUAL DELETION"
        print("=" * 80)
        print(f"COMPREHENSIVE DOCUMENT FRAGMENT CLEANUP - {mode}")
        print("=" * 80)
        print()
        
        # Get initial count
        initial_count = await self.conn.fetchval("SELECT COUNT(*) FROM political_dynasties")
        print(f"Initial record count: {initial_count:,}")
        print()
        
        total_deleted = 0
        
        # 1. Document fragment name pairs
        print("1. Removing document fragment name pairs...")
        deleted = await self.delete_by_name_pairs(dry_run)
        total_deleted += deleted
        print()
        
        # 2. Bad single names
        print("2. Removing bad first/last names (single letters, empty, dot, blacklist)...")
        deleted = await self.delete_bad_single_names(dry_run)
        total_deleted += deleted
        print()
        
        # 3. Dictionary word pairs
        print("3. Removing dictionary word pairs...")
        deleted = await self.delete_dictionary_word_pairs(dry_run)
        total_deleted += deleted
        print()
        
        # 4. Non-person entities
        print("4. Removing non-person entities...")
        deleted = await self.delete_non_person_entities(dry_run)
        total_deleted += deleted
        print()
        
        # 5. Very long names
        print("5. Removing very long names (parsing errors)...")
        deleted = await self.delete_very_long_names(max_name_length, dry_run)
        total_deleted += deleted
        print()
        
        # 6. BAC document fragments
        print("6. Removing BAC position document fragments...")
        deleted = await self.delete_bac_fragments(dry_run)
        total_deleted += deleted
        print()
        
        # Final count
        if not dry_run:
            final_count = await self.conn.fetchval("SELECT COUNT(*) FROM political_dynasties")
        else:
            final_count = initial_count - total_deleted
        
        print("=" * 80)
        print(f"SUMMARY - {mode}")
        print("=" * 80)
        print(f"Initial records: {initial_count:,}")
        print(f"Records to delete: {total_deleted:,}")
        print(f"Final records: {final_count:,}")
        print(f"Reduction: {(total_deleted/initial_count*100):.2f}%")
        print("=" * 80)
        
        return {
            'initial_count': initial_count,
            'deleted': total_deleted,
            'final_count': final_count
        }


async def main():
    """Main entry point"""
    import sys
    
    # Check for dry-run flag
    dry_run = True
    if len(sys.argv) > 1 and sys.argv[1] in ('--execute', '-x', '--delete'):
        dry_run = False
        print("⚠️  WARNING: Running in EXECUTION mode. Records will be DELETED!")
        response = input("Are you sure? Type 'yes' to continue: ")
        if response.lower() != 'yes':
            print("Aborted.")
            return
    else:
        print("ℹ️  Running in DRY-RUN mode. Use --execute to perform actual deletions.")
        print()
    
    conn = await get_dynasty_conn()
    
    try:
        cleaner = DocumentFragmentCleaner(conn)
        results = await cleaner.cleanup(dry_run=dry_run)
        
        # Save report
        if not dry_run:
            report_dir = Path(__file__).resolve().parent
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            report_file = report_dir / f"document_fragment_cleanup_{timestamp}.txt"
            with open(report_file, 'w') as f:
                f.write(f"Document Fragment Cleanup Report\n")
                f.write(f"Generated: {datetime.now()}\n")
                f.write(f"=" * 80 + "\n\n")
                f.write(f"Initial records: {results['initial_count']:,}\n")
                f.write(f"Records deleted: {results['deleted']:,}\n")
                f.write(f"Final records: {results['final_count']:,}\n")
            print(f"\n✅ Report saved to: {report_file}")
    
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())


#!/usr/bin/env python3
"""
Cleanup Engineer Document Fragments - Remove document fragment positions and names
from engineer position records
"""

import asyncio
import asyncpg
import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime


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


async def cleanup_engineer_fragments():
    """Cleanup engineer document fragments"""
    load_env_from_dotenv()
    load_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        print("=" * 100)
        print("CLEANUP ENGINEER DOCUMENT FRAGMENTS")
        print("=" * 100)
        print()
        
        deleted_count = 0
        deleted_records = []
        
        # 1. Delete suspicious engineer positions (document fragments)
        print("1. Deleting suspicious engineer positions (document fragments)...")
        print("-" * 100)
        
        suspicious_positions = [
            'ENGINEER TO', 'ENGINEER ON', 'ENGINEER THROUGH', 'ENGINEER OR',
            'ENGINEER PART', 'ENGINEER AS', 'ENGINEER WITHOUT', 'ENGINEER ALL',
            'ENGINEER BUT', 'ENGINEER WITHIN', 'ENGINEER WHEN', 'ENGINEER PROVISION',
            'ENGINEER SCHEDULE', 'ENGINEER AT', 'ENGINEER FLOOR', 'ENGINEER THAT',
            'ENGINEER OF', 'ENGINEER The', 'ENGINEER IS', 'ENGINEER DIRECT',
            'ENGINEER FROM', 'ENGINEER TYPICAL', 'ENGINEER EXCEPT', 'ENGINEER BONDED',
            'ENGINEER Provision', 'ENGINEER are', 'ENGINEER TOTAL', 'ENGINEER Part',
            'AND ENGINEER', 'ENGINEER CAN', 'ENGINEER CATCH', 'ENGINEER COMPRESSION',
            'ENGINEER DVR', 'ENGINEER EXPLOSIVES', 'ENGINEER GRADE', 'ENGINEER GUIDELINES',
            'ENGINEER HEADERS', 'ENGINEER IMMEDIATELY', 'ENGINEER MIXTURE', 'ENGINEER MO',
            'ENGINEER REINF', 'ENGINEER SALVACION', 'ENGINEER SDWK', 'ENGINEER SINGLE',
            'ENGINEER SIQUIJOR', 'ENGINEER SO', 'ENGINEER SUPERVISION', 'ENGINEER THREE',
            'ENGINEER WEAKEN', 'ENGINEER WHERE', 'ENGINEER mo',
            'SUPERVISIONOFADULYLICENSEDELECTRICALENGINEER',
            # Positions with unusual numbers (not ENGINEER I, II, III, IV)
            'ENGINEER 2', 'ENGINEER 1', 'ENGINEER 3', 'ENGINEER 13', 'ENGINEER 49',
            'ENGINEER 8', 'ENGINEER 01', 'ENGINEER 12', 'ENGINEER 14', 'ENGINEER 18',
            'ENGINEER 2025', 'ENGINEER 4', 'ENGINEER 45', 'ENGINEER 5', 'ENGINEER 6',
            'ENGINEER 0', 'ENGINEER 0442', 'ENGINEER 07', 'ENGINEER 11', 'ENGINEER 16',
            'ENGINEER 1702', 'ENGINEER 31', 'ENGINEER A1', 'ENGINEER A4',
            'Engineer 33',
        ]
        
        for pos in suspicious_positions:
            # Get records before deletion
            records = await conn.fetch('''
                SELECT id, first_name, last_name, position, province, municipality_city
                FROM political_dynasties
                WHERE UPPER(position) = $1
            ''', pos.upper())
            
            if records:
                result = await conn.execute('''
                    DELETE FROM political_dynasties
                    WHERE UPPER(position) = $1
                ''', pos.upper())
                
                count = int(result.split()[-1]) if result else 0
                deleted_count += count
                
                if count > 0:
                    print(f"   Deleted {count:3d} records: '{pos}'")
                    for r in records[:3]:  # Show first 3 examples
                        deleted_records.append(f"{r['first_name']} {r['last_name']} | {r['position']} | {r['province'] or 'N/A'}")
        
        print()
        
        # 2. Delete records with document fragment names (common document words)
        print("2. Deleting records with document fragment names...")
        print("-" * 100)
        
        bad_first_names = [
            'TO', 'ON', 'OF', 'AT', 'AS', 'OR', 'AND', 'THE', 'BUT', 'FOR', 'IN',
            'IS', 'THAT', 'ARE', 'WHEN', 'WHERE', 'WITHIN', 'WITHOUT', 'THROUGH',
            'EXCEPT', 'ALL', 'CAN', 'FROM', 'ENGINEER', 'ENGINEERING', 'FINISHED',
            'MILLIMETER', 'ERVICE', 'ERVICE', 'PICKUP', 'ADJUSTMENT', 'APPLICATION',
            'COMPRESSED', 'DEFICIENCY', 'FACILITIES', 'DESIGN', 'COLLECTIVELY',
            'EARTHWORK', 'RUBBER', 'USE', 'DEPTH', 'AUTHORIZED', 'ACCESS', 'BRIDGES',
            'DESIGNATED', 'SIDESLOPE', 'SCHEDULE', 'GROUNDING', 'ILITIES', 'FIELD',
            'KM', 'MAINTENANCE', 'GRAVEL', 'ED', 'TOTAL', 'TABLE', 'EXT.', 'ORNER',
            'STRUCTURAL', 'REQUIRE', 'LEAST', 'NDICATED', 'RO', 'SECTIONAL',
            'MEASUREMENT', 'IF', 'ED BY'
        ]
        
        bad_last_names = [
            'TO', 'ON', 'OF', 'AT', 'AS', 'OR', 'AND', 'THE', 'BUT', 'FOR', 'IN',
            'IS', 'THAT', 'ARE', 'ENGINEER', 'ENGINEERING', 'SECTION', 'UNIT',
            'OFFICE', 'ELEVATION', 'SET', 'DEPTH', 'AND', 'MUST', 'BE', 'VEHICLE',
            'ELECTRICAL', 'PAVEMENT', 'LIFE', 'RP', 'THE', 'SPECIMENS', 'DESIGNATED',
            'STRUCTURAL', 'REINF', 'REGISTERED', 'ENTRANCE', 'SLOPE', 'SHOULDER',
            'CHIEF', 'RIPRAP', 'GROUTED', 'LAMBERTO', 'MEASUREMENT', 'ELEVATIONS'
        ]
        
        # Delete by first name
        for bad_name in bad_first_names:
            result = await conn.execute('''
                DELETE FROM political_dynasties
                WHERE UPPER(position) LIKE '%ENGINEER%'
                  AND LENGTH(position) - LENGTH(REPLACE(position, ' ', '')) + 1 <= 2
                  AND UPPER(TRIM(first_name)) = $1
            ''', bad_name.upper().strip())
            
            count = int(result.split()[-1]) if result else 0
            deleted_count += count
        
        # Delete by last name
        for bad_name in bad_last_names:
            result = await conn.execute('''
                DELETE FROM political_dynasties
                WHERE UPPER(position) LIKE '%ENGINEER%'
                  AND LENGTH(position) - LENGTH(REPLACE(position, ' ', '')) + 1 <= 2
                  AND UPPER(TRIM(last_name)) = $1
            ''', bad_name.upper().strip())
            
            count = int(result.split()[-1]) if result else 0
            deleted_count += count
        
        print(f"   Deleted records with document fragment names")
        print()
        
        # 3. Delete records where name contains "ENGINEER" (parsing errors)
        print("3. Deleting records where name contains 'ENGINEER' (parsing errors)...")
        print("-" * 100)
        
        result = await conn.execute('''
            DELETE FROM political_dynasties
            WHERE UPPER(position) LIKE '%ENGINEER%'
              AND LENGTH(position) - LENGTH(REPLACE(position, ' ', '')) + 1 <= 2
              AND (
                  UPPER(first_name) LIKE '%ENGINEER%'
                  OR UPPER(last_name) LIKE '%ENGINEER%'
              )
        ''')
        
        count = int(result.split()[-1]) if result else 0
        deleted_count += count
        print(f"   Deleted {count} records")
        print()
        
        # 4. Delete records with single-letter names
        print("4. Deleting records with single-letter first or last names...")
        print("-" * 100)
        
        result = await conn.execute('''
            DELETE FROM political_dynasties
            WHERE UPPER(position) LIKE '%ENGINEER%'
              AND LENGTH(position) - LENGTH(REPLACE(position, ' ', '')) + 1 <= 2
              AND (
                  LENGTH(TRIM(first_name)) <= 1
                  OR LENGTH(TRIM(last_name)) <= 1
              )
        ''')
        
        count = int(result.split()[-1]) if result else 0
        deleted_count += count
        print(f"   Deleted {count} records")
        print()
        
        # 5. Delete records with very long names (likely parsing errors)
        print("5. Deleting records with very long names (>50 chars)...")
        print("-" * 100)
        
        result = await conn.execute('''
            DELETE FROM political_dynasties
            WHERE UPPER(position) LIKE '%ENGINEER%'
              AND LENGTH(position) - LENGTH(REPLACE(position, ' ', '')) + 1 <= 2
              AND (
                  LENGTH(first_name) > 50
                  OR LENGTH(last_name) > 50
              )
        ''')
        
        count = int(result.split()[-1]) if result else 0
        deleted_count += count
        print(f"   Deleted {count} records")
        print()
        
        # 6. Delete records where names contain position/technical words
        print("6. Deleting records where names contain position/technical words...")
        print("-" * 100)
        
        technical_words = ['SECTION', 'OFFICE', 'UNIT', 'DISTRICT', 'PROVINCE', 'CITY', 'DESIGN', 'PLANNING']
        
        for word in technical_words:
            result = await conn.execute('''
                DELETE FROM political_dynasties
                WHERE UPPER(position) LIKE '%ENGINEER%'
                  AND LENGTH(position) - LENGTH(REPLACE(position, ' ', '')) + 1 <= 2
                  AND (
                      UPPER(first_name) LIKE $1
                      OR UPPER(last_name) LIKE $1
                  )
            ''', f'%{word}%')
            
            count = int(result.split()[-1]) if result else 0
            if count > 0:
                deleted_count += count
                print(f"   Deleted {count} records containing '{word}' in name")
        
        print()
        
        # Final statistics
        remaining = await conn.fetchval('''
            SELECT COUNT(*) FROM political_dynasties
            WHERE UPPER(position) LIKE '%ENGINEER%'
              AND LENGTH(position) - LENGTH(REPLACE(position, ' ', '')) + 1 <= 2
        ''')
        
        remaining_positions = await conn.fetchval('''
            SELECT COUNT(DISTINCT position) FROM political_dynasties
            WHERE UPPER(position) LIKE '%ENGINEER%'
              AND LENGTH(position) - LENGTH(REPLACE(position, ' ', '')) + 1 <= 2
        ''')
        
        print("=" * 100)
        print("SUMMARY")
        print("=" * 100)
        print(f"Total records deleted: {deleted_count}")
        print(f"Remaining engineer records: {remaining}")
        print(f"Remaining unique engineer positions: {remaining_positions}")
        print()
        
        # Save deletion log
        report_dir = Path(__file__).resolve().parent
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = report_dir / f"engineer_cleanup_{timestamp}.txt"
        
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write("ENGINEER DOCUMENT FRAGMENT CLEANUP LOG\n")
            f.write(f"Generated: {datetime.now()}\n")
            f.write("=" * 100 + "\n\n")
            f.write(f"Total records deleted: {deleted_count}\n")
            f.write(f"Remaining records: {remaining}\n")
            f.write(f"Remaining positions: {remaining_positions}\n\n")
            f.write("Sample deleted records:\n")
            f.write("-" * 100 + "\n")
            for record in deleted_records[:100]:
                f.write(f"{record}\n")
        
        print(f"✅ Cleanup log saved to: {log_file}")
        print()
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(cleanup_engineer_fragments())


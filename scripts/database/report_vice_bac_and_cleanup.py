#!/usr/bin/env python3
"""
Report on VICE and BAC positions, then remove specified non-person entities
"""

import asyncio
import os
from pathlib import Path
import re

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


async def report_and_cleanup():
    load_env_from_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    print("=" * 80)
    print("VICE AND BAC POSITIONS REPORT")
    print("=" * 80)
    print()
    
    # Report on VICE positions
    print("VICE POSITIONS:")
    print("-" * 80)
    vice_positions = await conn.fetch(
        """
        SELECT position, COUNT(*) AS count
        FROM political_dynasties
        WHERE position IS NOT NULL
          AND position != ''
          AND UPPER(position) ILIKE '%VICE%'
        GROUP BY position
        ORDER BY count DESC
        """
    )
    
    vice_total = 0
    for row in vice_positions:
        print(f"  {row['position']:50s} ({row['count']:,} records)")
        vice_total += row['count']
    print(f"\n  Total VICE positions: {vice_total:,} records")
    print()
    
    # Report on BAC positions
    print("BAC POSITIONS:")
    print("-" * 80)
    bac_positions = await conn.fetch(
        """
        SELECT position, COUNT(*) AS count
        FROM political_dynasties
        WHERE position IS NOT NULL
          AND position != ''
          AND UPPER(position) ILIKE '%BAC%'
        GROUP BY position
        ORDER BY count DESC
        """
    )
    
    bac_total = 0
    for row in bac_positions:
        print(f"  {row['position']:50s} ({row['count']:,} records)")
        bac_total += row['count']
    print(f"\n  Total BAC positions: {bac_total:,} records")
    print()
    
    # Now remove specified patterns
    print("=" * 80)
    print("REMOVING SPECIFIED NON-PERSON ENTITIES")
    print("=" * 80)
    print()
    
    # Patterns to remove
    patterns_to_remove = [
        r'^TOP\s+AREA',
        r'^TOP\s+OF\s+ROOF',
        r'^TOP\s+OF\s+ROOF\s+BEAM',
        r'^OFFICE\s+OF\s+THE\s+COMMON\s+AREA',
        r'^F\s+SECRETARY',
        r'^OFFICE\s+OF\s+THE',  # Catch variations like "OFFICE OF THE COMMON AREA"
    ]
    
    # Find all matching name combinations
    all_rows = await conn.fetch(
        """
        SELECT DISTINCT
            UPPER(TRIM(first_name)) AS first_name,
            UPPER(TRIM(last_name)) AS last_name,
            COUNT(*) AS occurrences
        FROM political_dynasties
        WHERE TRIM(COALESCE(first_name,'')) <> ''
          AND TRIM(COALESCE(last_name,'')) <> ''
        GROUP BY UPPER(TRIM(first_name)), UPPER(TRIM(last_name))
        """
    )
    
    matches_to_remove = []
    for row in all_rows:
        first = row['first_name']
        last = row['last_name']
        full_name = f"{first} {last}"
        
        # Check if matches any pattern
        for pattern in patterns_to_remove:
            if re.search(pattern, full_name, re.IGNORECASE):
                matches_to_remove.append((first, last, row['occurrences'], pattern))
                break
    
    # Sort by occurrences
    matches_to_remove.sort(key=lambda x: x[2], reverse=True)
    
    print(f"Found {len(matches_to_remove)} name combinations matching removal patterns:")
    print("-" * 80)
    for first, last, occ, pattern in matches_to_remove[:50]:  # Show first 50
        print(f"  {first:30s} {last:30s} ({occ:5d} occurrences) - {pattern}")
    if len(matches_to_remove) > 50:
        print(f"  ... and {len(matches_to_remove) - 50} more")
    print()
    
    # Delete matching records
    total_deleted = 0
    for first, last, occ, pattern in matches_to_remove:
        result = await conn.execute(
            """
            DELETE FROM political_dynasties
            WHERE UPPER(TRIM(first_name)) = $1
              AND UPPER(TRIM(last_name)) = $2
            """,
            first, last
        )
        deleted = int(result.split()[-1])
        total_deleted += deleted
    
    print(f"✅ Deleted {total_deleted:,} records from {len(matches_to_remove)} name combinations")
    print()
    
    # Generate report file
    report_file = Path(__file__).resolve().parents[2] / "VICE_BAC_POSITIONS_REPORT.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("VICE AND BAC POSITIONS REPORT\n")
        f.write("=" * 80 + "\n\n")
        
        f.write("VICE POSITIONS:\n")
        f.write("-" * 80 + "\n")
        for row in vice_positions:
            f.write(f"  {row['position']:50s} ({row['count']:,} records)\n")
        f.write(f"\n  Total VICE positions: {vice_total:,} records\n\n")
        
        f.write("BAC POSITIONS:\n")
        f.write("-" * 80 + "\n")
        for row in bac_positions:
            f.write(f"  {row['position']:50s} ({row['count']:,} records)\n")
        f.write(f"\n  Total BAC positions: {bac_total:,} records\n\n")
        
        f.write("CLEANUP ACTIONS:\n")
        f.write("-" * 80 + "\n")
        f.write(f"Removed {len(matches_to_remove)} name combinations matching patterns:\n")
        f.write("  - TOP AREA\n")
        f.write("  - TOP OF ROOF\n")
        f.write("  - TOP OF ROOF BEAM\n")
        f.write("  - OFFICE OF THE COMMON AREA\n")
        f.write("  - F SECRETARY\n")
        f.write(f"\nTotal records deleted: {total_deleted:,}\n")
        f.write("\n")
        
        f.write("DELETED ENTRIES:\n")
        f.write("-" * 80 + "\n")
        for first, last, occ, pattern in matches_to_remove:
            f.write(f"  {first:30s} {last:30s} ({occ:5d} occurrences) - {pattern}\n")
    
    await conn.close()
    
    print(f"📄 Report saved to: {report_file}")


if __name__ == '__main__':
    asyncio.run(report_and_cleanup())


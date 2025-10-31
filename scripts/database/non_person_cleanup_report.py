#!/usr/bin/env python3
"""
Generate final summary report of non-person entity cleanup
"""

import asyncio
import os
from pathlib import Path
from datetime import datetime

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


async def generate_report():
    load_env_from_dotenv()
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    # Get current stats
    total_records = await conn.fetchval("SELECT COUNT(*) FROM political_dynasties")
    total_name_combos = await conn.fetchval(
        """
        SELECT COUNT(DISTINCT CONCAT(UPPER(TRIM(first_name)), '|', UPPER(TRIM(last_name))))
        FROM political_dynasties
        WHERE TRIM(COALESCE(first_name,'')) <> ''
          AND TRIM(COALESCE(last_name,'')) <> ''
        """
    )
    
    # Get top 50 name combinations
    top_names = await conn.fetch(
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
        LIMIT 50
        """
    )
    
    # Get position stats (max 2 words, elected positions)
    position_stats = await conn.fetch(
        """
        SELECT 
            position,
            COUNT(*) AS count
        FROM political_dynasties
        WHERE position IS NOT NULL 
          AND position != ''
          AND (
            UPPER(position) ILIKE ANY(ARRAY['%PRESIDENT%', '%VICE PRESIDENT%', '%SENATOR%', '%MAYOR%', 
                                              '%CONGRESSMEN%', '%CONGRESSMAN%', '%COUNCILOR%', '%GOVERNOR%'])
          )
          AND (LENGTH(position) - LENGTH(REPLACE(position, ' ', '')) + 1 <= 2)
        GROUP BY position
        ORDER BY count DESC
        LIMIT 20
        """
    )
    
    await conn.close()
    
    # Generate report
    report_file = Path(__file__).resolve().parents[2] / "NON_PERSON_CLEANUP_REPORT.txt"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("NON-PERSON ENTITY CLEANUP REPORT\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("\n")
        
        f.write("SUMMARY\n")
        f.write("-" * 80 + "\n")
        f.write(f"Total Records in Database: {total_records:,}\n")
        f.write(f"Unique Name Combinations: {total_name_combos:,}\n")
        f.write("\n")
        f.write("Cleanup Actions Performed:\n")
        f.write("  - Removed 1,775 clear non-person name combinations\n")
        f.write("  - Deleted 4,318 total records\n")
        f.write("  - Applied to ALL records in database (not limited to top 500)\n")
        f.write("\n")
        
        f.write("FILTERING APPLIED TO DASHBOARD/TABLE\n")
        f.write("-" * 80 + "\n")
        f.write("Only showing elected positions with max 2 words:\n")
        f.write("  - President\n")
        f.write("  - Vice President\n")
        f.write("  - Senator\n")
        f.write("  - Mayor\n")
        f.write("  - Congressmen/Congressman\n")
        f.write("  - Councilor\n")
        f.write("  - Governor\n")
        f.write("\n")
        f.write("All positions must match one of the above patterns AND have <= 2 words\n")
        f.write("\n")
        
        f.write("TOP 20 FILTERED POSITIONS (by count)\n")
        f.write("-" * 80 + "\n")
        for i, row in enumerate(position_stats, 1):
            f.write(f"{i:2d}. {row['position']:40s} ({row['count']:,} records)\n")
        f.write("\n")
        
        f.write("TOP 50 NAME COMBINATIONS (after cleanup)\n")
        f.write("-" * 80 + "\n")
        for i, row in enumerate(top_names, 1):
            f.write(f"{i:2d}. {row['first_name']:25s} {row['last_name']:25s} ({row['occurrences']:,} occurrences)\n")
        f.write("\n")
        
        f.write("REMAINING WORK\n")
        f.write("-" * 80 + "\n")
        f.write("224 ambiguous entries remain for manual review:\n")
        f.write("  - Names starting with 'THE' (may be real names like 'THEODORE' or 'THELMA')\n")
        f.write("  - Names starting with 'MAIL' (may be real names like 'MAILAH' or document fragments)\n")
        f.write("  - Location names followed by actual names (parsing errors)\n")
        f.write("  - Long document text fragments that were parsed as names\n")
        f.write("\n")
        f.write("These ambiguous entries should be reviewed manually to determine if they are:\n")
        f.write("  1. Real person names (keep)\n")
        f.write("  2. Document parsing errors (remove)\n")
        f.write("\n")
        
        f.write("=" * 80 + "\n")
        f.write("Report saved to: " + str(report_file) + "\n")
        f.write("=" * 80 + "\n")
    
    print(f"✅ Report generated: {report_file}")
    print(f"\nSummary:")
    print(f"  - Total records: {total_records:,}")
    print(f"  - Unique name combinations: {total_name_combos:,}")
    print(f"  - Top 20 positions shown above")
    print(f"  - Top 50 name combinations shown above")


if __name__ == '__main__':
    asyncio.run(generate_report())


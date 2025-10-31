#!/usr/bin/env python3
"""
Clean up malformed position names that look like document text.

These are positions that contain phrases like:
- "SHALL BE", "WILL BE", "AS DIRECTED BY"
- "APPROVED BY THE ENGINEER"
- Project descriptions
- Technical specifications
- Long descriptions (> 100 chars)
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
import re


async def identify_malformed_positions(conn):
    """Identify rows with malformed position names"""
    
    # Patterns that indicate document text rather than position titles
    malformed_patterns = [
        r'SHALL BE',
        r'WILL BE',
        r'AS DIRECTED BY',
        r'APPROVED BY',
        r'AS STAKED BY',
        r'AS SHOWN',
        r'SUBMIT IN',
        r'INDICATED ON',
        r'CONTRACTOR',
        r'THE ENGINEER',
        r'ENGINEER BEFORE',
        r'ENGINEER DATE',
        r'ENGINEER SHEET',
        r'ENGINEER FOR',
        r'ENGINEER AND',
        r'ENGINEER PRIOR',
        r'ENGINEER IN',
        r'ENGINEER OFFICER',
        r'ENGINEER No',
        r'WHITE BAC',
        r'REFLECTORIZED BAC',
        r'BACK OF.*BAC',
        r'CUTBAC',
        r'REFERENCE BAC',
        r'TYPICAL.*SECTION',
        r'CONSTRUCTION OF',
        r'APPROVED BUDGET',
        r'PROJECT',
        r'CONTRACT',
        r'PLAN',
        r'DESIGN',
    ]
    
    # Also flag very long positions (likely document text)
    max_reasonable_length = 100
    
    # Build query to find malformed positions
    conditions = []
    for pattern in malformed_patterns:
        conditions.append(f"position ILIKE '%{pattern.replace('%', '%%').replace('_', '__')}%'")
    
    conditions.append(f"LENGTH(position) > {max_reasonable_length}")
    
    where_clause = " OR ".join(conditions)
    
    print("🔍 Identifying malformed position names...")
    
    # First, get a preview of what will be deleted
    preview = await conn.fetch(f"""
        SELECT 
            id,
            CONCAT(first_name, ' ', last_name) as full_name,
            position,
            province,
            year
        FROM political_dynasties
        WHERE position IS NOT NULL 
          AND position <> ''
          AND ({where_clause})
        ORDER BY LENGTH(position) DESC, position
        LIMIT 50
    """)
    
    if preview:
        print(f"\n📋 Preview of malformed positions (showing first 50):")
        print("=" * 80)
        for row in preview[:20]:  # Show first 20
            print(f"ID: {row['id']:8} | {row['full_name'][:30]:30} | {row['position'][:40]}")
        if len(preview) > 20:
            print(f"... and {len(preview) - 20} more")
    
    # Get total count
    total_count = await conn.fetchval(f"""
        SELECT COUNT(*)
        FROM political_dynasties
        WHERE position IS NOT NULL 
          AND position <> ''
          AND ({where_clause})
    """)
    
    print(f"\n📊 Total rows to delete: {total_count:,}")
    
    return total_count, where_clause


async def delete_malformed_positions(conn, dry_run=True):
    """Delete rows with malformed position names"""
    
    total_count, where_clause = await identify_malformed_positions(conn)
    
    if total_count == 0:
        print("✅ No malformed positions found. Nothing to delete.")
        return
    
    if dry_run:
        print("\n⚠️  DRY RUN MODE - No rows will be deleted.")
        print("   Run with --execute flag to actually delete the rows.")
        return
    
    print(f"\n🗑️  Deleting {total_count:,} rows with malformed positions...")
    
    deleted = await conn.execute(f"""
        DELETE FROM political_dynasties
        WHERE position IS NOT NULL 
          AND position <> ''
          AND ({where_clause})
    """)
    
    print(f"✅ Deleted {deleted.split()[-1]} rows with malformed positions.")


async def main():
    load_dotenv()
    
    import sys
    dry_run = '--execute' not in sys.argv
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        await delete_malformed_positions(conn, dry_run=dry_run)
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())


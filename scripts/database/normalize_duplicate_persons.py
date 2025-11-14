#!/usr/bin/env python3
"""
Normalize duplicate persons in political_dynasties table.
For each group of duplicates (same normalized_name), keeps the best entry
and merges relationships, then deletes duplicates.
"""

import asyncio
import asyncpg
import os
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

def load_env_from_dotenv():
    """Load environment variables from .env file"""
    env_path = Path(__file__).parent.parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)

async def normalize_duplicates(dry_run=True, limit=None):
    """Normalize duplicate persons
    
    Args:
        dry_run: If True, only report what would be done without making changes
        limit: If set, only process this many duplicate groups
    """
    load_env_from_dotenv()
    load_dotenv()
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB', 'dynasty')
    )
    
    try:
        # Find duplicate groups
        print("🔍 Finding duplicate groups...")
        query = """
            SELECT normalized_name, COUNT(*) as count,
                   STRING_AGG(id::text, ',' ORDER BY id) as ids
            FROM political_dynasties
            WHERE normalized_name IS NOT NULL
            GROUP BY normalized_name
            HAVING COUNT(*) > 1
            ORDER BY COUNT(*) DESC
        """
        if limit:
            query += f" LIMIT {limit}"
        
        duplicate_groups = await conn.fetch(query)
        print(f"📊 Found {len(duplicate_groups)} duplicate groups\n")
        
        total_merged = 0
        total_deleted = 0
        
        for i, group in enumerate(duplicate_groups):
            normalized_name = group['normalized_name']
            count = group['count']
            ids = [int(x) for x in group['ids'].split(',')]
            
            if (i + 1) % 1000 == 0:
                print(f"  Processing group {i+1}/{len(duplicate_groups)}... (merged: {total_merged}, deleted: {total_deleted})", flush=True)
            
            # Get all entries for this group
            entries = await conn.fetch("""
                SELECT id, first_name, last_name, nickname, position, year, province, municipality_city
                FROM political_dynasties
                WHERE id = ANY($1::int[])
                ORDER BY 
                    CASE WHEN position IS NOT NULL AND position != 'UNKNOWN' THEN 0 ELSE 1 END,
                    CASE WHEN year IS NOT NULL THEN 0 ELSE 1 END,
                    id ASC
            """, ids)
            
            if len(entries) < 2:
                continue
            
            # Keep the first entry (best one based on ordering)
            keep_entry = entries[0]
            keep_id = keep_entry['id']
            merge_ids = [e['id'] for e in entries[1:]]
            
            if dry_run:
                total_merged += len(merge_ids)
            else:
                # Update relationships pointing to merged entries
                for merge_id in merge_ids:
                    # Update person_id
                    await conn.execute("""
                        UPDATE relationships
                        SET person_id = $1
                        WHERE person_id = $2
                    """, keep_id, merge_id)
                    
                    # Update related_person_id
                    await conn.execute("""
                        UPDATE relationships
                        SET related_person_id = $1
                        WHERE related_person_id = $2
                    """, keep_id, merge_id)
                
                # Delete duplicate entries
                await conn.execute("""
                    DELETE FROM political_dynasties
                    WHERE id = ANY($1::int[])
                """, merge_ids)
                
                total_deleted += len(merge_ids)
        
        if dry_run:
            print(f"\n📊 DRY RUN SUMMARY:")
            print(f"   Would merge: {total_merged:,} duplicate entries")
            print(f"   Would keep: {len(duplicate_groups):,} unique persons")
            print(f"\n   To actually perform the merge, run with --execute")
        else:
            print(f"\n✅ NORMALIZATION COMPLETE:")
            print(f"   Merged: {total_merged:,} duplicate entries")
            print(f"   Deleted: {total_deleted:,} duplicate entries")
            print(f"   Kept: {len(duplicate_groups):,} unique persons")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    import sys
    
    dry_run = True
    limit = None
    
    if '--execute' in sys.argv:
        dry_run = False
    
    if not dry_run:
        print("⚠️  This will DELETE duplicate entries.")
        print("   Starting normalization in 3 seconds...")
        import time
        time.sleep(3)
    
    asyncio.run(normalize_duplicates(dry_run=dry_run, limit=limit))

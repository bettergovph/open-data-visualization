#!/usr/bin/env python3
"""
Normalize contractor names in dynasty database.
For each group of duplicates (same normalized name), keeps the best entry
and merges references, then updates all related tables.
"""

import asyncio
import asyncpg
import os
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from collections import defaultdict

def load_env_from_dotenv():
    """Load environment variables from .env file"""
    env_path = Path(__file__).parent.parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)

def normalize_contractor_name(name: str) -> str:
    """Normalize contractor name for comparison"""
    if not name:
        return ""
    # Remove extra spaces, convert to uppercase
    normalized = ' '.join(name.upper().split())
    # Remove common variations
    normalized = normalized.replace('.', '')
    normalized = normalized.replace(',', '')
    normalized = normalized.replace('&', 'AND')
    # Normalize common suffixes
    normalized = normalized.replace(' INCORPORATED', ' INC')
    normalized = normalized.replace(' CORP.', ' CORP')
    normalized = normalized.replace(' CORPORATION', ' CORP')
    normalized = normalized.replace('  ', ' ')
    return normalized.strip()

async def normalize_contractors(dry_run=True):
    """Normalize duplicate contractor names
    
    Args:
        dry_run: If True, only report what would be done without making changes
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
        print("🔍 Finding duplicate contractor names in politician_contractors...")
        
        # Get all contractor names with counts
        all_names = await conn.fetch("""
            SELECT contractor_name, COUNT(*) as cnt
            FROM politician_contractors
            GROUP BY contractor_name
        """)
        
        # Group by normalized name
        groups = defaultdict(list)
        for row in all_names:
            normalized = normalize_contractor_name(row['contractor_name'])
            groups[normalized].append((row['contractor_name'], row['cnt']))
        
        # Find groups with multiple variants
        duplicate_groups = {k: v for k, v in groups.items() if len(v) > 1}
        
        print(f"📊 Found {len(duplicate_groups)} duplicate groups\n")
        
        total_updated = 0
        total_deleted = 0
        
        for i, (normalized, variants) in enumerate(sorted(duplicate_groups.items(), key=lambda x: sum(c for _, c in x[1]), reverse=True)):
            if (i + 1) % 10 == 0:
                print(f"  Processing group {i+1}/{len(duplicate_groups)}... (updated: {total_updated}, deleted: {total_deleted})", flush=True)
            
            # Choose canonical (most common, or longest if tie)
            canonical = max(variants, key=lambda v: (v[1], len(v[0])))
            canonical_name = canonical[0]
            others = [v[0] for v in variants if v[0] != canonical_name]
            
            if dry_run:
                print(f"   Group: '{normalized}'")
                print(f"     Canonical: '{canonical_name}' ({canonical[1]} entries)")
                for other_name in others:
                    other_cnt = next(v[1] for v in variants if v[0] == other_name)
                    print(f"     Merge: '{other_name}' ({other_cnt} entries)")
                    total_updated += other_cnt
            else:
                # Update all references to use canonical name
                for other_name in others:
                    # Get all politician_contractors entries with other_name
                    entries = await conn.fetch("""
                        SELECT politician_id, contractor_name
                        FROM politician_contractors
                        WHERE contractor_name = $1
                    """, other_name)
                    
                    for entry in entries:
                        # Check if canonical relationship already exists
                        exists = await conn.fetchval("""
                            SELECT id FROM politician_contractors
                            WHERE politician_id = $1 AND contractor_name = $2
                        """, entry['politician_id'], canonical_name)
                        
                        if exists:
                            # Delete duplicate
                            await conn.execute("""
                                DELETE FROM politician_contractors
                                WHERE politician_id = $1 AND contractor_name = $2
                            """, entry['politician_id'], other_name)
                            total_deleted += 1
                        else:
                            # Update to canonical
                            await conn.execute("""
                                UPDATE politician_contractors
                                SET contractor_name = $1
                                WHERE politician_id = $2 AND contractor_name = $3
                            """, canonical_name, entry['politician_id'], other_name)
                            total_updated += 1
                    
                    # Update other tables (no unique constraints to worry about)
                    await conn.execute("""
                        UPDATE contractor_dynasty_matches
                        SET company_name = $1
                        WHERE UPPER(TRIM(company_name)) = UPPER(TRIM($2))
                    """, canonical_name, other_name)
                    
                    await conn.execute("""
                        UPDATE company_affiliations
                        SET company_name = $1
                        WHERE UPPER(TRIM(company_name)) = UPPER(TRIM($2))
                    """, canonical_name, other_name)
                    
                    await conn.execute("""
                        UPDATE contractors_organizations
                        SET organization_name = $1
                        WHERE UPPER(TRIM(organization_name)) = UPPER(TRIM($2))
                    """, canonical_name, other_name)
        
        if dry_run:
            print(f"\n📊 DRY RUN SUMMARY:")
            print(f"   Would update: {total_updated:,} contractor name references")
            print(f"   Would delete: ~{total_deleted:,} duplicate entries")
            print(f"   Would normalize: {len(duplicate_groups):,} duplicate groups")
            print(f"\n   To actually perform the normalization, run with --execute")
        else:
            print(f"\n✅ NORMALIZATION COMPLETE:")
            print(f"   Updated: {total_updated:,} contractor name references")
            print(f"   Deleted: {total_deleted:,} duplicate entries")
            print(f"   Normalized: {len(duplicate_groups):,} duplicate groups")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    import sys
    
    dry_run = True
    if '--execute' in sys.argv:
        dry_run = False
    
    if not dry_run:
        print("⚠️  This will UPDATE contractor names across multiple tables.")
        print("   Starting normalization in 3 seconds...")
        import time
        time.sleep(3)
    
    asyncio.run(normalize_contractors(dry_run=dry_run))

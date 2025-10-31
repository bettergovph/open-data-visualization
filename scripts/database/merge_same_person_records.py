#!/usr/bin/env python3
"""
Merge records that represent the same person.
Handles:
1. Same canonical first + last name, with/without suffix (e.g., Ferdinand Marcos vs Ferdinand Marcos Jr)
2. Same canonical name with/without middle names
3. Creates a unified_person_id for tracking
"""

import asyncio
import asyncpg
import os
from typing import Dict, List, Set
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


async def ensure_unified_person_table(conn):
    """Create unified_person_id column and mapping table"""
    
    # Add unified_person_id column
    try:
        await conn.execute('''
            ALTER TABLE political_dynasties
            ADD COLUMN IF NOT EXISTS unified_person_id INTEGER
        ''')
    except Exception as e:
        print(f"   Note: unified_person_id column may already exist: {e}")
    
    # Create unified_persons table to track merged identities
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS unified_persons (
            id SERIAL PRIMARY KEY,
            canonical_name TEXT NOT NULL,
            primary_first_name TEXT NOT NULL,
            primary_last_name TEXT NOT NULL,
            primary_suffix TEXT,
            nickname TEXT,
            variant_names TEXT[],  -- Array of all name variations
            total_records INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(canonical_name)
        )
    ''')


async def identify_person_groups(conn) -> Dict[str, List[Dict]]:
    """
    Identify groups of records that likely represent the same person.
    Groups by:
    1. Same canonical_first_name + last_name (ignoring suffix)
    2. Similar province/region
    """
    print("🔍 Identifying potential same-person groups...")
    
    # Get all records with canonical names
    records = await conn.fetch('''
        SELECT id, first_name, last_name, canonical_first_name, canonical_name, suffix,
               province, region, position, year, nickname
        FROM political_dynasties
        WHERE canonical_name IS NOT NULL
        ORDER BY canonical_first_name, last_name, suffix
    ''')
    
    # Group by base canonical name (without suffix)
    groups = {}
    for record in records:
        # Extract base name (without suffix)
        base_name = f"{record['canonical_first_name']} {record['last_name']}"
        
        if base_name not in groups:
            groups[base_name] = []
        
        groups[base_name].append({
            'id': record['id'],
            'first_name': record['first_name'],
            'last_name': record['last_name'],
            'canonical_first': record['canonical_first_name'],
            'canonical_name': record['canonical_name'],
            'suffix': record['suffix'],
            'province': record['province'],
            'region': record['region'],
            'position': record['position'],
            'year': record['year'],
            'nickname': record['nickname']
        })
    
    # Filter to groups with multiple records or suffix variations
    same_person_groups = {}
    for base_name, group_records in groups.items():
        # If multiple records OR has suffix variations, it's a candidate
        if len(group_records) > 1:
            # Check if they have different suffixes (e.g., no suffix vs JR)
            suffixes = set(r['suffix'] or '' for r in group_records)
            if len(suffixes) > 1 or len(group_records) > 1:
                same_person_groups[base_name] = group_records
    
    print(f"   Found {len(same_person_groups)} base names with multiple records or suffix variations")
    print(f"   Total records in groups: {sum(len(v) for v in same_person_groups.values())}")
    
    return same_person_groups


async def create_unified_persons(conn, groups: Dict[str, List[Dict]]):
    """Create unified_person entries and assign unified_person_id to records"""
    print("📝 Creating unified person identities...")
    
    unified_count = 0
    
    for base_name, records in groups.items():
        # Determine primary canonical name (prefer one with suffix if available)
        primary_record = records[0]
        for r in records:
            if r['suffix']:
                primary_record = r
                break
        
        # Collect all name variations
        variants = []
        for r in records:
            variant = f"{r['first_name']} {r['last_name']}"
            if r['suffix']:
                variant += f" {r['suffix']}"
            variants.append(variant)
            if r['nickname']:
                variants.append(r['nickname'])
        
        variants = list(set(variants))  # Remove duplicates
        
        # Create unified_person entry
        unified_id = await conn.fetchval('''
            INSERT INTO unified_persons (
                canonical_name, primary_first_name, primary_last_name,
                primary_suffix, nickname, variant_names, total_records
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (canonical_name) 
            DO UPDATE SET 
                variant_names = unified_persons.variant_names || EXCLUDED.variant_names,
                total_records = unified_persons.total_records + EXCLUDED.total_records
            RETURNING id
        ''',
            primary_record['canonical_name'],
            primary_record['canonical_first'],
            primary_record['last_name'],
            primary_record['suffix'],
            primary_record['nickname'],
            variants,
            len(records)
        )
        
        # Update all records with unified_person_id
        for r in records:
            await conn.execute('''
                UPDATE political_dynasties
                SET unified_person_id = $1
                WHERE id = $2
            ''', unified_id, r['id'])
        
        unified_count += 1
        
        if unified_count % 100 == 0:
            print(f"   Progress: {unified_count}/{len(groups)}...")
    
    print(f"   ✅ Created {unified_count} unified person identities")


async def generate_merge_report(groups: Dict[str, List[Dict]], output_file: str = 'person_merge_report.txt'):
    """Generate a report of merged persons"""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("PERSON MERGE REPORT\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Found {len(groups)} person groups with multiple records/variations\n\n")
        
        # Sort by number of records
        sorted_groups = sorted(groups.items(), key=lambda x: len(x[1]), reverse=True)
        
        for base_name, records in sorted_groups[:100]:  # Top 100
            f.write(f"Base Name: {base_name}\n")
            f.write(f"  Records: {len(records)}\n")
            
            # Group by canonical name
            canonical_groups = {}
            for r in records:
                canonical = r['canonical_name']
                if canonical not in canonical_groups:
                    canonical_groups[canonical] = []
                canonical_groups[canonical].append(r)
            
            for canonical, recs in canonical_groups.items():
                f.write(f"    Canonical: {canonical} ({len(recs)} records)\n")
                for rec in recs[:3]:  # Show first 3 examples
                    f.write(f"      - {rec['first_name']} {rec['last_name']}")
                    if rec['suffix']:
                        f.write(f" {rec['suffix']}")
                    f.write(f" (ID: {rec['id']}, Year: {rec['year']})\n")
            f.write("\n")
    
    print(f"   📄 Report saved to: {output_file}")


async def main():
    load_env_from_dotenv()
    load_dotenv()
    
    conn = await get_dynasty_conn()
    
    try:
        print("=" * 80)
        print("MERGE SAME-PERSON RECORDS")
        print("=" * 80)
        print()
        
        # Ensure tables exist
        print("📋 Setting up unified person tables...")
        await ensure_unified_person_table(conn)
        print("   ✅ Tables ready")
        print()
        
        # Identify groups
        groups = await identify_person_groups(conn)
        print()
        
        if groups:
            # Generate report
            await generate_merge_report(groups)
            print()
            
            # Create unified persons
            await create_unified_persons(conn, groups)
            print()
        
        # Summary
        stats = await conn.fetchrow('''
            SELECT 
                COUNT(*) as total_records,
                COUNT(DISTINCT unified_person_id) as unique_persons,
                COUNT(unified_person_id) as records_with_unified_id
            FROM political_dynasties
        ''')
        
        unified_stats = await conn.fetchrow('''
            SELECT COUNT(*) as total_unified
            FROM unified_persons
        ''')
        
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total records: {stats['total_records']:,}")
        print(f"Records with unified_person_id: {stats['records_with_unified_id']:,}")
        print(f"Unique unified persons: {stats['unique_persons']:,}")
        print(f"Unified person entries: {unified_stats['total_unified']:,}")
        print()
        print("✅ Person merging complete!")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())


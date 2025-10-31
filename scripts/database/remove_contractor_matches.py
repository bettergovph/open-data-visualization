#!/usr/bin/env python3
"""
Remove all contractor-mediated connections from the database
and save the list of contractors for future review.
"""

import asyncio
import asyncpg
import json
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv


def load_env_from_dotenv():
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


async def get_db_connection():
    load_env_from_dotenv()
    load_dotenv()
    return await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
)


async def get_top_contractors(conn):
    """Get the top 15 contractors with their connection counts"""
    
    contractors = await conn.fetch("""
        SELECT 
            company_name,
            COUNT(DISTINCT dynasty_full_name) as connection_count,
            COUNT(*) as total_matches
        FROM contractor_dynasty_matches
        GROUP BY company_name
        ORDER BY connection_count DESC
        LIMIT 15
    """)
    
    return [dict(c) for c in contractors]


async def remove_contractor_matches():
    """Remove all contractor matches and save contractor list"""
    
    print("=" * 80)
    print("REMOVING CONTRACTOR-MEDIATED CONNECTIONS")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    conn = await get_db_connection()
    
    try:
        # Get contractors before deletion
        print("🔍 Fetching contractor list...")
        contractors = await get_top_contractors(conn)
        
        if not contractors:
            print("❌ No contractors found in database")
            return
        
        print(f"✅ Found {len(contractors)} contractors")
        print("\n📋 Contractors to be saved for review:")
        for i, c in enumerate(contractors, 1):
            print(f"   {i}. {c['company_name']} ({c['connection_count']} connections, {c['total_matches']} total matches)")
        
        # Get total count before deletion
        total_count = await conn.fetchval("""
            SELECT COUNT(*) FROM contractor_dynasty_matches
        """)
        
        print(f"\n📊 Total contractor_dynasty_matches records: {total_count}")
        
        # Confirm deletion
        print(f"\n⚠️  This will DELETE all {total_count} contractor_dynasty_matches records")
        print("   Press Ctrl+C within 5 seconds to cancel...")
        await asyncio.sleep(5)
        
        # Delete all contractor matches
        print(f"\n🗑️  Deleting contractor_dynasty_matches records...")
        deleted = await conn.execute("""
            DELETE FROM contractor_dynasty_matches
        """)
        
        print(f"✅ Deleted all contractor_dynasty_matches records")
        
        # Save contractors to JSON file for review
        contractors_data = {
            'removed_at': datetime.now().isoformat(),
            'total_contractors': len(contractors),
            'total_records_deleted': total_count,
            'contractors': [
                {
                    'company_name': c['company_name'],
                    'connection_count': c['connection_count'],
                    'total_matches': c['total_matches']
                }
                for c in contractors
            ]
        }
        
        output_file = 'CONTRACTORS_FOR_REVIEW.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(contractors_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Saved {len(contractors)} contractors to: {output_file}")
        
        # Also save as text file for easy reading
        text_file = 'CONTRACTORS_FOR_REVIEW.txt'
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("CONTRACTORS FOR REVIEW\n")
            f.write("=" * 80 + "\n")
            f.write(f"Removed from database: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total contractors: {len(contractors)}\n")
            f.write(f"Total records deleted: {total_count}\n\n")
            f.write("=" * 80 + "\n\n")
            
            for i, c in enumerate(contractors, 1):
                f.write(f"{i}. {c['company_name']}\n")
                f.write(f"   Connections: {c['connection_count']}\n")
                f.write(f"   Total matches: {c['total_matches']}\n\n")
        
        print(f"✅ Saved text list to: {text_file}")
        
        print(f"\n{'=' * 80}")
        print("SUMMARY")
        print(f"{'=' * 80}")
        print(f"✅ Deleted {total_count} contractor_dynasty_matches records")
        print(f"✅ Saved {len(contractors)} contractors for review")
        print(f"✅ Files created:")
        print(f"   - {output_file}")
        print(f"   - {text_file}")
        print(f"\n💡 Next steps:")
        print(f"   1. Review the contractor list")
        print(f"   2. Re-verify contractor officers with reliable sources")
        print(f"   3. Re-add verified matches only")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    load_env_from_dotenv()
    load_dotenv()
    asyncio.run(remove_contractor_matches())


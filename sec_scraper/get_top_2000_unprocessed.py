#!/usr/bin/env python3
"""
Generate contractor list of 2000 unprocessed contractors prioritized by project count
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def get_unprocessed_contractors():
    """Get contractors without SEC data, prioritized by project count"""
    print("🚀 Querying contractors without SEC data...")
    
    # Connect to SEC database
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database='sec'
    )
    
    try:
        # First, let's check the counts
        stats = await conn.fetchrow('''
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN sec_number IS NOT NULL AND sec_number != '' THEN 1 END) as with_sec,
                COUNT(CASE WHEN (sec_number IS NULL OR sec_number = '') AND status = 'NO_SEC_RESULTS' THEN 1 END) as no_results,
                COUNT(CASE WHEN (sec_number IS NULL OR sec_number = '') AND (status IS NULL OR status != 'NO_SEC_RESULTS') THEN 1 END) as unprocessed
            FROM contractors
        ''')
        
        print(f"📈 Database statistics:")
        print(f"   • Total contractors: {stats['total']}")
        print(f"   • With SEC data: {stats['with_sec']}")
        print(f"   • No SEC results found: {stats['no_results']}")
        print(f"   • Unprocessed (never searched): {stats['unprocessed']}")
        print()
        
        # Get contractors without SEC data (excluding those already searched with no results)
        contractors = await conn.fetch('''
            SELECT contractor_name, project_count, status
            FROM contractors
            WHERE (sec_number IS NULL OR sec_number = '')
              AND (status IS NULL OR status != 'NO_SEC_RESULTS')
            ORDER BY project_count DESC NULLS LAST, contractor_name
            LIMIT 2000
        ''')
        
        print(f"📊 Found {len(contractors)} unprocessed contractors")
        
        # Write to file
        output_file = 'sec_scraper/contractor_list_top2000_unprocessed.txt'
        with open(output_file, 'w', encoding='utf-8') as f:
            for contractor in contractors:
                f.write(f"{contractor['contractor_name']}\n")
        
        print(f"✅ Generated {output_file}")
        print(f"\nTop 10 by project count:")
        for i, contractor in enumerate(contractors[:10], 1):
            project_count = contractor['project_count'] or 0
            print(f"   {i}. {contractor['contractor_name']} ({project_count} projects)")
        
        # Stats
        with_projects = sum(1 for c in contractors if c['project_count'] and c['project_count'] > 0)
        without_projects = len(contractors) - with_projects
        
        print(f"\n📈 Statistics:")
        print(f"   • With project data: {with_projects}")
        print(f"   • Without project data: {without_projects}")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(get_unprocessed_contractors())


#!/usr/bin/env python3
"""
Consolidate duplicate contractor entries in sec.contractors
Combine sources for contractors that appear multiple times
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv('.env')

async def main():
    print("🚀 Starting SEC contractors consolidation...\n")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database='sec'
    )
    
    # Find all duplicate contractor names
    duplicates = await conn.fetch('''
        SELECT contractor_name, 
               array_agg(id ORDER BY id) as ids,
               array_agg(source ORDER BY id) as sources,
               array_agg(sec_number ORDER BY id) as sec_numbers,
               COUNT(*) as count
        FROM contractors
        GROUP BY contractor_name
        HAVING COUNT(*) > 1
    ''')
    
    print(f"📊 Found {len(duplicates)} contractors with duplicates\n")
    
    consolidated = 0
    deleted = 0
    
    for dup in duplicates:
        contractor_name = dup['contractor_name']
        ids = dup['ids']
        sources = dup['sources']
        sec_numbers = dup['sec_numbers']
        
        # Keep the first ID, combine sources, delete others
        keep_id = ids[0]
        
        # Combine unique sources
        unique_sources = []
        for src in sources:
            if src and src != 'unknown' and src not in unique_sources:
                unique_sources.append(src)
        
        combined_source = ', '.join(sorted(unique_sources)) if unique_sources else 'unknown'
        
        # Find the best SEC data (prefer entries with SEC numbers)
        best_sec_number = None
        for sec_num in sec_numbers:
            if sec_num:
                best_sec_number = sec_num
                break
        
        # Update the first entry with combined source
        await conn.execute('''
            UPDATE contractors 
            SET source = $1
            WHERE id = $2
        ''', combined_source, keep_id)
        
        # Delete other entries
        for delete_id in ids[1:]:
            await conn.execute('DELETE FROM contractors WHERE id = $1', delete_id)
            deleted += 1
        
        consolidated += 1
        
        if consolidated % 100 == 0:
            print(f"   Progress: {consolidated}/{len(duplicates)} contractors consolidated...")
    
    print(f"\n✅ Consolidation complete!")
    print(f"   • Consolidated: {consolidated} contractors")
    print(f"   • Deleted: {deleted} duplicate entries\n")
    
    # Show updated source distribution
    sources = await conn.fetch('''
        SELECT source, COUNT(*) as count
        FROM contractors
        WHERE source IS NOT NULL
        GROUP BY source
        ORDER BY count DESC
        LIMIT 20
    ''')
    
    print('📊 Updated source distribution:')
    for row in sources:
        print(f'   {row["source"]}: {row["count"]:,}')
    
    total = await conn.fetchval('SELECT COUNT(*) FROM contractors')
    print(f'\nTotal unique contractors: {total:,}')
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())


#!/usr/bin/env python3
"""
Consolidate duplicate contractor names in sec.contractors
Merge SEC data and source flags, keep the most complete entry
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv('.env')

async def main():
    print("🚀 Consolidating duplicate contractors in sec.contractors...\n")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database='sec'
    )
    
    # Find duplicates
    duplicates = await conn.fetch('''
        SELECT contractor_name, COUNT(*) as count
        FROM contractors
        GROUP BY contractor_name
        HAVING COUNT(*) > 1
        ORDER BY count DESC, contractor_name
    ''')
    
    print(f"📊 Found {len(duplicates)} contractor names with duplicates\n")
    
    consolidated = 0
    for dup in duplicates:
        name = dup['contractor_name']
        count = dup['count']
        
        # Get all entries for this contractor
        entries = await conn.fetch('''
            SELECT id, sec_number, date_registered, status, address, 
                   has_flood, has_dime, has_philgeps, project_count
            FROM contractors
            WHERE contractor_name = $1
            ORDER BY id
        ''', name)
        
        print(f"🔧 {name} ({count} entries)")
        
        # Merge data: combine all boolean flags and keep best SEC data
        merged_flood = any(e['has_flood'] for e in entries if e['has_flood'] is not None)
        merged_dime = any(e['has_dime'] for e in entries if e['has_dime'] is not None)
        merged_philgeps = any(e['has_philgeps'] for e in entries if e['has_philgeps'] is not None)
        
        # Keep the entry with SEC data if available, otherwise keep first
        best_entry = None
        for e in entries:
            if e['sec_number']:
                best_entry = e
                break
        if not best_entry:
            best_entry = entries[0]
        
        max_project_count = max((e['project_count'] or 0) for e in entries)
        
        # Update the best entry with merged data
        await conn.execute('''
            UPDATE contractors
            SET has_flood = $1,
                has_dime = $2,
                has_philgeps = $3,
                project_count = $4
            WHERE id = $5
        ''', merged_flood, merged_dime, merged_philgeps, max_project_count, best_entry['id'])
        
        # Delete other entries
        other_ids = [e['id'] for e in entries if e['id'] != best_entry['id']]
        if other_ids:
            await conn.execute('''
                DELETE FROM contractors
                WHERE id = ANY($1)
            ''', other_ids)
            
            print(f"   ✓ Kept ID {best_entry['id']}, deleted {len(other_ids)} duplicates")
            print(f"   → Merged flags: F:{merged_flood} D:{merged_dime} P:{merged_philgeps}")
            consolidated += 1
    
    await conn.close()
    
    print(f"\n✅ Consolidation complete!")
    print(f"   Contractors consolidated: {consolidated}")
    print(f"   Duplicate entries removed: {sum(d['count'] - 1 for d in duplicates)}")
    
    # Verify uniqueness
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database='sec'
    )
    
    remaining_dups = await conn.fetchval('''
        SELECT COUNT(*)
        FROM (
            SELECT contractor_name
            FROM contractors
            GROUP BY contractor_name
            HAVING COUNT(*) > 1
        ) AS dups
    ''')
    
    total_contractors = await conn.fetchval('SELECT COUNT(*) FROM contractors')
    
    await conn.close()
    
    print(f"\n📊 Final state:")
    print(f"   Total contractors: {total_contractors}")
    print(f"   Remaining duplicates: {remaining_dups}")
    
    if remaining_dups == 0:
        print(f"\n✅ All contractor names are now UNIQUE!")
    else:
        print(f"\n⚠️  Still have {remaining_dups} duplicates - investigate further")


if __name__ == "__main__":
    asyncio.run(main())


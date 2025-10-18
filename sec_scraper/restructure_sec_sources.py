#!/usr/bin/env python3
"""
Restructure sec.contractors to have boolean columns for each source
Instead of: source = 'flood, dime'
Use: has_flood = true, has_dime = true, has_philgeps = false
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv('.env')

async def main():
    print("🚀 Restructuring sec.contractors table...\n")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database='sec'
    )
    
    # Step 1: Add boolean columns for each source
    print("📊 Step 1: Adding source columns (has_flood, has_dime, has_philgeps)...")
    
    await conn.execute('ALTER TABLE contractors ADD COLUMN IF NOT EXISTS has_flood BOOLEAN DEFAULT false')
    await conn.execute('ALTER TABLE contractors ADD COLUMN IF NOT EXISTS has_dime BOOLEAN DEFAULT false')
    await conn.execute('ALTER TABLE contractors ADD COLUMN IF NOT EXISTS has_philgeps BOOLEAN DEFAULT false')
    
    print("✅ Added source columns\n")
    
    # Step 2: Populate the boolean columns based on current source field
    print("📊 Step 2: Populating source columns from existing source field...")
    
    contractors = await conn.fetch('SELECT id, source FROM contractors')
    
    updated = 0
    for contractor in contractors:
        contractor_id = contractor['id']
        source = contractor['source'] or ''
        source_lower = source.lower()
        
        has_flood = 'flood' in source_lower
        has_dime = 'dime' in source_lower
        has_philgeps = 'philgeps' in source_lower
        
        await conn.execute('''
            UPDATE contractors 
            SET has_flood = $1, has_dime = $2, has_philgeps = $3
            WHERE id = $4
        ''', has_flood, has_dime, has_philgeps, contractor_id)
        
        updated += 1
        if updated % 1000 == 0:
            print(f"   Progress: {updated}/{len(contractors)}...")
    
    print(f"✅ Updated {updated} contractors\n")
    
    # Step 3: Verify the new columns
    print("📊 Step 3: Verifying source distribution...")
    
    stats = await conn.fetchrow('''
        SELECT 
            COUNT(*) FILTER (WHERE has_flood AND NOT has_dime AND NOT has_philgeps) as flood_only,
            COUNT(*) FILTER (WHERE has_dime AND NOT has_flood AND NOT has_philgeps) as dime_only,
            COUNT(*) FILTER (WHERE has_philgeps AND NOT has_flood AND NOT has_dime) as philgeps_only,
            COUNT(*) FILTER (WHERE has_flood AND has_dime AND NOT has_philgeps) as flood_dime,
            COUNT(*) FILTER (WHERE has_flood AND has_philgeps AND NOT has_dime) as flood_philgeps,
            COUNT(*) FILTER (WHERE has_dime AND has_philgeps AND NOT has_flood) as dime_philgeps,
            COUNT(*) FILTER (WHERE has_flood AND has_dime AND has_philgeps) as all_three,
            COUNT(*) FILTER (WHERE has_flood) as total_flood,
            COUNT(*) FILTER (WHERE has_dime) as total_dime,
            COUNT(*) FILTER (WHERE has_philgeps) as total_philgeps,
            COUNT(*) as total
        FROM contractors
    ''')
    
    print("✅ Source distribution:")
    print(f"   🔵 Flood only:        {stats['flood_only']:,}")
    print(f"   🟢 DIME only:         {stats['dime_only']:,}")
    print(f"   🟡 PhilGEPS only:     {stats['philgeps_only']:,}")
    print(f"   🔵🟢 Flood + DIME:     {stats['flood_dime']:,}")
    print(f"   🔵🟡 Flood + PhilGEPS: {stats['flood_philgeps']:,}")
    print(f"   🟢🟡 DIME + PhilGEPS:  {stats['dime_philgeps']:,}")
    print(f"   🔵🟢🟡 All three:       {stats['all_three']:,}")
    print()
    print(f"   Total per source:")
    print(f"   🔵 Flood:    {stats['total_flood']:,}")
    print(f"   🟢 DIME:     {stats['total_dime']:,}")
    print(f"   🟡 PhilGEPS: {stats['total_philgeps']:,}")
    print(f"   Total unique: {stats['total']:,}")
    
    await conn.close()
    
    print("\n✅ Restructuring complete!")

if __name__ == '__main__':
    asyncio.run(main())


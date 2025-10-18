#!/usr/bin/env python3
"""
Clean up contractor names in the database:
- Remove double quotes
- Remove JSON fragments
- Fix malformed names
"""

import asyncio
import asyncpg
import os
import re
from dotenv import load_dotenv

load_dotenv()

async def clean_contractor_names():
    """Clean up malformed contractor names in the database"""
    print("🧹 Starting contractor name cleanup...")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
    )
    
    try:
        # Get all contractors with problematic names
        contractors = await conn.fetch(
            """
            SELECT id, contractor_name 
            FROM contractors 
            WHERE contractor_name LIKE '%"%' 
               OR contractor_name LIKE '%{%'
               OR contractor_name LIKE '%}%'
               OR contractor_name LIKE '%nameAbbreviation%'
               OR contractor_name LIKE '%logoUrl%'
            ORDER BY id
            """
        )
        
        print(f"📊 Found {len(contractors)} contractors with malformed names")
        
        cleaned = 0
        deleted = 0
        
        for contractor in contractors:
            contractor_id = contractor['id']
            name = contractor['contractor_name']
            original_name = name
            clean_name = None
            should_delete = False
            
            # Pattern 1: Full JSON object starting with {"id":
            if name.startswith('{"id":'):
                # Extract name from JSON
                match = re.search(r'"name":\s*"([^"]+)"', name)
                if match:
                    clean_name = match.group(1)
                else:
                    should_delete = True
            
            # Pattern 2: JSON fragments ending with ", "logoUrl": null}
            elif '", "logoUrl": null}' in name:
                clean_name = name.split('", "logoUrl": null}')[0]
                # Remove any leading quote or comma
                clean_name = clean_name.lstrip('",').strip()
            
            # Pattern 3: JSON fragments ending with ", "nameAbbreviation":
            elif '", "nameAbbreviation":' in name:
                clean_name = name.split('", "nameAbbreviation":')[0]
                # Remove any leading quote or comma
                clean_name = clean_name.lstrip('",').strip()
            
            # Pattern 4: Leading and trailing double quotes only
            elif name.startswith('"') and name.endswith('"') and name.count('"') == 2:
                clean_name = name.strip('"')
            
            # If we have a clean name, check if it already exists
            if clean_name and clean_name != name and len(clean_name) >= 3:
                # Check if this cleaned name already exists in the database
                existing = await conn.fetchval(
                    "SELECT id FROM contractors WHERE contractor_name = $1 AND id != $2",
                    clean_name,
                    contractor_id
                )
                
                if existing:
                    # Duplicate exists, delete this malformed one
                    await conn.execute("DELETE FROM contractors WHERE id = $1", contractor_id)
                    deleted += 1
                    if len(original_name) > 60:
                        print(f"   ❌ Deleted duplicate ID {contractor_id}: '{original_name[:60]}...' (duplicate of ID {existing})")
                    else:
                        print(f"   ❌ Deleted duplicate ID {contractor_id}: '{original_name}' (duplicate of ID {existing})")
                else:
                    # No duplicate, update the name
                    await conn.execute(
                        "UPDATE contractors SET contractor_name = $1 WHERE id = $2",
                        clean_name,
                        contractor_id
                    )
                    cleaned += 1
                    if len(original_name) > 60:
                        print(f"   ✅ Cleaned ID {contractor_id}: '{original_name[:60]}...' -> '{clean_name}'")
                    else:
                        print(f"   ✅ Cleaned ID {contractor_id}: '{original_name}' -> '{clean_name}'")
            
            # If we should delete (can't parse), delete it
            elif should_delete:
                await conn.execute("DELETE FROM contractors WHERE id = $1", contractor_id)
                deleted += 1
                print(f"   ❌ Deleted ID {contractor_id}: {original_name[:80]}...")
        
        print(f"\n✅ Cleanup complete:")
        print(f"   • Cleaned: {cleaned}")
        print(f"   • Deleted: {deleted}")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(clean_contractor_names())


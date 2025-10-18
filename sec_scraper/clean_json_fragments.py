#!/usr/bin/env python3
"""
Clean JSON fragments from contractor names in the database
Handles patterns like:
- . CONTRACTOR NAME)", "nameAbbreviation": "...", "logoUrl": null}
- ", "nameAbbreviation": "...", "logoUrl": null}
- / CONTRACTOR NAME", "nameAbbreviation": "...", "logoUrl": null}
"""

import asyncio
import asyncpg
import os
import re
from dotenv import load_dotenv

load_dotenv('.env')

async def clean_json_fragments():
    """Clean JSON fragments from contractor names."""
    print("🧹 Starting JSON fragment cleanup...")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
    )
    
    try:
        # Find contractors with JSON fragments
        contractors = await conn.fetch(
            """
            SELECT id, contractor_name 
            FROM contractors 
            WHERE contractor_name LIKE '%nameAbbreviation%' 
               OR contractor_name LIKE '%logoUrl%'
               OR contractor_name LIKE '%}%'
            """
        )
        
        print(f"📊 Found {len(contractors)} contractors with JSON fragments")
        
        cleaned = 0
        deleted = 0
        skipped = 0
        
        for contractor in contractors:
            contractor_id = contractor['id']
            name = contractor['contractor_name']
            original_name = name
            clean_name = None
            should_delete = False
            
            # Pattern 1: Starts with ", " and ends with JSON fragment
            # Example: ", "nameAbbreviation": "CCASC/MCADCF", "logoUrl": null}
            if name.startswith('", '):
                # This is pure garbage - delete it
                should_delete = True
            
            # Pattern 2: Starts with ". " or "/ " and contains contractor name before JSON
            # Example: . C.R. DOMINGO CONSTRUCTION, INC.)", "nameAbbreviation": "6BCC/CDCAPDIFCDCI", "logoUrl": null}
            elif ('", "nameAbbreviation":' in name or '", "logoUrl":' in name):
                # Extract text before the JSON fragment
                match = re.match(r'^[./\s]*(.*?)["\']\s*,\s*["\']nameAbbreviation', name)
                if not match:
                    match = re.match(r'^[./\s]*(.*?)["\']\s*,\s*["\']logoUrl', name)
                
                if match:
                    extracted = match.group(1).strip()
                    # Remove trailing characters like ) or "
                    extracted = re.sub(r'[)"\'\s]+$', '', extracted)
                    extracted = extracted.strip()
                    
                    if len(extracted) >= 3:
                        clean_name = extracted
                    else:
                        should_delete = True
                else:
                    # Can't parse - delete
                    should_delete = True
            
            # Pattern 3: Just ends with }
            elif name.endswith('}'):
                # Try to extract anything before the first quote or JSON marker
                parts = re.split(r'["\'{]', name)
                if parts and len(parts[0].strip()) >= 3:
                    clean_name = parts[0].strip().rstrip('.,/)')
                else:
                    should_delete = True
            
            # If we should delete, delete it
            if should_delete:
                await conn.execute("DELETE FROM contractors WHERE id = $1", contractor_id)
                deleted += 1
                if len(original_name) > 60:
                    print(f"   ❌ Deleted ID {contractor_id}: '{original_name[:60]}...'")
                else:
                    print(f"   ❌ Deleted ID {contractor_id}: '{original_name}'")
            
            # If we have a clean name, check if it already exists
            elif clean_name and clean_name != name:
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
                        print(f"   ✅ Cleaned ID {contractor_id}: '{original_name[:60]}...' → '{clean_name}'")
                    else:
                        print(f"   ✅ Cleaned ID {contractor_id}: '{original_name}' → '{clean_name}'")
            else:
                skipped += 1
                if skipped <= 10:
                    print(f"   ⚠️  Skipped ID {contractor_id}: {original_name[:80]}...")
        
        print(f"\n✅ Cleanup complete:")
        print(f"   • Cleaned: {cleaned}")
        print(f"   • Deleted: {deleted}")
        print(f"   • Skipped: {skipped}")
        
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(clean_json_fragments())


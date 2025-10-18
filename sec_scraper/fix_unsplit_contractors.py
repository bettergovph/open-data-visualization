#!/usr/bin/env python3
"""
Fix unsplit contractor names and remove invalid entries
"""

import asyncpg
import asyncio
import os
from dotenv import load_dotenv
import re

load_dotenv('.env')

COMMON_WORDS = {
    'SUPPLY', 'CONSTRUCTION', 'BUILDERS', 'TRADING', 'ENTERPRISE', 'ENTERPRISES',
    'INC', 'CORP', 'CORPORATION', 'CO', 'COMPANY', 'LTD', 'LIMITED',
    'THE', 'AND', 'FOR', 'OF', 'GENERAL', 'SERVICES', 'DEVELOPMENT'
}

def split_contractor(name):
    """Split contractor name into new and former names"""
    results = []
    
    # Pattern 1: "NEW NAME (FORMERLY OLD NAME)" - extract both, remove parentheses
    match = re.search(r'^(.+?)\s*\(\s*(?:FORMERLY|FORMER|PREVIOUSLY|PREV)[\s:]*(.+?)\s*\)(.*)$', name, re.IGNORECASE)
    if match:
        new_name = (match.group(1) + ' ' + match.group(3)).strip()
        old_name = match.group(2).strip()
        # Clean old name further
        old_name = re.sub(r'^[:.\s]+', '', old_name)
        
        if new_name and len(new_name) > 10:
            results.append(new_name)
        if old_name and len(old_name) > 10:
            results.append(old_name)
        
        return results
    
    # Pattern 2: "NEW NAME FORMERLY OLD NAME" (no parens)
    match = re.search(r'^(.+?)\s+(?:FORMERLY|FORMER|PREVIOUSLY|PREV)[\s:]+(.+)$', name, re.IGNORECASE)
    if match:
        new_name = match.group(1).strip()
        old_name = match.group(2).strip()
        
        if new_name and len(new_name) > 10:
            results.append(new_name)
        if old_name and len(old_name) > 10:
            results.append(old_name)
        
        return results
    
    # Pattern 3: JV with "/" 
    if '/' in name:
        parts = name.split('/')
        for part in parts:
            part = part.strip()
            # Remove any parenthetical content
            part = re.sub(r'\s*\([^)]*\)', '', part)
            part = part.strip()
            if part and len(part) > 10:
                results.append(part)
        
        return results
    
    # No splitting needed
    return [name]

def is_valid_name(name):
    """Check if contractor name is valid"""
    # Too short
    if len(name) < 5:
        return False
    
    # JSON fragment
    if '", "' in name or 'logoUrl' in name or 'nameAbbreviation' in name:
        return False
    
    words = name.split()
    
    # Single word that's common
    if len(words) == 1 and name.upper() in COMMON_WORDS:
        return False
    
    # All words are common
    if len(words) > 0:
        non_common = [w for w in words if w.upper() not in COMMON_WORDS]
        if len(non_common) == 0:
            return False
    
    return True

async def main():
    print("🔧 Fixing unsplit contractors and removing invalid entries...\n")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
    )
    
    # Get all contractors
    contractors = await conn.fetch('SELECT id, contractor_name, source, sec_number FROM contractors ORDER BY id')
    
    split_count = 0
    deleted_count = 0
    
    for row in contractors:
        contractor_id = row['id']
        name = row['contractor_name']
        source = row['source']
        sec_number = row['sec_number']
        
        # Check if needs splitting
        split_names = split_contractor(name)
        
        if len(split_names) > 1:
            # This contractor needs to be split
            print(f"🔧 Splitting ID {contractor_id}: {name[:70]}")
            
            added_any = False
            for split_name in split_names:
                # Check if this name already exists
                existing = await conn.fetchval(
                    'SELECT id FROM contractors WHERE contractor_name = $1',
                    split_name
                )
                
                if existing:
                    print(f"   ✓ Already exists: {split_name[:60]}")
                else:
                    # Insert new split name
                    await conn.execute('''
                        INSERT INTO contractors (contractor_name, source, former_id)
                        VALUES ($1, $2, $3)
                    ''', split_name, source, contractor_id)
                    print(f"   ➕ Added: {split_name[:60]}")
                    added_any = True
            
            # Delete original unsplit entry (only if we added new ones AND it has no SEC data)
            if added_any and not sec_number:
                # First, update any contractors that reference this as former_id
                await conn.execute('''
                    UPDATE contractors 
                    SET former_id = NULL 
                    WHERE former_id = $1
                ''', contractor_id)
                
                # Now delete the original
                await conn.execute('DELETE FROM contractors WHERE id = $1', contractor_id)
                print(f"   🗑️ Deleted original unsplit entry")
                split_count += 1
            elif sec_number:
                print(f"   ⚠️ Kept original (has SEC data)")
            else:
                print(f"   ℹ️  Kept original (no new entries added)")
        
        elif not is_valid_name(name):
            # Invalid name - delete if no SEC data
            if not sec_number:
                await conn.execute('DELETE FROM contractors WHERE id = $1', contractor_id)
                print(f"❌ Deleted invalid ID {contractor_id}: {name[:70]}")
                deleted_count += 1
    
    await conn.close()
    
    print(f"\n✅ Cleanup complete:")
    print(f"   Split: {split_count}")
    print(f"   Deleted: {deleted_count}")

if __name__ == '__main__':
    asyncio.run(main())


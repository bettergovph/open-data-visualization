#!/usr/bin/env python3
"""
Clean DIME database contractor names - parse JSON objects and extract actual names
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
import json
import re

load_dotenv('.env')

def parse_json_contractor(name):
    """Parse contractor name if it's a JSON object"""
    if not name:
        return name
    
    # Check if it looks like JSON
    if '{' not in name and '"name"' not in name:
        return name  # Not JSON, return as-is
    
    try:
        # Try to parse as complete JSON
        data = json.loads(name)
        if isinstance(data, dict) and 'name' in data:
            cleaned = data['name']
            print(f"  ✓ Parsed: {name[:50]}... -> {cleaned}")
            return cleaned
    except:
        pass
    
    # Try to extract from JSON fragment patterns
    # Pattern: {"id": 123, "name": "CONTRACTOR NAME", ...
    match = re.search(r'"name"\s*:\s*"([^"]+)"', name)
    if match:
        cleaned = match.group(1)
        print(f"  ✓ Extracted: {name[:50]}... -> {cleaned}")
        return cleaned
    
    # Pattern: {"id": 123, "name": "CONTRACTOR NAME (no closing quote/brace)
    match = re.search(r'"name"\s*:\s*"([^"]+)$', name)
    if match:
        cleaned = match.group(1)
        print(f"  ✓ Extracted (fragment): {name[:50]}... -> {cleaned}")
        return cleaned
    
    print(f"  ⚠ Could not parse: {name[:80]}")
    return name  # Return original if can't parse


async def main():
    print("🚀 Starting DIME database contractor cleanup...\n")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DIME', 'dime')
    )
    
    # Get all projects with contractors
    projects = await conn.fetch('''
        SELECT id, contractors
        FROM projects
        WHERE contractors IS NOT NULL
        AND array_length(contractors, 1) > 0
    ''')
    
    print(f"📊 Found {len(projects)} projects with contractors\n")
    
    updated_count = 0
    json_found = 0
    
    for project in projects:
        project_id = project['id']
        contractors = project['contractors']
        
        # Check if any contractor is JSON
        has_json = any('{' in c or '"name"' in c for c in contractors if c)
        
        if has_json:
            json_found += 1
            print(f"\n🔧 Project {project_id} has JSON contractors:")
            
            # Parse each contractor
            cleaned_contractors = []
            for contractor in contractors:
                if contractor:
                    cleaned = parse_json_contractor(contractor)
                    cleaned_contractors.append(cleaned)
                else:
                    cleaned_contractors.append(contractor)
            
            # Update the project
            await conn.execute('''
                UPDATE projects
                SET contractors = $1
                WHERE id = $2
            ''', cleaned_contractors, project_id)
            
            updated_count += 1
            
            if updated_count % 10 == 0:
                print(f"\n📊 Progress: {updated_count} projects updated...")
    
    await conn.close()
    
    print(f"\n✅ Cleanup completed!")
    print(f"   Projects checked: {len(projects)}")
    print(f"   Projects with JSON: {json_found}")
    print(f"   Projects updated: {updated_count}")
    print(f"\n💡 DIME contractors are now clean text instead of JSON objects")


if __name__ == "__main__":
    asyncio.run(main())


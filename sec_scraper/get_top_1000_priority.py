#!/usr/bin/env python3
"""
Generate top 1000 contractors prioritized by:
1. CLTG contractors first
2. Contractors without SEC data
3. Most projects first
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
import re

load_dotenv('.env')

def clean_for_ahk(name):
    """Clean contractor name for AHK search"""
    if not name:
        return ""
    
    # Remove symbols that might cause AHK issues
    cleaned = name.replace('.', '')
    cleaned = cleaned.replace(',', '')
    cleaned = cleaned.replace("'", '')
    cleaned = cleaned.replace('"', '')
    cleaned = cleaned.replace('&', '')
    cleaned = cleaned.replace('(', '')
    cleaned = cleaned.replace(')', '')
    cleaned = cleaned.replace('/', '')
    cleaned = cleaned.replace(':', '')
    cleaned = cleaned.replace('-', ' ')
    
    # Clean up extra spaces
    cleaned = ' '.join(cleaned.split())
    
    return cleaned.strip()


async def main():
    print("🚀 Generating top 1000 priority contractors list...\n")
    
    # Connect to SEC database
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database='sec'
    )
    
    # Get all contractors prioritized by:
    # 1. CLTG first (name contains CLTG)
    # 2. No SEC data
    # 3. Most projects
    contractors = await conn.fetch('''
        SELECT contractor_name, project_count, sec_number
        FROM contractors
        ORDER BY 
            CASE WHEN contractor_name ILIKE '%cltg%' THEN 0 ELSE 1 END,
            CASE WHEN sec_number IS NULL OR sec_number = '' THEN 0 ELSE 1 END,
            project_count DESC NULLS LAST,
            contractor_name
        LIMIT 1000
    ''')
    
    await conn.close()
    
    print(f"✅ Found {len(contractors)} contractors")
    print(f"\nTop 10 preview:")
    for i, contractor in enumerate(contractors[:10], 1):
        has_sec = "✓ SEC" if contractor['sec_number'] else "✗ No SEC"
        print(f"  {i}. {contractor['contractor_name'][:50]:50s} | Projects: {contractor['project_count'] or 0:4d} | {has_sec}")
    
    # Write to file for AHK
    with open('sec_scraper/contractor_list_top1000.txt', 'w', encoding='utf-8') as f:
        for contractor in contractors:
            name = contractor['contractor_name']
            cleaned_name = clean_for_ahk(name)
            if cleaned_name and len(cleaned_name) > 2:
                f.write(f"{cleaned_name}\n")
    
    print(f"\n✅ Wrote {len(contractors)} contractors to sec_scraper/contractor_list_top1000.txt")
    print(f"   CLTG contractors prioritized at the top!")
    print(f"   Then contractors without SEC data")
    print(f"   Then by project count (most projects first)")


if __name__ == "__main__":
    asyncio.run(main())


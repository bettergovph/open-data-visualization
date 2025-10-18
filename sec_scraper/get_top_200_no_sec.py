#!/usr/bin/env python3
"""
Generate list of top 200 contractors without SEC data from philgeps.contractors
Prioritize: 1) Flood source, 2) Number of projects
"""

import asyncpg
import asyncio
import os
from dotenv import load_dotenv
import re

load_dotenv('.env')

def clean_for_ahk(name):
    """Clean for AHK search - ONLY remove symbols for SEC frontend compatibility
    
    Do NOT fix database issues here - that's the sync scripts' job
    This function only makes names SEC-search-friendly
    """
    # Remove symbols that cause issues in SEC search frontend
    # Remove: . , ' " & ( ) / :
    cleaned = re.sub(r'[.,\'\"&()/:]+', ' ', name)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

async def main():
    print("📊 Fetching contractors from philgeps.contractors database...")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
    )
    
    # Get contractors without SEC data
    # Join with project_contractors to get actual project counts
    contractors = await conn.fetch('''
        SELECT 
            c.contractor_name,
            c.source,
            COUNT(DISTINCT pc.project_id) as project_count
        FROM contractors c
        LEFT JOIN project_contractors pc ON c.contractor_name = pc.contractor_name
        WHERE (c.sec_number IS NULL OR c.sec_number = '')
          AND c.status IS DISTINCT FROM 'NO_SEC_RESULTS'
        GROUP BY c.contractor_name, c.source
        ORDER BY 
            CASE WHEN c.source LIKE '%flood%' THEN 0 ELSE 1 END,
            COUNT(DISTINCT pc.project_id) DESC
        LIMIT 200
    ''')
    
    await conn.close()
    
    print(f"✅ Found {len(contractors)} contractors without SEC data")
    
    if contractors:
        print(f"\n📋 Top 10:")
        for i, row in enumerate(contractors[:10], 1):
            print(f"   {i}. {row['contractor_name'][:60]:60} ({row['project_count']:3} projects, source: {row['source']})")
        
        print(f"\n   ...")
        print(f"   200. {contractors[-1]['contractor_name'][:60]:60} ({contractors[-1]['project_count']:3} projects, source: {contractors[-1]['source']})")
    
    # Clean names for AHK (minimal cleaning)
    cleaned_contractors = []
    for row in contractors:
        cleaned = clean_for_ahk(row['contractor_name'])
        if cleaned and len(cleaned) > 3:
            cleaned_contractors.append(cleaned)
    
    # Write to file
    output_file = 'sec_scraper/contractor_list_top200_no_sec.txt'
    with open(output_file, 'w') as f:
        f.write('contractors := ["' + '", "'.join(cleaned_contractors) + '"]\n')
    
    print(f"\n✅ Generated {output_file}")
    print(f"   {len(cleaned_contractors)} contractors ready for AHK scraping")

if __name__ == '__main__':
    asyncio.run(main())

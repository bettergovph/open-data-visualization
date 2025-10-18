#!/usr/bin/env python3
"""
Generate list of top 200 contractors without SEC data
Prioritize: 1) Flood contractors, 2) Number of projects
"""

import requests
import asyncpg
import asyncio
import os
from dotenv import load_dotenv
import re

load_dotenv('.env')

def is_joint_venture(contractor_name):
    """Check if contractor name indicates a joint venture"""
    if not contractor_name:
        return False
    return '/' in contractor_name or ' & ' in contractor_name or ' AND ' in contractor_name.upper()

def split_joint_venture(contractor_name):
    """Split JV contractor names into individual contractors
    
    Only split on clear JV indicators (/), NOT on & or AND which are part of company names
    """
    if not contractor_name:
        return []
    
    # Remove former names first
    base_name = re.sub(r'\s*\([^)]*formerly[^)]*\)', '', contractor_name, flags=re.IGNORECASE)
    base_name = re.sub(r'\s*\([^)]*former[^)]*\)', '', base_name, flags=re.IGNORECASE)
    
    # ONLY split on / (forward slash) as clear JV indicator
    # Do NOT split on & or AND as they are part of company names like "ABC & SONS CONSTRUCTION"
    if '/' in base_name:
        parts = base_name.split('/')
    else:
        # Not a JV, return as-is
        parts = [base_name]
    
    # Clean each part
    cleaned = []
    for part in parts:
        part = part.strip()
        # Remove trailing symbols only
        part = re.sub(r'[.,\'"]+$', '', part)
        part = re.sub(r'^[.,\'"]+', '', part)
        # Filter out single words or very short names (likely extraction errors)
        if part and len(part) > 10:  # Minimum 10 chars for valid company name
            cleaned.append(part)
    
    return cleaned

async def get_flood_contractors():
    """Get all contractors from flood data with their project counts"""
    print("📊 Fetching flood control contractors from MeiliSearch...")
    
    meili_addr = os.getenv('MEILI_HTTP_ADDR', 'localhost:7700')
    if ':' in meili_addr:
        meilisearch_host, meilisearch_port = meili_addr.split(':')
    else:
        meilisearch_host = 'localhost'
        meilisearch_port = '7700'
    
    meilisearch_key = os.getenv('MEILI_MASTER_KEY', '')
    
    url = f"http://{meilisearch_host}:{meilisearch_port}/indexes/bettergov_flood_control/documents"
    
    headers = {}
    if meilisearch_key:
        headers['Authorization'] = f'Bearer {meilisearch_key}'
    
    all_projects = []
    offset = 0
    limit = 1000
    
    while True:
        response = requests.get(f"{url}?offset={offset}&limit={limit}", headers=headers)
        if not response.ok:
            print(f"⚠️  MeiliSearch request failed: {response.status_code}")
            break
        
        data = response.json()
        results = data.get('results', [])
        
        if not results:
            break
        
        all_projects.extend(results)
        offset += len(results)
        
        if len(results) < limit:
            break
    
    print(f"✅ Found {len(all_projects)} flood control projects")
    
    # Count projects per contractor
    contractor_counts = {}
    for project in all_projects:
        contractor_name = project.get('Contractor')
        if not contractor_name or not contractor_name.strip():
            continue
        
        # Split JVs
        individual_contractors = split_joint_venture(contractor_name)
        for contractor in individual_contractors:
            if contractor:
                contractor_counts[contractor] = contractor_counts.get(contractor, 0) + 1
    
    print(f"✅ Found {len(contractor_counts)} unique flood contractors")
    return contractor_counts

async def get_existing_sec_contractors():
    """Get contractors that already have SEC data or were searched"""
    print("📊 Fetching existing SEC contractors from database...")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
    )
    
    # Get all contractors with SEC data or NO_SEC_RESULTS status
    contractors = await conn.fetch('''
        SELECT contractor_name 
        FROM contractors 
        WHERE sec_number IS NOT NULL 
           OR status = 'NO_SEC_RESULTS'
    ''')
    
    await conn.close()
    
    existing = set(row['contractor_name'] for row in contractors)
    print(f"✅ Found {len(existing)} contractors already processed")
    return existing

def clean_contractor_name(name):
    """Clean contractor name for AHK script (remove symbols)"""
    # Remove symbols that might cause issues
    cleaned = re.sub(r'[.,&\'"()]+', ' ', name)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

async def main():
    # Get flood contractors with project counts
    flood_contractors = await get_flood_contractors()
    
    # Get existing SEC contractors
    existing_sec = await get_existing_sec_contractors()
    
    # Filter out contractors already processed
    missing_sec = {}
    for contractor, count in flood_contractors.items():
        if contractor not in existing_sec:
            missing_sec[contractor] = count
    
    print(f"\n📊 Contractors without SEC data: {len(missing_sec)}")
    
    # Sort by project count (descending) and take top 200
    sorted_contractors = sorted(missing_sec.items(), key=lambda x: x[1], reverse=True)[:200]
    
    print(f"📋 Selected top 200 contractors by project count")
    print(f"   Top contractor: {sorted_contractors[0][0]} ({sorted_contractors[0][1]} projects)")
    print(f"   200th contractor: {sorted_contractors[-1][0]} ({sorted_contractors[-1][1]} projects)")
    
    # Clean names for AHK
    cleaned_contractors = []
    for contractor, count in sorted_contractors:
        cleaned = clean_contractor_name(contractor)
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


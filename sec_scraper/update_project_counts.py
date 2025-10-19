#!/usr/bin/env python3
"""
Update project_count in sec.contractors by counting projects across all sources:
- Flood (MeiliSearch)
- DIME (PostgreSQL)
- PhilGEPS (PostgreSQL contracts)
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
import requests
from collections import Counter

load_dotenv('.env')

async def main():
    print("🚀 Updating project counts for all contractors...\n")
    
    # Track project counts by contractor
    project_counts = Counter()
    
    # 1. Count from Flood (MeiliSearch)
    print("📊 Counting projects from Flood (MeiliSearch)...")
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
    
    offset = 0
    limit = 1000
    flood_projects = 0
    
    while True:
        response = requests.get(f"{url}?offset={offset}&limit={limit}", headers=headers)
        if not response.ok:
            print(f"⚠️  MeiliSearch request failed: {response.status_code}")
            break
        
        data = response.json()
        results = data.get('results', [])
        
        if not results:
            break
        
        for project in results:
            contractor_name = project.get('Contractor')
            if contractor_name and contractor_name.strip():
                # Count for this contractor (we'll match to cleaned names later)
                project_counts[contractor_name.strip()] += 1
                flood_projects += 1
        
        offset += len(results)
        
        if len(results) < limit:
            break
    
    print(f"   ✅ Flood: {flood_projects} projects from {len(project_counts)} unique contractors")
    
    # 2. Count from DIME
    print("📊 Counting projects from DIME...")
    dime_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DIME', 'dime')
    )
    
    dime_projects_raw = await dime_conn.fetch('''
        SELECT unnest(contractors) as contractor_name
        FROM projects
        WHERE contractors IS NOT NULL
    ''')
    
    await dime_conn.close()
    
    dime_projects = 0
    for row in dime_projects_raw:
        contractor_name = row['contractor_name']
        if contractor_name and contractor_name.strip():
            project_counts[contractor_name.strip()] += 1
            dime_projects += 1
    
    print(f"   ✅ DIME: {dime_projects} project-contractor links")
    
    # 3. Count from PhilGEPS
    print("📊 Counting projects from PhilGEPS...")
    philgeps_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
    )
    
    philgeps_contracts = await philgeps_conn.fetch('''
        SELECT awardee_name
        FROM contracts
        WHERE awardee_name IS NOT NULL
    ''')
    
    await philgeps_conn.close()
    
    philgeps_projects = 0
    for row in philgeps_contracts:
        contractor_name = row['awardee_name']
        if contractor_name and contractor_name.strip():
            project_counts[contractor_name.strip()] += 1
            philgeps_projects += 1
    
    print(f"   ✅ PhilGEPS: {philgeps_projects} contracts")
    
    print(f"\n📊 Total raw project counts: {sum(project_counts.values())}")
    print(f"   Unique raw contractor names: {len(project_counts)}\n")
    
    # 4. Now match raw contractor names to sec.contractors and update counts
    print("📊 Matching to sec.contractors and updating project counts...")
    
    sec_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database='sec'
    )
    
    # Get all contractors from sec
    sec_contractors = await sec_conn.fetch('SELECT id, contractor_name FROM contractors')
    
    # Import the cleaning and matching functions
    import sys
    sys.path.insert(0, 'sec_scraper')
    from sync_flood_contractors import (
        parse_json_contractor_name, split_joint_venture, 
        is_valid_contractor_name, normalize_contractor_name
    )
    import re
    
    def clean_contractor_name(name):
        """Apply all cleaning logic"""
        if not name:
            return ""
        
        cleaned = parse_json_contractor_name(name)
        cleaned = cleaned.strip()
        cleaned = cleaned.lstrip('. /')
        cleaned = cleaned.rstrip('. /')
        cleaned = re.sub(r'\s*\(?\s*(FOR\.?|FORMERLY?\.?|PREV\.?)\s*$', '', cleaned, flags=re.IGNORECASE).strip()
        return cleaned
    
    # For each raw contractor name, clean it and match to sec.contractors
    contractor_project_map = {}  # sec.contractor_name -> total_projects
    
    for raw_name, count in project_counts.items():
        # Split if JV
        individual_contractors = split_joint_venture(raw_name)
        
        for contractor_data in individual_contractors:
            contractor_name = contractor_data['name']
            cleaned = clean_contractor_name(contractor_name)
            
            if not cleaned or not is_valid_contractor_name(cleaned):
                continue
            
            # Find matching sec contractor
            matched = None
            normalized_search = normalize_contractor_name(cleaned)
            
            for sec_contractor in sec_contractors:
                sec_name = sec_contractor['contractor_name']
                normalized_sec = normalize_contractor_name(sec_name)
                
                # Exact match or very close match
                if normalized_sec == normalized_search:
                    matched = sec_name
                    break
                
                # Partial match for longer names
                if len(normalized_sec) >= 10 and len(normalized_search) >= 10:
                    if normalized_sec in normalized_search or normalized_search in normalized_sec:
                        matched = sec_name
                        break
            
            if matched:
                contractor_project_map[matched] = contractor_project_map.get(matched, 0) + count
    
    print(f"   ✅ Matched {len(contractor_project_map)} contractors with project counts")
    
    # 5. Update sec.contractors with the counts
    print("\n📝 Updating project counts in sec.contractors...")
    updated = 0
    
    for contractor_name, total_projects in contractor_project_map.items():
        await sec_conn.execute('''
            UPDATE contractors
            SET project_count = $1
            WHERE contractor_name = $2
        ''', total_projects, contractor_name)
        updated += 1
        
        if updated % 1000 == 0:
            print(f"   Progress: {updated}/{len(contractor_project_map)}...")
    
    await sec_conn.close()
    
    print(f"   ✅ Updated {updated} contractors with project counts")
    
    # Show top 10
    print(f"\n📊 Top 10 contractors by project count:")
    top_10 = sorted(contractor_project_map.items(), key=lambda x: x[1], reverse=True)[:10]
    for i, (name, count) in enumerate(top_10, 1):
        print(f"   {i:2d}. {name[:50]:50s} {count:4d} projects")
    
    print(f"\n✅ Project count update complete!")


if __name__ == "__main__":
    asyncio.run(main())


#!/usr/bin/env python3
"""
Sync all sources (Flood, DIME, PhilGEPS) to sec.contractors using strict fuzzy matching
Populates has_flood, has_dime, has_philgeps boolean columns
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from difflib import SequenceMatcher
import requests
from sync_flood_contractors import parse_json_contractor_name, split_joint_venture, is_valid_contractor_name
import re

load_dotenv('.env')

def normalize_contractor_name(name):
    """Normalize contractor name for fuzzy matching"""
    if not name:
        return ""
    
    # Convert to uppercase
    normalized = name.upper().strip()
    
    # Remove common punctuation and extra spaces
    normalized = normalized.replace('.', ' ')
    normalized = normalized.replace(',', ' ')
    normalized = normalized.replace('-', ' ')
    normalized = normalized.replace('&', 'AND')
    normalized = normalized.replace('  ', ' ')
    normalized = normalized.strip()
    
    # Remove common suffixes for better matching
    suffixes_to_remove = [
        'CORPORATION', 'CORP', 'INC', 'INCORPORATED', 'CO', 'COMPANY',
        'LTD', 'LIMITED', 'ENTERPRISES', 'ENTERPRISE'
    ]
    
    words = normalized.split()
    filtered_words = [w for w in words if w not in suffixes_to_remove]
    
    return ' '.join(filtered_words) if filtered_words else normalized

def fuzzy_match(name1, name2, threshold=0.90):
    """Strict fuzzy matching with 90% similarity threshold"""
    if not name1 or not name2:
        return False
    
    # Exact match
    if name1 == name2:
        return True
    
    # Normalize both names
    norm1 = normalize_contractor_name(name1)
    norm2 = normalize_contractor_name(name2)
    
    if norm1 == norm2:
        return True
    
    # Use SequenceMatcher for fuzzy comparison (strict threshold)
    ratio = SequenceMatcher(None, norm1, norm2).ratio()
    return ratio >= threshold

def clean_contractor_name(name):
    """Apply all cleaning logic: JSON parsing, leading/trailing cleanup, incomplete FORMERLY removal"""
    if not name:
        return ""
    
    # Parse JSON if present
    cleaned = parse_json_contractor_name(name)
    # Clean leading/trailing junk
    cleaned = cleaned.strip()
    cleaned = cleaned.lstrip('. /')  # Remove leading dots, spaces, slashes
    cleaned = cleaned.rstrip('. /')  # Remove trailing dots, spaces, slashes
    # Remove incomplete FORMERLY/FOR patterns at the end
    cleaned = re.sub(r'\s*\(?\s*(FOR\.?|FORMERLY?\.?|PREV\.?)\s*$', '', cleaned, flags=re.IGNORECASE).strip()
    return cleaned


async def get_flood_contractors():
    """Get all contractors from MeiliSearch flood control data (with splitting and cleaning)"""
    print("📊 Fetching contractors from Flood Control (MeiliSearch)...")
    
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
    
    all_contractors = set()
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
        
        for project in results:
            contractor_name = project.get('Contractor')
            if contractor_name and contractor_name.strip():
                # Split JV and extract former names
                individual_contractors = split_joint_venture(contractor_name)
                
                for contractor_data in individual_contractors:
                    contractor = contractor_data['name']
                    if contractor and contractor.strip():
                        # Apply cleaning
                        cleaned = clean_contractor_name(contractor)
                        if cleaned and is_valid_contractor_name(cleaned):
                            all_contractors.add(cleaned)
        
        offset += len(results)
        
        if len(results) < limit:
            break
    
    print(f"✅ Found {len(all_contractors)} unique contractors in Flood (after splitting & cleaning)")
    return all_contractors

async def get_dime_contractors():
    """Get all contractors from DIME database (with splitting and cleaning)"""
    print("📊 Fetching contractors from DIME database...")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DIME', 'dime')
    )
    
    # Get contractors from DIME (stored as text array)
    contractors_raw = await conn.fetch('''
        SELECT DISTINCT unnest(contractors) as contractor_name
        FROM projects
        WHERE contractors IS NOT NULL
    ''')
    
    await conn.close()
    
    all_contractors = set()
    for row in contractors_raw:
        contractor_name = row['contractor_name']
        if contractor_name and contractor_name.strip():
            # Split JV and extract former names
            individual_contractors = split_joint_venture(contractor_name)
            
            for contractor_data in individual_contractors:
                contractor = contractor_data['name']
                if contractor and contractor.strip():
                    # Apply cleaning
                    cleaned = clean_contractor_name(contractor)
                    if cleaned and is_valid_contractor_name(cleaned):
                        all_contractors.add(cleaned)
    
    print(f"✅ Found {len(all_contractors)} unique contractors in DIME (after splitting & cleaning)")
    return all_contractors

async def get_philgeps_contractors():
    """Get all contractors from PhilGEPS contracts (with splitting and cleaning)"""
    print("📊 Fetching contractors from PhilGEPS contracts...")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
    )
    
    # Get awardee names from contracts
    contractors_raw = await conn.fetch('''
        SELECT DISTINCT awardee_name
        FROM contracts
        WHERE awardee_name IS NOT NULL
    ''')
    
    await conn.close()
    
    all_contractors = set()
    for row in contractors_raw:
        contractor_name = row['awardee_name']
        if contractor_name and contractor_name.strip():
            # Split JV and extract former names
            individual_contractors = split_joint_venture(contractor_name)
            
            for contractor_data in individual_contractors:
                contractor = contractor_data['name']
                if contractor and contractor.strip():
                    # Apply cleaning
                    cleaned = clean_contractor_name(contractor)
                    if cleaned and is_valid_contractor_name(cleaned):
                        all_contractors.add(cleaned)
    
    print(f"✅ Found {len(all_contractors)} unique contractors in PhilGEPS (after splitting & cleaning)")
    return all_contractors

async def main():
    print("🚀 Starting comprehensive source sync to SEC database...\n")
    print("📌 Extracting from raw sources with proper cleaning, JSON parsing, and JV splitting\n")
    
    # Fetch contractors from all raw sources with proper cleaning
    flood_contractors = await get_flood_contractors()
    dime_contractors = await get_dime_contractors()
    philgeps_contractors = await get_philgeps_contractors()
    
    print(f"\n📊 Total source contractors:")
    print(f"   Flood: {len(flood_contractors):,}")
    print(f"   DIME: {len(dime_contractors):,}")
    print(f"   PhilGEPS: {len(philgeps_contractors):,}\n")
    
    # Connect to SEC database
    sec_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database='sec'
    )
    
    # Get all contractors from SEC database
    sec_contractors = await sec_conn.fetch('SELECT id, contractor_name FROM contractors')
    
    print(f"📊 Processing {len(sec_contractors)} contractors in SEC database...\n")
    
    updated = 0
    flood_matches = 0
    dime_matches = 0
    philgeps_matches = 0
    
    for sec_contractor in sec_contractors:
        contractor_id = sec_contractor['id']
        contractor_name = sec_contractor['contractor_name']
        
        # Check for fuzzy matches in each source
        has_flood = False
        has_dime = False
        has_philgeps = False
        
        # Check Flood
        for flood_name in flood_contractors:
            if fuzzy_match(contractor_name, flood_name):
                has_flood = True
                break
        
        # Check DIME
        for dime_name in dime_contractors:
            if fuzzy_match(contractor_name, dime_name):
                has_dime = True
                break
        
        # Check PhilGEPS
        for philgeps_name in philgeps_contractors:
            if fuzzy_match(contractor_name, philgeps_name):
                has_philgeps = True
                break
        
        # Update the contractor
        await sec_conn.execute('''
            UPDATE contractors 
            SET has_flood = $1, has_dime = $2, has_philgeps = $3
            WHERE id = $4
        ''', has_flood, has_dime, has_philgeps, contractor_id)
        
        if has_flood:
            flood_matches += 1
        if has_dime:
            dime_matches += 1
        if has_philgeps:
            philgeps_matches += 1
        
        updated += 1
        if updated % 100 == 0:
            print(f"   Progress: {updated}/{len(sec_contractors)} (F:{flood_matches} D:{dime_matches} P:{philgeps_matches})...")
    
    print(f"\n✅ Updated {updated} contractors")
    print(f"   Flood matches: {flood_matches}")
    print(f"   DIME matches: {dime_matches}")
    print(f"   PhilGEPS matches: {philgeps_matches}\n")
    
    # Get final statistics
    stats = await sec_conn.fetchrow('''
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
            COUNT(*) FILTER (WHERE has_philgeps) as total_philgeps
        FROM contractors
    ''')
    
    print("📊 Final Venn Diagram Data:")
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
    
    await sec_conn.close()
    
    print("\n✅ Sync completed!")

if __name__ == '__main__':
    asyncio.run(main())


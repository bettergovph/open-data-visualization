#!/usr/bin/env python3
"""
Get top 100 contractors by project count that haven't been processed for SEC data yet.
Excludes contractors with NO_SEC_RESULTS status.
"""

import asyncio
import asyncpg
import os
import meilisearch
from dotenv import load_dotenv

load_dotenv('visualization.env')

async def get_top_100_no_sec():
    # Connect to MeiliSearch
    client = meilisearch.Client('http://localhost:7700')
    index = client.index('flood')
    
    # Get contractor project counts
    contractor_counts = {}
    offset = 0
    limit = 1000
    
    print('Loading contractors from MeiliSearch...')
    
    while True:
        try:
            # Use search with empty query to get all documents
            results = index.search('', {'limit': limit, 'offset': offset})
            documents = results.get('hits', [])
            
            if not documents:
                break
            
            for project in documents:
                contractor = project.get('Contractor', '').strip()
                if contractor and contractor.upper() not in ['UNKNOWN', 'N/A', '']:
                    contractor_counts[contractor] = contractor_counts.get(contractor, 0) + 1
            
            offset += limit
            if len(documents) < limit:
                break
                
            if offset % 5000 == 0:
                print(f'  Loaded {offset} projects...')
        except Exception as e:
            print(f'Error at offset {offset}: {e}')
            break
    
    print(f'\nTotal unique contractors found: {len(contractor_counts)}')
    
    # Get already processed contractors from database
    philgeps_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database='philgeps'
    )
    
    # Get contractors that already have SEC data (exclude NO_SEC_RESULTS)
    processed = await philgeps_conn.fetch('''
        SELECT DISTINCT contractor_name 
        FROM contractors
        WHERE sec_number IS NOT NULL
    ''')
    processed_names = {row['contractor_name'].strip() for row in processed}
    
    print(f'Already have SEC data: {len(processed_names)}')
    
    # Filter out already processed (those with SEC data)
    unprocessed = {k: v for k, v in contractor_counts.items() if k not in processed_names}
    
    print(f'Contractors without SEC data: {len(unprocessed)}')
    
    # Sort by project count and get top 100
    top_100 = sorted(unprocessed.items(), key=lambda x: x[1], reverse=True)[:100]
    
    print(f'\nTop 100 contractors without SEC data (by project count):')
    print('=' * 80)
    
    for i, (contractor, count) in enumerate(top_100, 1):
        print(f'{i:3}. {contractor[:60]:60} Projects: {count:4}')
    
    # Save to file for AHK script
    with open('sec_scraper/contractor_list_top100_no_sec.txt', 'w', encoding='utf-8') as f:
        f.write('contractors := [\n')
        for contractor, count in top_100:
            # Clean contractor name for AHK
            cleaned = contractor.replace('"', '').replace('.', '').replace('&', '').replace("'", '').strip()
            f.write(f'    "{cleaned}",\n')
        f.write(']\n')
    
    print(f'\n✅ Saved to sec_scraper/contractor_list_top100_no_sec.txt')
    
    await philgeps_conn.close()

if __name__ == "__main__":
    asyncio.run(get_top_100_no_sec())


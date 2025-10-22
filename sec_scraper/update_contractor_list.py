#!/usr/bin/env python3
"""
Simple script to update contractor_list_top2000_unprocessed.txt with fresh data from database
"""

import asyncio
import asyncpg
import os

async def update_contractor_list():
    """Update the contractor list with fresh data from database"""
    
    try:
        # Connect to database
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', 'wuQ5gBYCKkZiOGb61chLcByMu'),
            database=os.getenv('POSTGRES_DB_DIME', 'dime')
        )
        
        # Get unique contractors from projects table
        query = """
            SELECT DISTINCT unnest(contractors) as contractor_name
            FROM projects 
            WHERE contractors IS NOT NULL 
              AND array_length(contractors, 1) > 0
            ORDER BY contractor_name
        """
        
        all_contractors = await conn.fetch(query)
        await conn.close()
        
        # Check which contractors haven't been processed yet
        processed_files = set()
        if os.path.exists('sec_results'):
            for filename in os.listdir('sec_results'):
                if filename.endswith('.txt'):
                    # Remove .txt extension and convert back to contractor name
                    contractor_name = filename[:-4].replace('_', ' ')
                    processed_files.add(contractor_name)
        
        # Filter out already processed contractors
        unprocessed_contractors = []
        for contractor in all_contractors:
            contractor_name = contractor['contractor_name'].strip()
            if (contractor_name and len(contractor_name) > 2 and 
                contractor_name not in processed_files):
                unprocessed_contractors.append(contractor_name)
        
        # Limit to 2000 unprocessed contractors
        unprocessed_contractors = unprocessed_contractors[:2000]
        
        # Write to file
        with open('contractor_list_top2000_unprocessed.txt', 'w', encoding='utf-8') as f:
            for contractor_name in unprocessed_contractors:
                f.write(f"{contractor_name}\n")
        
        print(f"✅ Updated contractor list with {len(unprocessed_contractors)} unprocessed contractors")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(update_contractor_list())

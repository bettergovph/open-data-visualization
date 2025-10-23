#!/usr/bin/env python3
"""
Load contractors with 'no_results' status from parsed_sec_results.json
and mark them as 'NO_SEC_RESULTS' in the database.
"""

import asyncio
import os
import json
import asyncpg
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

async def get_db_connection():
    """Get PostgreSQL connection to SEC database"""
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_SEC', 'sec')
        )
        return conn
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return None

def load_parsed_results(file_path: str = "sec_scraper/parsed_sec_results.json"):
    """Load parsed SEC results from JSON file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading parsed results: {e}")
        return None

async def load_no_results_contractors():
    """Load contractors with no_results status and mark them as NO_SEC_RESULTS."""
    conn = await get_db_connection()
    if not conn:
        return
    
    try:
        print("🚀 Loading contractors with no SEC results...")
        
        # Load parsed results
        parsed_data = load_parsed_results()
        if not parsed_data:
            print("❌ Failed to load parsed results")
            return
        
        # Get contractors with no_results status
        no_results_contractors = []
        for contractor_name, contractor_data in parsed_data['contractors'].items():
            if contractor_data['status'] == 'no_results':
                no_results_contractors.append(contractor_name)
        
        print(f"Found {len(no_results_contractors)} contractors with no SEC results.")
        
        loaded_count = 0
        updated_count = 0
        not_found_count = 0
        
        for contractor_name in no_results_contractors:
            try:
                # Check if contractor exists in database
                existing = await conn.fetchrow(
                    'SELECT id, contractor_name FROM contractors WHERE contractor_name = $1', 
                    contractor_name
                )
                
                if existing:
                    # Update existing contractor with NO_SEC_RESULTS status
                    await conn.execute('''
                        UPDATE contractors 
                        SET status = 'NO_SEC_RESULTS', updated_at = $1
                        WHERE contractor_name = $2
                    ''', datetime.now(), contractor_name)
                    updated_count += 1
                else:
                    # Insert new contractor with NO_SEC_RESULTS status
                    await conn.execute('''
                        INSERT INTO contractors (contractor_name, status, created_at, updated_at)
                        VALUES ($1, 'NO_SEC_RESULTS', $2, $3)
                    ''', contractor_name, datetime.now(), datetime.now())
                    loaded_count += 1
                
                if (loaded_count + updated_count) % 100 == 0:
                    print(f"   Progress: {loaded_count + updated_count}/{len(no_results_contractors)} processed...")
                    
            except Exception as e:
                print(f"⚠️ Error processing {contractor_name}: {e}")
                not_found_count += 1
                continue
        
        print(f"\n✅ Loaded {loaded_count} new contractors with NO_SEC_RESULTS status.")
        print(f"📝 Updated {updated_count} existing contractors with NO_SEC_RESULTS status.")
        print(f"⚠️ {not_found_count} contractors not found in database.")
        
        # Get final statistics
        stats = await conn.fetchrow('''
            SELECT 
                COUNT(*) as total_contractors,
                COUNT(CASE WHEN sec_number IS NOT NULL AND sec_number != '' THEN 1 END) as with_sec_data,
                COUNT(CASE WHEN status = 'NO_SEC_RESULTS' THEN 1 END) as suspicious_no_results,
                COUNT(CASE WHEN status IS NULL THEN 1 END) as null_status
            FROM contractors
        ''')
        
        print(f"\n📊 Final Database Statistics:")
        print(f"  Total Contractors: {stats['total_contractors']:,}")
        print(f"  With SEC Data: {stats['with_sec_data']:,}")
        print(f"  Suspicious (NO_SEC_RESULTS): {stats['suspicious_no_results']:,}")
        print(f"  Null Status: {stats['null_status']:,}")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(load_no_results_contractors())

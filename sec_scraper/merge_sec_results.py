#!/usr/bin/env python3
"""
Merge new SEC results with existing contractor data.
This script adds new SEC data without destroying existing data.
"""

import asyncio
import asyncpg
import json
import os
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

def parse_date(date_str):
    """Parse date string to datetime object."""
    if not date_str:
        return None
    
    # Try different date formats
    formats = [
        "%B %d, %Y",  # "January 15, 2020"
        "%b %d, %Y",  # "Jan 15, 2020"
        "%Y-%m-%d",   # "2020-01-15"
        "%m/%d/%Y",   # "01/15/2020"
        "%d/%m/%Y",   # "15/01/2020"
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    
    return None

async def merge_contractors_to_db(conn, results):
    """Merge contractors from parsed results into database without destroying existing data."""
    companies = results.get("companies", [])
    
    if not companies:
        print("❌ No companies found in parsed results")
        return 0
    
    print(f"📊 Found {len(companies)} companies to merge")
    
    merged = 0
    skipped = 0
    errors = 0
    
    for company in companies:
        try:
            # Parse date
            date_registered = parse_date(company.get('date_registered'))
            
            # Insert or update contractor using ON CONFLICT
            await conn.execute('''
                INSERT INTO contractors (
                    contractor_name, sec_number, date_registered, status, 
                    address, secondary_licenses, source, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (sec_number) 
                DO UPDATE SET
                    contractor_name = EXCLUDED.contractor_name,
                    date_registered = EXCLUDED.date_registered,
                    status = EXCLUDED.status,
                    address = EXCLUDED.address,
                    secondary_licenses = EXCLUDED.secondary_licenses,
                    source = EXCLUDED.source,
                    updated_at = EXCLUDED.updated_at
                WHERE contractors.sec_number IS NOT NULL
            ''', 
                company.get('company_name', ''),
                company.get('sec_number', ''),
                date_registered,
                company.get('status', ''),
                company.get('address', ''),
                json.dumps(company.get('secondary_licenses', [])),
                'sec_scraper',
                datetime.now(),
                datetime.now()
            )
            
            merged += 1
            if merged % 100 == 0:
                print(f"   Progress: {merged}/{len(companies)}...")
                
        except Exception as e:
            errors += 1
            if "duplicate key" not in str(e).lower():
                print(f"⚠️  Error merging company '{company.get('company_name', 'Unknown')}': {e}")
            else:
                skipped += 1
    
    print(f"✅ Merged {merged} contractors successfully")
    print(f"📊 Skipped {skipped} duplicates")
    if errors > 0:
        print(f"⚠️  {errors} errors occurred")
    
    return merged

async def main():
    """Main function to merge parsed SEC results into database."""
    print("🚀 Merging new SEC results with existing contractor data...")
    
    # Load parsed results
    results = load_parsed_results()
    if not results:
        print("❌ Failed to load parsed results")
        return
    
    # Connect to database
    conn = await get_db_connection()
    if not conn:
        print("❌ Failed to connect to database")
        return
    
    try:
        # Get current count before merge
        current_count = await conn.fetchval('SELECT COUNT(*) FROM contractors')
        print(f"📊 Current contractors in database: {current_count:,}")
        
        # Merge contractors
        merged_count = await merge_contractors_to_db(conn, results)
        
        if merged_count > 0:
            # Get final count
            final_count = await conn.fetchval('SELECT COUNT(*) FROM contractors')
            print(f"\n✅ Successfully merged {merged_count} contractors!")
            print(f"📊 Total contractors in database: {final_count:,}")
            
            # Update statistics
            stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN sec_number IS NOT NULL AND sec_number != '' THEN 1 END) as with_sec,
                    COUNT(CASE WHEN sec_number IS NULL OR sec_number = '' THEN 1 END) as without_sec,
                    COUNT(CASE WHEN status = 'NO_SEC_RESULTS' THEN 1 END) as suspicious
                FROM contractors
            """)
            
            print(f"\n📊 Database Statistics:")
            print(f"   Total Contractors: {stats['total']:,}")
            print(f"   With SEC Data: {stats['with_sec']:,}")
            print(f"   Without SEC Data: {stats['without_sec']:,}")
            print(f"   Suspicious (No Results): {stats['suspicious']:,}")
        else:
            print("❌ No contractors were merged")
            
    except Exception as e:
        print(f"❌ Error merging data: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
Load parsed SEC results into the database.
This script takes the parsed_sec_results.json and loads it into the sec.contractors table.
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

def load_parsed_results(file_path: str = "parsed_sec_results.json"):
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

async def load_contractors_to_db(conn, results):
    """Load contractors from parsed results into database."""
    companies = results.get("companies", [])
    
    if not companies:
        print("❌ No companies found in parsed results")
        return 0
    
    print(f"📊 Found {len(companies)} companies to load")
    
    # Clear existing data first (optional - comment out if you want to keep existing data)
    print("🗑️  Clearing existing contractors...")
    await conn.execute("DELETE FROM contractors")
    print("✅ Cleared existing contractors")
    
    # Reset sequence
    await conn.execute("ALTER SEQUENCE contractors_id_seq RESTART WITH 1")
    
    loaded = 0
    errors = 0
    
    for company in companies:
        try:
            # Parse date
            date_registered = parse_date(company.get('date_registered'))
            
            # Insert contractor
            await conn.execute('''
                INSERT INTO contractors (
                    contractor_name, sec_number, date_registered, status, 
                    address, secondary_licenses, source, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
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
            
            loaded += 1
            if loaded % 100 == 0:
                print(f"   Progress: {loaded}/{len(companies)}...")
                
        except Exception as e:
            errors += 1
            print(f"⚠️  Error loading company '{company.get('company_name', 'Unknown')}': {e}")
    
    print(f"✅ Loaded {loaded} contractors successfully")
    if errors > 0:
        print(f"⚠️  {errors} errors occurred")
    
    return loaded

async def main():
    """Main function to load parsed SEC results into database."""
    print("🚀 Loading parsed SEC results into database...")
    
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
        # Load contractors
        loaded_count = await load_contractors_to_db(conn, results)
        
        if loaded_count > 0:
            print(f"\n✅ Successfully loaded {loaded_count} contractors into the database!")
            
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
            print("❌ No contractors were loaded")
            
    except Exception as e:
        print(f"❌ Error loading data: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())

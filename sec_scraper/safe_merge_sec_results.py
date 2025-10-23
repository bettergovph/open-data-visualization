#!/usr/bin/env python3
"""
Safely merge parsed SEC results into the PostgreSQL 'sec' database.
This script loads data from 'sec_scraper/parsed_sec_results.json'
and uses INSERT ... ON CONFLICT to safely update existing records or insert new ones.
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

async def safe_merge_parsed_results():
    """Safely merge parsed SEC results into the database using INSERT ... ON CONFLICT."""
    conn = await get_db_connection()
    if not conn:
        return
    
    try:
        print("🚀 Safely merging new SEC results with existing contractor data...")
        
        # Load parsed results
        parsed_data = load_parsed_results()
        if not parsed_data:
            print("❌ Failed to load parsed results")
            return
        
        # The parsed data structure has a 'companies' list directly
        companies_to_load = parsed_data.get('companies', [])
        
        print(f"Found {len(companies_to_load)} companies to merge into the database.")
        
        merged_count = 0
        updated_count = 0
        skipped_count = 0
        
        for company in companies_to_load:
            company_name = company.get("company_name")
            sec_number = company.get("sec_number")
            date_registered = company.get("date_registered")
            status = company.get("status")
            address = company.get("address")
            secondary_licenses = json.dumps(company.get("secondary_licenses", []))
            
            # Convert date_registered string to date object
            parsed_date = None
            if date_registered:
                for fmt in ["%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"]:
                    try:
                        parsed_date = datetime.strptime(date_registered, fmt).date()
                        break
                    except ValueError:
                        continue
            
            try:
                if sec_number and sec_number.strip():
                    # Check if contractor already exists
                    existing = await conn.fetchrow(
                        'SELECT id, sec_number FROM contractors WHERE sec_number = $1', 
                        sec_number
                    )
                    
                    if existing:
                        # Update existing record
                        await conn.execute('''
                            UPDATE contractors 
                            SET contractor_name = $1, date_registered = $2, status = $3, 
                                address = $4, secondary_licenses = $5, updated_at = $6
                            WHERE sec_number = $7
                        ''', company_name, parsed_date, status, address, secondary_licenses, 
                        datetime.now(), sec_number)
                        updated_count += 1
                    else:
                        # Insert new record
                        await conn.execute('''
                            INSERT INTO contractors (contractor_name, sec_number, date_registered, status, address, secondary_licenses, source, created_at, updated_at)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        ''', company_name, sec_number, parsed_date, status, address, secondary_licenses, 
                        'sec_scraper', datetime.now(), datetime.now())
                        merged_count += 1
                else:
                    # For records without an SEC number, just insert (they won't conflict)
                    await conn.execute('''
                        INSERT INTO contractors (contractor_name, sec_number, date_registered, status, address, secondary_licenses, source, created_at, updated_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ''', company_name, None, parsed_date, status, address, secondary_licenses, 
                    'sec_scraper', datetime.now(), datetime.now())
                    merged_count += 1
                    
            except Exception as e:
                print(f"⚠️  Error processing company '{company_name}' (SEC: {sec_number}): {e}")
                skipped_count += 1
            
            if (merged_count + updated_count + skipped_count) % 100 == 0:
                print(f"   Progress: {merged_count + updated_count + skipped_count}/{len(companies_to_load)} processed...")
        
        print(f"\n✅ Safely merged {merged_count} new contractors into the database.")
        print(f"📝 Updated {updated_count} existing contractors.")
        if skipped_count > 0:
            print(f"⚠️  Skipped {skipped_count} contractors due to errors.")
        
        # Get final statistics
        final_stats = await conn.fetchrow('''
            SELECT 
                COUNT(*) as total_contractors,
                COUNT(CASE WHEN sec_number IS NOT NULL AND sec_number != '' THEN 1 END) as with_sec_data,
                COUNT(CASE WHEN sec_number IS NULL OR sec_number = '' THEN 1 END) as without_sec_data,
                COUNT(CASE WHEN status = 'NO_SEC_RESULTS' THEN 1 END) as suspicious_no_results
            FROM contractors
        ''')
        
        print(f"\n📊 Final Database Statistics:")
        print(f"  Total Contractors: {final_stats['total_contractors']:,}")
        print(f"  With SEC Data: {final_stats['with_sec_data']:,}")
        print(f"  Without SEC Data: {final_stats['without_sec_data']:,}")
        print(f"  Suspicious (No Results): {final_stats['suspicious_no_results']:,}")
        
    except FileNotFoundError:
        print("❌ Error: 'sec_scraper/parsed_sec_results.json' not found. Please run parsing first.")
    except json.JSONDecodeError:
        print("❌ Error: Could not decode JSON from 'sec_scraper/parsed_sec_results.json'. Check file integrity.")
    except Exception as e:
        print(f"❌ An unexpected error occurred during database merge: {e}")
    finally:
        if conn:
            await conn.close()

async def main():
    await safe_merge_parsed_results()

if __name__ == "__main__":
    asyncio.run(main())

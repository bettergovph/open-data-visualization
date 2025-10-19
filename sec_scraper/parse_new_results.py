#!/usr/bin/env python3
"""
Parse only NEW SEC results that haven't been processed yet
Tracks processed files to avoid re-parsing
"""

import asyncio
import asyncpg
import os
import re
import chardet
import glob
from typing import List, Dict, Any
from dotenv import load_dotenv
from difflib import SequenceMatcher
from datetime import datetime

load_dotenv('.env')

def parse_date(date_str: str):
    """Parse date string to date object"""
    if not date_str or date_str == '--':
        return None
    
    try:
        # Try common formats
        for fmt in ['%B %d, %Y', '%b %d, %Y', '%Y-%m-%d', '%m/%d/%Y']:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except:
                continue
        return None
    except:
        return None

def detect_encoding(file_path: str) -> str:
    """Detect file encoding"""
    with open(file_path, 'rb') as f:
        raw_data = f.read()
        result = chardet.detect(raw_data)
        return result.get('encoding', 'utf-8')

def parse_sec_file(file_path: str) -> List[Dict[str, Any]]:
    """Parse SEC data from a single file"""
    encoding = detect_encoding(file_path)

    with open(file_path, 'r', encoding=encoding or 'utf-8', errors='ignore') as f:
        content = f.read()

    # Check for no results indicators
    if ('--' in content or 
        'Oops! No Record found' in content or 
        'Result/s Found: 0' in content or
        'Result/s Found: --' in content):
        return [{'status': 'NO_SEC_RESULTS'}]

    # Pattern to match company details
    company_pattern = r'COMPANY DETAILS\nCompany Name\n(.*?)\n\nSEC Number\n(.*?)\n\nDate Registered\n(.*?)\n\nStatus\n(.*?)\n\nAddress\n(.*?)\n\nSECONDARY LICENSE DETAILS'

    companies = []
    matches = re.findall(company_pattern, content, re.DOTALL)

    for match in matches:
        company_name = match[0].strip()
        sec_number = match[1].strip()
        date_registered_str = match[2].strip()
        status = match[3].strip()
        address = match[4].strip()

        # Parse date
        date_registered = parse_date(date_registered_str)
        
        # Clean up the data
        if status == '--':
            status = 'Unknown'
        if address == '--':
            address = None

        companies.append({
            'contractor_name': company_name,
            'sec_number': sec_number,
            'date_registered': date_registered,
            'status': status,
            'address': address
        })

    return companies

def calculate_similarity(str1: str, str2: str) -> float:
    """Calculate similarity ratio between two strings"""
    if not str1 or not str2:
        return 0.0
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

async def get_processed_files():
    """Get list of files that have already been successfully processed"""
    processed_file = 'sec_scraper/processed_files.txt'
    
    if not os.path.exists(processed_file):
        return set()
    
    with open(processed_file, 'r') as f:
        return set(line.strip() for line in f if line.strip())

async def mark_file_as_processed(filename: str):
    """Mark a file as successfully processed"""
    processed_file = 'sec_scraper/processed_files.txt'
    
    with open(processed_file, 'a') as f:
        f.write(f"{filename}\n")

async def update_contractor_with_sec_data(conn, sec_data: Dict[str, Any], search_term: str):
    """Update existing contractor with SEC data using fuzzy matching"""
    
    if sec_data.get('status') == 'NO_SEC_RESULTS':
        # Mark contractor as having no SEC results
        await conn.execute('''
            UPDATE contractors
            SET status = 'NO_SEC_RESULTS', updated_at = CURRENT_TIMESTAMP
            WHERE contractor_name ILIKE $1
        ''', f'%{search_term}%')
        return 'NO_RESULTS'
    
    sec_name = sec_data['contractor_name']
    sec_number = sec_data['sec_number']
    
    # Check if this SEC number already exists
    existing = await conn.fetchrow('''
        SELECT id, contractor_name 
        FROM contractors 
        WHERE sec_number = $1
    ''', sec_number)
    
    if existing:
        # Just update timestamps
        await conn.execute('''
            UPDATE contractors
            SET date_registered = $1, status = $2, address = $3, 
                updated_at = CURRENT_TIMESTAMP
            WHERE sec_number = $4
        ''', sec_data['date_registered'], sec_data['status'],
             sec_data['address'], sec_number)
        return 'UPDATED'
    
    # Find contractor by fuzzy matching against search term
    all_contractors = await conn.fetch('''
        SELECT id, contractor_name 
        FROM contractors 
        WHERE (sec_number IS NULL OR sec_number = '')
          AND has_flood = true
    ''')
    
    best_match = None
    best_ratio = 0.0
    
    # First try exact match on search term
    for db_contractor in all_contractors:
        db_name = db_contractor['contractor_name']
        
        # Exact match
        if db_name.upper() == search_term.upper():
            best_match = db_contractor
            best_ratio = 1.0
            break
        
        # Fuzzy match
        ratio = calculate_similarity(search_term, db_name)
        if ratio > best_ratio and ratio >= 0.85:
            best_ratio = ratio
            best_match = db_contractor
    
    if best_match:
        # Update the matched contractor
        await conn.execute('''
            UPDATE contractors
            SET sec_number = $1, date_registered = $2, status = $3, 
                address = $4, updated_at = CURRENT_TIMESTAMP
            WHERE id = $5
        ''', sec_number, sec_data['date_registered'], sec_data['status'],
             sec_data['address'], best_match['id'])
        return f"MATCHED ({best_ratio:.0%})"
    
    return 'NO_MATCH'

async def main():
    print("🚀 Parsing new SEC results...\n")
    
    # Get processed files
    processed_files = await get_processed_files()
    print(f"📊 Already processed: {len(processed_files)} files")
    
    # Find all SEC result files
    all_files = glob.glob('sec_scraper/sec_results/*.txt')
    print(f"📁 Total SEC files: {len(all_files)}")
    
    # Filter to only new files
    new_files = [f for f in all_files if os.path.basename(f) not in processed_files]
    print(f"📋 New files to parse: {len(new_files)}\n")
    
    if not new_files:
        print("✅ No new files to process!")
        return
    
    # Connect to SEC database
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database='sec'
    )
    
    updated = 0
    no_results = 0
    no_match = 0
    
    for file_path in new_files:
        filename = os.path.basename(file_path)
        
        # Extract search term from filename
        search_term = filename.replace('.txt', '').replace('_', ' ')
        
        # Parse the file
        companies = parse_sec_file(file_path)
        
        # Update database for each company found
        for company in companies:
            result = await update_contractor_with_sec_data(conn, company, search_term)
            
            if result == 'NO_RESULTS':
                no_results += 1
            elif result == 'NO_MATCH':
                no_match += 1
            else:
                updated += 1
        
        # Mark file as processed
        await mark_file_as_processed(filename)
        
        if (updated + no_results + no_match) % 50 == 0:
            print(f"   Progress: {updated} updated, {no_results} no results, {no_match} no match")
    
    await conn.close()
    
    print(f"\n✅ Parsing complete!")
    print(f"   Files processed: {len(new_files)}")
    print(f"   Contractors updated: {updated}")
    print(f"   No SEC results: {no_results}")
    print(f"   No match found: {no_match}")

if __name__ == '__main__':
    asyncio.run(main())


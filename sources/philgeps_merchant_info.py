#!/usr/bin/env python3
"""
PhilGEPS Merchant Information Scraper
Queries https://open.philgeps.gov.ph/analytics/load/merchantInfo
for contractor registration details using normalized contractor names from the database.
"""

import asyncio
import asyncpg
import os
import json
import re
import time
from typing import List, Dict, Optional
from datetime import datetime
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlencode

load_dotenv()


def normalize_contractor_name(name: str) -> str:
    """Normalize contractor name for searching"""
    if not name:
        return ""
    
    normalized = name.upper().strip()
    normalized = normalized.replace('.', ' ')
    normalized = normalized.replace(',', ' ')
    normalized = normalized.replace('-', ' ')
    normalized = normalized.replace('&', 'AND')
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    return normalized


async def get_normalized_contractors(limit: Optional[int] = None) -> List[Dict]:
    """
    Get normalized contractor names from the database.
    Returns list of dicts with contractor_name and normalized_name.
    """
    print("📊 Fetching normalized contractor names from database...")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_SEC', 'sec')
    )
    
    try:
        # Get unique contractor names from contractors table
        query = """
            SELECT DISTINCT contractor_name
            FROM contractors
            WHERE contractor_name IS NOT NULL
            AND contractor_name != ''
            ORDER BY contractor_name
        """
        
        if limit:
            query += f" LIMIT {limit}"
        
        rows = await conn.fetch(query)
        contractors = []
        
        for row in rows:
            contractor_name = row['contractor_name']
            normalized = normalize_contractor_name(contractor_name)
            if normalized:
                contractors.append({
                    'contractor_name': contractor_name,
                    'normalized_name': normalized
                })
        
        print(f"✅ Found {len(contractors)} contractors")
        return contractors
        
    finally:
        await conn.close()


def query_merchant_info(contractor_name: str, session: Optional[requests.Session] = None) -> Optional[Dict]:
    """
    Query PhilGEPS merchant info API for a contractor name.
    Returns dict with registration details or None if not found.
    """
    if not session:
        session = requests.Session()
    
    base_url = "https://open.philgeps.gov.ph/analytics/load/merchantInfo"
    
    # Set headers to mimic a browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0'
    }
    
    try:
        # First, get the page to see the form structure
        print(f"  🔍 Querying merchant info for: {contractor_name}")
        response = session.get(base_url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            print(f"    ❌ HTTP {response.status_code}")
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for the search form and input field
        # Based on the website structure, we need to find the search input
        search_input = soup.find('input', {'type': 'text'}) or soup.find('input', {'type': 'search'})
        
        if not search_input:
            # Try to find by placeholder or name attributes
            search_input = soup.find('input', {'placeholder': re.compile(r'merchant|search', re.I)}) or \
                          soup.find('input', {'name': re.compile(r'merchant|search|name', re.I)})
        
        # Try POST request with form data
        form_data = {}
        if search_input:
            input_name = search_input.get('name') or search_input.get('id') or 'merchantName'
            form_data[input_name] = contractor_name
        
        # Try different possible form field names
        possible_fields = ['merchantName', 'merchant_name', 'name', 'search', 'q', 'query']
        
        results = []
        
        for field_name in possible_fields:
            try:
                # Try POST request
                post_data = {field_name: contractor_name}
                post_response = session.post(base_url, data=post_data, headers=headers, timeout=30)
                
                if post_response.status_code == 200:
                    # Parse the response
                    result = parse_merchant_response(post_response.text, contractor_name)
                    if result:
                        results.append(result)
                
                # Also try GET request with query parameters
                get_params = {field_name: contractor_name}
                get_response = session.get(base_url, params=get_params, headers=headers, timeout=30)
                
                if get_response.status_code == 200:
                    result = parse_merchant_response(get_response.text, contractor_name)
                    if result:
                        results.append(result)
                
            except Exception as e:
                continue
        
        # If we found results, return the first one
        if results:
            return results[0]
        
        # If no results found, try to find if there's an API endpoint
        # Look for JavaScript that might make API calls
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                # Look for API endpoints
                api_match = re.search(r'["\']([^"\']*merchant[^"\']*api[^"\']*)["\']', script.string, re.I)
                if api_match:
                    api_url = api_match.group(1)
                    if not api_url.startswith('http'):
                        api_url = f"https://open.philgeps.gov.ph{api_url}"
                    
                    try:
                        api_response = session.get(api_url, params={'name': contractor_name}, headers=headers, timeout=30)
                        if api_response.status_code == 200:
                            try:
                                api_data = api_response.json()
                                return parse_api_response(api_data, contractor_name)
                            except:
                                result = parse_merchant_response(api_response.text, contractor_name)
                                if result:
                                    return result
                    except:
                        pass
        
        print(f"    ⚠️ No results found")
        return None
        
    except requests.exceptions.RequestException as e:
        print(f"    ❌ Request error: {e}")
        return None
    except Exception as e:
        print(f"    ❌ Error: {e}")
        return None


def parse_merchant_response(html_content: str, contractor_name: str) -> Optional[Dict]:
    """
    Parse HTML response from merchant info page to extract registration details.
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Look for tables with merchant information
        tables = soup.find_all('table')
        
        for table in tables:
            # Look for rows that might contain registration details
            rows = table.find_all('tr')
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    # Check if this row contains registration details
                    header = cells[0].get_text(strip=True).lower()
                    value = cells[1].get_text(strip=True)
                    
                    if 'registration' in header or 'reg' in header:
                        # Found registration details row
                        # Look for the full table structure
                        return extract_registration_details_from_table(table, contractor_name)
        
        # If no table found, look for divs or other elements with registration info
        reg_elements = soup.find_all(string=re.compile(r'registration|reg\s+details', re.I))
        if reg_elements:
            # Try to find parent elements with data
            for elem in reg_elements:
                parent = elem.parent
                if parent:
                    # Look for sibling or parent elements with actual data
                    data_elem = parent.find_next_sibling()
                    if data_elem:
                        return {
                            'contractor_name': contractor_name,
                            'registration_details': data_elem.get_text(strip=True),
                            'source': 'philgeps_merchant_info',
                            'scraped_at': datetime.now().isoformat()
                        }
        
        return None
        
    except Exception as e:
        print(f"    ⚠️ Error parsing response: {e}")
        return None


def extract_registration_details_from_table(table, contractor_name: str) -> Dict:
    """
    Extract registration details from a table structure.
    """
    result = {
        'contractor_name': contractor_name,
        'registration_details': {},
        'source': 'philgeps_merchant_info',
        'scraped_at': datetime.now().isoformat()
    }
    
    rows = table.find_all('tr')
    for row in rows:
        cells = row.find_all(['td', 'th'])
        if len(cells) >= 2:
            key = cells[0].get_text(strip=True)
            value = cells[1].get_text(strip=True)
            
            if key and value:
                result['registration_details'][key] = value
    
    # If we found a "Registration Details" column, extract it
    if 'Registration Details' in result['registration_details']:
        result['registration_details_text'] = result['registration_details']['Registration Details']
    
    return result


def parse_api_response(json_data: Dict, contractor_name: str) -> Optional[Dict]:
    """
    Parse JSON API response.
    """
    try:
        if isinstance(json_data, list) and len(json_data) > 0:
            json_data = json_data[0]
        
        if not isinstance(json_data, dict):
            return None
        
        result = {
            'contractor_name': contractor_name,
            'registration_details': json_data,
            'source': 'philgeps_merchant_info',
            'scraped_at': datetime.now().isoformat()
        }
        
        # Look for registration details field
        reg_fields = ['registration_details', 'registrationDetails', 'reg_details', 'regDetails']
        for field in reg_fields:
            if field in json_data:
                result['registration_details_text'] = json_data[field]
                break
        
        return result
        
    except Exception as e:
        print(f"    ⚠️ Error parsing API response: {e}")
        return None


async def save_merchant_info(merchant_data: Dict):
    """
    Save merchant info to database.
    Creates a table if it doesn't exist.
    """
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_SEC', 'sec')
    )
    
    try:
        # Create table if it doesn't exist
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS philgeps_merchant_info (
                id SERIAL PRIMARY KEY,
                contractor_name TEXT NOT NULL,
                normalized_name TEXT,
                registration_details JSONB,
                registration_details_text TEXT,
                source TEXT DEFAULT 'philgeps_merchant_info',
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(contractor_name)
            )
        ''')
        
        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_philgeps_merchant_contractor 
            ON philgeps_merchant_info(contractor_name)
        ''')
        
        await conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_philgeps_merchant_normalized 
            ON philgeps_merchant_info(normalized_name)
        ''')
        
        # Insert or update merchant info
        registration_details_json = json.dumps(merchant_data.get('registration_details', {}))
        registration_details_text = merchant_data.get('registration_details_text', '')
        
        await conn.execute('''
            INSERT INTO philgeps_merchant_info (
                contractor_name, normalized_name, registration_details,
                registration_details_text, source, scraped_at
            ) VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (contractor_name) 
            DO UPDATE SET
                registration_details = EXCLUDED.registration_details,
                registration_details_text = EXCLUDED.registration_details_text,
                scraped_at = EXCLUDED.scraped_at,
                updated_at = CURRENT_TIMESTAMP
        ''',
            merchant_data['contractor_name'],
            normalize_contractor_name(merchant_data['contractor_name']),
            registration_details_json,
            registration_details_text,
            merchant_data.get('source', 'philgeps_merchant_info'),
            datetime.now()
        )
        
        print(f"    ✅ Saved merchant info for {merchant_data['contractor_name']}")
        
    finally:
        await conn.close()


async def main(limit: Optional[int] = None, delay: float = 2.0):
    """
    Main function to scrape PhilGEPS merchant info for all contractors.
    
    Args:
        limit: Maximum number of contractors to process (None for all)
        delay: Delay between requests in seconds (to avoid rate limiting)
    """
    print("🚀 PhilGEPS Merchant Information Scraper")
    print("=" * 80)
    print()
    
    # Get normalized contractors from database
    contractors = await get_normalized_contractors(limit=limit)
    
    if not contractors:
        print("❌ No contractors found in database")
        return
    
    print(f"📋 Processing {len(contractors)} contractors...")
    print(f"⏱️  Delay between requests: {delay} seconds")
    print()
    
    session = requests.Session()
    successful = 0
    failed = 0
    not_found = 0
    
    for i, contractor in enumerate(contractors, 1):
        print(f"[{i}/{len(contractors)}] Processing: {contractor['contractor_name']}")
        
        try:
            # Query merchant info
            merchant_info = query_merchant_info(contractor['contractor_name'], session=session)
            
            if merchant_info:
                # Save to database
                await save_merchant_info(merchant_info)
                successful += 1
            else:
                not_found += 1
                print(f"    ⚠️ No merchant info found")
            
            # Delay to avoid rate limiting
            if i < len(contractors):
                time.sleep(delay)
                
        except Exception as e:
            print(f"    ❌ Error: {e}")
            failed += 1
            continue
    
    print()
    print("=" * 80)
    print("📊 SUMMARY")
    print(f"   Total processed: {len(contractors)}")
    print(f"   ✅ Successful: {successful}")
    print(f"   ⚠️  Not found: {not_found}")
    print(f"   ❌ Failed: {failed}")
    print()


if __name__ == "__main__":
    import sys
    
    limit = None
    delay = 2.0
    
    # Parse command line arguments
    if '--limit' in sys.argv:
        idx = sys.argv.index('--limit')
        if idx + 1 < len(sys.argv):
            limit = int(sys.argv[idx + 1])
    
    if '--delay' in sys.argv:
        idx = sys.argv.index('--delay')
        if idx + 1 < len(sys.argv):
            delay = float(sys.argv[idx + 1])
    
    asyncio.run(main(limit=limit, delay=delay))










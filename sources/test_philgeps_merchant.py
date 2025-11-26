#!/usr/bin/env python3
"""
Test script to query PhilGEPS merchant info for one contractor.
Shows normalization process and saves results to JSON.
"""

import asyncio
import asyncpg
import os
import json
import re
from datetime import datetime
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup

load_dotenv()


def normalize_contractor_name(name: str) -> str:
    """Normalize contractor name for searching"""
    if not name:
        return ""
    
    print(f"  Original name: '{name}'")
    
    # Strip quotes and whitespace
    normalized = name.strip().strip('"').strip("'").strip()
    print(f"  After stripping quotes: '{normalized}'")
    
    normalized = normalized.upper()
    print(f"  After uppercase: '{normalized}'")
    
    normalized = normalized.replace('.', ' ')
    normalized = normalized.replace(',', ' ')
    normalized = normalized.replace('-', ' ')
    normalized = normalized.replace('&', 'AND')
    print(f"  After character replacement: '{normalized}'")
    
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    print(f"  After whitespace normalization: '{normalized}'")
    
    print(f"  ✅ Final normalized: '{normalized}'")
    return normalized


async def get_contractors(limit: int = 10, search_term: str = None, prioritize_top: bool = True) -> list:
    """Get contractors from the database, prioritizing by project count"""
    print(f"📊 Fetching {limit} contractors from database...")
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_SEC', 'sec')
    )
    
    try:
        # Build query - prioritize by project_count if available
        if search_term:
            query = """
                SELECT contractor_name, COALESCE(project_count, 0) as project_count
                FROM contractors
                WHERE contractor_name IS NOT NULL
                AND contractor_name != ''
                AND UPPER(contractor_name) LIKE $1
                ORDER BY project_count DESC, contractor_name
                LIMIT $2
            """
            rows = await conn.fetch(query, f'%{search_term.upper()}%', limit)
        else:
            if prioritize_top:
                # Order by project_count descending to get top contractors first
                query = """
                    SELECT contractor_name, COALESCE(project_count, 0) as project_count
                    FROM contractors
                    WHERE contractor_name IS NOT NULL
                    AND contractor_name != ''
                    ORDER BY project_count DESC, contractor_name
                    LIMIT $1
                """
            else:
                query = """
                    SELECT contractor_name, COALESCE(project_count, 0) as project_count
                    FROM contractors
                    WHERE contractor_name IS NOT NULL
                    AND contractor_name != ''
                    ORDER BY contractor_name
                    LIMIT $1
                """
            rows = await conn.fetch(query, limit)
        
        contractors = []
        for row in rows:
            contractors.append({
                'contractor_name': row['contractor_name'],
                'project_count': row['project_count']
            })
        
        if prioritize_top and contractors:
            top_count = contractors[0]['project_count']
            print(f"✅ Found {len(contractors)} contractors (top has {top_count} projects)")
        else:
            print(f"✅ Found {len(contractors)} contractors")
        return contractors
            
    finally:
        await conn.close()


def query_merchant_info(contractor_name: str) -> dict:
    """
    Query PhilGEPS merchant info API for a contractor name.
    Uses normalized name for searching.
    """
    normalized = normalize_contractor_name(contractor_name)
    print(f"\n🔍 Querying PhilGEPS merchant info for: '{contractor_name}'")
    print(f"   Using normalized name: '{normalized}'")
    
    base_url = "https://open.philgeps.gov.ph/analytics/load/merchantInfo"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': base_url
    }
    
    session = requests.Session()
    
    try:
        # First, get the page to understand the structure and get cookies
        print(f"  📄 Fetching page: {base_url}")
        response = session.get(base_url, headers=headers, timeout=30)
        
        print(f"  Status code: {response.status_code}")
        
        if response.status_code != 200:
            return {
                'error': f'HTTP {response.status_code}',
                'contractor_name': contractor_name
            }
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for the search input field
        search_input = None
        input_id = None
        input_name = None
        
        # Try to find input by id='name' (we saw this in the output)
        search_input = soup.find('input', {'id': 'name'})
        if search_input:
            input_id = 'name'
            input_name = search_input.get('name', 'name')
            print(f"  ✅ Found search input with id='name', name='{input_name}'")
        else:
            # Try other common patterns
            for attr in ['id', 'name']:
                for value in ['merchantName', 'merchant_name', 'name', 'search', 'merchant']:
                    found = soup.find('input', {attr: re.compile(value, re.I)})
                    if found:
                        search_input = found
                        if attr == 'id':
                            input_id = found.get('id')
                        else:
                            input_name = found.get('name')
                        print(f"  ✅ Found search input with {attr}='{value}'")
                        break
                if search_input:
                    break
        
        # Find the search button
        search_button = None
        button_text = None
        button_type = None
        
        # Look for button with text "Search" or type="submit"
        buttons = soup.find_all('button') + soup.find_all('input', {'type': 'submit'})
        for btn in buttons:
            btn_text = btn.get_text(strip=True).lower() if btn.name == 'button' else btn.get('value', '').lower()
            if 'search' in btn_text or btn.get('type') == 'submit':
                search_button = btn
                button_text = btn_text
                button_type = btn.get('type', 'button')
                print(f"  ✅ Found search button: type='{button_type}', text='{btn_text}'")
                break
        
        if not search_input:
            print("  ⚠️ Could not find search input field")
            return {
                'contractor_name': contractor_name,
                'normalized_name': normalized,
                'status': 'error',
                'error': 'Could not find search input field'
            }
        
        # Look for JavaScript that might handle the search and find API endpoint
        scripts = soup.find_all('script')
        api_endpoint = None
        search_function = None
        
        # Look for button click handlers and search functions
        api_patterns = [
            r'["\']([^"\']*merchantInfo[^"\']*)["\']',
            r'["\']([^"\']*merchant/load[^"\']*)["\']',
            r'url\s*[:=]\s*["\']([^"\']*merchant[^"\']*)["\']',
            r'ajax[^}]*url\s*[:=]\s*["\']([^"\']*merchant[^"\']*)["\']',
            r'fetch\s*\(["\']([^"\']*merchant[^"\']*)["\']',
            r'\.post\s*\(["\']([^"\']*merchant[^"\']*)["\']',
            r'\.get\s*\(["\']([^"\']*merchant[^"\']*)["\']',
        ]
        
        # Look for button click handler (id='btn')
        button_click_patterns = [
            r'#btn[^}]*click[^}]*function',
            r'getElementById\(["\']btn["\'][^}]*addEventListener',
            r'["\']#btn["\'][^}]*on\(["\']click',
            r'btn[^}]*\.click\s*\([^}]*function',
        ]
        
        for script in scripts:
            if script.string:
                script_text = script.string
                
                # Look for API endpoints
                for pattern in api_patterns:
                    matches = re.findall(pattern, script_text, re.I)
                    if matches:
                        api_endpoint = matches[0]
                        print(f"  Found potential API endpoint: {api_endpoint}")
                        break
                
                # Look for button click handler
                for pattern in button_click_patterns:
                    if re.search(pattern, script_text, re.I):
                        print(f"  Found button click handler in script")
                        # Try to extract the function that gets called
                        # Look for the search function name
                        func_match = re.search(r'function\s+(\w*search\w*)\s*\(', script_text, re.I)
                        if func_match:
                            search_function = func_match.group(1)
                            print(f"  Found search function: {search_function}")
                        break
                
                if api_endpoint:
                    break
        
        # Use normalized contractor name for searching (or just the key part)
        # For better matching, try both the normalized name and key words
        search_terms_to_try = [
            normalized,  # Full normalized name
            contractor_name.strip().strip('"').strip("'"),  # Original cleaned
        ]
        
        # Extract key words from the name (remove common suffixes)
        key_words = normalized.split()
        # Remove very common words
        filtered_words = [w for w in key_words if len(w) > 2 and w not in ['INC', 'CORP', 'CO', 'LTD', 'AND']]
        if filtered_words:
            # Try the longest meaningful word or combination
            if len(filtered_words) >= 2:
                search_terms_to_try.append(' '.join(filtered_words[:2]))  # First 2 words
            search_terms_to_try.append(filtered_words[0])  # First word
        
        # Use the first search term (normalized name) as primary
        search_term = search_terms_to_try[0]
        print(f"  Using search term: '{search_term}'")
        print(f"  Alternative terms available: {search_terms_to_try[1:3]}")
        
        result = None
        
        # The JavaScript shows the button calls:
        # POST to https://open.philgeps.gov.ph/analytics/merchant/load/
        # with data: { template: 'A3YFYQchU3oER1NnUjIAbVtnBy5VTAdoVGgDaA==', keyword: $("#search-name").val() }
        api_url = "https://open.philgeps.gov.ph/analytics/merchant/load/"
        template_value = 'A3YFYQchU3oER1NnUjIAbVtnBy5VTAdoVGgDaA=='
        
        # Call the API with the correct parameters (as the JavaScript does)
        # Try multiple search terms if first one doesn't work
        result = None
        for search_term in search_terms_to_try[:3]:  # Try up to 3 search terms
            try:
                print(f"  Calling API: {api_url}")
                print(f"  With keyword: '{search_term}'")
                
                # POST with template and keyword (as the JavaScript button click does)
                api_data = {
                    'template': template_value,
                    'keyword': search_term
                }
                
                submit_response = session.post(api_url, data=api_data, headers=headers, timeout=30)
                print(f"    POST returned status: {submit_response.status_code}")
                
                if submit_response.status_code == 200:
                    # Save response for debugging
                    debug_file = f'database/philgeps_response_{search_term[:10]}.html'
                    with open(debug_file, 'w', encoding='utf-8') as f:
                        f.write(submit_response.text)
                    print(f"    💾 Saved response to {debug_file} for debugging")
                    
                    # Parse the response from the POST/API call directly
                    print(f"    🔍 Parsing POST response...")
                    print(f"    Response length: {len(submit_response.text)} characters")
                    result = parse_merchant_response(submit_response.text, contractor_name, normalized)
                    
                    # Check if we got actual results (not just "No Result")
                    if result:
                        # Check if we have actual registration details
                        reg_details = result.get('registration_details', {})
                        reg_text = result.get('registration_details_text', '')
                        all_data = result.get('all_table_data', {})
                        
                        # Check if any result has actual data (not "No Result")
                        has_real_data = False
                        if reg_text and reg_text.lower() != 'no result' and len(reg_text) > 10:
                            has_real_data = True
                        elif all_data:
                            for key, value in all_data.items():
                                if isinstance(value, str) and value.lower() != 'no result' and len(value) > 10:
                                    has_real_data = True
                                    break
                        
                        if has_real_data:
                            print(f"    ✅ Found results in POST response!")
                            return result
                        else:
                            print(f"    ⚠️ POST response has 'No Result', trying next search term...")
                            # Try next search term
                            continue
                    else:
                        print(f"    ⚠️ Could not parse POST response, trying next search term...")
                        continue
                        
            except Exception as e:
                print(f"    ⚠️ Error with search term '{search_term}': {e}")
                continue
        
        # If we get here, none of the search terms worked
        if result:
            return result
        else:
            return {
                'contractor_name': contractor_name,
                'normalized_name': normalized,
                'status': 'no_results_found',
                'note': 'Could not find registration details in the response. The page may require JavaScript to perform the search.'
            }
            
    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            'error': str(e),
            'contractor_name': contractor_name
        }


def parse_registration_details(reg_details_text: str) -> dict:
    """
    Parse registration details text into structured fields.
    Example input: "Platinum202401-375315-901591731 (Exp:2026-03-15 23:59:59)Mayor's Permit: 0442 (Exp:2025-12-31)Tax Clearance: 05-25B-11-22-R01617-2024M (Exp: 2025-11-22)DTI: 1999546 (Exp: 2030-07-24)"
    """
    parsed = {
        'status': None,
        'registration_number': None,
        'registration_expiry': None,
        'mayors_permit': None,
        'mayors_permit_expiry': None,
        'tax_clearance': None,
        'tax_clearance_expiry': None,
        'dti': None,
        'dti_expiry': None,
        'sec': None,
        'approved_date': None
    }
    
    if not reg_details_text:
        return parsed
    
    text = reg_details_text.strip()
    
    # Extract status (Platinum, Red, etc.)
    status_match = re.search(r'^(Platinum|Red|Gold|Silver)', text, re.I)
    if status_match:
        parsed['status'] = status_match.group(1)
    
    # Extract registration number and expiry
    reg_match = re.search(r'(\d{6}-\d+-\d+)\s*\(Exp:([^)]+)\)', text)
    if reg_match:
        parsed['registration_number'] = reg_match.group(1)
        parsed['registration_expiry'] = reg_match.group(2).strip()
    
    # Extract Mayor's Permit
    mayor_match = re.search(r"Mayor's Permit:\s*([^\s(]+)\s*\(Exp:\s*([^)]+)\)", text, re.I)
    if mayor_match:
        parsed['mayors_permit'] = mayor_match.group(1).strip()
        parsed['mayors_permit_expiry'] = mayor_match.group(2).strip()
    
    # Extract Tax Clearance
    tax_match = re.search(r'Tax Clearance:\s*([^\s(]+)\s*\(Exp:\s*([^)]+)\)', text, re.I)
    if tax_match:
        parsed['tax_clearance'] = tax_match.group(1).strip()
        parsed['tax_clearance_expiry'] = tax_match.group(2).strip()
    
    # Extract DTI
    dti_match = re.search(r'DTI:\s*(\d+)\s*\(Exp:\s*([^)]+)\)', text, re.I)
    if dti_match:
        parsed['dti'] = dti_match.group(1).strip()
        parsed['dti_expiry'] = dti_match.group(2).strip()
    
    # Extract SEC
    sec_match = re.search(r'SEC:\s*([^\s]+)', text, re.I)
    if sec_match:
        parsed['sec'] = sec_match.group(1).strip()
    
    # Extract Approved Date
    approved_match = re.search(r'Approved Date:\s*([^/\s]+/[^/\s]+/[^/\s]+)', text, re.I)
    if approved_match:
        parsed['approved_date'] = approved_match.group(1).strip()
    
    return parsed


def parse_merchant_response(html_content: str, contractor_name: str, normalized_name: str = None) -> dict:
    """
    Parse HTML response to extract registration details.
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Look for tables
        tables = soup.find_all('table')
        print(f"    Found {len(tables)} tables")
        
        # Look for registration details
        registration_details = {}
        registration_text = None
        all_table_data = {}
        
        for table in tables:
            rows = table.find_all('tr')
            print(f"    Table has {len(rows)} rows")
            
            # Print full table structure for debugging
            print(f"    📋 Full table structure:")
            for i, row in enumerate(rows):
                cells = row.find_all(['td', 'th'])
                cell_texts = [cell.get_text(strip=True) for cell in cells]
                print(f"      Row {i+1}: {cell_texts}")
            
            # Find the header row to identify column positions
            header_row = None
            registration_details_col_idx = None
            name_col_idx = None
            
            for row_idx, row in enumerate(rows):
                cells = row.find_all(['td', 'th'])
                cell_texts = [cell.get_text(strip=True).lower() for cell in cells]
                
                # Check if this is the header row
                if 'registration details' in cell_texts or 'name' in cell_texts:
                    header_row = row_idx
                    # Find which column has "Registration Details"
                    for col_idx, cell_text in enumerate(cell_texts):
                        if 'registration details' in cell_text:
                            registration_details_col_idx = col_idx
                            print(f"    ✅ Found 'Registration Details' column at index {col_idx}")
                        if cell_text == 'name':
                            name_col_idx = col_idx
                            print(f"    ✅ Found 'Name' column at index {name_col_idx}")
                    break
            
            # Now extract data from data rows (rows after header)
            if header_row is not None and registration_details_col_idx is not None:
                found_results = []
                
                for row_idx in range(header_row + 1, len(rows)):
                    row = rows[row_idx]
                    cells = row.find_all(['td', 'th'])
                    
                    if len(cells) > registration_details_col_idx:
                        reg_details_value = cells[registration_details_col_idx].get_text(strip=True)
                        
                        # Get the name from the name column if available
                        contractor_name_in_table = None
                        if name_col_idx is not None and len(cells) > name_col_idx:
                            contractor_name_in_table = cells[name_col_idx].get_text(strip=True)
                        
                        # Skip if it's "No Result" or empty
                        if reg_details_value and reg_details_value.lower() != 'no result' and len(reg_details_value) > 5:
                            # Parse structured registration details
                            parsed_details = parse_registration_details(reg_details_value)
                            
                            result_entry = {
                                'name': contractor_name_in_table,
                                'registration_details': reg_details_value,
                                'parsed_details': parsed_details
                            }
                            found_results.append(result_entry)
                            
                            print(f"    ✅ Found: {contractor_name_in_table}")
                            print(f"       Status: {parsed_details.get('status', 'N/A')}")
                            if parsed_details.get('registration_number'):
                                print(f"       Registration: {parsed_details['registration_number']} (Exp: {parsed_details.get('registration_expiry', 'N/A')})")
                            
                            # Check if this matches our contractor (fuzzy match)
                            if contractor_name_in_table and normalized_name:
                                # Normalize and compare - extract just the company name (before "Corporation", "Single Proprietorship", etc.)
                                company_name_only = re.sub(r'\s*(Corporation|Single Proprietorship|Individual Local Consultant|JV).*$', '', contractor_name_in_table, flags=re.I).strip()
                                normalized_table_name = normalize_contractor_name(company_name_only)
                                if normalized_name == normalized_table_name or normalized_name in normalized_table_name or normalized_table_name in normalized_name:
                                    registration_text = reg_details_value
                                    registration_details['Registration Details'] = reg_details_value
                                    registration_details['Name'] = contractor_name_in_table
                                    registration_details['Parsed Details'] = parsed_details
                                    all_table_data['Name'] = contractor_name_in_table
                                    all_table_data['Registration Details'] = reg_details_value
                                    all_table_data['Parsed Details'] = parsed_details
                                    print(f"    🎯 MATCHED our contractor!")
                                    print(f"       📋 Extracted registration details:")
                                    print(f"          Status: {parsed_details.get('status', 'N/A')}")
                                    if parsed_details.get('registration_number'):
                                        print(f"          Registration: {parsed_details['registration_number']} (Exp: {parsed_details.get('registration_expiry', 'N/A')})")
                                    if parsed_details.get('mayors_permit'):
                                        print(f"          Mayor's Permit: {parsed_details['mayors_permit']} (Exp: {parsed_details.get('mayors_permit_expiry', 'N/A')})")
                                    if parsed_details.get('tax_clearance'):
                                        print(f"          Tax Clearance: {parsed_details['tax_clearance']} (Exp: {parsed_details.get('tax_clearance_expiry', 'N/A')})")
                                    if parsed_details.get('dti'):
                                        print(f"          DTI: {parsed_details['dti']} (Exp: {parsed_details.get('dti_expiry', 'N/A')})")
                                    if parsed_details.get('sec'):
                                        print(f"          SEC: {parsed_details['sec']}")
                                    if parsed_details.get('approved_date'):
                                        print(f"          Approved Date: {parsed_details['approved_date']}")
                        elif reg_details_value.lower() == 'no result':
                            print(f"    ⚠️ No result found for this search")
                            all_table_data['Registration Details'] = 'No Result'
                            if contractor_name_in_table:
                                all_table_data['Name'] = contractor_name_in_table
                
                # Store all found results
                if found_results:
                    registration_details['all_results'] = found_results
                    all_table_data['all_results'] = found_results
                    print(f"    📊 Total results found: {len(found_results)}")
                    
                    # If we didn't find an exact match, use the first result or best match
                    if not registration_text and found_results:
                        # Try to find best match
                        best_match = None
                        for result in found_results:
                            result_name = result.get('name', '')
                            normalized_result = normalize_contractor_name(result_name)
                            if 'tiqui' in normalized_result.lower():
                                best_match = result
                                break
                        
                        if best_match:
                            registration_text = best_match['registration_details']
                            registration_details['Registration Details'] = best_match['registration_details']
                            registration_details['Name'] = best_match['name']
                            if 'parsed_details' in best_match:
                                registration_details['Parsed Details'] = best_match['parsed_details']
                            print(f"    🎯 Using best match: {best_match['name']}")
                        else:
                            # Use first result
                            first_result = found_results[0]
                            registration_text = first_result['registration_details']
                            registration_details['Registration Details'] = first_result['registration_details']
                            registration_details['Name'] = first_result['name']
                            if 'parsed_details' in first_result:
                                registration_details['Parsed Details'] = first_result['parsed_details']
                            print(f"    📝 Using first result: {first_result['name']}")
            else:
                # Fallback: try to parse without knowing column structure
                print(f"    ⚠️ Could not identify column structure, trying fallback parsing...")
                for row_idx, row in enumerate(rows):
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        header = cells[0].get_text(strip=True)
                        value = cells[1].get_text(strip=True)
                        
                        if header and value:
                            all_table_data[header] = value
                            
                            if 'registration' in header.lower() or 'reg' in header.lower():
                                if value.lower() != 'no result' and len(value) > 5:
                                    registration_text = value
                                    registration_details[header] = value
                                    print(f"    ✅ Found registration details: {value[:200]}...")
        
        # If we found table data but no specific registration column, check all columns
        if all_table_data and not registration_text:
            # Look for any column that might contain registration info
            for key, value in all_table_data.items():
                if any(word in key.lower() for word in ['reg', 'status', 'info', 'detail']):
                    registration_text = value
                    registration_details[key] = value
                    print(f"    ✅ Found potential registration info in '{key}': {value[:100]}...")
                    break
        
        # If no table found, look for divs or other elements
        if not registration_details:
            reg_elements = soup.find_all(string=re.compile(r'registration|reg\s+details', re.I))
            if reg_elements:
                for elem in reg_elements:
                    parent = elem.parent
                    if parent:
                        data_elem = parent.find_next_sibling()
                        if data_elem:
                            registration_text = data_elem.get_text(strip=True)
                            print(f"    Found registration text: {registration_text[:100]}...")
                            break
        
        # If we have any table data, return it
        if all_table_data:
            return {
                'contractor_name': contractor_name,
                'normalized_name': normalized_name if normalized_name else normalize_contractor_name(contractor_name),
                'registration_details': registration_details if registration_details else all_table_data,
                'registration_details_text': registration_text,
                'all_table_data': all_table_data,
                'source': 'philgeps_merchant_info',
                'scraped_at': datetime.now().isoformat(),
                'status': 'success' if registration_text else 'partial'
            }
        
        return None
        
    except Exception as e:
        print(f"    ⚠️ Error parsing: {e}")
        import traceback
        traceback.print_exc()
        return None


def parse_api_response(json_data: dict, contractor_name: str) -> dict:
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
            'normalized_name': normalize_contractor_name(contractor_name),
            'registration_details': json_data,
            'source': 'philgeps_merchant_info',
            'scraped_at': datetime.now().isoformat(),
            'status': 'success'
        }
        
        # Look for registration details field
        reg_fields = ['registration_details', 'registrationDetails', 'reg_details', 'regDetails', 'registration']
        for field in reg_fields:
            if field in json_data:
                result['registration_details_text'] = json_data[field]
                break
        
        return result
        
    except Exception as e:
        print(f"    ⚠️ Error parsing API response: {e}")
        return None


async def main(limit: int = None, delay: float = 2.0, resume: bool = True):
    """Main function - process all contractors, prioritizing top ones"""
    print("🚀 PhilGEPS Merchant Info Scraper - All Contractors")
    print("=" * 80)
    print()
    
    output_file = 'database/philgeps_merchant_info_test.json'
    results = []
    processed_contractors = set()  # Track processed contractors by name
    
    # Try to resume from previous run
    if resume:
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                if existing_data.get('results'):
                    results = existing_data['results']
                    # Create set of already processed contractor names
                    processed_contractors = {r.get('contractor_name', '') for r in results if r.get('contractor_name')}
                    print(f"📂 Resuming from previous run: {len(processed_contractors)} unique contractors already processed")
                    print(f"   Last updated: {existing_data.get('last_updated', 'N/A')}")
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            print("📂 Starting fresh run")
    
    # Get contractors from database, prioritizing by project count
    print("📊 Fetching contractors from database (prioritizing top contractors)...")
    # Use a very large limit if None to get all contractors
    fetch_limit = limit if limit else 100000
    all_contractors = await get_contractors(limit=fetch_limit, search_term=None, prioritize_top=True)
    
    if not all_contractors:
        print("❌ No contractors found")
        return
    
    # Filter out already processed contractors by name (not by index)
    if processed_contractors:
        contractors = [c for c in all_contractors if c['contractor_name'] not in processed_contractors]
        skipped_count = len(all_contractors) - len(contractors)
        print(f"⏭️  Skipping {skipped_count} already processed contractors (by name)")
        print(f"📋 Remaining: {len(contractors)} contractors to process")
        
        if len(contractors) == 0:
            print(f"✅ All {len(all_contractors)} contractors already processed!")
            return
    else:
        contractors = all_contractors
    
    print(f"\n📋 Processing {len(contractors)} contractors (sorted by project count)...")
    
    if not processed_contractors:
        print(f"\n📋 Top {min(10, len(contractors))} contractors by project count:")
        for i, c in enumerate(contractors[:10], 1):
            print(f"  {i}. {c['contractor_name']} ({c.get('project_count', 0)} projects)")
        if len(contractors) > 10:
            print(f"  ... and {len(contractors) - 10} more")
    
    successful = 0
    failed = 0
    
    total_expected = len(all_contractors)
    total_processed_before = len(processed_contractors)
    
    for i, contractor in enumerate(contractors, 1):
        contractor_name = contractor['contractor_name']
        project_count = contractor.get('project_count', 0)
        current_index = total_processed_before + i
        
        # Double-check: skip if already processed (safety check)
        if contractor_name in processed_contractors:
            print(f"\n⏭️  Skipping {contractor_name} (already processed)")
            continue
        
        print(f"\n{'='*80}")
        print(f"[{current_index}/{total_expected}] Processing: {contractor_name} ({project_count} projects)")
        print(f"{'='*80}")
        
        print(f"\n📝 Normalization Process:")
        print("-" * 80)
        normalized = normalize_contractor_name(contractor_name)
        
        print(f"\n🔍 Querying PhilGEPS...")
        print("-" * 80)
        result = query_merchant_info(contractor_name)
        
        # Add normalized name and project count if not already present
        if 'normalized_name' not in result:
            result['normalized_name'] = normalized
        result['project_count'] = project_count
        
        # Check if we got structured registration details
        parsed_details = result.get('registration_details', {}).get('Parsed Details') or result.get('Parsed Details')
        if parsed_details:
            successful += 1
            print(f"\n✅ Successfully extracted structured registration details:")
            if parsed_details.get('status'):
                print(f"   Status: {parsed_details['status']}")
            if parsed_details.get('registration_number'):
                print(f"   Registration: {parsed_details['registration_number']} (Exp: {parsed_details.get('registration_expiry', 'N/A')})")
            if parsed_details.get('mayors_permit'):
                print(f"   Mayor's Permit: {parsed_details['mayors_permit']} (Exp: {parsed_details.get('mayors_permit_expiry', 'N/A')})")
            if parsed_details.get('tax_clearance'):
                print(f"   Tax Clearance: {parsed_details['tax_clearance']} (Exp: {parsed_details.get('tax_clearance_expiry', 'N/A')})")
            if parsed_details.get('dti'):
                print(f"   DTI: {parsed_details['dti']} (Exp: {parsed_details.get('dti_expiry', 'N/A')})")
            if parsed_details.get('sec'):
                print(f"   SEC: {parsed_details['sec']}")
            if parsed_details.get('approved_date'):
                print(f"   Approved Date: {parsed_details['approved_date']}")
        else:
            failed += 1
        
        # Only add if not already in results (prevent duplicates)
        if not any(r.get('contractor_name') == contractor_name for r in results):
            results.append(result)
        processed_contractors.add(contractor_name)  # Mark as processed
        
        # Save after every contractor to avoid losing any progress
        # This also introduces a natural delay that helps with rate limiting
        output_file = 'database/philgeps_merchant_info_test.json'
        total_processed = len(processed_contractors)
        total_expected = len(all_contractors)
        output_data = {
            'total_contractors_tested': total_processed,
            'total_contractors_expected': total_expected,
            'last_updated': datetime.now().isoformat(),
            'test_date': datetime.now().isoformat(),
            'progress': f"{total_processed}/{total_expected} ({100*total_processed/total_expected:.1f}%)",
            'completed': False,
            'results': results
        }
        
        # Save to temporary file first, then rename (atomic write)
        # The file I/O operation itself provides some natural throttling
        import time
        save_start = time.time()
        temp_file = output_file + '.tmp'
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        import shutil
        shutil.move(temp_file, output_file)
        save_time = time.time() - save_start
        
        # Calculate remaining delay needed (save operation already took some time)
        # This ensures we maintain the specified delay between API requests
        if i < len(contractors):
            remaining_delay = max(0, delay - save_time)
            if remaining_delay > 0:
                time.sleep(remaining_delay)
        
        # Print progress every 10 contractors to reduce console spam
        if i % 10 == 0 or i == len(contractors):
            print(f"\n💾 Progress saved: {total_processed}/{total_expected} ({100*total_processed/total_expected:.1f}%)")
    
    # Final save
    output_file = 'database/philgeps_merchant_info_test.json'
    print(f"\n💾 Final save to: {output_file}")
    
    total_processed = len(processed_contractors)
    total_expected = len(all_contractors)
    output_data = {
        'total_contractors_tested': total_processed,
        'total_contractors_expected': total_expected,
        'last_updated': datetime.now().isoformat(),
        'test_date': datetime.now().isoformat(),
        'progress': f"{total_processed}/{total_expected} (100%)",
        'completed': True,
        'results': results
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ All results saved!")
    print()
    print("📊 Summary:")
    print("-" * 80)
    
    with_parsed = sum(1 for r in results if r.get('registration_details', {}).get('Parsed Details') or r.get('Parsed Details'))
    with_details = sum(1 for r in results if r.get('registration_details_text') or (r.get('registration_details') and len(r.get('registration_details', {})) > 0))
    no_results = sum(1 for r in results if r.get('status') == 'no_results_found' or 'error' in r)
    
    print(f"  Total tested: {len(results)}")
    print(f"  ✅ With structured details: {with_parsed}")
    print(f"  ⚠️  With raw details: {with_details - with_parsed}")
    print(f"  ❌ No results/Errors: {no_results}")
    
    # Show contractors with structured registration details
    print(f"\n📋 Contractors with structured registration details:")
    for r in results:
        parsed = r.get('registration_details', {}).get('Parsed Details') or r.get('Parsed Details')
        if parsed:
            print(f"\n  ✅ {r['contractor_name']}")
            if parsed.get('status'):
                print(f"     Status: {parsed['status']}")
            if parsed.get('registration_number'):
                print(f"     Registration: {parsed['registration_number']} (Exp: {parsed.get('registration_expiry', 'N/A')})")
            if parsed.get('mayors_permit'):
                print(f"     Mayor's Permit: {parsed['mayors_permit']} (Exp: {parsed.get('mayors_permit_expiry', 'N/A')})")
            if parsed.get('tax_clearance'):
                print(f"     Tax Clearance: {parsed['tax_clearance']} (Exp: {parsed.get('tax_clearance_expiry', 'N/A')})")
            if parsed.get('dti'):
                print(f"     DTI: {parsed['dti']} (Exp: {parsed.get('dti_expiry', 'N/A')})")
            if parsed.get('sec'):
                print(f"     SEC: {parsed['sec']}")
            if parsed.get('approved_date'):
                print(f"     Approved Date: {parsed['approved_date']}")


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


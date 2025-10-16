#!/usr/bin/env python3
"""
SEC Philippines Check with SEC Automation Script
Searches for company registration information
"""

import requests
from bs4 import BeautifulSoup
import time
import json

def search_sec_company(company_name):
    """
    Search for a company on SEC Philippines Check with SEC website
    """
    print(f"🔍 Searching for company: '{company_name}'")
    
    # Step 1: Get the search page
    url = 'https://checkwithsec.sec.gov.ph/check-with-sec/index'
    session = requests.Session()
    
    # Set headers to mimic a real browser
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0'
    }
    
    try:
        print("📄 Step 1: Getting search page...")
        response = session.get(url, headers=headers, timeout=30)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for forms and input fields
            forms = soup.find_all('form')
            print(f"   Found {len(forms)} forms")
            
            # Look for input fields
            inputs = soup.find_all('input')
            print(f"   Found {len(inputs)} input fields")
            
            # Look for search-related elements
            search_inputs = soup.find_all('input', {'type': 'text'}) + soup.find_all('input', {'type': 'search'})
            print(f"   Found {len(search_inputs)} text/search inputs")
            
            # Look for buttons
            buttons = soup.find_all('button') + soup.find_all('input', {'type': 'submit'})
            print(f"   Found {len(buttons)} buttons")
            
            # Print form details
            for i, form in enumerate(forms):
                print(f"   Form {i+1}:")
                print(f"     Action: {form.get('action', 'No action')}")
                print(f"     Method: {form.get('method', 'GET')}")
                print(f"     Inputs: {len(form.find_all('input'))}")
            
            # Print input field details
            for i, inp in enumerate(inputs[:10]):  # Show first 10 inputs
                print(f"   Input {i+1}:")
                print(f"     Type: {inp.get('type', 'text')}")
                print(f"     Name: {inp.get('name', 'No name')}")
                print(f"     ID: {inp.get('id', 'No ID')}")
                print(f"     Placeholder: {inp.get('placeholder', 'No placeholder')}")
            
            # Look for JavaScript that might handle the search
            scripts = soup.find_all('script')
            print(f"   Found {len(scripts)} script tags")
            
            # Check if page is protected by Cloudflare
            if "Just a moment" in response.text or "Enable JavaScript" in response.text:
                print("   ⚠️ Page is protected by Cloudflare - requires JavaScript")
                return {"error": "Page protected by Cloudflare", "requires_js": True}
            
            # Try to find API endpoints in the page
            api_endpoints = []
            for script in scripts:
                if script.string:
                    script_text = script.string
                    if 'api' in script_text.lower():
                        print(f"   Found potential API reference in script")
                        # Look for API URLs
                        import re
                        urls = re.findall(r'["\']([^"\']*api[^"\']*)["\']', script_text)
                        api_endpoints.extend(urls)
            
            if api_endpoints:
                print(f"   Found potential API endpoints: {api_endpoints}")
            
            return {
                "status": "success",
                "forms_found": len(forms),
                "inputs_found": len(inputs),
                "search_inputs": len(search_inputs),
                "buttons_found": len(buttons),
                "api_endpoints": api_endpoints,
                "cloudflare_protected": "Just a moment" in response.text
            }
            
        else:
            return {"error": f"HTTP {response.status_code}", "status_code": response.status_code}
            
    except requests.exceptions.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}
    except Exception as e:
        return {"error": f"Unexpected error: {str(e)}"}

def main():
    """Main function to test SEC search"""
    company_name = "kench lightyear"
    
    print("🏢 SEC Philippines Company Search Automation")
    print("=" * 50)
    
    result = search_sec_company(company_name)
    
    print("\n📊 Results:")
    print(json.dumps(result, indent=2))
    
    if result.get("cloudflare_protected"):
        print("\n⚠️ Note: The SEC website is protected by Cloudflare and requires JavaScript.")
        print("   Manual search may be required at: https://checkwithsec.sec.gov.ph/check-with-sec/index")

if __name__ == "__main__":
    main()

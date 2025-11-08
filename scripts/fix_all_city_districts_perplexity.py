#!/usr/bin/env python3
"""
Automatically fix all city districts with incomplete barangay data using Perplexity API.
Uses sonar-pro model to get official barangay lists from PSA, COMELEC, and other sources.
"""

import os
import re
import json
import asyncio
import asyncpg
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Cities that need fixing (excluding Manila which is complete)
CITIES_TO_FIX = [
    # Priority 1: Davao City (already did 1st, need 2nd and 3rd)
    {'city': 'Davao City', 'district': '2nd District', 'current_count': 23},
    {'city': 'Davao City', 'district': '3rd District', 'current_count': 22},
    
    # Priority 2: Quezon City
    {'city': 'Quezon City', 'district': '2nd District', 'current_count': 5},
    {'city': 'Quezon City', 'district': '4th District', 'current_count': 5},
    {'city': 'Quezon City', 'district': '5th District', 'current_count': 5},
    {'city': 'Quezon City', 'district': '6th District', 'current_count': 5},
    
    # Priority 3: Caloocan
    {'city': 'Caloocan', 'district': '1st District', 'current_count': 2},
    {'city': 'Caloocan', 'district': '2nd District', 'current_count': 2},
    {'city': 'Caloocan', 'district': '3rd District', 'current_count': 1},
    
    # Priority 4: Cities with 0 barangays
    {'city': 'Antipolo', 'district': '1st District', 'current_count': 1},
    {'city': 'Biñan', 'district': 'Lone District', 'current_count': 0},
    {'city': 'Las Piñas', 'district': 'Lone District', 'current_count': 0},
    {'city': 'Makati', 'district': '1st District', 'current_count': 7},
    {'city': 'Makati', 'district': '2nd District', 'current_count': 2},
    {'city': 'Malabon', 'district': 'Lone District', 'current_count': 0},
    {'city': 'Mandaluyong', 'district': 'Lone District', 'current_count': 0},
    {'city': 'Marikina', 'district': '2nd District', 'current_count': 0},
    {'city': 'Muntinlupa', 'district': 'Lone District', 'current_count': 0},
    {'city': 'Navotas', 'district': 'Lone District', 'current_count': 0},
    {'city': 'Parañaque', 'district': '1st District', 'current_count': 9},
    {'city': 'Parañaque', 'district': '2nd District', 'current_count': 8},
    {'city': 'Pasay', 'district': 'Lone District', 'current_count': 0},
    {'city': 'Pasig', 'district': 'Lone District', 'current_count': 0},
    {'city': 'San Juan', 'district': 'Lone District', 'current_count': 0},
    {'city': 'Taguig–Pateros', 'district': '2nd District', 'current_count': 10},
    {'city': 'Valenzuela', 'district': '1st District', 'current_count': 8},
    {'city': 'Valenzuela', 'district': '2nd District', 'current_count': 8},
]


def call_perplexity(prompt: str) -> str:
    """Call Perplexity API with the prompt"""
    api_key = os.getenv('PERPLEXITY_API_KEY')
    if not api_key:
        raise RuntimeError('PERPLEXITY_API_KEY not set in environment')
    
    model = 'sonar-pro'
    url = 'https://api.perplexity.ai/chat/completions'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': model,
        'temperature': 0.0,
        'top_p': 1.0,
        'max_tokens': 8000,
        'messages': [
            {'role': 'system', 'content': 'You are a precise research assistant. Return complete, accurate data from official sources like PSA, COMELEC, and Wikipedia.'},
            {'role': 'user', 'content': prompt}
        ]
    }
    
    response = requests.post(url, json=payload, headers=headers, timeout=60)
    response.raise_for_status()
    
    data = response.json()
    return data['choices'][0]['message']['content']


def build_barangay_query(city: str, district: str) -> str:
    """Build Perplexity prompt for getting complete barangay list"""
    return f"""Please provide the COMPLETE official list of barangays for {city} {district} in the Philippines.

Requirements:
1. Get data from official sources: Philippine Statistics Authority (PSA), COMELEC, Wikipedia, or House of Representatives
2. List ALL barangays - do not abbreviate or summarize
3. Use the exact official barangay names
4. Return ONLY a JSON array of barangay names, nothing else

Format your response as:
```json
["Barangay Name 1", "Barangay Name 2", "Barangay Name 3", ...]
```

City: {city}
District: {district}

Provide the complete list now."""


def extract_json_from_response(response: str) -> list:
    """Extract JSON array from Perplexity response"""
    # Try to find JSON in code blocks
    json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Try to find JSON array directly
    json_match = re.search(r'\[.*?\]', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    
    return None


async def update_district_barangays(conn, city: str, district: str, barangays: list):
    """Update database with barangays for a district"""
    query = """
        UPDATE dynasty_projects_congressmen_config
        SET barangays = $1::jsonb,
            updated_at = NOW()
        WHERE province = $2
          AND district_number = $3
          AND is_city_district = true
        RETURNING id, display_name, jsonb_array_length(barangays) as count
    """
    
    barangays_json = json.dumps(barangays)
    results = await conn.fetch(query, barangays_json, city, district)
    
    return results


async def main():
    # Connect to database
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD'),
        database=os.getenv('POSTGRES_DB_DYNASTY')
    )
    
    print("✅ Connected to dynasty database\n")
    print("=" * 80)
    print("FIXING CITY DISTRICTS WITH PERPLEXITY API")
    print("=" * 80)
    print()
    
    success_count = 0
    failed = []
    
    for idx, district_info in enumerate(CITIES_TO_FIX, 1):
        city = district_info['city']
        district = district_info['district']
        current_count = district_info['current_count']
        
        print(f"[{idx}/{len(CITIES_TO_FIX)}] {city} {district} (currently {current_count} barangays)")
        
        try:
            # Build query
            prompt = build_barangay_query(city, district)
            
            # Call Perplexity
            print(f"   📡 Querying Perplexity API...")
            response = call_perplexity(prompt)
            
            # Extract barangays
            barangays = extract_json_from_response(response)
            
            if not barangays:
                print(f"   ❌ Failed to extract barangay list from response")
                print(f"   Response preview: {response[:200]}...")
                failed.append({'city': city, 'district': district, 'reason': 'Could not parse response'})
                print()
                continue
            
            print(f"   ✅ Found {len(barangays)} barangays")
            
            # Update database
            results = await update_district_barangays(conn, city, district, barangays)
            
            if results:
                for row in results:
                    print(f"   ✅ Updated {row['display_name']} (ID: {row['id']}) with {row['count']} barangays")
                success_count += 1
            else:
                print(f"   ⚠️  No congressmen found for this district")
                failed.append({'city': city, 'district': district, 'reason': 'No congressmen in database'})
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            failed.append({'city': city, 'district': district, 'reason': str(e)})
        
        print()
        
        # Rate limiting - wait 2 seconds between requests
        if idx < len(CITIES_TO_FIX):
            await asyncio.sleep(2)
    
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"✅ Successfully fixed: {success_count}/{len(CITIES_TO_FIX)} districts")
    
    if failed:
        print(f"❌ Failed: {len(failed)} districts")
        for item in failed:
            print(f"   - {item['city']} {item['district']}: {item['reason']}")
    
    print()
    print("Next steps:")
    print("1. Review the updates")
    print("2. Run scripts/export_dynasty_json_from_db.py to update JSON files")
    print("3. Run scripts/generate_dynasty_projects_cache.py to regenerate caches")
    
    await conn.close()


if __name__ == '__main__':
    asyncio.run(main())


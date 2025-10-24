#!/usr/bin/env python3
"""
Simple Wikipedia test with minimal requests
"""

import asyncio
import aiohttp
import json

async def simple_test():
    """Simple test with just one request"""
    
    headers = {
        'User-Agent': 'BetterGovPH Research Bot 1.0 (https://visualizations.bettergov.ph)',
        'Accept': 'application/json'
    }
    
    async with aiohttp.ClientSession(headers=headers) as session:
        print("🔍 Testing Wikipedia API with simple request...")
        
        # Try a simple search
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            'action': 'query',
            'format': 'json',
            'list': 'search',
            'srsearch': 'Philippines',
            'srlimit': 1
        }
        
        try:
            async with session.get(url, params=params) as response:
                print(f"📊 Response status: {response.status}")
                print(f"📊 Response headers: {dict(response.headers)}")
                
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Success! Data keys: {list(data.keys())}")
                    if 'query' in data:
                        print(f"📋 Query keys: {list(data['query'].keys())}")
                        if 'search' in data['query']:
                            print(f"🔍 Found {len(data['query']['search'])} search results")
                            for result in data['query']['search']:
                                print(f"   - {result['title']}")
                else:
                    text = await response.text()
                    print(f"❌ Error response: {text[:200]}...")
                    
        except Exception as e:
            print(f"❌ Exception: {e}")

if __name__ == "__main__":
    asyncio.run(simple_test())

#!/usr/bin/env python3
"""
Test Wikipedia Scraper with well-known politicians
"""

import asyncio
import aiohttp
import json
import re
from urllib.parse import quote

async def test_wikipedia_search():
    """Test Wikipedia search with well-known politicians"""
    
    test_politicians = [
        "Gloria Macapagal Arroyo",
        "Ferdinand Marcos",
        "Corazon Aquino", 
        "Joseph Estrada",
        "Benigno Aquino",
        "Rodrigo Duterte",
        "Bongbong Marcos",
        "Leni Robredo"
    ]
    
    async with aiohttp.ClientSession() as session:
        for politician in test_politicians:
            print(f"\n🔍 Testing: {politician}")
            
            # Test Wikipedia search
            search_url = "https://en.wikipedia.org/w/api.php"
            params = {
                'action': 'query',
                'format': 'json',
                'list': 'search',
                'srsearch': f"{politician} Philippines",
                'srlimit': 3
            }
            
            try:
                async with session.get(search_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'query' in data and 'search' in data['query'] and data['query']['search']:
                            results = data['query']['search']
                            print(f"✅ Found {len(results)} results:")
                            for i, result in enumerate(results, 1):
                                print(f"   {i}. {result['title']} (snippet: {result['snippet'][:100]}...)")
                        else:
                            print(f"❌ No results found")
                    else:
                        print(f"❌ HTTP {response.status}")
                        
            except Exception as e:
                print(f"❌ Error: {e}")
            
            await asyncio.sleep(1)  # Rate limiting

if __name__ == "__main__":
    asyncio.run(test_wikipedia_search())

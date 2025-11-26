#!/usr/bin/env python3
"""
Test script to check MeiliSearch endpoint at https://search.bettergov.ph/
"""

import requests
import json
from typing import Dict, Any

MEILISEARCH_URL = "https://search.bettergov.ph"
API_KEY = "p06cYon0-vFvw-tuHbEvGG"

def make_request(endpoint: str, method: str = "GET", data: Dict = None) -> Dict[str, Any]:
    """Make HTTP request to MeiliSearch API"""
    url = f"{MEILISEARCH_URL}/{endpoint}"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=10)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=10)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP Error: {e}")
        if hasattr(e.response, 'text'):
            print(f"   Response: {e.response.text}")
        return {"error": str(e), "status_code": e.response.status_code}
    except requests.exceptions.RequestException as e:
        print(f"❌ Request Error: {e}")
        return {"error": str(e)}

def main():
    print(f"🔍 Testing MeiliSearch endpoint: {MEILISEARCH_URL}")
    print(f"🔑 Using API key: {API_KEY[:10]}...")
    print()
    
    # 1. Check health status
    print("1️⃣ Checking health status...")
    health = make_request("health")
    print(f"   Health: {json.dumps(health, indent=2)}")
    print()
    
    # 2. Get version info
    print("2️⃣ Getting version info...")
    version = make_request("version")
    print(f"   Version: {json.dumps(version, indent=2)}")
    print()
    
    # 3. List all indexes
    print("3️⃣ Listing all indexes...")
    indexes = make_request("indexes")
    print(f"   Indexes: {json.dumps(indexes, indent=2)}")
    print()
    
    # 4. Get stats
    print("4️⃣ Getting stats...")
    stats = make_request("stats")
    print(f"   Stats: {json.dumps(stats, indent=2)}")
    print()
    
    # 5. Try known indexes directly (bypassing list endpoint)
    known_indexes = ["bettergov_flood_control", "contractors"]
    
    print("5️⃣ Testing known indexes directly...")
    for index_uid in known_indexes:
        print(f"\n   📊 Testing index: {index_uid}")
        
        # Try search endpoint first (most common use case)
        print(f"      Testing search endpoint...")
        search_result = make_request(
            f"indexes/{index_uid}/search",
            method="POST",
            data={"q": "", "limit": 3}
        )
        if "error" not in search_result:
            print(f"      ✅ Search successful!")
            if "hits" in search_result:
                print(f"      Found {len(search_result.get('hits', []))} results")
                print(f"      Total: {search_result.get('estimatedTotalHits', 'unknown')}")
                if len(search_result.get("hits", [])) > 0:
                    sample_doc = search_result["hits"][0]
                    print(f"      Sample document keys: {list(sample_doc.keys())[:10]}...")
            print(f"      Full result: {json.dumps(search_result, indent=8)}")
        else:
            print(f"      ❌ Search failed: {search_result.get('error', 'Unknown error')}")
        
        # Try stats endpoint
        print(f"      Testing stats endpoint...")
        index_stats = make_request(f"indexes/{index_uid}/stats")
        if "error" not in index_stats:
            print(f"      ✅ Stats: {json.dumps(index_stats, indent=8)}")
        else:
            print(f"      ❌ Stats failed: {index_stats.get('error', 'Unknown error')}")
        
        # Try settings endpoint
        print(f"      Testing settings endpoint...")
        index_settings = make_request(f"indexes/{index_uid}/settings")
        if "error" not in index_settings:
            print(f"      ✅ Settings retrieved")
            print(f"      Searchable attributes: {index_settings.get('searchableAttributes', [])}")
        else:
            print(f"      ❌ Settings failed: {index_settings.get('error', 'Unknown error')}")
    
    print("\n✅ Test completed!")

if __name__ == "__main__":
    main()


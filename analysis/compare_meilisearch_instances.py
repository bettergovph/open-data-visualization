"""
Compare two Meilisearch instances to identify differences in indexes, settings, and facets.
Compares:
- Local instance: MEILI_HTTP_ADDR + MEILI_LOCAL_MASTER_KEY (or MEILI_MASTER_KEY)
- Remote instance: MEILI_HTTPS_ADDR + MEILI_MASTER_KEY
"""

import os
import json
import requests
from typing import Dict, Any, Optional, List, Set
from urllib.parse import urlparse

# Load environment variables
from dotenv import load_dotenv
# Try multiple .env file locations
load_dotenv('.env')  # Default .env file
load_dotenv('visualization.env')  # Example/template file

# Local instance (HTTP)
LOCAL_ADDR = os.getenv('MEILI_HTTP_ADDR', '127.0.0.1:7700')
LOCAL_KEY = os.getenv('MEILI_LOCAL_MASTER_KEY') or os.getenv('MEILI_MASTER_KEY', '')
LOCAL_URL = f"http://{LOCAL_ADDR}"

# Remote instance (HTTPS)
# Note: For remote, MEILI_MASTER_KEY is shared, but we check MEILI_HTTPS_ADDR specifically
REMOTE_ADDR = os.getenv('MEILI_HTTPS_ADDR', '')
# For remote, use MEILI_MASTER_KEY (the main/remote key)
# If you need a different key for remote, add MEILI_REMOTE_MASTER_KEY to your .env
REMOTE_KEY = os.getenv('MEILI_REMOTE_MASTER_KEY') or os.getenv('MEILI_MASTER_KEY', '')

# Ensure remote URL has protocol if set
if REMOTE_ADDR:
    if not REMOTE_ADDR.startswith('http'):
        REMOTE_URL = f"https://{REMOTE_ADDR}"
    else:
        REMOTE_URL = REMOTE_ADDR
else:
    REMOTE_URL = None

def make_request(instance_name: str, base_url: str, api_key: str, endpoint: str, method: str = "GET") -> Optional[Dict]:
    """Make a request to Meilisearch instance"""
    url = f"{base_url}{endpoint}"
    headers = {
        "Content-Type": "application/json"
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=10)
        elif method == "POST":
            response = requests.post(url, headers=headers, json={}, timeout=10)
        else:
            response = requests.request(method, url, headers=headers, timeout=10)
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Error querying {instance_name} at {url}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                print(f"   Response: {e.response.text}")
            except:
                pass
        return None

def get_indexes(instance_name: str, base_url: str, api_key: str) -> List[str]:
    """Get list of indexes from Meilisearch instance"""
    result = make_request(instance_name, base_url, api_key, "/indexes")
    if result:
        return [idx['uid'] for idx in result.get('results', [])]
    return []

def get_index_settings(instance_name: str, base_url: str, api_key: str, index_uid: str) -> Optional[Dict]:
    """Get all settings for an index"""
    settings = {}
    
    # Get all possible settings
    endpoints = {
        'displayedAttributes': f"/indexes/{index_uid}/settings/displayed-attributes",
        'searchableAttributes': f"/indexes/{index_uid}/settings/searchable-attributes",
        'filterableAttributes': f"/indexes/{index_uid}/settings/filterable-attributes",
        'sortableAttributes': f"/indexes/{index_uid}/settings/sortable-attributes",
        'rankingRules': f"/indexes/{index_uid}/settings/ranking-rules",
        'stopWords': f"/indexes/{index_uid}/settings/stop-words",
        'synonyms': f"/indexes/{index_uid}/settings/synonyms",
        'distinctAttribute': f"/indexes/{index_uid}/settings/distinct-attribute",
        'typoTolerance': f"/indexes/{index_uid}/settings/typo-tolerance",
        'faceting': f"/indexes/{index_uid}/settings/faceting",
        'pagination': f"/indexes/{index_uid}/settings/pagination",
    }
    
    for key, endpoint in endpoints.items():
        result = make_request(instance_name, base_url, api_key, endpoint)
        if result is not None:
            settings[key] = result
    
    # Also get index stats and info
    info = make_request(instance_name, base_url, api_key, f"/indexes/{index_uid}")
    if info:
        settings['_indexInfo'] = {
            'uid': info.get('uid'),
            'primaryKey': info.get('primaryKey'),
            'createdAt': info.get('createdAt'),
            'updatedAt': info.get('updatedAt'),
        }
    
    stats = make_request(instance_name, base_url, api_key, f"/indexes/{index_uid}/stats")
    if stats:
        settings['_stats'] = stats
    
    return settings

def compare_settings(local_settings: Dict, remote_settings: Dict, setting_name: str) -> Dict[str, Any]:
    """Compare a specific setting between two instances"""
    local_val = local_settings.get(setting_name)
    remote_val = remote_settings.get(setting_name)
    
    result = {
        'setting': setting_name,
        'local': local_val,
        'remote': remote_val,
        'match': local_val == remote_val,
        'local_only': [],
        'remote_only': [],
    }
    
    if isinstance(local_val, list) and isinstance(remote_val, list):
        local_set = set(local_val) if local_val else set()
        remote_set = set(remote_val) if remote_val else set()
        result['local_only'] = list(local_set - remote_set)
        result['remote_only'] = list(remote_set - local_set)
        result['match'] = local_set == remote_set
    
    return result

def format_diff(diff: Dict) -> str:
    """Format a difference for display"""
    lines = [f"  📋 Setting: {diff['setting']}"]
    
    if diff['match']:
        lines.append("     ✅ Match")
    else:
        lines.append("     ❌ Mismatch")
        
        if diff['local_only']:
            lines.append(f"     🔵 Local only: {diff['local_only']}")
        if diff['remote_only']:
            lines.append(f"     🔴 Remote only: {diff['remote_only']}")
        
        if not isinstance(diff['local'], list) and not isinstance(diff['remote'], list):
            lines.append(f"     Local: {diff['local']}")
            lines.append(f"     Remote: {diff['remote']}")
    
    return "\n".join(lines)

def main():
    print("🔍 Meilisearch Instance Comparison Tool")
    print("=" * 80)
    print(f"\n📡 Local Instance: {LOCAL_URL}")
    if REMOTE_URL:
        print(f"📡 Remote Instance: {REMOTE_URL}")
    else:
        print(f"📡 Remote Instance: ❌ MEILI_HTTPS_ADDR not set")
        print("\n⚠️  To compare instances, please set:")
        print("   - MEILI_HTTPS_ADDR (e.g., 'meilisearch.example.com' or 'https://meilisearch.example.com')")
        print("   - MEILI_MASTER_KEY (for remote instance)")
        print("\n   Current environment variables found:")
        print(f"   - MEILI_HTTP_ADDR: {os.getenv('MEILI_HTTP_ADDR', 'NOT SET')}")
        print(f"   - MEILI_HTTPS_ADDR: {os.getenv('MEILI_HTTPS_ADDR', 'NOT SET')}")
        print(f"   - MEILI_MASTER_KEY: {'SET' if os.getenv('MEILI_MASTER_KEY') else 'NOT SET'}")
        print(f"   - MEILI_LOCAL_MASTER_KEY: {'SET' if os.getenv('MEILI_LOCAL_MASTER_KEY') else 'NOT SET'}")
        print(f"   - MEILI_REMOTE_MASTER_KEY: {'SET' if os.getenv('MEILI_REMOTE_MASTER_KEY') else 'NOT SET'}")
        return
    print("=" * 80)
    
    # Test connections
    print("\n🔌 Testing connections...")
    local_health = make_request("Local", LOCAL_URL, LOCAL_KEY, "/health")
    remote_health = make_request("Remote", REMOTE_URL, REMOTE_KEY, "/health")
    
    if not local_health:
        print("❌ Cannot connect to local instance")
        return
    print(f"✅ Local instance: {local_health.get('status', 'unknown')}")
    
    if not remote_health:
        print("❌ Cannot connect to remote instance")
        return
    print(f"✅ Remote instance: {remote_health.get('status', 'unknown')}")
    
    # Get indexes
    print("\n📚 Fetching indexes...")
    local_indexes = get_indexes("Local", LOCAL_URL, LOCAL_KEY)
    remote_indexes = get_indexes("Remote", REMOTE_URL, REMOTE_KEY)
    
    print(f"   Local indexes ({len(local_indexes)}): {', '.join(local_indexes)}")
    print(f"   Remote indexes ({len(remote_indexes)}): {', '.join(remote_indexes)}")
    
    # Find common indexes
    common_indexes = set(local_indexes) & set(remote_indexes)
    local_only = set(local_indexes) - set(remote_indexes)
    remote_only = set(remote_indexes) - set(local_indexes)
    
    print(f"\n📊 Index Comparison:")
    print(f"   Common indexes: {len(common_indexes)}")
    if local_only:
        print(f"   🔵 Local only: {', '.join(local_only)}")
    if remote_only:
        print(f"   🔴 Remote only: {', '.join(remote_only)}")
    
    # Compare settings for common indexes
    if common_indexes:
        print(f"\n🔬 Comparing settings for {len(common_indexes)} common index(es)...")
        
        for index_uid in sorted(common_indexes):
            print(f"\n{'='*80}")
            print(f"📇 Index: {index_uid}")
            print('='*80)
            
            print(f"\n📥 Fetching settings from local instance...")
            local_settings = get_index_settings("Local", LOCAL_URL, LOCAL_KEY, index_uid)
            
            print(f"📥 Fetching settings from remote instance...")
            remote_settings = get_index_settings("Remote", REMOTE_URL, REMOTE_KEY, index_uid)
            
            if not local_settings or not remote_settings:
                print("⚠️  Could not fetch all settings, skipping detailed comparison")
                continue
            
            # Compare key settings
            settings_to_compare = [
                'displayedAttributes',
                'searchableAttributes',
                'filterableAttributes',
                'sortableAttributes',
                'rankingRules',
                'stopWords',
                'synonyms',
                'distinctAttribute',
                'faceting',  # This is the key one - facets configuration
                'typoTolerance',
                'pagination',
            ]
            
            print(f"\n⚙️  Settings Comparison:")
            differences = []
            for setting in settings_to_compare:
                diff = compare_settings(local_settings, remote_settings, setting)
                if not diff['match']:
                    differences.append(diff)
                    print(format_diff(diff))
                else:
                    print(f"  ✅ {setting}: Match")
            
            # Compare index info
            local_info = local_settings.get('_indexInfo', {})
            remote_info = remote_settings.get('_indexInfo', {})
            
            print(f"\n📊 Index Info:")
            print(f"   Local primary key: {local_info.get('primaryKey')}")
            print(f"   Remote primary key: {remote_info.get('primaryKey')}")
            
            local_stats = local_settings.get('_stats', {})
            remote_stats = remote_settings.get('_stats', {})
            
            print(f"\n📈 Statistics:")
            print(f"   Local documents: {local_stats.get('numberOfDocuments', 'N/A')}")
            print(f"   Remote documents: {remote_stats.get('numberOfDocuments', 'N/A')}")
            
            # Highlight faceting differences
            faceting_diff = compare_settings(local_settings, remote_settings, 'faceting')
            if not faceting_diff['match']:
                print(f"\n⚠️  FACETING DIFFERENCES DETECTED!")
                print(f"   This is important - facets affect search filtering capabilities")
                print(format_diff(faceting_diff))
                
                # Show detailed faceting config
                if local_settings.get('faceting'):
                    print(f"\n   Local faceting config:")
                    print(json.dumps(local_settings['faceting'], indent=6))
                if remote_settings.get('faceting'):
                    print(f"\n   Remote faceting config:")
                    print(json.dumps(remote_settings['faceting'], indent=6))
            
            # Show filterable attributes differences (related to faceting)
            filterable_diff = compare_settings(local_settings, remote_settings, 'filterableAttributes')
            if not filterable_diff['match']:
                print(f"\n⚠️  FILTERABLE ATTRIBUTES DIFFERENCES (affects faceting):")
                print(format_diff(filterable_diff))
            
            if not differences:
                print(f"\n✅ All settings match for index '{index_uid}'")
    
    print(f"\n{'='*80}")
    print("✅ Comparison complete!")

if __name__ == "__main__":
    main()


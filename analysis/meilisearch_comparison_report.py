"""
Meilisearch Instance Comparison Report
Generates a detailed report comparing local HTTP and remote HTTPS Meilisearch instances
"""

import os
import json
import requests
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

# Load environment variables
load_dotenv('.env')

# Configuration
LOCAL_ADDR = os.getenv('MEILI_HTTP_ADDR', '127.0.0.1:7700')
LOCAL_KEY = os.getenv('MEILI_LOCAL_MASTER_KEY') or os.getenv('MEILI_MASTER_KEY', '')
LOCAL_URL = f"http://{LOCAL_ADDR}"

REMOTE_ADDR = os.getenv('MEILI_HTTPS_ADDR', '')
REMOTE_KEY = os.getenv('MEILI_MASTER_KEY', '')
if REMOTE_ADDR:
    if not REMOTE_ADDR.startswith('http'):
        REMOTE_URL = f"https://{REMOTE_ADDR}"
    else:
        REMOTE_URL = REMOTE_ADDR
else:
    REMOTE_URL = None

def make_request(instance_name: str, base_url: str, api_key: str, endpoint: str) -> Optional[Dict]:
    """Make a request to Meilisearch instance"""
    url = f"{base_url}{endpoint}"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Error querying {instance_name}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_data = e.response.json()
                print(f"   Error details: {error_data}")
            except:
                print(f"   Response: {e.response.text}")
        return None

def get_index_info(instance_name: str, base_url: str, api_key: str, index_uid: str) -> Dict[str, Any]:
    """Get comprehensive information about an index"""
    info = {}
    
    # Basic index info
    basic_info = make_request(instance_name, base_url, api_key, f"/indexes/{index_uid}")
    if basic_info:
        info['basic'] = basic_info
    
    # Index stats
    stats = make_request(instance_name, base_url, api_key, f"/indexes/{index_uid}/stats")
    if stats:
        info['stats'] = stats
    
    # Settings
    settings_endpoints = {
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
    
    info['settings'] = {}
    for setting_name, endpoint in settings_endpoints.items():
        result = make_request(instance_name, base_url, api_key, endpoint)
        if result is not None:
            info['settings'][setting_name] = result
    
    return info

def generate_report():
    """Generate comprehensive comparison report"""
    print("🔍 Meilisearch Instance Comparison Report")
    print("=" * 80)
    print(f"📅 Generated: {os.popen('date').read().strip()}")
    print("=" * 80)
    
    print(f"\n📡 INSTANCE CONFIGURATION")
    print(f"Local (HTTP):  {LOCAL_URL}")
    print(f"Remote (HTTPS): {REMOTE_URL if REMOTE_URL else 'NOT CONFIGURED'}")
    print(f"Local Key: {'SET' if LOCAL_KEY else 'NOT SET'}")
    print(f"Remote Key: {'SET' if REMOTE_KEY else 'NOT SET'}")
    
    # Test connections
    print(f"\n🔌 CONNECTION TEST")
    local_health = make_request("Local", LOCAL_URL, LOCAL_KEY, "/health")
    if local_health:
        print(f"✅ Local instance: {local_health.get('status', 'unknown')}")
    else:
        print("❌ Local instance: CONNECTION FAILED")
        return
    
    if REMOTE_URL:
        remote_health = make_request("Remote", REMOTE_URL, REMOTE_KEY, "/health")
        if remote_health:
            print(f"✅ Remote instance: {remote_health.get('status', 'unknown')}")
        else:
            print("❌ Remote instance: CONNECTION FAILED")
            print("⚠️  Cannot proceed with detailed comparison due to remote connection failure")
            return
    else:
        print("❌ Remote instance: NOT CONFIGURED")
        return
    
    # Get indexes
    print(f"\n📚 INDEX DISCOVERY")
    local_indexes = []
    remote_indexes = []
    
    local_indexes_result = make_request("Local", LOCAL_URL, LOCAL_KEY, "/indexes")
    if local_indexes_result:
        local_indexes = [idx['uid'] for idx in local_indexes_result.get('results', [])]
    
    remote_indexes_result = make_request("Remote", REMOTE_URL, REMOTE_KEY, "/indexes")
    if remote_indexes_result:
        remote_indexes = [idx['uid'] for idx in remote_indexes_result.get('results', [])]
    
    print(f"Local indexes ({len(local_indexes)}): {', '.join(local_indexes) if local_indexes else 'NONE'}")
    print(f"Remote indexes ({len(remote_indexes)}): {', '.join(remote_indexes) if remote_indexes else 'NONE'}")
    
    # Find common indexes
    common_indexes = set(local_indexes) & set(remote_indexes)
    local_only = set(local_indexes) - set(remote_indexes)
    remote_only = set(remote_indexes) - set(local_indexes)
    
    print(f"\n📊 INDEX COMPARISON SUMMARY")
    print(f"Common indexes: {len(common_indexes)}")
    if local_only:
        print(f"🔵 Local only: {', '.join(local_only)}")
    if remote_only:
        print(f"🔴 Remote only: {', '.join(remote_only)}")
    
    # Detailed comparison for common indexes
    if common_indexes:
        print(f"\n🔬 DETAILED COMPARISON FOR COMMON INDEXES")
        print("=" * 80)
        
        for index_uid in sorted(common_indexes):
            print(f"\n📇 INDEX: {index_uid}")
            print("-" * 60)
            
            # Get detailed info for both instances
            print("📥 Fetching local index details...")
            local_info = get_index_info("Local", LOCAL_URL, LOCAL_KEY, index_uid)
            
            print("📥 Fetching remote index details...")
            remote_info = get_index_info("Remote", REMOTE_URL, REMOTE_KEY, index_uid)
            
            # Compare basic info
            if local_info.get('basic') and remote_info.get('basic'):
                local_basic = local_info['basic']
                remote_basic = remote_info['basic']
                
                print(f"\n📋 BASIC INFO:")
                print(f"   Primary Key - Local: {local_basic.get('primaryKey')}, Remote: {remote_basic.get('primaryKey')}")
                print(f"   Created - Local: {local_basic.get('createdAt')}, Remote: {remote_basic.get('createdAt')}")
                print(f"   Updated - Local: {local_basic.get('updatedAt')}, Remote: {remote_basic.get('updatedAt')}")
            
            # Compare stats
            if local_info.get('stats') and remote_info.get('stats'):
                local_stats = local_info['stats']
                remote_stats = remote_info['stats']
                
                print(f"\n📈 STATISTICS:")
                print(f"   Documents - Local: {local_stats.get('numberOfDocuments', 'N/A')}, Remote: {remote_stats.get('numberOfDocuments', 'N/A')}")
                print(f"   Index Size - Local: {local_stats.get('indexSize', 'N/A')}, Remote: {remote_stats.get('indexSize', 'N/A')}")
            
            # Compare settings
            print(f"\n⚙️  SETTINGS COMPARISON:")
            local_settings = local_info.get('settings', {})
            remote_settings = remote_info.get('settings', {})
            
            settings_to_compare = [
                'displayedAttributes',
                'searchableAttributes', 
                'filterableAttributes',
                'sortableAttributes',
                'rankingRules',
                'stopWords',
                'synonyms',
                'distinctAttribute',
                'faceting',
                'typoTolerance',
                'pagination'
            ]
            
            differences_found = False
            for setting in settings_to_compare:
                local_val = local_settings.get(setting)
                remote_val = remote_settings.get(setting)
                
                if local_val != remote_val:
                    differences_found = True
                    print(f"\n   🔴 DIFFERENCE in {setting}:")
                    print(f"      Local:  {json.dumps(local_val, indent=8) if local_val else 'None'}")
                    print(f"      Remote: {json.dumps(remote_val, indent=8) if remote_val else 'None'}")
                else:
                    print(f"   ✅ {setting}: Match")
            
            if not differences_found:
                print("   ✅ All settings match!")
            
            # Highlight critical differences
            faceting_local = local_settings.get('faceting')
            faceting_remote = remote_settings.get('faceting')
            if faceting_local != faceting_remote:
                print(f"\n⚠️  CRITICAL: FACETING CONFIGURATION DIFFERS!")
                print("   This affects search filtering capabilities")
            
            filterable_local = local_settings.get('filterableAttributes', [])
            filterable_remote = remote_settings.get('filterableAttributes', [])
            if set(filterable_local) != set(filterable_remote):
                print(f"\n⚠️  CRITICAL: FILTERABLE ATTRIBUTES DIFFER!")
                print("   This affects which fields can be used for filtering")
                print(f"   Local only:  {set(filterable_local) - set(filterable_remote)}")
                print(f"   Remote only: {set(filterable_remote) - set(filterable_local)}")
    
    else:
        print(f"\n⚠️  NO COMMON INDEXES FOUND")
        print("Cannot perform detailed comparison without shared indexes")
    
    print(f"\n{'='*80}")
    print("✅ COMPARISON REPORT COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    generate_report()

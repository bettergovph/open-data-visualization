#!/usr/bin/env python3
"""
Verify that dynasty flags are consistent across runs
"""

import json
import hashlib

def verify_flag_consistency():
    """Verify that the same dynasty-location combination always gets the same flag ID"""
    
    # Load the current flag cache
    with open('static/data/dynasty_flags_cache.json', 'r', encoding='utf-8') as f:
        flag_data = json.load(f)
    
    print("🔍 Verifying flag consistency...")
    print(f"📊 Total dynasties in cache: {flag_data['summary']['total_dynasties']}")
    print(f"📅 Cache version: {flag_data['summary'].get('version', 'unknown')}")
    print(f"📅 Last updated: {flag_data['summary']['last_updated']}")
    
    # Test consistency for a sample of dynasties
    test_dynasties = list(flag_data['dynasties'].items())[:10]
    all_consistent = True
    
    print("\n🏴 Testing flag consistency for sample dynasties:")
    for key, dynasty in test_dynasties:
        # Recalculate the flag ID using the same method
        hash_object = hashlib.md5(key.encode())
        hex_dig = hash_object.hexdigest()
        recalculated_id = int(hex_dig[:8], 16) % 10000
        
        is_consistent = recalculated_id == dynasty['dynasty_id']
        status = "✅" if is_consistent else "❌"
        
        print(f"  {dynasty['surname']} ({dynasty['location_display']})")
        print(f"    Cached ID: {dynasty['dynasty_id']} | Recalculated: {recalculated_id} {status}")
        
        if not is_consistent:
            all_consistent = False
    
    print(f"\n{'✅ All flags are consistent!' if all_consistent else '❌ Some flags are inconsistent!'}")
    
    # Test a specific dynasty multiple times
    print("\n🔄 Testing same dynasty multiple times:")
    test_key = "TAN_CITY OF CALBAYOG_SAMAR"
    if test_key in flag_data['dynasties']:
        dynasty = flag_data['dynasties'][test_key]
        print(f"Testing: {dynasty['surname']} ({dynasty['location_display']})")
        
        for i in range(5):
            hash_object = hashlib.md5(test_key.encode())
            hex_dig = hash_object.hexdigest()
            recalculated_id = int(hex_dig[:8], 16) % 10000
            is_consistent = recalculated_id == dynasty['dynasty_id']
            print(f"  Run {i+1}: {recalculated_id} {'✅' if is_consistent else '❌'}")
    
    return all_consistent

if __name__ == "__main__":
    verify_flag_consistency()

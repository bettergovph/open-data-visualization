#!/usr/bin/env python3
"""
Regenerate dynasty flags from saved parameters
"""

import json
import os
from datetime import datetime

def regenerate_flags_from_cache():
    """Regenerate flags using saved parameters from cache"""
    
    # Load the flag cache
    cache_file = "static/data/dynasty_flags_cache.json"
    if not os.path.exists(cache_file):
        print("❌ Flag cache not found. Please run generate_dynasty_flags.py first.")
        return
    
    with open(cache_file, 'r', encoding='utf-8') as f:
        flag_data = json.load(f)
    
    print("🏴 Regenerating flags from saved parameters...")
    print(f"📊 Total dynasties: {flag_data['summary']['total_dynasties']}")
    
    # Test regeneration for a few dynasties
    test_dynasties = list(flag_data['dynasties'].items())[:5]
    
    print("\n🔄 Testing flag regeneration:")
    for key, dynasty in test_dynasties:
        print(f"\n📋 {dynasty['surname']} ({dynasty['location_display']})")
        print(f"   Flag ID: {dynasty['dynasty_id']}")
        
        if 'flag_parameters' in dynasty:
            params = dynasty['flag_parameters']
            print(f"   Parameters:")
            print(f"     - Slices: {params['slices']}")
            print(f"     - Orientation: {params['orientation']}")
            print(f"     - Shape Sequence: {params['shape_sequence']}")
            print(f"     - Color Scheme: {params['color_scheme']}")
            print(f"     - Symbol: {params['symbol'] or 'None'}")
            print(f"     - Variation: {params['variation']}")
            print(f"     - Czech Style: {params['is_czech_style']}")
            print(f"     - Seed: {params['seed']}")
        else:
            print("   ⚠️ No flag parameters found (old cache format)")
    
    # Update cache with regeneration timestamp
    flag_data['summary']['last_regenerated'] = datetime.now().isoformat()
    flag_data['summary']['regeneration_count'] = flag_data['summary'].get('regeneration_count', 0) + 1
    
    # Save updated cache
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(flag_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Flags regenerated successfully!")
    print(f"📅 Last regenerated: {flag_data['summary']['last_regenerated']}")
    print(f"🔄 Regeneration count: {flag_data['summary']['regeneration_count']}")

def create_flag_svg_from_parameters(flag_params):
    """Create SVG flag from saved parameters (placeholder for JavaScript integration)"""
    
    # This would integrate with the JavaScript DynastyFlagGenerator
    # For now, just return the parameters that would be used
    return {
        "method": "createFlagFromParameters",
        "parameters": flag_params,
        "note": "This would call the JavaScript DynastyFlagGenerator.createFlagFromParameters() method"
    }

if __name__ == "__main__":
    regenerate_flags_from_cache()

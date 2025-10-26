#!/usr/bin/env python3
"""
Generate dynasty flags based on province/municipality/city
"""

import asyncio
import asyncpg
import json
import os
import hashlib
from datetime import datetime

def generate_flag_parameters(flag_id, surname):
    """Generate deterministic flag parameters for a dynasty"""
    
    # Create a seeded random number generator using the flag_id
    def seeded_rng(seed):
        def rng():
            seed_val = (seed * 9301 + 49297) % 233280
            return seed_val / 233280.0
        return rng
    
    rng = seeded_rng(flag_id)
    
    # Generate flag parameters with more variation
    colors = [
        '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7',
        '#DDA0DD', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9',
        '#FF9F43', '#6C5CE7', '#A29BFE', '#FD79A8', '#FDCB6E',
        '#E17055', '#00B894', '#00CEC9', '#74B9FF', '#0984E3'
    ]
    
    shapes = ['rectangle', 'horizontal-rectangle', 'rounded-rectangle', 'diamond', 'circle', 'triangle']
    czech_shapes = ['triangle', 'chevron', 'arrow']
    symbols = ['circle', 'cross', 'crescent', 'star', 'diamond', 'triangle', 'square', 'hexagon', 'arrow', 'heart', 'shield', 'crown', 'eagle', 'lion']
    slice_orientations = ['vertical', 'horizontal', 'diagonal-right', 'diagonal-left', 'radial', 'spiral']
    
    # Generate number of slices (weighted random like in JavaScript)
    slice_weights = [1, 3, 4, 4, 4, 4, 4, 4, 3, 1]  # Weights for 1-10 slices
    total_weight = sum(slice_weights)
    random_value = rng() * total_weight
    
    num_slices = 1
    for i, weight in enumerate(slice_weights):
        random_value -= weight
        if random_value <= 0:
            num_slices = i + 1
            break
    
    # Generate variation
    variation = int(rng() * 10)
    
    # Decide if Czech-style (50% chance)
    is_czech_style = rng() < 0.5
    
    # Generate shape sequence
    shape_sequence = []
    for i in range(num_slices):
        if is_czech_style:
            shape_sequence.append('triangle')
        else:
            shape_sequence.append(shapes[int(rng() * len(shapes))])
    
    # Generate color scheme - ensure different colors for each slice
    color_scheme = []
    for i in range(num_slices):
        # Use slice index to ensure different colors
        color_index = (int(rng() * len(colors)) + i) % len(colors)
        color_scheme.append(colors[color_index])
    
    # Generate orientation
    orientation = slice_orientations[int(rng() * len(slice_orientations))]
    
    # Generate symbol (50% chance of having a symbol)
    symbol = None
    if rng() < 0.5:
        symbol = symbols[int(rng() * len(symbols))]
    
    return {
        "slices": num_slices,
        "orientation": orientation,
        "shape_sequence": shape_sequence,
        "color_scheme": color_scheme,
        "symbol": symbol,
        "variation": variation,
        "is_czech_style": is_czech_style,
        "seed": flag_id
    }

async def generate_dynasty_flags():
    """Generate flags for each dynasty based on their location"""
    
    # Database connection
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu',
        database='dynasty'
    )
    
    try:
        print("🏴 Generating dynasty flags...")
        
        # Get unique dynasties grouped by surname+province for unique flags
        query = """
        SELECT DISTINCT 
            last_name as surname,
            region,
            province,
            COUNT(*) as member_count
        FROM political_dynasties 
        WHERE last_name IS NOT NULL 
        AND last_name != ''
        AND province IS NOT NULL
        AND province != ''
        GROUP BY last_name, region, province
        ORDER BY member_count DESC, last_name, province
        """
        
        dynasties = await conn.fetch(query)
        print(f"📊 Found {len(dynasties)} dynasty-location combinations")
        
        # Create flag assignments
        flag_assignments = {}
        
        for dynasty in dynasties:
            # Create a unique key for this dynasty-location combination
            # Use surname + province for unique flags per surname+province
            location_key = f"{dynasty['surname']}_{dynasty['province']}"
            
            # Generate a deterministic flag ID based on the surname+province combination
            import hashlib
            # Create a stable hash from the location key
            hash_object = hashlib.md5(location_key.encode())
            hex_dig = hash_object.hexdigest()
            # Convert first 8 characters to integer for consistent flag ID
            flag_id = int(hex_dig[:8], 16) % 10000
            
            # Determine the location display name
            location_parts = []
            if dynasty['province']:
                location_parts.append(dynasty['province'])
            if dynasty['region']:
                location_parts.append(dynasty['region'])
            
            location_display = ', '.join(location_parts) if location_parts else 'Unknown Location'
            
            # Generate flag parameters for this dynasty
            flag_params = generate_flag_parameters(flag_id, dynasty['surname'])
            
            flag_assignments[location_key] = {
                "dynasty_id": flag_id,
                "surname": dynasty['surname'],
                "region": dynasty['region'],
                "province": dynasty['province'],
                "location_display": location_display,
                "member_count": dynasty['member_count'],
                "flag_parameters": flag_params
            }
        
        # Create cache data structure
        cache_data = {
            "summary": {
                "total_dynasties": len(flag_assignments),
                "last_updated": datetime.now().isoformat(),
                "version": "1.0",
                "description": "Dynasty flags assigned by province/municipality/city with deterministic hash-based IDs"
            },
            "dynasties": flag_assignments
        }
        
        # Ensure cache directory exists
        cache_dir = "static/data"
        os.makedirs(cache_dir, exist_ok=True)
        
        # Write cache file
        cache_file = os.path.join(cache_dir, "dynasty_flags_cache.json")
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Dynasty flags cache generated: {cache_file}")
        print(f"📊 Total dynasties: {len(flag_assignments)}")
        
        # Show some examples
        print("\n🏴 Sample dynasty flags:")
        for i, (key, dynasty) in enumerate(list(flag_assignments.items())[:5]):
            print(f"  {dynasty['surname']} ({dynasty['location_display']}) - Flag ID: {dynasty['dynasty_id']}")
        
        # Test flag consistency
        print("\n🔍 Testing flag consistency:")
        test_keys = list(flag_assignments.keys())[:3]
        for key in test_keys:
            dynasty = flag_assignments[key]
            # Recalculate the flag ID to verify consistency
            hash_object = hashlib.md5(key.encode())
            hex_dig = hash_object.hexdigest()
            recalculated_id = int(hex_dig[:8], 16) % 10000
            is_consistent = recalculated_id == dynasty['dynasty_id']
            print(f"  {dynasty['surname']}: {dynasty['dynasty_id']} {'✅' if is_consistent else '❌'} (recalculated: {recalculated_id})")
        
        return cache_data
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(generate_dynasty_flags())

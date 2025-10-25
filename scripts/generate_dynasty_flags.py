#!/usr/bin/env python3
"""
Generate dynasty flags based on province/municipality/city
"""

import asyncio
import asyncpg
import json
import os
from datetime import datetime

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
        
        # Get unique dynasties with their locations
        query = """
        SELECT DISTINCT 
            last_name as surname,
            region,
            province,
            municipality_city,
            COUNT(*) as member_count
        FROM political_dynasties 
        WHERE last_name IS NOT NULL 
        AND last_name != ''
        GROUP BY last_name, region, province, municipality_city
        ORDER BY member_count DESC, last_name, province, municipality_city
        """
        
        dynasties = await conn.fetch(query)
        print(f"📊 Found {len(dynasties)} dynasty-location combinations")
        
        # Create flag assignments
        flag_assignments = {}
        
        for dynasty in dynasties:
            # Create a unique key for this dynasty-location combination
            location_key = f"{dynasty['surname']}_{dynasty['province']}_{dynasty['municipality_city']}"
            
            # Generate a deterministic flag ID based on the location
            flag_id = hash(location_key) % 10000  # Keep it reasonable
            
            # Determine the location display name
            location_parts = []
            if dynasty['municipality_city']:
                location_parts.append(dynasty['municipality_city'])
            if dynasty['province']:
                location_parts.append(dynasty['province'])
            if dynasty['region']:
                location_parts.append(dynasty['region'])
            
            location_display = ', '.join(location_parts) if location_parts else 'Unknown Location'
            
            flag_assignments[location_key] = {
                "dynasty_id": flag_id,
                "surname": dynasty['surname'],
                "region": dynasty['region'],
                "province": dynasty['province'],
                "municipality_city": dynasty['municipality_city'],
                "location_display": location_display,
                "member_count": dynasty['member_count']
            }
        
        # Create cache data structure
        cache_data = {
            "summary": {
                "total_dynasties": len(flag_assignments),
                "last_updated": datetime.now().isoformat(),
                "description": "Dynasty flags assigned by province/municipality/city"
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
        
        return cache_data
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(generate_dynasty_flags())

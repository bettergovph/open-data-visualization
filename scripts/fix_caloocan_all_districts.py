#!/usr/bin/env python3
"""
Fix all 3 Caloocan districts with complete barangays.
Source: Perplexity API (sonar-pro) with PSA/COMELEC/Wikipedia sources
Total: 193 barangays (updated 2024, includes split of Barangay 176)
"""

import asyncio
import asyncpg
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

async def main():
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD'),
        database=os.getenv('POSTGRES_DB_DYNASTY')
    )
    
    print("✅ Connected to dynasty database\n")
    
    # Caloocan districts (193 total barangays as of 2024)
    districts = {
        '1st District': [
            "Barangay 1", "Barangay 2", "Barangay 3", "Barangay 4",
            "Barangay 77", "Barangay 78", "Barangay 79", "Barangay 80", "Barangay 81", 
            "Barangay 82", "Barangay 83", "Barangay 84", "Barangay 85",
            "Barangay 132", "Barangay 133", "Barangay 134", "Barangay 135", "Barangay 136", 
            "Barangay 137", "Barangay 138", "Barangay 139", "Barangay 140", "Barangay 141", 
            "Barangay 142", "Barangay 143", "Barangay 144", "Barangay 145", "Barangay 146", 
            "Barangay 147", "Barangay 148", "Barangay 149", "Barangay 150", "Barangay 151", 
            "Barangay 152", "Barangay 153", "Barangay 154", "Barangay 155", "Barangay 156", 
            "Barangay 157", "Barangay 158", "Barangay 159", "Barangay 160", "Barangay 161", 
            "Barangay 162", "Barangay 163", "Barangay 164",
            "Barangay 165", "Barangay 166", "Barangay 167", "Barangay 168", "Barangay 169", 
            "Barangay 170", "Barangay 171", "Barangay 172", "Barangay 173", "Barangay 174", 
            "Barangay 175",
            "Barangay 176-A", "Barangay 176-B", "Barangay 176-C", "Barangay 176-D", 
            "Barangay 176-E", "Barangay 176-F",
            "Barangay 177"
        ],
        '2nd District': [
            "Barangay 5", "Barangay 6", "Barangay 7", "Barangay 8", "Barangay 9", 
            "Barangay 10", "Barangay 11", "Barangay 12", "Barangay 13", "Barangay 14", 
            "Barangay 15", "Barangay 16", "Barangay 17", "Barangay 18", "Barangay 19", 
            "Barangay 20", "Barangay 21", "Barangay 22", "Barangay 23", "Barangay 24", 
            "Barangay 25", "Barangay 26", "Barangay 27", "Barangay 28", "Barangay 29", 
            "Barangay 30", "Barangay 31", "Barangay 32", "Barangay 33", "Barangay 34", 
            "Barangay 35", "Barangay 36", "Barangay 37", "Barangay 38", "Barangay 39", 
            "Barangay 40", "Barangay 41", "Barangay 42", "Barangay 43", "Barangay 44", 
            "Barangay 45", "Barangay 46", "Barangay 47", "Barangay 48", "Barangay 49", 
            "Barangay 50", "Barangay 51", "Barangay 52", "Barangay 53", "Barangay 54", 
            "Barangay 55", "Barangay 56", "Barangay 57", "Barangay 58", "Barangay 59", 
            "Barangay 60", "Barangay 61", "Barangay 62", "Barangay 63", "Barangay 64", 
            "Barangay 65", "Barangay 66", "Barangay 67", "Barangay 68", "Barangay 69", 
            "Barangay 70", "Barangay 71", "Barangay 72", "Barangay 73", "Barangay 74", 
            "Barangay 75", "Barangay 76",
            "Barangay 86", "Barangay 87", "Barangay 88", "Barangay 89", "Barangay 90", 
            "Barangay 91", "Barangay 92", "Barangay 93", "Barangay 94", "Barangay 95", 
            "Barangay 96", "Barangay 97", "Barangay 98", "Barangay 99", "Barangay 100", 
            "Barangay 101", "Barangay 102", "Barangay 103", "Barangay 104", "Barangay 105", 
            "Barangay 106", "Barangay 107", "Barangay 108", "Barangay 109", "Barangay 110", 
            "Barangay 111", "Barangay 112", "Barangay 113", "Barangay 114", "Barangay 115", 
            "Barangay 116", "Barangay 117", "Barangay 118", "Barangay 119", "Barangay 120", 
            "Barangay 121", "Barangay 122", "Barangay 123", "Barangay 124", "Barangay 125", 
            "Barangay 126", "Barangay 127", "Barangay 128", "Barangay 129", "Barangay 130", 
            "Barangay 131"
        ],
        '3rd District': [
            "Barangay 178", "Barangay 179", "Barangay 180", "Barangay 181", "Barangay 182", 
            "Barangay 183", "Barangay 184", "Barangay 185", "Barangay 186", "Barangay 187", 
            "Barangay 188"
        ]
    }
    
    print("📍 Caloocan Districts:")
    total = 0
    for district, barangays in districts.items():
        print(f"   {district}: {len(barangays)} barangays")
        total += len(barangays)
    print(f"   TOTAL: {total} barangays\n")
    
    # Update each district
    query = """
        UPDATE dynasty_projects_congressmen_config
        SET barangays = $1::jsonb,
            updated_at = NOW()
        WHERE province = 'Caloocan' 
          AND district_number = $2
          AND is_city_district = true
        RETURNING id, display_name, jsonb_array_length(barangays) as count
    """
    
    updated_count = 0
    for district, barangays in districts.items():
        print(f"Updating {district}...")
        results = await conn.fetch(query, json.dumps(barangays), district)
        if results:
            for row in results:
                print(f"✅ Updated {row['display_name']} (ID: {row['id']}) with {row['count']} barangays")
                updated_count += 1
        else:
            print(f"⚠️  No congressmen found for {district}")
        print()
    
    print("=" * 80)
    print(f"✅ Caloocan complete! Updated {updated_count} congressmen across 3 districts")
    print(f"   Total: {total} barangays (includes 2024 split of Barangay 176)")
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())




















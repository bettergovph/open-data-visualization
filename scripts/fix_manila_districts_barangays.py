#!/usr/bin/env python3
"""
Fix Manila districts with complete barangay lists based on official PSA data.
Manila has 896 barangays numbered 1-905 (with some gaps).
"""

import asyncio
import asyncpg
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

async def main():
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    # Connect to dynasty database
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER'),
        password=os.getenv('POSTGRES_PASSWORD'),
        database=os.getenv('POSTGRES_DB_DYNASTY')
    )
    
    print("✅ Connected to dynasty database\n")
    
    # Manila district barangay ranges based on PSA official data
    manila_districts = {
        '1st District': list(range(1, 147)),  # Barangays 1-146 (Western Tondo)
        '2nd District': list(range(147, 268)),  # Barangays 147-267 (Eastern Tondo)
        '3rd District': list(range(268, 395)),  # Barangays 268-394 (Binondo, Quiapo, San Nicolas, Santa Cruz)
        '4th District': list(range(395, 587)),  # Barangays 395-586 (Sampaloc)
        '5th District': list(range(649, 829)),  # Barangays 649-828 (Ermita, Malate, Paco, Port Area, San Andres)
        '6th District': list(range(587, 649)) + list(range(829, 906))  # Barangays 587-648 and 829-905 (San Miguel, Santa Ana, Santa Mesa, Pandacan)
    }
    
    print("=" * 80)
    print("UPDATING MANILA DISTRICTS WITH COMPLETE BARANGAY DATA")
    print("=" * 80)
    print()
    
    for district, barangay_numbers in manila_districts.items():
        # Format barangays as "Barangay 1", "Barangay 2", etc.
        barangays = [f"Barangay {num}" for num in barangay_numbers]
        
        print(f"📍 {district}: {len(barangays)} barangays (numbers {barangay_numbers[0]}-{barangay_numbers[-1]})")
        
        # Update all congressmen in this district
        query = """
            UPDATE dynasty_projects_congressmen_config
            SET barangays = $1::jsonb,
                updated_at = NOW()
            WHERE province = 'Manila' 
              AND district_number = $2
            RETURNING id, display_name, jsonb_array_length(barangays) as count
        """
        
        import json
        barangays_json = json.dumps(barangays)
        
        results = await conn.fetch(query, barangays_json, district)
        
        for row in results:
            print(f"  ✅ Updated {row['display_name']} (ID: {row['id']}) with {row['count']} barangays")
        
        print()
    
    print("=" * 80)
    print("VERIFICATION")
    print("=" * 80)
    print()
    
    # Verify the updates
    verify_query = """
        SELECT 
            district_number,
            display_name,
            jsonb_array_length(barangays) as barangay_count
        FROM dynasty_projects_congressmen_config
        WHERE province = 'Manila'
        ORDER BY district_number, display_name
    """
    
    rows = await conn.fetch(verify_query)
    
    for row in rows:
        print(f"  {row['district_number']}: {row['display_name']} - {row['barangay_count']} barangays")
    
    print()
    print("✅ All Manila districts updated with complete barangay data!")
    print()
    print("Next steps:")
    print("1. Run scripts/export_dynasty_json_from_db.py to update JSON files")
    print("2. Run scripts/generate_dynasty_projects_cache.py to regenerate caches")
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())











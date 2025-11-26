#!/usr/bin/env python3
"""
Fix Davao City 1st District with complete 54 barangays.
Source: Wikipedia, PSA official data
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
    
    # Davao City 1st District: 54 barangays (Poblacion 40 + Talomo 14)
    poblacion_barangays = [
        "1-A", "2-A", "3-A", "4-A", "5-A", "6-A", "7-A", "8-A", "9-A", "10-A",
        "11-B", "12-B", "13-B", "14-B", "15-B", "16-B", "17-B", "18-B", "19-B", "20-B",
        "21-C", "22-C", "23-C", "24-C", "25-C", "26-C", "27-C", "28-C", "29-C", "30-C",
        "31-D", "32-D", "33-D", "34-D", "35-D", "36-D", "37-D", "38-D", "39-D", "40-D"
    ]
    
    talomo_barangays = [
        "Bago Aplaya", "Bago Gallera", "Baliok", "Bucana", "Catalunan Grande",
        "Catalunan Pequeño", "Dumoy", "Langub", "Ma-a", "Magtuod",
        "Matina Aplaya", "Matina Crossing", "Matina Pangi", "Talomo Proper"
    ]
    
    all_barangays = poblacion_barangays + talomo_barangays
    
    print(f"📍 Davao City 1st District: {len(all_barangays)} barangays")
    print(f"   - Poblacion: {len(poblacion_barangays)} barangays")
    print(f"   - Talomo: {len(talomo_barangays)} barangays")
    print()
    
    query = """
        UPDATE dynasty_projects_congressmen_config
        SET barangays = $1::jsonb,
            updated_at = NOW()
        WHERE province = 'Davao City' 
          AND district_number = '1st District'
          AND is_city_district = true
        RETURNING id, display_name, jsonb_array_length(barangays) as count
    """
    
    barangays_json = json.dumps(all_barangays)
    results = await conn.fetch(query, barangays_json)
    
    for row in results:
        print(f"✅ Updated {row['display_name']} (ID: {row['id']}) with {row['count']} barangays")
    
    print()
    print("✅ Davao City 1st District complete!")
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())




















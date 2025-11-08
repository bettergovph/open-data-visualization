#!/usr/bin/env python3
"""
Fix all 6 Quezon City districts with complete barangays.
Source: Perplexity API (sonar-pro) with PSA/COMELEC/Wikipedia sources
Total: 142 barangays across 6 districts
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
    
    # Quezon City districts
    districts = {
        '1st District': [
            "Alicia", "Bagong Pag-asa", "Bahay Toro", "Balingasa", "Bungad", "Damar", 
            "Damayan", "Del Monte", "Katipunan", "Lourdes", "Maharlika", "Manresa", 
            "Mariblo", "Masambong", "N.S. Amoranto (Gintong Silahis)", "Nayong Kanluran", 
            "Paang Bundok", "Pag-ibig sa Nayon", "Paltok", "Paraiso", "Phil-Am", "Project 6", 
            "Ramon Magsaysay", "Saint Peter", "Salvacion", "San Antonio", "San Isidro Labrador", 
            "San Jose", "Santa Cruz", "Santa Teresita", "Sto. Cristo", "Santo Domingo (Matalahib)", 
            "Siena", "Talayan", "Vasra", "Veterans Village", "West Triangle"
        ],
        '2nd District': [
            "Bagong Silangan", "Batasan Hills", "Commonwealth", "Holy Spirit", "Payatas"
        ],
        '3rd District': [
            "Amihan", "Bagumbayan", "Bagumbuhay", "Bayanihan", "Blue Ridge A", "Blue Ridge B",
            "Camp Aguinaldo", "Claro", "Dioquino Zobel", "Duyan-Duyan", "E. Rodriguez", 
            "East Kamias", "Escopa I", "Escopa II", "Escopa III", "Escopa IV", "Libis", 
            "Loyola Heights", "Mangga", "Marilag", "Masagana", "Matandang Balara", "Milagrosa", 
            "Pansol", "Quirino 2-A", "Quirino 2-B", "Quirino 2-C", "Quirino 3-A", "Saint Ignatius", 
            "San Roque", "Silangan", "Socorro", "Tagumpay", "Ugong Norte", "Villa Maria Clara", 
            "West Kamias", "White Plains"
        ],
        '4th District': [
            "Bagong Lipunan ng Crame", "Botocan", "Central", "Damayang Lagi", "Don Manuel", 
            "Doña Aurora", "Doña Imelda", "Doña Josefa", "Horseshoe", "Immaculate Concepcion", 
            "Kalusugan", "Kamuning", "Kaunlaran", "Kristong Hari", "Krus na Ligas", "Laging Handa", 
            "Malaya", "Mariana", "Obrero", "Old Capitol Site", "Paligsahan", "Pinagkaisahan", 
            "Pinyahan", "Roxas", "Sacred Heart", "San Isidro Galas", "San Martin de Porres", 
            "San Vicente", "Santol", "Sikatuna Village", "South Triangle", "Santo Niño", "Tatalon", 
            "Teacher's Village East", "Teacher's Village West", "U.P. Campus", "U.P. Village", "Valencia"
        ],
        '5th District': [
            "Bagbag", "Capri", "Fairview", "Greater Lagro", "Gulod", "Kaligayahan", 
            "Nagkaisang Nayon", "North Fairview", "Novaliches Proper", "Pasong Putik Proper", 
            "San Agustin", "San Bartolome", "Santa Lucia", "Santa Monica"
        ],
        '6th District': [
            "Apolonio Samson", "Baesa", "Balon Bato", "Culiat", "New Era", "Pasong Tamo", 
            "Sangandaan", "Sauyo", "Talipapa", "Tandang Sora", "Unang Sigaw"
        ]
    }
    
    print("📍 Quezon City Districts:")
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
        WHERE province = 'Quezon City' 
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
    print(f"✅ Quezon City complete! Updated {updated_count} congressmen across 6 districts")
    print(f"   Total: {total} barangays")
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())


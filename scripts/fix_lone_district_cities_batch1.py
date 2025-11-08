#!/usr/bin/env python3
"""
Fix lone district cities batch 1 with complete barangays.
Source: Perplexity API (sonar-pro) with PSA/COMELEC/Wikipedia sources
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
    
    # Lone district cities
    cities = {
        'Biñan': [
            "Biñan", "Bungahan", "Canlalay", "Casile", "De La Paz", "Ganado", "Langkiwa", 
            "Loma", "Malaban", "Malamig", "Mampalasan", "Platero", "Poblacion", "San Antonio", 
            "San Francisco (Halang)", "San Jose", "San Vicente", "Santo Domingo", "Santo Niño", 
            "Santo Tomas (Calabuso)", "Soro-Soro", "Timbao", "Tubigan", "Zapote"
        ],
        'Las Piñas': [
            "Almanza Uno", "Almanza Dos", "CAA-B.F. International", "Daniel Fajardo", "Elias Aldana", 
            "Ilaya", "Manuyo Uno", "Manuyo Dos", "Pamplona Uno", "Pamplona Dos", "Pamplona Tres", 
            "Pilar Village", "Pulanglupa Uno", "Pulanglupa Dos", "Talon Uno", "Talon Dos", 
            "Talon Tres", "Talon Cuatro", "Talon Singko", "Zapote"
        ],
        'Malabon': [
            "Acacia", "Baritan", "Bayan-Bayanan", "Catmon", "Concepcion", "Dampalit", "Flores", 
            "Hulong Duhat", "Ibaba", "Longos", "Maysilo", "Muzon", "Niugan", "Panghulo", 
            "Potrero", "San Agustin", "Santulan", "Tañong", "Tinajeros", "Tonsuya", "Tugatog"
        ],
        'Mandaluyong': [
            "Addition Hills", "Bagong Silang", "Barangka Drive", "Barangka Ibaba", "Barangka Ilaya", 
            "Barangka Itaas", "Buayang Bato", "Burol", "Daang Bakal", "Hagdang Bato Itaas", 
            "Hagdang Bato Libis", "Harapin Ang Bukas", "Highway Hills", "Hulo", "Mabini-J. Rizal", 
            "Malamig", "Mauway", "Namayan", "New Zañiga", "Old Zañiga", "Pag-asa", "Plainview", 
            "Pleasant Hills", "Poblacion", "San Jose", "Vergara", "Wack-Wack Greenhills"
        ],
        'Muntinlupa': [
            "Alabang", "Ayala Alabang", "Bayanan", "Buli", "Cupang", "New Alabang Village", 
            "Poblacion", "Putatan", "Sucat", "Tunasan"
        ],
        'Navotas': [
            "Bagumbayan North", "Bagumbayan South", "Bangkulasi", "Daanghari", "Navotas East", 
            "Navotas West", "North Bay Boulevard North", "NBBS Dagat-dagatan", "NBBS Kaunlaran", 
            "NBBS Proper", "San Jose", "San Rafael Village", "San Roque", "Sipac-Almacen", 
            "Tangos North", "Tangos South", "Tanza 1", "Tanza 2"
        ],
        'Pasay': [f"Barangay {i}" for i in range(1, 202)],  # Barangay 1 to 201
        'Pasig': [
            "Bagong Ilog", "Bagong Katipunan", "Bambang", "Buting", "Caniogan", "Dela Paz", 
            "Kalawaan", "Kapasigan", "Kapitolyo", "Malinao", "Manggahan", "Maybunga", "Oranbo", 
            "Palatiw", "Pinagbuhatan", "Pineda", "Rosario", "Sagad", "San Antonio", "San Joaquin", 
            "San Jose", "San Miguel", "San Nicolas", "Santa Cruz", "Santa Lucia", "Santa Rosa", 
            "Santolan", "Santo Tomas", "Sumilang", "Ugong"
        ],
        'San Juan': [
            "Addition Hills", "Balong-Bato", "Batis", "Corazon de Jesus", "Ermitaño", "Greenhills", 
            "Isabelita", "Kabayanan", "Little Baguio", "Maytunas", "Onse", "Pasadena", "Pedro Cruz", 
            "Progreso", "Rivera", "Salapan", "San Perfecto", "Santa Lucia", "St. Joseph", 
            "Tibagan", "West Crame"
        ]
    }
    
    print("📍 Lone District Cities:")
    for city, barangays in cities.items():
        print(f"   {city}: {len(barangays)} barangays")
    print()
    
    # Update each city
    query = """
        UPDATE dynasty_projects_congressmen_config
        SET barangays = $1::jsonb,
            updated_at = NOW()
        WHERE province = $2
          AND district_number = 'Lone District'
          AND is_city_district = true
        RETURNING id, display_name, jsonb_array_length(barangays) as count
    """
    
    updated_count = 0
    for city, barangays in cities.items():
        print(f"Updating {city}...")
        results = await conn.fetch(query, json.dumps(barangays), city)
        if results:
            for row in results:
                print(f"✅ Updated {row['display_name']} (ID: {row['id']}) with {row['count']} barangays")
                updated_count += 1
        else:
            print(f"⚠️  No congressmen found for {city}")
        print()
    
    print("=" * 80)
    print(f"✅ Batch 1 complete! Updated {updated_count} congressmen across 9 cities")
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())


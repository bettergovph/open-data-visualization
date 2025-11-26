#!/usr/bin/env python3
"""
Populate missing city barangay data in district_entries table.
Sources: PSA, COMELEC, PhilAtlas, Wikipedia, House of Representatives
"""

import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    await conn.set_type_codec('json', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')
    await conn.set_type_codec('jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')

    print("✅ Connected to dynasty database\n")

    # Complete barangay lists from official sources (PSA, COMELEC, PhilAtlas)
    city_barangays = {
        'Navotas': {
            'Lone District': [
                "Bagumbayan North",
                "Bagumbayan South",
                "Bangculasi",
                "Daanghari",
                "Navotas East",
                "Navotas West",
                "North Bay Boulevard North",
                "North Bay Boulevard South",
                "San Jose",
                "San Rafael Village",
                "San Roque",
                "Sipac-Almacen",
                "Tangos North",
                "Tangos South",
                "Tanza 1",
                "Tanza 2",
                "NBBS (North Bay Boulevard South)",
                "NBBN (North Bay Boulevard North)"
            ]
        },
        'Malabon': {
            'Lone District': [
                "Acacia",
                "Baritan",
                "Bayan-Bayanan",
                "Catmon",
                "Concepcion",
                "Dampalit",
                "Flores",
                "Hulong Duhat",
                "Ibaba",
                "Longos",
                "Maysilo",
                "Muzon",
                "Niugan",
                "Panghulo",
                "Potrero",
                "San Agustin",
                "Santolan",
                "Tañong",
                "Tinajeros",
                "Tonsuya",
                "Tugatog"
            ]
        },
        'Mandaluyong': {
            'Lone District': [
                "Addition Hills",
                "Bagong Silang",
                "Barangka Drive",
                "Barangka Ibaba",
                "Barangka Ilaya",
                "Barangka Itaas",
                "Buayang Bato",
                "Burol",
                "Daang Bakal",
                "Hagdang Bato Itaas",
                "Hagdang Bato Libis",
                "Harapin Ang Bukas",
                "Highway Hills",
                "Hulo",
                "Mabini-J. Rizal",
                "Malamig",
                "Mauway",
                "Namayan",
                "New Zañiga",
                "Old Zañiga",
                "Pag-asa",
                "Plainview",
                "Pleasant Hills",
                "Poblacion",
                "San Jose",
                "Vergara",
                "Wack-Wack Greenhills"
            ]
        },
        'Valenzuela': {
            '1st District': [
                "Arkong Bato",
                "Balangkas",
                "Bignay",
                "Bisig",
                "Canumay East",
                "Canumay West",
                "Coloong",
                "Dalandanan",
                "Isla",
                "Lawang Bato",
                "Lingunan",
                "Mabolo",
                "Malanday",
                "Malinta",
                "Palasan",
                "Pariancillo Villa",
                "Pasolo",
                "Poblacion",
                "Polo",
                "Punturin",
                "Rincon",
                "Tagalag",
                "Veinte Reales",
                "Wawang Pulo"
            ],
            '2nd District': [
                "Bagbaguin",
                "Gen. T. de Leon",
                "Karuhatan",
                "Mapulang Lupa",
                "Marulas",
                "Maysan",
                "Parada",
                "Paso de Blas",
                "Ugong"
            ]
        }
    }

    # Update district_entries for each city
    for city_name, districts in city_barangays.items():
        print(f"📍 Updating {city_name}...")
        
        # Fetch existing entry
        row = await conn.fetchrow('SELECT name, data FROM district_entries WHERE name = $1', city_name)
        
        if row:
            # Update existing entry
            data = row['data']
            if isinstance(data, str):
                data = json.loads(data)
            
            data['barangays'] = districts
            
            # Ensure all_districts exists
            if 'all_districts' not in data:
                data['all_districts'] = list(districts.keys())
            
            # Ensure representatives exists
            if 'representatives' not in data:
                data['representatives'] = {}
            
            await conn.execute(
                'UPDATE district_entries SET data = $1, updated_at = NOW() WHERE name = $2',
                json.dumps(data),
                city_name
            )
            print(f"   ✅ Updated {city_name} with {sum(len(b) for b in districts.values())} barangays across {len(districts)} district(s)")
        else:
            # Create new entry (for Valenzuela if missing)
            data = {
                'barangays': districts,
                'all_districts': list(districts.keys()),
                'representatives': {
                    '1st District': 'Wes Gatchalian (2022-present)' if city_name == 'Valenzuela' else '',
                    '2nd District': 'Eric Martinez (2022-present)' if city_name == 'Valenzuela' else ''
                } if len(districts) > 1 else {
                    'Lone District': ''
                }
            }
            
            await conn.execute(
                'INSERT INTO district_entries (name, entity_type, data, created_at, updated_at) VALUES ($1, $2, $3, NOW(), NOW())',
                city_name,
                'city',
                json.dumps(data)
            )
            print(f"   ✅ Created {city_name} with {sum(len(b) for b in districts.values())} barangays across {len(districts)} district(s)")
    
    print("\n" + "=" * 80)
    print("✅ ALL CITY BARANGAYS POPULATED!")
    print("\nNext steps:")
    print("1. Run: python3 scripts/export_dynasty_json_from_db.py")
    print("2. Run: python3 scripts/generate_dynasty_projects_cache.py (or targeted fix scripts)")
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())


















#!/usr/bin/env python3
"""
Fix Davao City 2nd and 3rd Districts with complete barangays.
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
    
    # Davao City 2nd District: 47 barangays (Agdao, Buhangin, Bunawan, Paquibato)
    barangays_2nd = [
        "Agdao Proper", "Centro (Agdao)", "Dacudao", "Gov. Paciano Bangoy", "Lapu-Lapu",
        "Leon Garcia", "San Antonio", "Ubalde", "Wilfredo Aquino",
        "Buhangin Proper", "Cabantian", "Communal", "Indangan", "Mudiang", "Sasa", "Tigatto",
        "Biao Escuela", "Biao Joaquin", "Bunawan Proper", "Mahayag", "Pampanga", "San Isidro (Bunawan)",
        "Panacan", "Paradise Embac", "Tibungco",
        "Ilang", "Lasang", "Paquibato Proper", "Colosas", "Fatima (Paquibato)",
        "Lacson", "Lamanan", "Lampianao", "Malabog", "Mapula",
        "Pandaitan", "Paquibato", "Salapawan", "Sumimao", "Tapak",
        "Upper Paquibato", "Wangan", "Megkawayan", "Pangyan", "Riverside",
        "Dominga", "Inayangan"
    ]
    
    # Davao City 3rd District: 61 barangays (Baguio, Calinan, Tugbok, Toril, Paquibato)
    barangays_3rd = [
        "Baguio Proper", "Cadalian", "Carmen", "Gumalang", "Malagos", "Tamayong", "Tawan-tawan", "Wangan",
        "Calinan Poblacion", "Cawayan", "Dacudao", "Dalagdag", "Dominga", "Inayangan",
        "Lacson", "Lamanan", "Lampianao", "Megkawayan", "Pangyan", "Riverside",
        "Sirib", "Subasta", "Talomo River", "Tigatto",
        "Angalan", "Bago Gallera", "Bago Oshiro", "Baliok", "Catalunan Grande",
        "Catalunan Pequeño", "Mintal", "Sto. Niño", "Tacunan", "Tugbok Proper", "Ula",
        "Binugao", "Bato", "Baracatan", "Bayabas", "Camansi", "Catigan",
        "Crossing Bayabas", "Daliao", "Eden", "Lizada", "Lubogan", "Marapangi",
        "Mulig", "Sibulan", "Sirawan", "Tagluno", "Tagurano", "Toril Proper", "Tungkalan",
        "Bangkas Heights", "Malabog", "Mapula", "Paquibato Proper", "Pandaitan",
        "Paradise Embac", "Salapawan", "Sumimao", "Tapak"
    ]
    
    print(f"📍 Davao City 2nd District: {len(barangays_2nd)} barangays")
    print(f"📍 Davao City 3rd District: {len(barangays_3rd)} barangays")
    print()
    
    # Update 2nd District
    query = """
        UPDATE dynasty_projects_congressmen_config
        SET barangays = $1::jsonb,
            updated_at = NOW()
        WHERE province = 'Davao City' 
          AND district_number = $2
          AND is_city_district = true
        RETURNING id, display_name, jsonb_array_length(barangays) as count
    """
    
    print("Updating 2nd District...")
    results_2nd = await conn.fetch(query, json.dumps(barangays_2nd), '2nd District')
    for row in results_2nd:
        print(f"✅ Updated {row['display_name']} (ID: {row['id']}) with {row['count']} barangays")
    
    print()
    print("Updating 3rd District...")
    results_3rd = await conn.fetch(query, json.dumps(barangays_3rd), '3rd District')
    for row in results_3rd:
        print(f"✅ Updated {row['display_name']} (ID: {row['id']}) with {row['count']} barangays")
    
    print()
    print("✅ Davao City 2nd and 3rd Districts complete!")
    print(f"   Total: 54 (1st) + {len(barangays_2nd)} (2nd) + {len(barangays_3rd)} (3rd) = {54 + len(barangays_2nd) + len(barangays_3rd)} barangays")
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())











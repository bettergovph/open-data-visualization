#!/usr/bin/env python3
"""
Fix all remaining cities with complete barangays.
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
    
    # All remaining cities and districts
    districts_data = {
        ('Antipolo', '1st District'): [
            "Bagong Nayon", "Beverly Hills", "De La Paz", "Mambugan", "Mayamot", 
            "Muntingdilaw", "San Isidro", "Sta. Cruz"
        ],
        ('Cebu City', '1st District'): [
            "Adlaon", "Agsungot", "Apas", "Bacayan", "Banilad", "Binaliw", "Budlaan", 
            "Busay", "Cambinocot", "Camputhaw", "Capitol Site", "Carreta", "Central (Santo Niño)", 
            "Cogon Ramos", "Day-as", "Ermita", "Guba", "Hipodromo", "Kalubihan", "Kamagayan", 
            "Kasambagan", "Lahug", "Lorega San Miguel", "Lusaran", "Luz", "Mabini", "Mabolo", 
            "Malubog", "Pahina Central", "Parian", "Paril", "Pit-os", "Pulangbato", "Sambag I", 
            "Sambag II", "San Antonio", "San Jose", "San Roque", "Santa Cruz", "Sirao", 
            "T. Padilla", "Talamban", "Taptap", "Tejero", "Tinago", "Zapatera"
        ],
        ('Cebu City', '2nd District'): [
            "Babag", "Basak Pardo", "Basak San Nicolas", "Bonbon", "Buhisan", "Bulacao", "Buot", 
            "Calamba", "Cogon Pardo", "Duljo Fatima", "Guadalupe", "Inayawan", "Kalunasan", 
            "Kinasang-an Pardo", "Labangon", "Mambaling", "Pahina San Nicolas", "Pamutan", 
            "Pasil", "Poblacion Pardo", "Pung-ol Sibugay", "Punta Princesa", "Quiot", 
            "San Nicolas Proper", "Sapangdaku", "Sawang Calero", "Sinsin", "Suba", "Sudlon I", 
            "Sudlon II", "Tabunan", "Tagbao", "Tisa", "Toong"
        ],
        ('Makati', '1st District'): [
            "Bangkal", "Bel-Air", "Carmona", "Dasmariñas", "Forbes Park", "Kasilawan", "La Paz", 
            "Magallanes", "Olympia", "Palanan", "Pio del Pilar", "Poblacion", "San Antonio", 
            "San Isidro", "San Lorenzo", "Santa Cruz", "Singkamas", "Tejeros", "Urdaneta", "Valenzuela"
        ],
        ('Makati', '2nd District'): [
            "Bangkal", "Bel-Air", "Carmona", "Cembo", "Comembo", "East Rembo", "Guadalupe Nuevo", 
            "Guadalupe Viejo", "Magallanes", "Pembo", "Pinagkaisahan", "Pitogo", 
            "Post Proper Northside", "Post Proper Southside", "Rizal", "San Lorenzo", 
            "South Cembo", "West Rembo"
        ],
        ('Marikina', '2nd District'): [
            "Concepcion Uno", "Concepcion Dos", "Fortune", "Marikina Heights", "Nangka", 
            "Parang", "Tumana"
        ],
        ('Parañaque', '1st District'): [
            "Baclaran", "Don Galo", "La Huerta", "San Dionisio", "San Isidro", "Santo Niño", 
            "Tambo", "Vitalez"
        ],
        ('Parañaque', '2nd District'): [
            "BF Homes", "Don Bosco", "Marcelo Green", "Merville", "Moonwalk", "San Antonio", 
            "San Martin de Porres", "Sun Valley"
        ],
        ('Taguig–Pateros', '2nd District'): [
            "Bagumbayan", "Bambang", "Calzada", "Hagonoy", "Ibayo-Tipas", "Ligid-Tipas", 
            "Lower Bicutan", "New Lower Bicutan", "Napindan", "Palingon", "San Miguel", 
            "Santa Ana", "Tuktukan", "Ususan", "Wawa", "Central Bicutan", "Central Signal Village", 
            "Fort Bonifacio", "Katuparan", "Maharlika Village", "North Daang Hari", 
            "North Signal Village", "Pinagsama", "South Daang Hari", "South Signal Village", 
            "Tanyag", "Upper Bicutan", "Western Bicutan"
        ],
        ('Valenzuela', '1st District'): [
            "Arkong Bato", "Balangkas", "Bignay", "Bisig", "Canumay East", "Canumay West", 
            "Coloong", "Dalandanan", "Isla", "Lawang Bato", "Lingunan", "Mabolo", "Malanday", 
            "Malinta", "Palasan", "Pariancillo Villa", "Pasolo", "Poblacion", "Polo", "Punturin", 
            "Rincon", "Tagalag", "Veinte Reales", "Wawang Pulo"
        ],
        ('Valenzuela', '2nd District'): [
            "Bagbaguin", "Gen. T. de Leon", "Karuhatan", "Mapulang Lupa", "Marulas", "Maysan", 
            "Parada", "Paso de Blas", "Ugong"
        ],
        ('Zamboanga City', '1st District'): [
            "Ayala", "Baliwasan", "Baluno", "Cabatangan", "Calarian", "Camino Nuevo", "Campo Islam", 
            "Canelar", "Capisan", "Cawit", "Dulian (Pasonanca)", "Labuan", "La Paz", "Limpapa", 
            "Maasin", "Malagutay", "Mariki", "Pamucutan", "Pasonanca", "Patalon", "Recodo", 
            "Rio Hondo", "San Jose Cawa-Cawa", "San Jose Gusu", "San Roque", "Santa Barbara", 
            "Santa Maria", "Santo Niño", "Sinubung", "Sinunuc", "Talisayan", "Tulungatung", 
            "Tumaga", "Zone I", "Zone II", "Zone III", "Zone IV"
        ],
        ('Zamboanga City', '2nd District'): [
            "Arena Blanco", "Boalan", "Bolong", "Buenavista", "Bunguiao", "Busay", "Cabaluay", 
            "Cacao", "Calabasa", "Culianan", "Curuan", "Dita", "Dulian (Upper Bunguiao)", 
            "Lamisahan", "Lanzones", "Lapakan", "Licomo", "Limaong", "Limpapa", "Lubigan", 
            "Lumayang", "Lunzuran", "Malagutay", "Manalipa", "Manicahan", "Mercedes", "Pamucutan", 
            "Panubigan", "Pasilmanta", "Pasobolong", "Putik", "Quiniput", "Salaan", "Sangali", 
            "San Jose Gusu", "San Roque", "Sibulao", "Sinubong", "Sinunuc", "Tagasilay", "Taguiti", 
            "Talabaan", "Talisayan", "Talon-Talon", "Taluksangay", "Tetuan", "Tictapul", 
            "Tigbalabag", "Tigtabon", "Tolosa", "Tugbungan", "Tulungatung", "Tumaga", "Tumalutab", 
            "Tumitus", "Vitali", "Victoria", "Zambowood", "Kasanyangan", "Capisan", "Camino Nuevo"
        ],
        ('Cagayan de Oro', '2nd District'): [
            "Barangay 1", "Barangay 2", "Barangay 3", "Barangay 4", "Barangay 5", "Barangay 6", 
            "Barangay 7", "Barangay 8", "Barangay 9", "Barangay 10", "Barangay 11", "Barangay 12", 
            "Barangay 13", "Barangay 14", "Barangay 15", "Barangay 16", "Barangay 17", "Barangay 18", 
            "Barangay 19", "Barangay 20", "Barangay 21", "Barangay 22", "Barangay 23", "Barangay 24", 
            "Barangay 25", "Barangay 26", "Barangay 27", "Barangay 28", "Barangay 29", "Barangay 30", 
            "Barangay 31", "Barangay 32", "Barangay 33", "Barangay 34", "Barangay 35", "Barangay 36", 
            "Barangay 37", "Barangay 38", "Barangay 39", "Barangay 40", "Agusan", "Balubal", "Bugo", 
            "Camaman-an", "Consolacion", "Cugman", "F.S. Catanico", "Gusa", "Indahag", "Lapasan", 
            "Macabalan", "Macasandig", "Nazareth", "Puerto", "Puntod", "Tablon"
        ],
    }
    
    print("📍 Remaining Cities and Districts:")
    for (city, district), barangays in districts_data.items():
        print(f"   {city} {district}: {len(barangays)} barangays")
    print()
    
    # Update each district
    query = """
        UPDATE dynasty_projects_congressmen_config
        SET barangays = $1::jsonb,
            updated_at = NOW()
        WHERE province = $2
          AND district_number = $3
          AND is_city_district = true
        RETURNING id, display_name, jsonb_array_length(barangays) as count
    """
    
    updated_count = 0
    for (city, district), barangays in districts_data.items():
        print(f"Updating {city} {district}...")
        results = await conn.fetch(query, json.dumps(barangays), city, district)
        if results:
            for row in results:
                print(f"✅ Updated {row['display_name']} (ID: {row['id']}) with {row['count']} barangays")
                updated_count += 1
        else:
            print(f"⚠️  No congressmen found for {city} {district}")
        print()
    
    print("=" * 80)
    print(f"✅ ALL CITIES COMPLETE! Updated {updated_count} congressmen across {len(districts_data)} districts")
    print()
    print("Next step: Run scripts/export_dynasty_json_from_db.py to export to JSON files")
    
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())




















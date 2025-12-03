#!/usr/bin/env python3
"""
Update district_entries and dynasty_projects_congressmen_config tables in PostgreSQL database 
with missing district data from official PSA, COMELEC, and House of Representatives sources.
"""

import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# Official data from PSA PSGC and COMELEC sources
MISSING_DISTRICTS = {
    # Albay 2nd District
    "Albay": {
        "entity_type": "province",
        "add_municipalities": {
            "Daraga": "2nd District",
            "Camalig": "2nd District",
            "Guinobatan": "2nd District",
            "Jovellar": "2nd District",
            "Libon": "2nd District",
            "Malilipot": "2nd District",
            "Malinao": "2nd District",
            "Oas": "2nd District",
            "Polangui": "2nd District",
            "Sto. Domingo": "2nd District"
        }
    },
    
    # Batangas 3rd and 5th Districts
    "Batangas": {
        "entity_type": "province",
        "add_municipalities": {
            "Balayan": "3rd District",
            "Calaca": "3rd District",
            "Calatagan": "3rd District",
            "Lemery": "3rd District",
            "Lian": "3rd District",
            "Nasugbu": "3rd District",
            "Taal": "3rd District",
            "Tuy": "3rd District",
            "Agoncillo": "5th District",
            "Alitagtag": "5th District",
            "Balete": "5th District",
            "Cuenca": "5th District",
            "Laurel": "5th District",
            "Mataas na Kahoy": "5th District",
            "San Nicolas": "5th District",
            "Santa Teresita": "5th District",
            "Talisay": "5th District"
        }
    },
    
    # Biñan City
    "Biñan": {
        "entity_type": "city",
        "add_municipalities": {
            "Biñan": "Lone District",
            "Bungahan": "Lone District",
            "Canlalay": "Lone District",
            "Casile": "Lone District",
            "De La Paz": "Lone District",
            "Ganado": "Lone District",
            "Langkiwa": "Lone District",
            "Loma": "Lone District",
            "Malaban": "Lone District",
            "Malamig": "Lone District",
            "Mampalasan": "Lone District",
            "Platero": "Lone District",
            "Poblacion": "Lone District",
            "San Antonio": "Lone District",
            "San Francisco": "Lone District",
            "San Jose": "Lone District",
            "San Vicente": "Lone District",
            "Santo Domingo": "Lone District",
            "Santo Niño": "Lone District",
            "Santo Tomas": "Lone District",
            "Soro-soro": "Lone District",
            "Timbao": "Lone District",
            "Tubigan": "Lone District",
            "Zapote": "Lone District"
        }
    },
    
    # Davao de Oro 1st District
    "Davao de Oro": {
        "entity_type": "province",
        "add_municipalities": {
            "Compostela": "1st District",
            "Laak": "1st District",
            "Mabini": "1st District",
            "Maco": "1st District",
            "Maragusan": "1st District",
            "Mawab": "1st District",
            "Nabunturan": "1st District"
        }
    },
    
    # Davao del Sur 1st District
    "Davao del Sur": {
        "entity_type": "province",
        "add_municipalities": {
            "Bansalan": "1st District",
            "Magsaysay": "1st District",
            "Matanao": "1st District",
            "Santa Cruz": "1st District"
        }
    },
    
    # Las Piñas City
    "Las Piñas": {
        "entity_type": "city",
        "add_municipalities": {
            "Almanza Dos": "Lone District",
            "Almanza Uno": "Lone District",
            "B.F. International": "Lone District",
            "Daniel Fajardo": "Lone District",
            "Elias Aldana": "Lone District",
            "Ilaya": "Lone District",
            "Manuyo Dos": "Lone District",
            "Manuyo Uno": "Lone District",
            "Pamplona Dos": "Lone District",
            "Pamplona Tres": "Lone District",
            "Pamplona Uno": "Lone District",
            "Pilar": "Lone District",
            "Pulang Lupa Dos": "Lone District",
            "Pulang Lupa Uno": "Lone District",
            "Talon Dos": "Lone District",
            "Talon Kuatro": "Lone District",
            "Talon Singko": "Lone District",
            "Talon Tres": "Lone District",
            "Talon Uno": "Lone District",
            "Zapote": "Lone District"
        }
    },
    
    # Leyte 3rd, 4th, 5th Districts
    "Leyte": {
        "entity_type": "province",
        "add_municipalities": {
            "Abuyog": "3rd District",
            "Javier": "3rd District",
            "Julita": "3rd District",
            "Mahaplag": "3rd District",
            "Silago": "3rd District",
            "Alangalang": "4th District",
            "Barugo": "4th District",
            "Capoocan": "4th District",
            "Carigara": "4th District",
            "Jaro": "4th District",
            "Pastrana": "4th District",
            "San Miguel": "4th District",
            "Santa Fe": "4th District",
            "Tabango": "4th District",
            "Tunga": "4th District",
            "Albuera": "5th District",
            "Burauen": "5th District",
            "Dagami": "5th District",
            "Dulag": "5th District",
            "La Paz": "5th District",
            "MacArthur": "5th District",
            "Mayorga": "5th District",
            "Palo": "5th District",
            "Tabontabon": "5th District",
            "Tanauan": "5th District",
            "Tolosa": "5th District"
        }
    },
    
    # Parañaque City
    "Parañaque": {
        "entity_type": "city",
        "add_municipalities": {
            "Baclaran": "Lone District",
            "B.F. Homes": "Lone District",
            "Don Bosco": "Lone District",
            "Don Galo": "Lone District",
            "La Huerta": "Lone District",
            "Marcelo Green": "Lone District",
            "Merville": "Lone District",
            "Moonwalk": "Lone District",
            "San Antonio": "Lone District",
            "San Dionisio": "Lone District",
            "San Isidro": "Lone District",
            "San Martin de Porres": "Lone District",
            "Santo Niño": "Lone District",
            "Sun Valley": "Lone District",
            "Tambo": "Lone District",
            "Vitalez": "Lone District"
        }
    }
}

async def update_district_entries():
    """Update district_entries table with missing district data"""
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        print(f"🔄 Updating district_entries table...")
        
        updated = 0
        added = 0
        
        for district_name, district_info in MISSING_DISTRICTS.items():
            # Check if entry exists
            existing = await conn.fetchrow(
                'SELECT name, entity_type, data FROM district_entries WHERE name = $1',
                district_name
            )
            
            if existing:
                # Update existing entry
                data = json.loads(existing['data']) if isinstance(existing['data'], str) else existing['data']
                
                # Ensure municipalities key exists
                if 'municipalities' not in data:
                    data['municipalities'] = {}
                
                # Ensure all_districts list exists
                if 'all_districts' not in data:
                    data['all_districts'] = []
                
                # Add new municipalities
                if 'add_municipalities' in district_info:
                    for municipality, district in district_info['add_municipalities'].items():
                        data['municipalities'][municipality] = district
                        
                        # Add district to all_districts if not present
                        if district not in data['all_districts']:
                            data['all_districts'].append(district)
                
                # Update in database
                await conn.execute(
                    '''UPDATE district_entries 
                       SET data = $1, updated_at = NOW() 
                       WHERE name = $2''',
                    json.dumps(data),
                    district_name
                )
                
                updated += 1
                muni_count = len(district_info.get('add_municipalities', {}))
                print(f"  ✅ Updated {district_name} with {muni_count} municipalities/barangays")
            else:
                # Create new entry
                data = {
                    "all_districts": [],
                    "municipalities": {},
                    "representatives": {}
                }
                
                # Add municipalities
                if 'add_municipalities' in district_info:
                    for municipality, district in district_info['add_municipalities'].items():
                        data['municipalities'][municipality] = district
                        
                        # Add district to all_districts if not present
                        if district not in data['all_districts']:
                            data['all_districts'].append(district)
                
                # Insert into database
                await conn.execute(
                    '''INSERT INTO district_entries (name, entity_type, data, created_at, updated_at)
                       VALUES ($1, $2, $3, NOW(), NOW())''',
                    district_name,
                    district_info['entity_type'],
                    json.dumps(data)
                )
                
                added += 1
                muni_count = len(district_info.get('add_municipalities', {}))
                print(f"  ✅ Added {district_name} with {muni_count} municipalities/barangays")
        
        # Verify total count
        total_count = await conn.fetchval('SELECT COUNT(*) FROM district_entries')
        
        print(f"\n📊 district_entries Summary:")
        print(f"  ✅ Updated: {updated} districts")
        print(f"  ✅ Added: {added} districts")
        print(f"  💾 Total entries in database: {total_count}")
        
        # Now update dynasty_projects_congressmen_config table
        print(f"\n🔄 Updating dynasty_projects_congressmen_config table...")
        
        # Re-run the populate_barangays logic to update congressmen with new data
        congressmen_updated = 0
        
        for district_name, district_info in MISSING_DISTRICTS.items():
            if 'add_municipalities' not in district_info:
                continue
            
            # Group municipalities by district
            districts_map = {}
            for municipality, district in district_info['add_municipalities'].items():
                if district not in districts_map:
                    districts_map[district] = []
                districts_map[district].append(municipality)
            
            # Update congressmen for each district
            for district_num, municipalities in districts_map.items():
                # Find congressmen matching this province and district
                congressmen = await conn.fetch('''
                    SELECT id, display_name, province, district_number, is_city_district
                    FROM dynasty_projects_congressmen_config
                    WHERE province = $1 
                    AND district_number = $2
                    AND is_partylist = false
                    AND (barangays IS NULL OR barangays = '[]'::jsonb)
                ''', district_name, district_num)
                
                for congressman in congressmen:
                    # Update with municipalities/barangays
                    municipalities_json = json.dumps(municipalities)
                    await conn.execute(
                        'UPDATE dynasty_projects_congressmen_config SET barangays = $1::jsonb WHERE id = $2',
                        municipalities_json, congressman['id']
                    )
                    
                    entity_type = "barangays" if congressman['is_city_district'] else "municipalities"
                    congressmen_updated += 1
                    print(f"  ✅ Updated {congressman['display_name']} ({district_name} - {district_num}): {len(municipalities)} {entity_type}")
        
        # Verify final count
        final_count = await conn.fetchval('''
            SELECT COUNT(*) FROM dynasty_projects_congressmen_config 
            WHERE barangays IS NOT NULL AND barangays != '[]'::jsonb
        ''')
        
        print(f"\n📊 dynasty_projects_congressmen_config Summary:")
        print(f"  ✅ Updated: {congressmen_updated} congressmen")
        print(f"  💾 Total with barangays data: {final_count}")
        
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(update_district_entries())

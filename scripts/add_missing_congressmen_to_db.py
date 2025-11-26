#!/usr/bin/env python3
"""
Add missing congressmen to the dynasty_projects_congressmen_config database table.
These congressmen exist in the ranking but are missing from the config.
"""

import asyncio
import json
import os
from dotenv import load_dotenv
import asyncpg

load_dotenv()

async def add_missing_congressmen():
    """Add missing congressmen to the database"""
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        # Get max ID
        max_id = await conn.fetchval("SELECT MAX(id) FROM dynasty_projects_congressmen_config")
        next_id = (max_id or 0) + 1
        
        print(f"Current max ID: {max_id}, starting new IDs from: {next_id}")
        
        # Missing congressmen to add
        missing_congressmen = [
            {
                "id": next_id,
                "first_name_pattern": "JUN",
                "last_name_pattern": "BABASA",
                "display_name": "Jun Babasa",
                "full_name": "Jun Babasa",
                "province": None,  # TODO: Research and fill in
                "district_number": None,  # TODO: Research and fill in
                "is_city_district": False,
                "is_partylist": False,
                "barangays": [],
                "terms": [],
                "family_connections": None,
                "previous_positions": None,
                "barangays_file": None
            },
            {
                "id": next_id + 1,
                "first_name_pattern": "MARVEY",
                "last_name_pattern": "MARIÑO",
                "display_name": "Marvey Mariño",
                "full_name": "Marvey Mariño",
                "province": None,  # TODO: Research and fill in
                "district_number": None,  # TODO: Research and fill in
                "is_city_district": False,
                "is_partylist": False,
                "barangays": [],
                "terms": [],
                "family_connections": None,
                "previous_positions": None,
                "barangays_file": None
            },
            {
                "id": next_id + 2,
                "first_name_pattern": "ELISA",
                "last_name_pattern": "KHO",
                "display_name": "Elisa Olga Kho",
                "full_name": "Elisa Olga Kho",
                "province": None,  # TODO: Research and fill in
                "district_number": None,  # TODO: Research and fill in
                "is_city_district": False,
                "is_partylist": False,
                "barangays": [],
                "terms": [],
                "family_connections": None,
                "previous_positions": None,
                "barangays_file": None
            },
            {
                "id": next_id + 3,
                "first_name_pattern": "JOY",
                "last_name_pattern": "TAMBUTING",
                "display_name": "Joy Tambuting",
                "full_name": "Joy Tambuting",
                "province": None,  # TODO: Research and fill in
                "district_number": None,  # TODO: Research and fill in
                "is_city_district": False,
                "is_partylist": False,
                "barangays": [],
                "terms": [],
                "family_connections": None,
                "previous_positions": None,
                "barangays_file": None
            }
        ]
        
        print(f"\nAdding {len(missing_congressmen)} missing congressmen to database...")
        
        for cm in missing_congressmen:
            # Check if already exists
            existing = await conn.fetchval(
                "SELECT id FROM dynasty_projects_congressmen_config WHERE display_name = $1",
                cm["display_name"]
            )
            
            if existing:
                print(f"  ⚠️  {cm['display_name']} already exists with ID {existing}")
                continue
            
            # Insert into database
            await conn.execute("""
                INSERT INTO dynasty_projects_congressmen_config (
                    id, first_name_pattern, last_name_pattern, display_name, full_name,
                    province, district_number, is_city_district, is_partylist,
                    barangays, terms, family_connections, previous_positions, barangays_file,
                    created_at, updated_at
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW(), NOW()
                )
            """,
                cm["id"],
                cm["first_name_pattern"],
                cm["last_name_pattern"],
                cm["display_name"],
                cm["full_name"],
                cm["province"],
                cm["district_number"],
                cm["is_city_district"],
                cm["is_partylist"],
                cm["barangays"],
                cm["terms"],
                cm["family_connections"],
                cm["previous_positions"],
                cm["barangays_file"]
            )
            
            print(f"  ✅ Added {cm['display_name']} (ID: {cm['id']})")
        
        print(f"\n✅ Successfully added missing congressmen to database")
        print(f"⚠️  Note: These entries need to be updated with province, district, terms, and barangays/municipalities")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(add_missing_congressmen())






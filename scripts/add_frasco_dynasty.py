#!/usr/bin/env python3
"""
Add Duke Frasco and family to the political dynasties database.
"""

import asyncio
import asyncpg
import os
from datetime import date
from dotenv import load_dotenv

load_dotenv()

async def add_frasco_dynasty():
    """Add Duke Frasco and his family to the dynasty database."""
    
    # Connect to dynasty database
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        # Check if Duke Frasco already exists
        existing = await conn.fetchrow(
            "SELECT id FROM political_dynasties WHERE first_name = $1 AND last_name = $2",
            "Vincent Franco", "Frasco"
        )
        
        if existing:
            print(f"✅ Duke Frasco already exists in database (ID: {existing['id']})")
            duke_id = existing['id']
        else:
            # Insert Duke Frasco
            duke_id = await conn.fetchval("""
                INSERT INTO political_dynasties (
                    first_name, middle_name, last_name, nickname, suffix,
                    position, province, municipality_city, region,
                    party, dynasty_family_id, birth_date
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                RETURNING id
            """,
                "Vincent Franco", "Domingo", "Frasco", "Duke", None,
                "Congressman, 5th District", "Cebu", "Liloan", "Region VII (Central Visayas)",
                None, "Garcia-Frasco", date(1980, 10, 27)
            )
            print(f"✅ Added Duke Frasco (ID: {duke_id})")
        
        # Check if Christina Garcia Frasco exists
        existing_christina = await conn.fetchrow(
            "SELECT id FROM political_dynasties WHERE first_name = $1 AND last_name = $2",
            "Christina", "Frasco"
        )
        
        if existing_christina:
            print(f"✅ Christina Garcia Frasco already exists (ID: {existing_christina['id']})")
            christina_id = existing_christina['id']
        else:
            # Insert Christina Garcia Frasco
            christina_id = await conn.fetchval("""
                INSERT INTO political_dynasties (
                    first_name, middle_name, last_name, maiden_name, suffix,
                    position, province, municipality_city, region,
                    party, dynasty_family_id, birth_date
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                RETURNING id
            """,
                "Christina", "Garcia", "Frasco", "Garcia", None,
                "Secretary of Tourism; Former Mayor of Liloan (2016-2022)", "Cebu", "Liloan", "Region VII (Central Visayas)",
                None, "Garcia-Frasco", date(1981, 12, 25)
            )
            print(f"✅ Added Christina Garcia Frasco (ID: {christina_id})")
        
        # Check if Panphil Frasco exists
        existing_panphil = await conn.fetchrow(
            "SELECT id FROM political_dynasties WHERE first_name = $1 AND last_name = $2",
            "Panphil", "Frasco"
        )
        
        if existing_panphil:
            print(f"✅ Panphil Frasco already exists (ID: {existing_panphil['id']})")
            panphil_id = existing_panphil['id']
        else:
            # Insert Panphil "Dodong Daku" Frasco (Duke's father)
            panphil_id = await conn.fetchval("""
                INSERT INTO political_dynasties (
                    first_name, middle_name, last_name, nickname, suffix,
                    position, province, municipality_city, region,
                    party, dynasty_family_id
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                RETURNING id
            """,
                "Panphil", None, "Frasco", "Dodong Daku", None,
                "Former Mayor of Liloan", "Cebu", "Liloan", "Region VII (Central Visayas)",
                None, "Garcia-Frasco"
            )
            print(f"✅ Added Panphil Frasco (ID: {panphil_id})")
        
        # Check if Aljew Frasco exists
        existing_aljew = await conn.fetchrow(
            "SELECT id FROM political_dynasties WHERE first_name = $1 AND last_name = $2",
            "Aljew", "Frasco"
        )
        
        if existing_aljew:
            print(f"✅ Aljew Frasco already exists (ID: {existing_aljew['id']})")
            aljew_id = existing_aljew['id']
        else:
            # Insert Aljew Frasco (current Mayor of Liloan, Duke's cousin-in-law)
            aljew_id = await conn.fetchval("""
                INSERT INTO political_dynasties (
                    first_name, middle_name, last_name, suffix,
                    position, province, municipality_city, region,
                    party, dynasty_family_id
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id
            """,
                "Aljew", None, "Frasco", None,
                "Mayor of Liloan (2022-present)", "Cebu", "Liloan", "Region VII (Central Visayas)",
                None, "Garcia-Frasco"
            )
            print(f"✅ Added Aljew Frasco (ID: {aljew_id})")
        
        # Add family relationships
        # Duke married to Christina
        await conn.execute("""
            INSERT INTO family_relationships (person_id, related_person_id, relationship_type)
            VALUES ($1, $2, 'spouse')
            ON CONFLICT DO NOTHING
        """, duke_id, christina_id)
        
        await conn.execute("""
            INSERT INTO family_relationships (person_id, related_person_id, relationship_type)
            VALUES ($1, $2, 'spouse')
            ON CONFLICT DO NOTHING
        """, christina_id, duke_id)
        
        # Panphil is Duke's father
        await conn.execute("""
            INSERT INTO family_relationships (person_id, related_person_id, relationship_type)
            VALUES ($1, $2, 'parent')
            ON CONFLICT DO NOTHING
        """, panphil_id, duke_id)
        
        await conn.execute("""
            INSERT INTO family_relationships (person_id, related_person_id, relationship_type)
            VALUES ($1, $2, 'child')
            ON CONFLICT DO NOTHING
        """, duke_id, panphil_id)
        
        # Christina is daughter of Gwendolyn Garcia (if Gwendolyn exists)
        gwendolyn = await conn.fetchrow(
            "SELECT id FROM political_dynasties WHERE first_name = $1 AND last_name = $2",
            "Gwendolyn", "Garcia"
        )
        
        if gwendolyn:
            await conn.execute("""
                INSERT INTO family_relationships (person_id, related_person_id, relationship_type)
                VALUES ($1, $2, 'parent')
                ON CONFLICT DO NOTHING
            """, gwendolyn['id'], christina_id)
            
            await conn.execute("""
                INSERT INTO family_relationships (person_id, related_person_id, relationship_type)
                VALUES ($1, $2, 'child')
                ON CONFLICT DO NOTHING
            """, christina_id, gwendolyn['id'])
            
            print(f"✅ Linked Christina to mother Gwendolyn Garcia")
        
        # Aljew is Duke's cousin-in-law
        await conn.execute("""
            INSERT INTO family_relationships (person_id, related_person_id, relationship_type)
            VALUES ($1, $2, 'cousin-in-law')
            ON CONFLICT DO NOTHING
        """, aljew_id, duke_id)
        
        await conn.execute("""
            INSERT INTO family_relationships (person_id, related_person_id, relationship_type)
            VALUES ($1, $2, 'cousin-in-law')
            ON CONFLICT DO NOTHING
        """, duke_id, aljew_id)
        
        print("\n✅ All Frasco family members and relationships added successfully!")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(add_frasco_dynasty())


#!/usr/bin/env python3
"""Add Sara Duterte relationship with Glenn Escandor and Genesis88 Construction:
- Sara Duterte -> Glenn Escandor (friend, campaign donor)
- Sara Duterte -> Genesis88 Construction (contractor connection via Escandor)
- Sara Duterte -> Esdevco Realty Corporation (campaign donor, owned by Escandor)
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def add_sara_duterte_escandor_relationship():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    try:
        # Source URL
        source_url_pcij = "https://pcij.org/2025/09/18/marcos-and-duterte-contractors/"
        
        # Get relationship types
        business_partner_type = await conn.fetchval("SELECT id FROM connection_types WHERE name = 'Business Partner' LIMIT 1")
        political_ally_type = await conn.fetchval("SELECT id FROM connection_types WHERE name = 'Political Ally' LIMIT 1")
        
        if not business_partner_type or not political_ally_type:
            print("❌ Relationship types not found")
            return
        
        # Find or create Sara Duterte
        sara_duterte = await conn.fetchrow('''
            SELECT id, first_name, last_name, position FROM political_dynasties
            WHERE (UPPER(first_name) LIKE '%SARA%' OR UPPER(first_name) LIKE '%SARA ZIMMERMANN%')
              AND UPPER(last_name) LIKE '%DUTERTE%'
              AND (UPPER(position) LIKE '%VICE PRESIDENT%' OR UPPER(position) LIKE '%VP%' OR UPPER(position) LIKE '%MAYOR%')
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not sara_duterte:
            # Create Sara Duterte if not found
            sara_id = await conn.fetchval('''
                INSERT INTO political_dynasties (first_name, last_name, position, province)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            ''', "SARA", "DUTERTE", "VICE PRESIDENT", "DAVAO DEL SUR")
            sara_duterte = {'id': sara_id, 'first_name': 'SARA', 'last_name': 'DUTERTE', 'position': 'VICE PRESIDENT'}
            print(f"✅ Created Sara Duterte: ID {sara_id}")
        else:
            print(f"✅ Found Sara Duterte: ID {sara_duterte['id']} - {sara_duterte['first_name']} {sara_duterte['last_name']} ({sara_duterte['position']})")
        
        # Find or create Glenn Escandor
        glenn_escandor = await conn.fetchrow('''
            SELECT id, first_name, last_name FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%GLENN%'
              AND UPPER(last_name) LIKE '%ESCANDOR%'
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not glenn_escandor:
            # Create Glenn Escandor if not found
            glenn_id = await conn.fetchval('''
                INSERT INTO political_dynasties (first_name, last_name, position, province)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            ''', "GLENN", "ESCANDOR", "CONSTRUCTION MAGNATE, OWNER OF GENESIS88 CONSTRUCTION", "DAVAO DEL SUR")
            glenn_escandor = {'id': glenn_id, 'first_name': 'GLENN', 'last_name': 'ESCANDOR'}
            print(f"✅ Created Glenn Escandor: ID {glenn_id}")
        else:
            print(f"✅ Found Glenn Escandor: ID {glenn_escandor['id']}")
        
        # Add relationship: Sara Duterte <-> Glenn Escandor (friend, campaign donor, business connection)
        existing_relationship = await conn.fetchrow('''
            SELECT id FROM relationships
            WHERE person_id = $1 AND related_person_id = $2
              AND (relationship_description ILIKE '%Escandor%' OR relationship_description ILIKE '%Genesis88%' OR relationship_description ILIKE '%campaign%')
        ''', sara_duterte['id'], glenn_escandor['id'])
        
        if not existing_relationship:
            await conn.execute('''
                INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description, source_url)
                VALUES ($1, $2, $3, $4, $5)
            ''', sara_duterte['id'], glenn_escandor['id'], political_ally_type,
                "Longtime friend and campaign donor. Escandor's Esdevco Realty Corporation donated ₱19.9M for Sara Duterte's 2022 vice presidential campaign", source_url_pcij)
            print(f"✅ Added relationship: Sara Duterte -> Glenn Escandor (friend, campaign donor)")
        else:
            print(f"✅ Relationship already exists (ID {existing_relationship['id']})")
        
        # Add reverse relationship
        existing_reverse = await conn.fetchrow('''
            SELECT id FROM relationships
            WHERE person_id = $1 AND related_person_id = $2
              AND (relationship_description ILIKE '%Duterte%' OR relationship_description ILIKE '%campaign%')
        ''', glenn_escandor['id'], sara_duterte['id'])
        
        if not existing_reverse:
            await conn.execute('''
                INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description, source_url)
                VALUES ($1, $2, $3, $4, $5)
            ''', glenn_escandor['id'], sara_duterte['id'], political_ally_type,
                "Longtime friend of Duterte family. Donated ₱19.9M through Esdevco Realty Corporation for Sara Duterte's 2022 vice presidential campaign", source_url_pcij)
            print(f"✅ Added reverse relationship: Glenn Escandor -> Sara Duterte")
        else:
            print(f"✅ Reverse relationship already exists (ID {existing_reverse['id']})")
        
        # Add contractor connections
        contractors = [
            ("GENESIS88 CONSTRUCTION INC", "Top flood-control contractor in Davao del Sur with ₱2.9B in contracts. Owned by Glenn Escandor, longtime friend of Duterte family"),
            ("ESDEVCO REALTY CORPORATION", "Sole corporate donor for Sara Duterte's 2022 vice presidential campaign, funding ₱19.9M worth of advertisements. Owned by Glenn Escandor")
        ]
        
        for contractor_name, notes in contractors:
            existing_contractor = await conn.fetchrow('''
                SELECT id FROM politician_contractors
                WHERE politician_id = $1 AND contractor_name = $2
            ''', sara_duterte['id'], contractor_name)
            
            if not existing_contractor:
                await conn.execute('''
                    INSERT INTO politician_contractors (politician_id, contractor_name, match_confidence, notes, source)
                    VALUES ($1, $2, $3, $4, $5)
                ''', sara_duterte['id'], contractor_name, 10, notes, source_url_pcij)
                print(f"✅ Added contractor connection: Sara Duterte -> {contractor_name}")
            else:
                print(f"✅ Contractor connection already exists: Sara Duterte -> {contractor_name}")
        
        # Also add Glenn Escandor's connection to Genesis88 Construction
        existing_glenn_contractor = await conn.fetchrow('''
            SELECT id FROM politician_contractors
            WHERE politician_id = $1 AND contractor_name = $2
        ''', glenn_escandor['id'], "GENESIS88 CONSTRUCTION INC")
        
        if not existing_glenn_contractor:
            await conn.execute('''
                INSERT INTO politician_contractors (politician_id, contractor_name, match_confidence, notes, source)
                VALUES ($1, $2, $3, $4, $5)
            ''', glenn_escandor['id'], "GENESIS88 CONSTRUCTION INC", 10,
                "Owner of Genesis88 Construction Inc. Top flood-control contractor in Davao del Sur with ₱2.9B in contracts (2023-2024)", source_url_pcij)
            print(f"✅ Added contractor connection: Glenn Escandor -> Genesis88 Construction Inc")
        else:
            print(f"✅ Contractor connection already exists: Glenn Escandor -> Genesis88 Construction Inc")
        
        print("\n✅ Done! Sara Duterte-Escandor relationships added")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(add_sara_duterte_escandor_relationship())






















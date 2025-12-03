#!/usr/bin/env python3
"""Add Ferdinand Marcos Jr. relationships with contractor-donors:
- Ferdinand Marcos Jr. -> Rodulfo D. Hilot Jr. (campaign donor, P20M)
- Ferdinand Marcos Jr. -> Rudhil Construction & Enterprises Inc (contractor connection)
- Ferdinand Marcos Jr. -> Jonathan M. Quirante (campaign donor, P1M)
- Ferdinand Marcos Jr. -> Quirante Construction Corporation (contractor connection)
- Rodulfo D. Hilot Jr. -> Rudhil Construction & Enterprises Inc (owner)
- Jonathan M. Quirante -> Quirante Construction Corporation (owner)
- Jonathan M. Quirante -> Allan Quirante (uncle, QM Builders owner)
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def add_marcos_contractor_donors():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    try:
        # Source URLs
        source_url_pcij = "https://pcij.org/2025/09/18/marcos-and-duterte-contractors/"
        source_url_inquirer = "https://newsinfo.inquirer.net/2125842/marcos-sara-duterte-urged-explain-campaign-donations-from-contractors"
        source_url_philstar = "https://www.philstar.com/the-freeman/cebu-news/2025/09/20/2474128/quirante-among-marcos-donors"
        
        # Get relationship types
        political_ally_type = await conn.fetchval("SELECT id FROM connection_types WHERE name = 'Political Ally' LIMIT 1")
        business_partner_type = await conn.fetchval("SELECT id FROM connection_types WHERE name = 'Business Partner' LIMIT 1")
        uncle_type = await conn.fetchval("SELECT id FROM connection_types WHERE name = 'Uncle' LIMIT 1")
        nephew_type = await conn.fetchval("SELECT id FROM connection_types WHERE name = 'Nephew' LIMIT 1")
        
        if not political_ally_type:
            print("❌ Relationship types not found")
            return
        
        # Find or create Ferdinand Marcos Jr.
        marcos_jr = await conn.fetchrow('''
            SELECT id, first_name, last_name, position FROM political_dynasties
            WHERE (UPPER(first_name) LIKE '%FERDINAND%' OR UPPER(first_name) LIKE '%BONGBONG%' OR UPPER(first_name) LIKE '%BBM%')
              AND UPPER(last_name) LIKE '%MARCOS%'
              AND (UPPER(position) LIKE '%PRESIDENT%' OR UPPER(position) LIKE '%SENATOR%')
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not marcos_jr:
            # Create Ferdinand Marcos Jr. if not found
            marcos_id = await conn.fetchval('''
                INSERT INTO political_dynasties (first_name, last_name, position, province)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            ''', "FERDINAND", "MARCOS JR", "PRESIDENT", "ILOCOS NORTE")
            marcos_jr = {'id': marcos_id, 'first_name': 'FERDINAND', 'last_name': 'MARCOS JR', 'position': 'PRESIDENT'}
            print(f"✅ Created Ferdinand Marcos Jr.: ID {marcos_id}")
        else:
            print(f"✅ Found Ferdinand Marcos Jr.: ID {marcos_jr['id']} - {marcos_jr['first_name']} {marcos_jr['last_name']} ({marcos_jr['position']})")
        
        # Find or create Rodulfo D. Hilot Jr.
        rodulfo_hilot = await conn.fetchrow('''
            SELECT id, first_name, last_name FROM political_dynasties
            WHERE (UPPER(first_name) LIKE '%RODULFO%' OR UPPER(first_name) LIKE '%RODOLFO%')
              AND UPPER(last_name) LIKE '%HILOT%'
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not rodulfo_hilot:
            # Create Rodulfo D. Hilot Jr. if not found
            hilot_id = await conn.fetchval('''
                INSERT INTO political_dynasties (first_name, last_name, position, province)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            ''', "RODULFO D", "HILOT JR", "CEO, RUDHIL GROUP OF COMPANIES", "ZAMBOANGA DEL SUR")
            rodulfo_hilot = {'id': hilot_id, 'first_name': 'RODULFO D', 'last_name': 'HILOT JR'}
            print(f"✅ Created Rodulfo D. Hilot Jr.: ID {hilot_id}")
        else:
            print(f"✅ Found Rodulfo D. Hilot Jr.: ID {rodulfo_hilot['id']}")
        
        # Find or create Jonathan M. Quirante
        jonathan_quirante = await conn.fetchrow('''
            SELECT id, first_name, last_name FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%JONATHAN%'
              AND UPPER(last_name) LIKE '%QUIRANTE%'
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not jonathan_quirante:
            # Create Jonathan M. Quirante if not found
            quirante_id = await conn.fetchval('''
                INSERT INTO political_dynasties (first_name, last_name, position, province)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            ''', "JONATHAN M", "QUIRANTE", "OWNER, QUIRANTE CONSTRUCTION CORPORATION", "CEBU")
            jonathan_quirante = {'id': quirante_id, 'first_name': 'JONATHAN M', 'last_name': 'QUIRANTE'}
            print(f"✅ Created Jonathan M. Quirante: ID {quirante_id}")
        else:
            print(f"✅ Found Jonathan M. Quirante: ID {jonathan_quirante['id']}")
        
        # Find or create Allan Quirante (uncle of Jonathan)
        allan_quirante = await conn.fetchrow('''
            SELECT id, first_name, last_name FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%ALLAN%'
              AND UPPER(last_name) LIKE '%QUIRANTE%'
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not allan_quirante:
            # Create Allan Quirante if not found
            allan_id = await conn.fetchval('''
                INSERT INTO political_dynasties (first_name, last_name, position, province)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            ''', "ALLAN", "QUIRANTE", "OWNER, QM BUILDERS", "CEBU")
            allan_quirante = {'id': allan_id, 'first_name': 'ALLAN', 'last_name': 'QUIRANTE'}
            print(f"✅ Created Allan Quirante: ID {allan_id}")
        else:
            print(f"✅ Found Allan Quirante: ID {allan_quirante['id']}")
        
        # Add relationships: Marcos Jr. <-> Rodulfo Hilot (campaign donor)
        existing_hilot = await conn.fetchrow('''
            SELECT id FROM relationships
            WHERE person_id = $1 AND related_person_id = $2
              AND (relationship_description ILIKE '%Hilot%' OR relationship_description ILIKE '%campaign%' OR relationship_description ILIKE '%donor%')
        ''', marcos_jr['id'], rodulfo_hilot['id'])
        
        if not existing_hilot:
            await conn.execute('''
                INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description, source_url)
                VALUES ($1, $2, $3, $4, $5)
            ''', marcos_jr['id'], rodulfo_hilot['id'], political_ally_type,
                "Campaign donor who gave ₱20 million to elect Marcos Jr. in 2022. One of the president's largest contributors", source_url_pcij)
            print(f"✅ Added relationship: Marcos Jr. -> Rodulfo Hilot (campaign donor)")
        else:
            print(f"✅ Relationship already exists (ID {existing_hilot['id']})")
        
        # Add relationships: Marcos Jr. <-> Jonathan Quirante (campaign donor)
        existing_quirante = await conn.fetchrow('''
            SELECT id FROM relationships
            WHERE person_id = $1 AND related_person_id = $2
              AND (relationship_description ILIKE '%Quirante%' OR relationship_description ILIKE '%campaign%' OR relationship_description ILIKE '%donor%')
        ''', marcos_jr['id'], jonathan_quirante['id'])
        
        if not existing_quirante:
            await conn.execute('''
                INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description, source_url)
                VALUES ($1, $2, $3, $4, $5)
            ''', marcos_jr['id'], jonathan_quirante['id'], political_ally_type,
                "Campaign donor who gave ₱1 million to elect Marcos Jr. in 2022", source_url_pcij)
            print(f"✅ Added relationship: Marcos Jr. -> Jonathan Quirante (campaign donor)")
        else:
            print(f"✅ Relationship already exists (ID {existing_quirante['id']})")
        
        # Add uncle-nephew relationship: Allan Quirante <-> Jonathan Quirante
        if uncle_type and nephew_type:
            existing_uncle = await conn.fetchrow('''
                SELECT id FROM relationships
                WHERE person_id = $1 AND related_person_id = $2
                  AND relationship_type = $3
            ''', jonathan_quirante['id'], allan_quirante['id'], uncle_type)
            
            if not existing_uncle:
                await conn.execute('''
                    INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description, source_url)
                    VALUES ($1, $2, $3, $4, $5)
                ''', jonathan_quirante['id'], allan_quirante['id'], uncle_type,
                    "Allan Quirante is uncle of Jonathan M. Quirante. Both own construction companies (QM Builders and Quirante Construction)", source_url_philstar)
                print(f"✅ Added relationship: Jonathan Quirante -> Allan Quirante (uncle)")
            
            # Add reverse relationship (nephew)
            existing_nephew = await conn.fetchrow('''
                SELECT id FROM relationships
                WHERE person_id = $1 AND related_person_id = $2
                  AND relationship_type = $3
            ''', allan_quirante['id'], jonathan_quirante['id'], nephew_type)
            
            if not existing_nephew:
                await conn.execute('''
                    INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description, source_url)
                    VALUES ($1, $2, $3, $4, $5)
                ''', allan_quirante['id'], jonathan_quirante['id'], nephew_type,
                    "Jonathan M. Quirante is nephew of Allan Quirante. Both own construction companies (Quirante Construction and QM Builders)", source_url_philstar)
                print(f"✅ Added relationship: Allan Quirante -> Jonathan Quirante (nephew)")
        
        # Add contractor connections for Marcos Jr.
        marcos_contractors = [
            ("RUDHIL CONSTRUCTION & ENTERPRISES INC", "Contractor-donor connection. Rodulfo Hilot gave ₱20M to Marcos Jr.'s 2022 campaign. Company received P2.7B in 2023, P3.5B in 2024", source_url_pcij),
            ("QUIRANTE CONSTRUCTION CORPORATION", "Contractor-donor connection. Jonathan Quirante gave ₱1M to Marcos Jr.'s 2022 campaign. Company contracts leaped to P3B in 2023, P3.8B in first 8 months of 2025", source_url_pcij)
        ]
        
        for contractor_name, notes, source_url in marcos_contractors:
            existing_contractor = await conn.fetchrow('''
                SELECT id FROM politician_contractors
                WHERE politician_id = $1 AND contractor_name = $2
            ''', marcos_jr['id'], contractor_name)
            
            if not existing_contractor:
                await conn.execute('''
                    INSERT INTO politician_contractors (politician_id, contractor_name, match_confidence, notes, source)
                    VALUES ($1, $2, $3, $4, $5)
                ''', marcos_jr['id'], contractor_name, 10, notes, source_url)
                print(f"✅ Added contractor connection: Marcos Jr. -> {contractor_name}")
            else:
                print(f"✅ Contractor connection already exists: Marcos Jr. -> {contractor_name}")
        
        # Add contractor connections for Rodulfo Hilot
        existing_hilot_contractor = await conn.fetchrow('''
            SELECT id FROM politician_contractors
            WHERE politician_id = $1 AND contractor_name = $2
        ''', rodulfo_hilot['id'], "RUDHIL CONSTRUCTION & ENTERPRISES INC")
        
        if not existing_hilot_contractor:
            await conn.execute('''
                INSERT INTO politician_contractors (politician_id, contractor_name, match_confidence, notes, source)
                VALUES ($1, $2, $3, $4, $5)
            ''', rodulfo_hilot['id'], "RUDHIL CONSTRUCTION & ENTERPRISES INC", 10,
                "Owner and CEO of Rudhil Construction & Enterprises Inc. Company received P2.7B in 2023, P3.5B in 2024. Also CEO of Rudhil Group of Companies", source_url_pcij)
            print(f"✅ Added contractor connection: Rodulfo Hilot -> Rudhil Construction & Enterprises Inc")
        else:
            print(f"✅ Contractor connection already exists: Rodulfo Hilot -> Rudhil Construction & Enterprises Inc")
        
        # Add contractor connections for Jonathan Quirante
        existing_jonathan_contractor = await conn.fetchrow('''
            SELECT id FROM politician_contractors
            WHERE politician_id = $1 AND contractor_name = $2
        ''', jonathan_quirante['id'], "QUIRANTE CONSTRUCTION CORPORATION")
        
        if not existing_jonathan_contractor:
            await conn.execute('''
                INSERT INTO politician_contractors (politician_id, contractor_name, match_confidence, notes, source)
                VALUES ($1, $2, $3, $4, $5)
            ''', jonathan_quirante['id'], "QUIRANTE CONSTRUCTION CORPORATION", 10,
                "Owner of Quirante Construction Corporation. Company contracts leaped to P3B in 2023, P3.8B in first 8 months of 2025. Almost 60% of contracts are flood control", source_url_pcij)
            print(f"✅ Added contractor connection: Jonathan Quirante -> Quirante Construction Corporation")
        else:
            print(f"✅ Contractor connection already exists: Jonathan Quirante -> Quirante Construction Corporation")
        
        # Add contractor connection for Allan Quirante
        existing_allan_contractor = await conn.fetchrow('''
            SELECT id FROM politician_contractors
            WHERE politician_id = $1 AND contractor_name = $2
        ''', allan_quirante['id'], "QM BUILDERS")
        
        if not existing_allan_contractor:
            await conn.execute('''
                INSERT INTO politician_contractors (politician_id, contractor_name, match_confidence, notes, source)
                VALUES ($1, $2, $3, $4, $5)
            ''', allan_quirante['id'], "QM BUILDERS", 10,
                "Owner of QM Builders. Uncle of Jonathan M. Quirante. QM Builders had the largest flood-control funds in Cebu", source_url_philstar)
            print(f"✅ Added contractor connection: Allan Quirante -> QM Builders")
        else:
            print(f"✅ Contractor connection already exists: Allan Quirante -> QM Builders")
        
        print("\n✅ Done! Marcos Jr. contractor-donor relationships added")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(add_marcos_contractor_donors())
























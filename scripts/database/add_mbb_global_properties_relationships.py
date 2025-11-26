#!/usr/bin/env python3
"""Add MBB Global Properties relationships:
- Fatima Gay Bonoan Dela Cruz (daughter of Manuel Bonoan) -> MBB Global Properties (treasurer)
- Sunshine M. Bernardo (daughter of Roberto Bernardo) -> MBB Global Properties (corporate secretary)
- Macy Monique Maglanque (daughter of Rene Maglanque) -> MBB Global Properties (president)
- Connect daughters to their parents
"""

import asyncio
import asyncpg

async def add_mbb_global_properties_relationships():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # Source URLs
        source_url_philstar = "https://www.philstar.com/opinion/2025/09/11/2471919/sd-mbb-bbm-and-corruption"
        source_url_gmanetwork = "https://www.gmanetwork.com/news/topstories/nation/958560/lacson-links-ex-dpwh-chief-bonoan-to-bulacan-flood-contractor/story/"
        source_url_bilyonaryo = "https://bilyonaryo.com/2025/11/24/nagtalunan-parang-daga-heiresses-of-maglanque-bonoan-and-bernardo-bolt-from-p1-billion-wyndham-clark-builder-as-flood-control-stink-spreads/business/"
        
        # Get relationship types
        daughter_type = await conn.fetchval("SELECT id FROM connection_types WHERE name = 'Daughter' LIMIT 1")
        business_partner_type = await conn.fetchval("SELECT id FROM connection_types WHERE name = 'Business Partner' LIMIT 1")
        
        if not daughter_type or not business_partner_type:
            print("❌ Relationship types not found")
            return
        
        # Find or create Manuel Bonoan
        manuel_bonoan = await conn.fetchrow('''
            SELECT id, first_name, last_name FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%MANUEL%' 
              AND UPPER(last_name) LIKE '%BONOAN%'
              AND (UPPER(position) LIKE '%DPWH%' OR UPPER(position) LIKE '%SECRETARY%')
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not manuel_bonoan:
            print("❌ Manuel Bonoan not found")
            return
        
        print(f"✅ Found Manuel Bonoan: ID {manuel_bonoan['id']}")
        
        # Find or create Roberto Bernardo
        roberto_bernardo = await conn.fetchrow('''
            SELECT id, first_name, last_name FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%ROBERTO%' 
              AND UPPER(last_name) LIKE '%BERNARDO%'
              AND (UPPER(position) LIKE '%DPWH%' OR UPPER(position) LIKE '%UNDERSECRETARY%')
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not roberto_bernardo:
            print("❌ Roberto Bernardo not found")
            return
        
        print(f"✅ Found Roberto Bernardo: ID {roberto_bernardo['id']}")
        
        # Find or create Rene Maglanque
        rene_maglanque = await conn.fetchrow('''
            SELECT id, first_name, last_name FROM political_dynasties
            WHERE (UPPER(first_name) LIKE '%RENE%' OR UPPER(first_name) LIKE '%RENATO%')
              AND UPPER(last_name) LIKE '%MAGLANQUE%'
              AND (UPPER(position) LIKE '%MAYOR%' OR UPPER(position) LIKE '%CANDABA%')
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not rene_maglanque:
            # Create Rene Maglanque if not found
            rene_maglanque_id = await conn.fetchval('''
                INSERT INTO political_dynasties (first_name, last_name, position, province, municipality_city)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            ''', "RENE", "MAGLANQUE", "MAYOR", "PAMPANGA", "CANDABA")
            rene_maglanque = {'id': rene_maglanque_id, 'first_name': 'RENE', 'last_name': 'MAGLANQUE'}
            print(f"✅ Created Rene Maglanque: ID {rene_maglanque_id}")
        else:
            print(f"✅ Found Rene Maglanque: ID {rene_maglanque['id']}")
        
        # Find or create Fatima Gay Bonoan Dela Cruz
        fatima_bonoan = await conn.fetchrow('''
            SELECT id, first_name, last_name FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%FATIMA%'
              AND (UPPER(last_name) LIKE '%BONOAN%' OR UPPER(last_name) LIKE '%DELA CRUZ%' OR UPPER(last_name) LIKE '%CRUZ%')
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not fatima_bonoan:
            # Create Fatima Gay Bonoan Dela Cruz
            fatima_id = await conn.fetchval('''
                INSERT INTO political_dynasties (first_name, last_name, position)
                VALUES ($1, $2, $3)
                RETURNING id
            ''', "FATIMA GAY", "BONOAN DELA CRUZ", "TREASURER, MBB GLOBAL PROPERTIES")
            fatima_bonoan = {'id': fatima_id, 'first_name': 'FATIMA GAY', 'last_name': 'BONOAN DELA CRUZ'}
            print(f"✅ Created Fatima Gay Bonoan Dela Cruz: ID {fatima_id}")
        else:
            print(f"✅ Found Fatima Gay Bonoan Dela Cruz: ID {fatima_bonoan['id']}")
        
        # Find or create Sunshine M. Bernardo
        sunshine_bernardo = await conn.fetchrow('''
            SELECT id, first_name, last_name FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%SUNSHINE%'
              AND UPPER(last_name) LIKE '%BERNARDO%'
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not sunshine_bernardo:
            # Create Sunshine M. Bernardo
            sunshine_id = await conn.fetchval('''
                INSERT INTO political_dynasties (first_name, last_name, position)
                VALUES ($1, $2, $3)
                RETURNING id
            ''', "SUNSHINE M", "BERNARDO", "CORPORATE SECRETARY, MBB GLOBAL PROPERTIES")
            sunshine_bernardo = {'id': sunshine_id, 'first_name': 'SUNSHINE M', 'last_name': 'BERNARDO'}
            print(f"✅ Created Sunshine M. Bernardo: ID {sunshine_id}")
        else:
            print(f"✅ Found Sunshine M. Bernardo: ID {sunshine_bernardo['id']}")
        
        # Find or create Macy Monique Maglanque
        macy_maglanque = await conn.fetchrow('''
            SELECT id, first_name, last_name FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%MACY%'
              AND UPPER(last_name) LIKE '%MAGLANQUE%'
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not macy_maglanque:
            # Create Macy Monique Maglanque
            macy_id = await conn.fetchval('''
                INSERT INTO political_dynasties (first_name, last_name, position)
                VALUES ($1, $2, $3)
                RETURNING id
            ''', "MACY MONIQUE", "MAGLANQUE", "PRESIDENT, MBB GLOBAL PROPERTIES")
            macy_maglanque = {'id': macy_id, 'first_name': 'MACY MONIQUE', 'last_name': 'MAGLANQUE'}
            print(f"✅ Created Macy Monique Maglanque: ID {macy_id}")
        else:
            print(f"✅ Found Macy Monique Maglanque: ID {macy_maglanque['id']}")
        
        # Contractor name (MBB Global Properties Corp)
        contractor_name = "MBB GLOBAL PROPERTIES"
        
        # Add daughter relationships
        # Fatima -> Manuel Bonoan (daughter)
        existing = await conn.fetchrow('''
            SELECT id FROM relationships
            WHERE person_id = $1 AND related_person_id = $2 AND relationship_type = $3
        ''', fatima_bonoan['id'], manuel_bonoan['id'], daughter_type)
        
        if not existing:
            await conn.execute('''
                INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description, source_url)
                VALUES ($1, $2, $3, $4, $5)
            ''', fatima_bonoan['id'], manuel_bonoan['id'], daughter_type,
                "Fatima Gay Bonoan Dela Cruz is daughter of Manuel Bonoan", source_url_philstar)
            print(f"✅ Added relationship: Fatima -> Manuel Bonoan (daughter)")
        
        # Sunshine -> Roberto Bernardo (daughter)
        existing = await conn.fetchrow('''
            SELECT id FROM relationships
            WHERE person_id = $1 AND related_person_id = $2 AND relationship_type = $3
        ''', sunshine_bernardo['id'], roberto_bernardo['id'], daughter_type)
        
        if not existing:
            await conn.execute('''
                INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description, source_url)
                VALUES ($1, $2, $3, $4, $5)
            ''', sunshine_bernardo['id'], roberto_bernardo['id'], daughter_type,
                "Sunshine M. Bernardo is daughter of Roberto Bernardo", source_url_philstar)
            print(f"✅ Added relationship: Sunshine -> Roberto Bernardo (daughter)")
        
        # Macy -> Rene Maglanque (daughter)
        existing = await conn.fetchrow('''
            SELECT id FROM relationships
            WHERE person_id = $1 AND related_person_id = $2 AND relationship_type = $3
        ''', macy_maglanque['id'], rene_maglanque['id'], daughter_type)
        
        if not existing:
            await conn.execute('''
                INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description, source_url)
                VALUES ($1, $2, $3, $4, $5)
            ''', macy_maglanque['id'], rene_maglanque['id'], daughter_type,
                "Macy Monique Maglanque is daughter of Rene Maglanque", source_url_philstar)
            print(f"✅ Added relationship: Macy -> Rene Maglanque (daughter)")
        
        # Add contractor connections for all three daughters
        people_contractors = [
            (fatima_bonoan['id'], "Treasurer"),
            (sunshine_bernardo['id'], "Corporate Secretary"),
            (macy_maglanque['id'], "President")
        ]
        
        for person_id, role in people_contractors:
            existing = await conn.fetchrow('''
                SELECT id FROM politician_contractors
                WHERE politician_id = $1 AND contractor_name = $2
            ''', person_id, contractor_name)
            
            if not existing:
                await conn.execute('''
                    INSERT INTO politician_contractors (politician_id, contractor_name, match_confidence, notes, source)
                    VALUES ($1, $2, $3, $4, $5)
                ''', person_id, contractor_name, 10, f"{role} of MBB Global Properties Corp", source_url_philstar)
                print(f"✅ Added contractor connection: {role} -> {contractor_name}")
        
        # Add contractor connections for the parents (they're connected through their daughters' company)
        parents = [
            (manuel_bonoan['id'], "Father of treasurer"),
            (roberto_bernardo['id'], "Father of corporate secretary"),
            (rene_maglanque['id'], "Father of president")
        ]
        
        for person_id, note in parents:
            existing = await conn.fetchrow('''
                SELECT id FROM politician_contractors
                WHERE politician_id = $1 AND contractor_name = $2
            ''', person_id, contractor_name)
            
            if not existing:
                await conn.execute('''
                    INSERT INTO politician_contractors (politician_id, contractor_name, match_confidence, notes, source)
                    VALUES ($1, $2, $3, $4, $5)
                ''', person_id, contractor_name, 9, note, source_url_philstar)
                print(f"✅ Added contractor connection: Parent -> {contractor_name}")
        
        # Add business partner relationships between the daughters (they co-own MBB Global Properties)
        daughters = [
            (fatima_bonoan['id'], "Fatima Gay Bonoan Dela Cruz"),
            (sunshine_bernardo['id'], "Sunshine M. Bernardo"),
            (macy_maglanque['id'], "Macy Monique Maglanque")
        ]
        
        for i, (person1_id, person1_name) in enumerate(daughters):
            for person2_id, person2_name in daughters[i+1:]:
                existing = await conn.fetchrow('''
                    SELECT id FROM relationships
                    WHERE person_id = $1 AND related_person_id = $2
                      AND relationship_description ILIKE '%MBB%'
                ''', person1_id, person2_id)
                
                if not existing:
                    await conn.execute('''
                        INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description, source_url)
                        VALUES ($1, $2, $3, $4, $5)
                    ''', person1_id, person2_id, business_partner_type,
                        f"Co-owners and officers of MBB Global Properties Corp", source_url_philstar)
                    print(f"✅ Added relationship: {person1_name} <-> {person2_name} (business partners)")
        
        print("\n✅ Done! MBB Global Properties relationships added")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(add_mbb_global_properties_relationships())


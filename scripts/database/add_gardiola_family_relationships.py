#!/usr/bin/env python3
"""Add Gardiola family relationships and contractor connections based on:
- User-provided information about JSG Construction, E. Gardiola Construction, St. Gerrard Construction
- Politicontractors.xlsx data showing additional contractors and relationships
"""

import asyncio
import asyncpg
import pandas as pd
from pathlib import Path

async def add_gardiola_family_relationships():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # Source URLs
        source_url_rappler = "https://www.rappler.com/newsbreak/investigative/politicians-government-contractors-connections-map/"
        source_url_politicontractors = "POLITICONTRACTORS.xlsx"
        
        # Get relationship types
        wife_type = await conn.fetchval("SELECT id FROM connection_types WHERE name = 'Wife' LIMIT 1")
        husband_type = await conn.fetchval("SELECT id FROM connection_types WHERE name = 'Husband' LIMIT 1")
        brother_type = await conn.fetchval("SELECT id FROM connection_types WHERE name = 'Brother' LIMIT 1")
        daughter_type = await conn.fetchval("SELECT id FROM connection_types WHERE name = 'Daughter' LIMIT 1")
        business_partner_type = await conn.fetchval("SELECT id FROM connection_types WHERE name = 'Business Partner' LIMIT 1")
        
        if not all([wife_type, husband_type, brother_type, daughter_type, business_partner_type]):
            print("❌ Relationship types not found")
            return
        
        # Find or create Edwin Gardiola
        edwin_gardiola = await conn.fetchrow('''
            SELECT id, first_name, last_name FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%EDWIN%' 
              AND UPPER(last_name) LIKE '%GARDIOLA%'
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not edwin_gardiola:
            edwin_id = await conn.fetchval('''
                INSERT INTO political_dynasties (first_name, last_name, position)
                VALUES ($1, $2, $3)
                RETURNING id
            ''', "EDWIN", "GARDIOLA", "REPRESENTATIVE, CONSTRUCTION WORKERS SOLIDARITY PARTY-LIST")
            edwin_gardiola = {'id': edwin_id, 'first_name': 'EDWIN', 'last_name': 'GARDIOLA'}
            print(f"✅ Created Edwin Gardiola: ID {edwin_id}")
        else:
            print(f"✅ Found Edwin Gardiola: ID {edwin_gardiola['id']}")
        
        # Find or create Judy Silva Gardiola (wife)
        judy_gardiola = await conn.fetchrow('''
            SELECT id, first_name, last_name FROM political_dynasties
            WHERE (UPPER(first_name) LIKE '%JUDY%' AND UPPER(last_name) LIKE '%GARDIOLA%')
               OR (UPPER(first_name) LIKE '%JUDY%' AND UPPER(last_name) LIKE '%SILVA%')
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not judy_gardiola:
            judy_id = await conn.fetchval('''
                INSERT INTO political_dynasties (first_name, last_name, position)
                VALUES ($1, $2, $3)
                RETURNING id
            ''', "JUDY SILVA", "GARDIOLA", "PRESIDENT, S-ANG CONSTRUCTION & GENERAL TRADING INCORPORATED")
            judy_gardiola = {'id': judy_id, 'first_name': 'JUDY SILVA', 'last_name': 'GARDIOLA'}
            print(f"✅ Created Judy Silva Gardiola: ID {judy_id}")
        else:
            print(f"✅ Found Judy Silva Gardiola: ID {judy_gardiola['id']}")
        
        # Find or create Elmer Gardiola (brother)
        elmer_gardiola = await conn.fetchrow('''
            SELECT id, first_name, last_name FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%ELMER%' 
              AND UPPER(last_name) LIKE '%GARDIOLA%'
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not elmer_gardiola:
            elmer_id = await conn.fetchval('''
                INSERT INTO political_dynasties (first_name, last_name, position)
                VALUES ($1, $2, $3)
                RETURNING id
            ''', "ELMER", "GARDIOLA", "BUSINESS OWNER")
            elmer_gardiola = {'id': elmer_id, 'first_name': 'ELMER', 'last_name': 'GARDIOLA'}
            print(f"✅ Created Elmer Gardiola: ID {elmer_id}")
        else:
            print(f"✅ Found Elmer Gardiola: ID {elmer_gardiola['id']}")
        
        # Find or create Elaine Gardiola (Elmer's wife, president of Newington Builders)
        elaine_gardiola = await conn.fetchrow('''
            SELECT id, first_name, last_name FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%ELAINE%' 
              AND UPPER(last_name) LIKE '%GARDIOLA%'
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not elaine_gardiola:
            elaine_id = await conn.fetchval('''
                INSERT INTO political_dynasties (first_name, last_name, position)
                VALUES ($1, $2, $3)
                RETURNING id
            ''', "ELAINE", "GARDIOLA", "PRESIDENT, NEWINGTON BUILDERS INC")
            elaine_gardiola = {'id': elaine_id, 'first_name': 'ELAINE', 'last_name': 'GARDIOLA'}
            print(f"✅ Created Elaine Gardiola: ID {elaine_id}")
        else:
            print(f"✅ Found Elaine Gardiola: ID {elaine_gardiola['id']}")
        
        # Find or create Alberto Gardiola (brother, VP of Newington Builders)
        alberto_gardiola = await conn.fetchrow('''
            SELECT id, first_name, last_name FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%ALBERTO%' 
              AND UPPER(last_name) LIKE '%GARDIOLA%'
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not alberto_gardiola:
            alberto_id = await conn.fetchval('''
                INSERT INTO political_dynasties (first_name, last_name, position)
                VALUES ($1, $2, $3)
                RETURNING id
            ''', "ALBERTO", "GARDIOLA", "VICE PRESIDENT, NEWINGTON BUILDERS INC")
            alberto_gardiola = {'id': alberto_id, 'first_name': 'ALBERTO', 'last_name': 'GARDIOLA'}
            print(f"✅ Created Alberto Gardiola: ID {alberto_id}")
        else:
            print(f"✅ Found Alberto Gardiola: ID {alberto_gardiola['id']}")
        
        # Find or create Earel Gardiola (brother, president of Lourel Development)
        earel_gardiola = await conn.fetchrow('''
            SELECT id, first_name, last_name FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%EAREL%' 
              AND UPPER(last_name) LIKE '%GARDIOLA%'
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not earel_gardiola:
            earel_id = await conn.fetchval('''
                INSERT INTO political_dynasties (first_name, last_name, position)
                VALUES ($1, $2, $3)
                RETURNING id
            ''', "EAREL", "GARDIOLA", "PRESIDENT, LOUREL DEVELOPMENT CORPORATION")
            earel_gardiola = {'id': earel_id, 'first_name': 'EAREL', 'last_name': 'GARDIOLA'}
            print(f"✅ Created Earel Gardiola: ID {earel_id}")
        else:
            print(f"✅ Found Earel Gardiola: ID {earel_gardiola['id']}")
        
        # Find or create Kim Ann Gardiola (daughter)
        kim_ann_gardiola = await conn.fetchrow('''
            SELECT id, first_name, last_name FROM political_dynasties
            WHERE (UPPER(first_name) LIKE '%KIM%' AND UPPER(last_name) LIKE '%GARDIOLA%')
               OR (UPPER(first_name) LIKE '%KIM ANN%' AND UPPER(last_name) LIKE '%GARDIOLA%')
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not kim_ann_gardiola:
            kim_ann_id = await conn.fetchval('''
                INSERT INTO political_dynasties (first_name, last_name, position)
                VALUES ($1, $2, $3)
                RETURNING id
            ''', "KIM ANN", "GARDIOLA", "CORPORATE OFFICER")
            kim_ann_gardiola = {'id': kim_ann_id, 'first_name': 'KIM ANN', 'last_name': 'GARDIOLA'}
            print(f"✅ Created Kim Ann Gardiola: ID {kim_ann_id}")
        else:
            print(f"✅ Found Kim Ann Gardiola: ID {kim_ann_gardiola['id']}")
        
        # Find or create Katrina Mara Gardiola (daughter)
        katrina_gardiola = await conn.fetchrow('''
            SELECT id, first_name, last_name FROM political_dynasties
            WHERE (UPPER(first_name) LIKE '%KATRINA%' AND UPPER(last_name) LIKE '%GARDIOLA%')
               OR (UPPER(first_name) LIKE '%KATRINA MARA%' AND UPPER(last_name) LIKE '%GARDIOLA%')
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not katrina_gardiola:
            katrina_id = await conn.fetchval('''
                INSERT INTO political_dynasties (first_name, last_name, position)
                VALUES ($1, $2, $3)
                RETURNING id
            ''', "KATRINA MARA", "GARDIOLA", "CORPORATE OFFICER")
            katrina_gardiola = {'id': katrina_id, 'first_name': 'KATRINA MARA', 'last_name': 'GARDIOLA'}
            print(f"✅ Created Katrina Mara Gardiola: ID {katrina_id}")
        else:
            print(f"✅ Found Katrina Mara Gardiola: ID {katrina_gardiola['id']}")
        
        # Add family relationships
        relationships_to_add = [
            # Edwin <-> Judy (husband/wife)
            (edwin_gardiola['id'], judy_gardiola['id'], husband_type, "Edwin Gardiola is husband of Judy Silva Gardiola", source_url_rappler),
            (judy_gardiola['id'], edwin_gardiola['id'], wife_type, "Judy Silva Gardiola is wife of Edwin Gardiola", source_url_rappler),
            
            # Edwin <-> Elmer (brothers)
            (edwin_gardiola['id'], elmer_gardiola['id'], brother_type, "Edwin Gardiola and Elmer Gardiola are brothers", source_url_politicontractors),
            (elmer_gardiola['id'], edwin_gardiola['id'], brother_type, "Elmer Gardiola and Edwin Gardiola are brothers", source_url_politicontractors),
            
            # Edwin <-> Alberto (brothers)
            (edwin_gardiola['id'], alberto_gardiola['id'], brother_type, "Edwin Gardiola and Alberto Gardiola are brothers", source_url_politicontractors),
            (alberto_gardiola['id'], edwin_gardiola['id'], brother_type, "Alberto Gardiola and Edwin Gardiola are brothers", source_url_politicontractors),
            
            # Edwin <-> Earel (brothers)
            (edwin_gardiola['id'], earel_gardiola['id'], brother_type, "Edwin Gardiola and Earel Gardiola are brothers", source_url_politicontractors),
            (earel_gardiola['id'], edwin_gardiola['id'], brother_type, "Earel Gardiola and Edwin Gardiola are brothers", source_url_politicontractors),
            
            # Elmer <-> Elaine (husband/wife)
            (elmer_gardiola['id'], elaine_gardiola['id'], husband_type, "Elmer Gardiola is husband of Elaine Gardiola", source_url_politicontractors),
            (elaine_gardiola['id'], elmer_gardiola['id'], wife_type, "Elaine Gardiola is wife of Elmer Gardiola", source_url_politicontractors),
            
            # Edwin -> Kim Ann (father/daughter)
            (edwin_gardiola['id'], kim_ann_gardiola['id'], daughter_type, "Kim Ann Gardiola is daughter of Edwin Gardiola", source_url_rappler),
            
            # Edwin -> Katrina Mara (father/daughter)
            (edwin_gardiola['id'], katrina_gardiola['id'], daughter_type, "Katrina Mara Gardiola is daughter of Edwin Gardiola", source_url_rappler),
        ]
        
        for person_id, related_id, rel_type, description, url in relationships_to_add:
            existing = await conn.fetchrow('''
                SELECT id FROM relationships
                WHERE person_id = $1 AND related_person_id = $2 AND relationship_type = $3
            ''', person_id, related_id, rel_type)
            
            if not existing:
                await conn.execute('''
                    INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description, source_url)
                    VALUES ($1, $2, $3, $4, $5)
                ''', person_id, related_id, rel_type, description, url)
                print(f"✅ Added relationship: {description}")
        
        # Add contractor connections from user info and politicontractors
        contractors = [
            # From user-provided info
            ("JSG CONSTRUCTION COMPANY INC.", [
                (edwin_gardiola['id'], "Owner/Co-owner"),
                (judy_gardiola['id'], "Owner/Co-owner"),
                (elmer_gardiola['id'], "Incorporator"),
                (kim_ann_gardiola['id'], "Corporate Officer"),
                (katrina_gardiola['id'], "Corporate Officer"),
            ]),
            ("E. GARDIOLA CONSTRUCTION", [
                (elmer_gardiola['id'], "Owner/Co-owner"),
                (elaine_gardiola['id'], "Owner/Co-owner"),
            ]),
            ("ST. GERRARD CONSTRUCTION GENERAL CONTRACTOR AND DEVELOPMENT CORPORATION", [
                (edwin_gardiola['id'], "Affiliate/Owner"),
                (judy_gardiola['id'], "Affiliate/Owner"),
            ]),
            # From politicontractors data
            ("NEWINGTON BUILDERS INC", [
                (edwin_gardiola['id'], "Brother of Elaine and Alberto Gardiola, president and vice president"),
                (elaine_gardiola['id'], "President"),
                (alberto_gardiola['id'], "Vice President"),
            ]),
            ("S-ANG CONSTRUCTION & GENERAL TRADING INC", [
                (edwin_gardiola['id'], "Husband of Judy Gardiola, incorporator and president"),
                (judy_gardiola['id'], "Incorporator and President"),
            ]),
            ("C.T. LEONCIO CONSTRUCTION & TRADING", [
                (edwin_gardiola['id'], "Husband of Judy Gardiola, incorporator and president of S-Ang Construction"),
                (judy_gardiola['id'], "Related through S-Ang Construction"),
            ]),
            ("MORTAR MASTERS & CONCRETE BUILDERS", [
                (edwin_gardiola['id'], "Husband of Judy Gardiola, incorporator and president of S-Ang Construction"),
                (judy_gardiola['id'], "Related through S-Ang Construction"),
            ]),
            ("LOUREL DEVELOPMENT CORPORATION", [
                (edwin_gardiola['id'], "Brother of Earel Gardiola, president of Lourel Development Corporation"),
                (earel_gardiola['id'], "President"),
            ]),
            ("CHIARA2300 INCORPORATED", [
                (edwin_gardiola['id'], "Brother of Earel Gardiola, president of Lourel Development Corporation"),
            ]),
            ("THREE W BUILDERS INC", [
                (edwin_gardiola['id'], "Brother of Earel Gardiola, president of Lourel Development Corporation"),
            ]),
        ]
        
        for contractor_name, people_roles in contractors:
            for person_id, role in people_roles:
                existing = await conn.fetchrow('''
                    SELECT id FROM politician_contractors
                    WHERE politician_id = $1 AND contractor_name = $2
                ''', person_id, contractor_name)
                
                if not existing:
                    await conn.execute('''
                        INSERT INTO politician_contractors (politician_id, contractor_name, match_confidence, notes, source)
                        VALUES ($1, $2, $3, $4, $5)
                    ''', person_id, contractor_name, 10, role, source_url_politicontractors if "politicontractors" in role.lower() or contractor_name in ["NEWINGTON BUILDERS INC", "S-ANG CONSTRUCTION & GENERAL TRADING INC", "C.T. LEONCIO CONSTRUCTION & TRADING", "MORTAR MASTERS & CONCRETE BUILDERS", "LOUREL DEVELOPMENT CORPORATION", "CHIARA2300 INCORPORATED", "THREE W BUILDERS INC"] else source_url_rappler)
                    print(f"✅ Added contractor connection: {role} -> {contractor_name}")
        
        print("\n✅ Done! Gardiola family relationships and contractor connections added")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(add_gardiola_family_relationships())

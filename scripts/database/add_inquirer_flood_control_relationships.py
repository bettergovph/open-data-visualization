#!/usr/bin/env python3
"""
Parse and add relationships from Inquirer flood control investigation articles
Based on Roberto Bernardo's testimony linking senators to DPWH kickbacks
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def add_inquirer_relationships():
    """Add relationships from Inquirer flood control investigation articles"""
    
    # Database connection
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu',
        database='dynasty'
    )
    
    try:
        print("🔍 Adding relationships from Inquirer flood control investigation...")
        
        # Get connection type IDs
        connection_types = await conn.fetch("""
            SELECT id, code, description 
            FROM connection_types 
            ORDER BY id
        """)
        
        type_map = {(ct['description'] or '').upper(): ct['id'] for ct in connection_types if ct['description']}
        
        # Helper function to find or create person
        async def find_or_create_person(first_name, last_name, position=None, party=None, province=None, region=None, year=2025):
            person = await conn.fetchrow("""
                SELECT id FROM political_dynasties 
                WHERE first_name ILIKE $1 AND last_name ILIKE $2
                LIMIT 1
            """, first_name.upper(), last_name.upper())
            
            if person:
                return person['id']
            
            max_id = await conn.fetchval("SELECT MAX(id) FROM political_dynasties") or 0
            person_id = max_id + 1
            
            await conn.execute("""
                INSERT INTO political_dynasties 
                (id, first_name, last_name, position, year, party, province, region)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """, person_id, first_name.upper(), last_name.upper(), position, year, party, province, region)
            
            print(f"✅ Created {first_name} {last_name} (ID: {person_id})")
            return person_id
        
        # Helper function to add relationship
        async def add_relationship(person_id, related_id, rel_type_id, description, source_url):
            try:
                await conn.execute("""
                    INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (person_id, related_person_id, relationship_type) DO UPDATE
                    SET relationship_description = EXCLUDED.relationship_description
                """, person_id, related_id, rel_type_id, description)
                print(f"✅ Added: {person_id} -> {related_id} ({description})")
            except Exception as e:
                print(f"⚠️ Relationship may already exist: {e}")
        
        # Get relationship type IDs
        staff_type_id = None
        cousin_type_id = type_map.get('COUSIN', 13)
        business_partner_type_id = None
        
        for ct in connection_types:
            desc = (ct['description'] or '').upper()
            if 'STAFF' in desc or 'ASSISTANT' in desc:
                staff_type_id = ct['id']
            if 'BUSINESS PARTNER' in desc or 'PATRON' in desc:
                business_partner_type_id = ct['id']
        
        if not staff_type_id:
            staff_type_id = business_partner_type_id or 28  # Default to business partner
        if not business_partner_type_id:
            business_partner_type_id = await conn.fetchval("SELECT id FROM connection_types WHERE code = 28 LIMIT 1") or 28
        
        # Source URLs
        source_url_1 = "https://newsinfo.inquirer.net/2140264/former-dpwh-official-links-more-senators-to-kickbacks"
        source_url_2 = "https://newsinfo.inquirer.net/2139951/flood-control-senate-hearing"
        source_url_3 = "https://newsinfo.inquirer.net/2114950/escudero-revilla-binay-in-flood-control-mess-ex-dpwh-exec"
        source_url_4 = "https://newsinfo.inquirer.net/2115457/escudero-binay-depeds-olaivar-issue-denials"
        
        # 1. Grace Poe relationships (from article 1)
        print("\n📋 Processing Grace Poe relationships...")
        grace_poe_id = await find_or_create_person("GRACE", "POE", "SENATOR", "INDEPENDENT")
        jy_dela_rosa_id = await find_or_create_person("JY", "DELA ROSA", "STAFF")
        mrs_patron_id = await find_or_create_person("MRS", "PATRON", "CONTRACTOR")
        
        await add_relationship(grace_poe_id, jy_dela_rosa_id, staff_type_id, 
                              "Staff of Grace Poe - coordinates DPWH projects", source_url_1)
        await add_relationship(jy_dela_rosa_id, mrs_patron_id, business_partner_type_id,
                              "Coordinates with contractor Mrs. Patron for V.R. PATRON BUILDERS projects", source_url_1)
        
        # 2. Mark Villar relationships (from article 1)
        print("\n📋 Processing Mark Villar relationships...")
        mark_villar_id = await find_or_create_person("MARK", "VILLAR", "SENATOR", None, None, None, 2025)
        carlo_aguilar_id = await find_or_create_person("CARLO", "AGUILAR", "CONTRACTOR")
        catalina_cabral_id = await find_or_create_person("CATALINA", "CABRAL", "FORMER DPWH UNDERSECRETARY")
        roberto_bernardo_id = await find_or_create_person("ROBERTO", "BERNARDO", "FORMER DPWH UNDERSECRETARY")
        
        await add_relationship(mark_villar_id, carlo_aguilar_id, cousin_type_id,
                              "Cousin of Mark Villar - receives commissions for DPWH projects", source_url_1)
        await add_relationship(mark_villar_id, catalina_cabral_id, business_partner_type_id,
                              "Worked closely with Catalina Cabral for DPWH project allocations", source_url_1)
        await add_relationship(catalina_cabral_id, roberto_bernardo_id, business_partner_type_id,
                              "Worked with Roberto Bernardo on DPWH project approvals", source_url_1)
        
        # 3. Sonny Angara relationships (from article 1)
        print("\n📋 Processing Sonny Angara relationships...")
        sonny_angara_id = await find_or_create_person("SONNY", "ANGARA", "EDUCATION SECRETARY", None, None, None, 2025)
        trygve_olaivar_id = await find_or_create_person("TRYGVE", "OLAIVAR", "EDUCATION UNDERSECRETARY")
        
        await add_relationship(sonny_angara_id, trygve_olaivar_id, staff_type_id,
                              "Undersecretary receives deliveries for Sonny Angara", source_url_1)
        await add_relationship(trygve_olaivar_id, roberto_bernardo_id, business_partner_type_id,
                              "Transactions with Roberto Bernardo for DPWH projects", source_url_1)
        
        # 4. Bong Revilla relationships (from article 1)
        print("\n📋 Processing Bong Revilla relationships...")
        bong_revilla_id = await find_or_create_person("RAMON", "REVILLA", "FORMER SENATOR", None, None, None, 2025)
        gerard_opulencia_id = await find_or_create_person("GERARD", "OPULENCIA", "NCR DISTRICT ENGINEER")
        henry_alcantara_id = await find_or_create_person("HENRY", "ALCANTARA", "ENGINEER")
        
        await add_relationship(bong_revilla_id, roberto_bernardo_id, business_partner_type_id,
                              "Received kickbacks from DPWH flood control projects", source_url_1)
        await add_relationship(roberto_bernardo_id, gerard_opulencia_id, business_partner_type_id,
                              "Coordinated project lists with NCR district engineer", source_url_1)
        await add_relationship(roberto_bernardo_id, henry_alcantara_id, business_partner_type_id,
                              "Engineer collected commitments for projects", source_url_1)
        
        # 5. Jinggoy Estrada relationships (from article 1)
        print("\n📋 Processing Jinggoy Estrada relationships...")
        jinggoy_estrada_id = await find_or_create_person("JINGGOY", "ESTRADA", "SENATOR", None, None, None, 2025)
        manuel_bonoan_id = await find_or_create_person("MANUEL", "BONOAN", "FORMER DPWH SECRETARY")
        
        await add_relationship(jinggoy_estrada_id, roberto_bernardo_id, business_partner_type_id,
                              "Received kickbacks from DPWH projects through Roberto Bernardo", source_url_1)
        await add_relationship(jinggoy_estrada_id, manuel_bonoan_id, business_partner_type_id,
                              "Requested projects through Manuel Bonoan", source_url_1)
        await add_relationship(manuel_bonoan_id, roberto_bernardo_id, business_partner_type_id,
                              "Worked with Roberto Bernardo on project allocations", source_url_1)
        
        # 6. Nancy Binay relationships (from article 1)
        print("\n📋 Processing Nancy Binay relationships...")
        nancy_binay_id = await find_or_create_person("NANCY", "BINAY", "FORMER SENATOR", None, None, None, 2025)
        
        await add_relationship(nancy_binay_id, roberto_bernardo_id, business_partner_type_id,
                              "Received commitments from DPWH flood control projects", source_url_1)
        
        # 7. Chiz Escudero relationships (from article 1)
        print("\n📋 Processing Chiz Escudero relationships...")
        chiz_escudero_id = await find_or_create_person("FRANCIS", "ESCUDERO", "SENATOR", None, None, None, 2025)
        meynard_ngu_id = await find_or_create_person("MEYNARD", "NGU", "BUSINESSMAN")
        
        await add_relationship(chiz_escudero_id, meynard_ngu_id, business_partner_type_id,
                              "Businessman and campaign contributor - received P160M for Escudero", source_url_1)
        await add_relationship(meynard_ngu_id, roberto_bernardo_id, business_partner_type_id,
                              "Received P160 million (20% of P800M project) from Roberto Bernardo for Escudero", source_url_1)
        
        # 8. Zaldy Co relationships (from multiple sources)
        print("\n📋 Processing Zaldy Co relationships...")
        zaldy_co_id = await find_or_create_person("ELIZALDY", "CO", "CONGRESSMAN", "AKO BICOL PARTYLIST")
        orly_guteza_id = await find_or_create_person("ORLY", "GUTEZA", "SECURITY AIDE")
        martin_romualdez_id = await find_or_create_person("MARTIN", "ROMUALDEZ", "HOUSE SPEAKER")
        
        await add_relationship(zaldy_co_id, roberto_bernardo_id, business_partner_type_id,
                              "Received kickbacks from DPWH projects - P355M in 2025 GAA, P600M in 2023", source_url_1)
        await add_relationship(henry_alcantara_id, zaldy_co_id, business_partner_type_id,
                              "Delivered alleged kickbacks to Zaldy Co's residence in Pasig and Taguig", source_url_1)
        await add_relationship(zaldy_co_id, orly_guteza_id, staff_type_id,
                              "Security aide to Zaldy Co - delivered cash to Martin Romualdez", source_url_1)
        await add_relationship(orly_guteza_id, martin_romualdez_id, business_partner_type_id,
                              "Regularly delivered luggage filled with cash to Martin Romualdez's residence", source_url_1)
        
        # 9. Joel Villanueva relationships (from Wikipedia and other sources)
        print("\n📋 Processing Joel Villanueva relationships...")
        joel_villanueva_id = await find_or_create_person("JOEL", "VILLANUEVA", "SENATOR", None, None, None, 2025)
        
        await add_relationship(joel_villanueva_id, roberto_bernardo_id, business_partner_type_id,
                              "Requested P1.5B multipurpose buildings in 2022 - received P1B in cash through staff", source_url_1)
        await add_relationship(henry_alcantara_id, joel_villanueva_id, business_partner_type_id,
                              "Delivered P1B in cash to Joel Villanueva's staff at rest house in Bocaue, Bulacan", source_url_1)
        
        # 10. Additional DPWH officials
        print("\n📋 Processing additional DPWH officials...")
        brice_hernandez_id = await find_or_create_person("BRICE", "HERNANDEZ", "FORMER DPWH ASSISTANT DISTRICT ENGINEER")
        jaypee_mendoza_id = await find_or_create_person("JAYPEE", "MENDOZA", "FORMER DPWH OFFICIAL")
        curlee_discaya_id = await find_or_create_person("CURLEE", "DISCAYA", "CONTRACTOR")
        sarah_discaya_id = await find_or_create_person("SARAH", "DISCAYA", "CONTRACTOR")
        mario_lipana_id = await find_or_create_person("MARIO", "LIPANA", "COA COMMISSIONER")
        
        await add_relationship(brice_hernandez_id, roberto_bernardo_id, business_partner_type_id,
                              "Former DPWH engineer - admitted to racket in Bulacan 1st District Engineering Office", source_url_1)
        await add_relationship(jaypee_mendoza_id, roberto_bernardo_id, business_partner_type_id,
                              "Former DPWH official - protected witness in flood control investigation", source_url_1)
        await add_relationship(curlee_discaya_id, roberto_bernardo_id, business_partner_type_id,
                              "Contractor - protected witness, named lawmakers in payoff ledger", source_url_1)
        await add_relationship(sarah_discaya_id, roberto_bernardo_id, business_partner_type_id,
                              "Contractor - protected witness in flood control investigation", source_url_1)
        await add_relationship(mario_lipana_id, roberto_bernardo_id, business_partner_type_id,
                              "COA Commissioner - mentioned in connection with anomalous flood control projects", source_url_1)
        
        # 11. Update Bong Revilla relationship with correct amount
        await add_relationship(roberto_bernardo_id, bong_revilla_id, business_partner_type_id,
                              "Personally delivered P125 million (25% commission) to Bong Revilla's residence in Cavite", source_url_1)
        
        # 12. Update Nancy Binay relationship with correct amount
        await add_relationship(roberto_bernardo_id, nancy_binay_id, business_partner_type_id,
                              "Personally delivered P37 million (15% of P250M projects) to Nancy Binay at house in Quezon City", source_url_1)
        
        print("\n✅ All relationships from Inquirer articles and additional sources added!")
        print(f"\n📊 Summary:")
        print(f"  - Grace Poe -> JY dela Rosa -> Mrs. Patron")
        print(f"  - Mark Villar -> Carlo Aguilar (cousin) -> Catalina Cabral -> Roberto Bernardo")
        print(f"  - Sonny Angara -> Trygve Olaivar -> Roberto Bernardo")
        print(f"  - Bong Revilla -> Roberto Bernardo (P125M) -> Gerard Opulencia, Henry Alcantara")
        print(f"  - Jinggoy Estrada -> Roberto Bernardo, Manuel Bonoan")
        print(f"  - Nancy Binay -> Roberto Bernardo (P37M)")
        print(f"  - Chiz Escudero -> Meynard Ngu (P160M) -> Roberto Bernardo")
        print(f"  - Zaldy Co -> Roberto Bernardo (P355M 2025, P600M 2023) -> Orly Guteza -> Martin Romualdez")
        print(f"  - Joel Villanueva -> Roberto Bernardo (P1B) -> Henry Alcantara")
        print(f"  - Additional: Brice Hernandez, Jaypee Mendoza, Curlee Discaya, Sarah Discaya, Mario Lipana")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(add_inquirer_relationships())


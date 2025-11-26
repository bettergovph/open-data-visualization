#!/usr/bin/env python3
"""
Add Grace Poe -> Mark Patron (FPJ Partylist) -> JV dela Rosa -> V.R. PATRON BUILDERS relationship chain
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def add_poe_patron_relationship():
    """Add the relationship chain: Grace Poe -> Mark Patron -> JV dela Rosa -> V.R. PATRON BUILDERS"""
    
    # Database connection
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu',
        database='dynasty'
    )
    
    try:
        print("🔍 Adding Grace Poe -> Mark Patron -> JV dela Rosa -> V.R. PATRON BUILDERS relationship chain...")
        
        # Get connection type IDs
        connection_types = await conn.fetch("""
            SELECT id, code, description 
            FROM connection_types 
            ORDER BY id
        """)
        
        type_map = {(ct['description'] or '').upper(): ct['id'] for ct in connection_types if ct['description']}
        
        # Check if "Patron" relationship type exists, if not use Business Partner
        patron_type_id = None
        for ct in connection_types:
            desc = (ct['description'] or '').upper()
            if 'PATRON' in desc or 'BUSINESS PARTNER' in desc:
                patron_type_id = ct['id']
                break
        
        if not patron_type_id:
            # Use Business Partner (code 28) or create one
            business_partner = await conn.fetchrow("""
                SELECT id FROM connection_types WHERE code = 28 OR description ILIKE '%business partner%'
            """)
            if business_partner:
                patron_type_id = business_partner['id']
            else:
                # Create patron relationship type
                patron_type_id = await conn.fetchval("""
                    INSERT INTO connection_types (code, name, description, category, bidirectional)
                    VALUES (32, 'Patron', 'Business patron or sponsor relationship', 'business', TRUE)
                    RETURNING id
                """)
                print(f"✅ Created 'Patron' connection type (ID: {patron_type_id})")
        
        # Find or create Grace Poe (Senator)
        grace_poe = await conn.fetchrow("""
            SELECT id FROM political_dynasties 
            WHERE (first_name ILIKE '%GRACE%' AND last_name ILIKE '%POE%')
               OR (first_name ILIKE '%GRACE%' AND last_name ILIKE '%POE%')
            LIMIT 1
        """)
        
        if not grace_poe:
            # Get next ID
            max_id = await conn.fetchval("SELECT MAX(id) FROM political_dynasties") or 0
            grace_poe_id = max_id + 1
            
            await conn.execute("""
                INSERT INTO political_dynasties 
                (id, first_name, last_name, position, year, party)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, grace_poe_id, 'GRACE', 'POE', 'SENATOR', 2025, 'INDEPENDENT')
            print(f"✅ Created Grace Poe (ID: {grace_poe_id})")
        else:
            grace_poe_id = grace_poe['id']
            print(f"✅ Found Grace Poe (ID: {grace_poe_id})")
        
        # Find or create Mark Patron (FPJ Partylist nominee)
        mark_patron = await conn.fetchrow("""
            SELECT id FROM political_dynasties 
            WHERE (first_name ILIKE '%MARK%' AND last_name ILIKE '%PATRON%')
            LIMIT 1
        """)
        
        if not mark_patron:
            max_id = await conn.fetchval("SELECT MAX(id) FROM political_dynasties") or 0
            mark_patron_id = max_id + 1
            
            await conn.execute("""
                INSERT INTO political_dynasties 
                (id, first_name, last_name, position, year, party, province, region)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """, mark_patron_id, 'MARK', 'PATRON', 'FPJ PARTYLIST NOMINEE', 2025, 'FPJ PARTYLIST', 'BATANGAS', 'REGION IV-A')
            print(f"✅ Created Mark Patron (ID: {mark_patron_id})")
        else:
            mark_patron_id = mark_patron['id']
            print(f"✅ Found Mark Patron (ID: {mark_patron_id})")
        
        # Find or create JV dela Rosa (staff of Grace Poe)
        jv_dela_rosa = await conn.fetchrow("""
            SELECT id FROM political_dynasties 
            WHERE (first_name ILIKE '%JV%' AND last_name ILIKE '%DELA ROSA%')
               OR (first_name ILIKE '%J%' AND last_name ILIKE '%DELA ROSA%')
            LIMIT 1
        """)
        
        if not jv_dela_rosa:
            max_id = await conn.fetchval("SELECT MAX(id) FROM political_dynasties") or 0
            jv_dela_rosa_id = max_id + 1
            
            await conn.execute("""
                INSERT INTO political_dynasties 
                (id, first_name, last_name, position, year)
                VALUES ($1, $2, $3, $4, $5)
            """, jv_dela_rosa_id, 'JV', 'DELA ROSA', 'STAFF', 2025)
            print(f"✅ Created JV dela Rosa (ID: {jv_dela_rosa_id})")
        else:
            jv_dela_rosa_id = jv_dela_rosa['id']
            print(f"✅ Found JV dela Rosa (ID: {jv_dela_rosa_id})")
        
        # Find other Patron family members (if any exist)
        patron_family = await conn.fetch("""
            SELECT id, first_name, last_name FROM political_dynasties 
            WHERE last_name ILIKE '%PATRON%'
            ORDER BY id
        """)
        
        patron_ids = [p['id'] for p in patron_family]
        print(f"✅ Found {len(patron_ids)} Patron family members: {[p['first_name'] + ' ' + p['last_name'] for p in patron_family]}")
        
        # Get relationship type IDs
        staff_type_id = None
        # Look for staff/assistant relationship type
        for ct in connection_types:
            desc = (ct['description'] or '').upper()
            if 'STAFF' in desc or 'ASSISTANT' in desc or 'AIDE' in desc:
                staff_type_id = ct['id']
                break
        
        if not staff_type_id:
            # Use a generic relationship or create one
            staff_type_id = await conn.fetchval("""
                SELECT id FROM connection_types WHERE code = 28 OR description ILIKE '%business partner%'
                LIMIT 1
            """) or patron_type_id
        
        business_partner_type_id = patron_type_id
        
        # Add relationships
        relationships_to_add = [
            # Grace Poe -> JV dela Rosa (staff relationship)
            (grace_poe_id, jv_dela_rosa_id, staff_type_id, 'Staff of Grace Poe'),
        ]
        
        # Add JV dela Rosa -> Patron family relationships
        for patron_id in patron_ids:
            relationships_to_add.append(
                (jv_dela_rosa_id, patron_id, business_partner_type_id, 
                 f'Communicates with Patron family member - V.R. PATRON BUILDERS & DEVELOPERS CORP.')
            )
        
        for person_id, related_id, rel_type, description in relationships_to_add:
            try:
                await conn.execute("""
                    INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (person_id, related_person_id, relationship_type) DO UPDATE
                    SET relationship_description = EXCLUDED.relationship_description
                """, person_id, related_id, rel_type, description)
                print(f"✅ Added relationship: {person_id} -> {related_id} ({description})")
            except Exception as e:
                print(f"⚠️ Relationship may already exist: {e}")
        
        # Add V.R. PATRON BUILDERS as a note/description in the relationship
        # Or create it as a separate entity if needed
        vr_patron_builders_note = await conn.fetchrow("""
            SELECT id FROM political_dynasties 
            WHERE last_name ILIKE '%PATRON%' AND position ILIKE '%BUILDER%'
            LIMIT 1
        """)
        
        print("\n📊 Relationship chain added:")
        print(f"  Grace Poe (ID: {grace_poe_id}) - Senator")
        print(f"    -> JV dela Rosa (ID: {jv_dela_rosa_id}) - Staff")
        for patron in patron_family:
            print(f"      -> {patron['first_name']} {patron['last_name']} (ID: {patron['id']}) - Patron family")
        print(f"        -> V.R. PATRON BUILDERS & DEVELOPERS CORP.")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(add_poe_patron_relationship())


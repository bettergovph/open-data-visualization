#!/usr/bin/env python3
"""Add missing relationships: MBB (Manuel Bonoan) -> Roberto Bernardo"""

import asyncio
import asyncpg

async def add_mbb_relationships():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # Find Manuel Bonoan (MBB) - use the one with more complete position info
        mbb = await conn.fetchrow('''
            SELECT id, first_name, last_name, position
            FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%MANUEL%' 
              AND UPPER(last_name) LIKE '%BONOAN%'
              AND (UPPER(position) LIKE '%DPWH%' OR UPPER(position) LIKE '%SECRETARY%')
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not mbb:
            print("❌ Manuel Bonoan not found")
            return
        
        print(f"✅ Found MBB: ID {mbb['id']} - {mbb['first_name']} {mbb['last_name']} ({mbb['position']})")
        
        # Find Roberto Bernardo
        bernardo = await conn.fetchrow('''
            SELECT id, first_name, last_name, position
            FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%ROBERTO%' 
              AND UPPER(last_name) LIKE '%BERNARDO%'
              AND (UPPER(position) LIKE '%DPWH%' OR UPPER(position) LIKE '%UNDERSECRETARY%')
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not bernardo:
            print("❌ Roberto Bernardo not found")
            return
        
        print(f"✅ Found Roberto Bernardo: ID {bernardo['id']} - {bernardo['first_name']} {bernardo['last_name']} ({bernardo['position']})")
        
        # Get business partner relationship type
        business_partner_type = await conn.fetchval('''
            SELECT id FROM connection_types WHERE name = 'Business Partner' LIMIT 1
        ''')
        
        if not business_partner_type:
            print("❌ Business Partner relationship type not found")
            return
        
        # Check if relationship already exists
        existing = await conn.fetchrow('''
            SELECT id FROM relationships
            WHERE person_id = $1 AND related_person_id = $2
              AND relationship_description ILIKE '%Bernardo%'
        ''', mbb['id'], bernardo['id'])
        
        if existing:
            print(f"✅ Relationship already exists (ID {existing['id']})")
        else:
            # Add relationship
            source_url = "https://newsinfo.inquirer.net/2140264/former-dpwh-official-links-more-senators-to-kickbacks"
            rel_id = await conn.fetchval('''
                INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description, source_url)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            ''', mbb['id'], bernardo['id'], business_partner_type,
                "Worked with Roberto Bernardo on DPWH project allocations", source_url)
            print(f"✅ Added relationship (ID {rel_id}): MBB -> Roberto Bernardo")
        
        # Also check if there's a relationship in the reverse direction
        existing_reverse = await conn.fetchrow('''
            SELECT id FROM relationships
            WHERE person_id = $1 AND related_person_id = $2
              AND relationship_description ILIKE '%Bonoan%'
        ''', bernardo['id'], mbb['id'])
        
        if existing_reverse:
            print(f"✅ Reverse relationship already exists (ID {existing_reverse['id']})")
        else:
            # The relationship is bidirectional, but we'll add it explicitly if needed
            print("ℹ️  Reverse relationship not found (may be handled by bidirectional flag)")
        
        print("\n✅ Done!")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(add_mbb_relationships())
























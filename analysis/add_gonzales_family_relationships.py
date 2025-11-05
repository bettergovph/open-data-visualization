#!/usr/bin/env python3
"""
Add family relationships for Aurelio Gonzales Jr. and his children
Connects them to A.D. Gonzales Jr. Construction and Trading Co., Inc.
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def add_gonzales_relationships():
    """Add family relationships and company connections for Gonzales family"""
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        print("🔍 Finding Aurelio Gonzales Jr. in database...")
        
        # Find Aurelio Gonzales Jr.
        aurelio = await conn.fetchrow('''
            SELECT id, first_name, last_name
            FROM political_dynasties
            WHERE UPPER(first_name) LIKE '%AURELIO%'
              AND UPPER(last_name) = 'GONZALES'
              AND UPPER(first_name) LIKE '%DUEÑAS%'
            LIMIT 1
        ''')
        
        if not aurelio:
            # Try alternative search
            aurelio = await conn.fetchrow('''
                SELECT id, first_name, last_name
                FROM political_dynasties
                WHERE UPPER(first_name) LIKE '%AURELIO%'
                  AND UPPER(last_name) = 'GONZALES'
                LIMIT 1
            ''')
        
        if not aurelio:
            print("❌ Aurelio Gonzales Jr. not found in database")
            return
        
        print(f"✅ Found: {aurelio['first_name']} {aurelio['last_name']} (ID: {aurelio['id']})")
        aurelio_id = aurelio['id']
        
        # Children to add
        children = [
            {
                'first_name': 'AURELIO BRENZ',
                'last_name': 'GONZALES',
                'position': 'Vice Mayor of San Fernando City',
                'role': 'President',
                'ownership': '60%'
            },
            {
                'first_name': 'AURELIO',
                'middle_name': 'M.',
                'last_name': 'GONZALES',
                'suffix': 'III',
                'position': 'Vice President',
                'role': 'Vice President',
                'ownership': '19%'
            },
            {
                'first_name': 'AURELIO MICHAELINE',
                'last_name': 'GONZALES',
                'position': 'Deputy Majority Leader, Congress',
                'role': 'Secretary-Treasurer',
                'ownership': '19%'
            }
        ]
        
        # Get relationship types
        father_type = await conn.fetchval('''
            SELECT id FROM connection_types WHERE UPPER(name) = 'FATHER'
        ''')
        son_type = await conn.fetchval('''
            SELECT id FROM connection_types WHERE UPPER(name) = 'SON'
        ''')
        daughter_type = await conn.fetchval('''
            SELECT id FROM connection_types WHERE UPPER(name) = 'DAUGHTER'
        ''')
        
        company_name = 'A.D. GONZALES JR. CONSTRUCTION & TRADING CO. INC.'
        
        for child in children:
            print(f"\n🔍 Processing {child['first_name']} {child.get('middle_name', '')} {child['last_name']} {child.get('suffix', '')}")
            
            # Find or create child in political_dynasties
            child_query = '''
                SELECT id, first_name, last_name
                FROM political_dynasties
                WHERE UPPER(first_name) = $1
                  AND UPPER(last_name) = $2
            '''
            
            if child.get('middle_name'):
                child_query = '''
                    SELECT id, first_name, middle_name, last_name
                    FROM political_dynasties
                    WHERE UPPER(first_name) = $1
                      AND UPPER(middle_name) = $2
                      AND UPPER(last_name) = $3
                '''
                child_record = await conn.fetchrow(
                    child_query,
                    child['first_name'],
                    child['middle_name'],
                    child['last_name']
                )
            else:
                child_record = await conn.fetchrow(
                    child_query,
                    child['first_name'],
                    child['last_name']
                )
            
            if not child_record:
                # Create new entry
                insert_query = '''
                    INSERT INTO political_dynasties (
                        first_name, middle_name, last_name, suffix,
                        position, province, municipality_city, party
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    RETURNING id, first_name, last_name
                '''
                child_record = await conn.fetchrow(
                    insert_query,
                    child['first_name'],
                    child.get('middle_name'),
                    child['last_name'],
                    child.get('suffix'),
                    child['position'],
                    'Pampanga',
                    'San Fernando City',
                    None
                )
                print(f"  ✅ Created new entry (ID: {child_record['id']})")
            else:
                print(f"  ✅ Found existing entry (ID: {child_record['id']})")
            
            child_id = child_record['id']
            
            # Determine relationship type (son or daughter)
            is_daughter = 'MICHAELINE' in child['first_name'].upper()
            relationship_type = daughter_type if is_daughter else son_type
            relationship_name = 'Daughter' if is_daughter else 'Son'
            
            # Add father-child relationship (both directions)
            # Father -> Child
            await conn.execute('''
                INSERT INTO relationships (
                    person_id, related_person_id, relationship_type, relationship_description
                )
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (person_id, related_person_id, relationship_type) DO NOTHING
            ''', aurelio_id, child_id, father_type, f'Father of {child_record["first_name"]} {child_record["last_name"]}')
            
            # Child -> Father
            await conn.execute('''
                INSERT INTO relationships (
                    person_id, related_person_id, relationship_type, relationship_description
                )
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (person_id, related_person_id, relationship_type) DO NOTHING
            ''', child_id, aurelio_id, relationship_type, f'{relationship_name} of {aurelio["first_name"]} {aurelio["last_name"]}')
            
            print(f"  ✅ Added {relationship_name} relationship")
            
            # Add company connection
            # Check if company connection already exists
            existing = await conn.fetchrow('''
                SELECT id FROM contractor_dynasty_matches
                WHERE dynasty_first_name = $1
                  AND dynasty_last_name = $2
                  AND company_name = $3
            ''', child_record['first_name'], child_record['last_name'], company_name)
            
            if not existing:
                full_name = f"{child_record['first_name']} {child_record['last_name']}"
                await conn.execute('''
                    INSERT INTO contractor_dynasty_matches (
                        dynasty_full_name, dynasty_first_name, dynasty_last_name,
                        company_name, role, person_name
                    )
                    VALUES ($1, $2, $3, $4, $5, $6)
                ''', 
                full_name,
                child_record['first_name'],
                child_record['last_name'],
                company_name,
                f"{child['role']} ({child['ownership']} owner)",
                full_name
                )
                print(f"  ✅ Added company connection: {child['role']} ({child['ownership']})")
            else:
                print(f"  ℹ️  Company connection already exists")
        
        print("\n✅ All relationships and company connections added successfully!")
        print(f"   Company: {company_name}")
        print(f"   Connected through: 3 children (Aurelio Brenz, Aurelio M. III, Aurelio Michaeline)")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(add_gonzales_relationships())


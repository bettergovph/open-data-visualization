#!/usr/bin/env python3
"""Add Duterte family relationships from database/duterte.csv:
- Rodrigo Duterte (Patriarch) -> Sara Duterte (Daughter)
- Rodrigo Duterte (Patriarch) -> Paolo Duterte (Son)
- Rodrigo Duterte (Patriarch) -> Sebastian Duterte (Son)
- Rodrigo Duterte (Patriarch) -> Honeylet Avanceña (Partner)
- Rodrigo Duterte (Patriarch) -> Elizabeth Zimmerman (Former wife)
- Paolo Duterte -> Paolo Duterte Jr. (Son/Grandchild)
"""

import asyncio
import asyncpg
import os
import csv
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

async def add_duterte_family_relationships():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    try:
        # Read CSV file
        csv_path = Path(__file__).parent.parent.parent / 'database' / 'duterte.csv'
        if not csv_path.exists():
            print(f"❌ CSV file not found: {csv_path}")
            return
        
        print(f"📖 Reading {csv_path}...")
        relationships_data = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('Name') and row.get('Relationship'):
                    relationships_data.append(row)
        
        print(f"📊 Found {len(relationships_data)} relationships to process")
        
        # Get relationship types
        father_type = await conn.fetchval("SELECT id FROM connection_types WHERE name = 'Father' LIMIT 1")
        daughter_type = await conn.fetchval("SELECT id FROM connection_types WHERE name = 'Daughter' LIMIT 1")
        son_type = await conn.fetchval("SELECT id FROM connection_types WHERE name = 'Son' LIMIT 1")
        wife_type = await conn.fetchval("SELECT id FROM connection_types WHERE name = 'Wife' LIMIT 1")
        husband_type = await conn.fetchval("SELECT id FROM connection_types WHERE name = 'Husband' LIMIT 1")
        grandson_type = await conn.fetchval("SELECT id FROM connection_types WHERE name = 'Grandson' LIMIT 1")
        grandfather_type = await conn.fetchval("SELECT id FROM connection_types WHERE name = 'Grandfather' LIMIT 1")
        
        if not all([father_type, daughter_type, son_type, wife_type, husband_type]):
            print("❌ Relationship types not found")
            return
        
        # Find or create Rodrigo Duterte (Patriarch)
        rodrigo = await conn.fetchrow('''
            SELECT id, first_name, last_name, position FROM political_dynasties
            WHERE (UPPER(first_name) LIKE '%RODRIGO%' OR UPPER(first_name) LIKE '%ROD%')
              AND UPPER(last_name) LIKE '%DUTERTE%'
              AND (UPPER(position) LIKE '%PRESIDENT%' OR UPPER(position) LIKE '%MAYOR%')
            ORDER BY id DESC
            LIMIT 1
        ''')
        
        if not rodrigo:
            # Create Rodrigo Duterte if not found
            rodrigo_id = await conn.fetchval('''
                INSERT INTO political_dynasties (first_name, last_name, position, province)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            ''', "RODRIGO", "DUTERTE", "FORMER PRESIDENT OF THE PHILIPPINES", "DAVAO DEL SUR")
            rodrigo = {'id': rodrigo_id, 'first_name': 'RODRIGO', 'last_name': 'DUTERTE', 'position': 'FORMER PRESIDENT'}
            print(f"✅ Created Rodrigo Duterte: ID {rodrigo_id}")
        else:
            print(f"✅ Found Rodrigo Duterte: ID {rodrigo['id']} - {rodrigo['first_name']} {rodrigo['last_name']} ({rodrigo['position']})")
        
        # Process relationships
        for row in relationships_data:
            name = row['Name'].strip()
            relationship = row['Relationship'].strip()
            role_notes = row.get('Role/Notes', '').strip()
            url = row.get('URL', '').strip()
            
            if name == 'Rodrigo Duterte':
                continue  # Skip the patriarch itself
            
            print(f"\n📋 Processing: {name} ({relationship})")
            
            # Find or create the person
            name_parts = name.split()
            if len(name_parts) >= 2:
                first_name = name_parts[0]
                last_name = ' '.join(name_parts[1:])
            else:
                first_name = name
                last_name = ''
            
            person = await conn.fetchrow('''
                SELECT id, first_name, last_name FROM political_dynasties
                WHERE UPPER(first_name) LIKE $1
                  AND UPPER(last_name) LIKE $2
                ORDER BY id DESC
                LIMIT 1
            ''', f'%{first_name.upper()}%', f'%{last_name.upper()}%')
            
            if not person:
                # Create person if not found
                person_id = await conn.fetchval('''
                    INSERT INTO political_dynasties (first_name, last_name, position, province)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id
                ''', first_name.upper(), last_name.upper(), role_notes.upper() if role_notes else None, "DAVAO DEL SUR")
                person = {'id': person_id, 'first_name': first_name.upper(), 'last_name': last_name.upper()}
                print(f"  ✅ Created {name}: ID {person_id}")
            else:
                print(f"  ✅ Found {name}: ID {person['id']}")
            
            # Determine relationship type and direction
            rel_type = None
            reverse_rel_type = None
            description = f"{relationship}: {role_notes}" if role_notes else relationship
            
            if relationship == 'Daughter':
                rel_type = daughter_type
                reverse_rel_type = father_type
            elif relationship == 'Son':
                rel_type = son_type
                reverse_rel_type = father_type
            elif relationship == 'Partner of Rodrigo Duterte':
                # Use wife/husband relationship
                rel_type = wife_type
                reverse_rel_type = husband_type
                description = f"Partner: {role_notes}"
            elif relationship == 'Former wife of Rodrigo Duterte':
                # Use wife/husband relationship (former)
                rel_type = wife_type
                reverse_rel_type = husband_type
                description = f"Former wife: {role_notes}"
            elif relationship == 'Grandchild':
                # This is Paolo Duterte Jr., son of Paolo Duterte
                # We need to find Paolo Duterte first
                paolo = await conn.fetchrow('''
                    SELECT id FROM political_dynasties
                    WHERE UPPER(first_name) LIKE '%PAOLO%'
                      AND UPPER(last_name) LIKE '%DUTERTE%'
                    ORDER BY id DESC
                    LIMIT 1
                ''')
                if paolo:
                    # Paolo Duterte -> Paolo Duterte Jr. (son)
                    rel_type = son_type
                    reverse_rel_type = father_type
                    # Add relationship: Paolo -> Paolo Jr.
                    existing = await conn.fetchrow('''
                        SELECT id FROM relationships
                        WHERE person_id = $1 AND related_person_id = $2
                          AND relationship_type = $3
                    ''', paolo['id'], person['id'], rel_type)
                    
                    if not existing:
                        await conn.execute('''
                            INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description, source_url)
                            VALUES ($1, $2, $3, $4, $5)
                        ''', paolo['id'], person['id'], rel_type, description, url if url and url != 'Not widely documented' else None)
                        print(f"  ✅ Added relationship: Paolo Duterte -> {name} (son)")
                    
                    # Add reverse: Paolo Jr. -> Paolo (father)
                    existing_reverse = await conn.fetchrow('''
                        SELECT id FROM relationships
                        WHERE person_id = $1 AND related_person_id = $2
                          AND relationship_type = $3
                    ''', person['id'], paolo['id'], reverse_rel_type)
                    
                    if not existing_reverse:
                        await conn.execute('''
                            INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description, source_url)
                            VALUES ($1, $2, $3, $4, $5)
                        ''', person['id'], paolo['id'], reverse_rel_type, f"Father: {role_notes}" if role_notes else "Father", url if url and url != 'Not widely documented' else None)
                        print(f"  ✅ Added reverse relationship: {name} -> Paolo Duterte (father)")
                    
                    continue  # Skip adding to Rodrigo for grandchild
            
            if rel_type and relationship != 'Grandchild':
                # Add relationship: Rodrigo -> Person
                existing = await conn.fetchrow('''
                    SELECT id FROM relationships
                    WHERE person_id = $1 AND related_person_id = $2
                      AND relationship_type = $3
                ''', rodrigo['id'], person['id'], rel_type)
                
                if not existing:
                    await conn.execute('''
                        INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description, source_url)
                        VALUES ($1, $2, $3, $4, $5)
                    ''', rodrigo['id'], person['id'], rel_type, description, url if url and url != 'Not widely documented' else None)
                    print(f"  ✅ Added relationship: Rodrigo Duterte -> {name} ({relationship})")
                else:
                    print(f"  ✅ Relationship already exists: Rodrigo Duterte -> {name}")
                
                # Add reverse relationship
                if reverse_rel_type:
                    existing_reverse = await conn.fetchrow('''
                        SELECT id FROM relationships
                        WHERE person_id = $1 AND related_person_id = $2
                          AND relationship_type = $3
                    ''', person['id'], rodrigo['id'], reverse_rel_type)
                    
                    if not existing_reverse:
                        reverse_description = "Father" if relationship in ['Daughter', 'Son'] else ("Husband" if relationship == 'Partner of Rodrigo Duterte' else "Former husband")
                        await conn.execute('''
                            INSERT INTO relationships (person_id, related_person_id, relationship_type, relationship_description, source_url)
                            VALUES ($1, $2, $3, $4, $5)
                        ''', person['id'], rodrigo['id'], reverse_rel_type, reverse_description, url if url and url != 'Not widely documented' else None)
                        print(f"  ✅ Added reverse relationship: {name} -> Rodrigo Duterte ({reverse_description})")
        
        print("\n✅ Done! Duterte family relationships added")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(add_duterte_family_relationships())











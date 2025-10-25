#!/usr/bin/env python3
"""
Test UY family relationships
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def test_uy_relationships():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DYNASTY_SEC', 'dynasty')
    )
    
    # Get UY family member IDs
    uy_members = await conn.fetch("""
        SELECT id, first_name, last_name 
        FROM political_dynasties 
        WHERE last_name = 'UY' AND province = 'SAMAR'
    """)
    
    print('UY family members:')
    uy_ids = []
    for member in uy_members:
        print(f'  {member["id"]}: {member["first_name"]} {member["last_name"]}')
        uy_ids.append(member['id'])
    
    if not uy_ids:
        print("No UY family members found!")
        await conn.close()
        return
    
    # Check relationships for UY family
    relationships = await conn.fetch("""
        SELECT 
            p1.first_name || ' ' || p1.last_name as person,
            p2.first_name || ' ' || p2.last_name as related_person,
            ct.description as relationship,
            r.relationship_description
        FROM relationships r
        JOIN political_dynasties p1 ON r.person_id = p1.id
        JOIN political_dynasties p2 ON r.related_person_id = p2.id
        JOIN connection_types ct ON r.relationship_type = ct.id
        WHERE p1.id = ANY($1) OR p2.id = ANY($1)
        ORDER BY p1.first_name, p1.last_name
    """, uy_ids)
    
    print('\nRelationships for UY family:')
    for rel in relationships:
        print(f'  {rel["person"]} -> {rel["related_person"]} ({rel["relationship"]})')
    
    # Test the API query directly
    print('\nTesting API query logic:')
    connected_query = """
        WITH RECURSIVE connected_people AS (
            -- Base case: people directly connected to family members via relationships table
            SELECT DISTINCT
                p.id,
                p.first_name,
                p.last_name,
                p.position,
                p.province,
                p.municipality_city,
                p.year,
                p.fat,
                r.relationship_description as connection,
                r.relationship_type,
                r.related_person_id as connection_id,
                p.nickname,
                1 as level
            FROM political_dynasties p
            JOIN relationships r ON p.id = r.person_id
            WHERE r.related_person_id = ANY($1)
        )
        SELECT DISTINCT
            id,
            first_name,
            last_name,
            position,
            province,
            municipality_city,
            year,
            fat,
            connection,
            relationship_type,
            connection_id,
            nickname
        FROM connected_people
        WHERE CONCAT(first_name, ' ', last_name) NOT IN (
            SELECT CONCAT(first_name, ' ', last_name) 
            FROM political_dynasties 
            WHERE last_name = $2 AND province = $3
        )
        ORDER BY year DESC, first_name
    """
    
    connected_results = await conn.fetch(connected_query, uy_ids, 'UY', 'SAMAR')
    
    print(f'\nConnected people found: {len(connected_results)}')
    for person in connected_results:
        print(f'  {person["first_name"]} {person["last_name"]} - {person["connection"]}')
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(test_uy_relationships())

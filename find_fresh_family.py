#!/usr/bin/env python3
"""
Find Fresh Family Names (Excluding TAN and UY)
"""

import asyncio
import asyncpg

async def find_fresh_family():
    conn = await asyncpg.connect(
        host='localhost',
        port='5432',
        user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu',
        database='dynasty'
    )
    
    print('🔍 FINDING FRESH FAMILY NAMES (EXCLUDING TAN AND UY)')
    print('=' * 60)
    
    # Find families with multiple members, excluding TAN and UY
    families = await conn.fetch('''
        SELECT 
            last_name,
            province,
            COUNT(*) as member_count,
            STRING_AGG(DISTINCT position, ', ') as positions,
            STRING_AGG(DISTINCT first_name, ', ') as first_names
        FROM political_dynasties 
        WHERE year = 2025 
        AND last_name IS NOT NULL
        AND last_name NOT IN ('TAN', 'UY')
        GROUP BY last_name, province
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC
        LIMIT 15
    ''')
    
    print('📊 TOP FAMILIES (EXCLUDING TAN & UY):')
    for i, family in enumerate(families, 1):
        print(f'{i:>2}. {family["last_name"]} ({family["province"]}) - {family["member_count"]} members')
        print(f'    Names: {family["first_names"]}')
        print(f'    Positions: {family["positions"]}')
        print()
    
    # Pick a good family with relationships
    if families:
        selected_family = families[0]
        print(f'🎯 SELECTED FAMILY: {selected_family["last_name"]} from {selected_family["province"]}')
        print(f'   Members: {selected_family["member_count"]}')
        
        # Check for relationships for this family
        relationships = await conn.fetch('''
            SELECT 
                r.relationship_type,
                ct.name as relationship_name,
                pd1.first_name || ' ' || pd1.last_name as person1,
                pd1.province as province1,
                pd2.first_name || ' ' || pd2.last_name as person2,
                pd2.province as province2,
                r.relationship_description,
                r.confidence_level,
                r.source_url
            FROM relationships r
            JOIN political_dynasties pd1 ON r.person_id = pd1.id
            JOIN political_dynasties pd2 ON r.related_person_id = pd2.id
            JOIN connection_types ct ON r.relationship_type = ct.code
            WHERE (pd1.last_name = $1 OR pd2.last_name = $1)
            ORDER BY r.confidence_level DESC
        ''', selected_family['last_name'])
        
        print(f'\n🔗 FAMILY RELATIONSHIPS:')
        if relationships:
            for rel in relationships:
                print(f'   - {rel["person1"]} ({rel["province1"]}) is {rel["relationship_name"]} of {rel["person2"]} ({rel["province2"]})')
                if rel['relationship_description']:
                    print(f'     Description: {rel["relationship_description"]}')
                print(f'     Confidence: {rel["confidence_level"]}/10')
                if rel['source_url']:
                    print(f'     Source: {rel["source_url"]}')
                print()
        else:
            print('   No relationships found in database')
        
        await conn.close()
        
        # Generate family link
        family_surname = selected_family['last_name']
        family_province = selected_family['province']
        
        print(f'\n🔗 FAMILY LINK:')
        print(f'http://localhost:8001/family?surname={family_surname}&province={family_province}')
        print(f'\nOr without province filter:')
        print(f'http://localhost:8001/family?surname={family_surname}')
        
        return family_surname, family_province
    else:
        print('❌ No families found')
        await conn.close()
        return None, None

if __name__ == "__main__":
    asyncio.run(find_fresh_family())

#!/usr/bin/env python3
"""
Find High Member Family for Verification
"""

import asyncio
import asyncpg

async def find_high_member_family():
    conn = await asyncpg.connect(
        host='localhost',
        port='5432',
        user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu',
        database='dynasty'
    )
    
    print('🔍 FINDING FAMILIES WITH HIGH MEMBER COUNT')
    print('=' * 60)
    
    # Find families with most members
    families = await conn.fetch('''
        SELECT 
            last_name,
            province,
            COUNT(*) as member_count,
            STRING_AGG(DISTINCT position, ', ') as positions
        FROM political_dynasties 
        WHERE year = 2025 AND last_name IS NOT NULL
        GROUP BY last_name, province
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC
        LIMIT 10
    ''')
    
    print('📊 Top 10 Families by Member Count:')
    for i, family in enumerate(families, 1):
        print(f'{i:>2}. {family["last_name"]} ({family["province"]}) - {family["member_count"]} members')
        print(f'    Positions: {family["positions"]}')
        print()
    
    # Pick the top family
    if families:
        top_family = families[0]
        print(f'🎯 SELECTED FAMILY: {top_family["last_name"]} from {top_family["province"]}')
        print(f'   Members: {top_family["member_count"]}')
        print(f'   Positions: {top_family["positions"]}')
        
        # Get family members details
        members = await conn.fetch('''
            SELECT 
                first_name,
                last_name,
                position,
                government_branch,
                appointment_type
            FROM political_dynasties 
            WHERE last_name = $1 AND province = $2 AND year = 2025
            ORDER BY position, first_name
        ''', top_family['last_name'], top_family['province'])
        
        print(f'\n👥 FAMILY MEMBERS:')
        for member in members:
            print(f'   - {member["first_name"]} {member["last_name"]} ({member["position"]})')
            if member['government_branch']:
                print(f'     Branch: {member["government_branch"]} ({member["appointment_type"]})')
        
        # Check relationships for this family
        relationships = await conn.fetch('''
            SELECT 
                r.relationship_type,
                ct.name as relationship_name,
                pd1.first_name || ' ' || pd1.last_name as person1,
                pd2.first_name || ' ' || pd2.last_name as person2,
                r.relationship_description,
                r.confidence_level
            FROM relationships r
            JOIN political_dynasties pd1 ON r.person_id = pd1.id
            JOIN political_dynasties pd2 ON r.related_person_id = pd2.id
            JOIN connection_types ct ON r.relationship_type = ct.code
            WHERE (pd1.last_name = $1 OR pd2.last_name = $1)
            AND (pd1.province = $2 OR pd2.province = $2)
            ORDER BY r.confidence_level DESC, ct.name
        ''', top_family['last_name'], top_family['province'])
        
        print(f'\n🔗 FAMILY RELATIONSHIPS:')
        if relationships:
            for rel in relationships:
                print(f'   - {rel["person1"]} is {rel["relationship_name"]} of {rel["person2"]}')
                if rel['relationship_description']:
                    print(f'     Description: {rel["relationship_description"]}')
                print(f'     Confidence: {rel["confidence_level"]}/10')
                print()
        else:
            print('   No relationships found in database')
        
        await conn.close()
        
        # Generate family link
        family_surname = top_family['last_name']
        family_province = top_family['province']
        
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
    asyncio.run(find_high_member_family())

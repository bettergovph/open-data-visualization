#!/usr/bin/env python3
"""Normalize Villar entries (Camille and Mark) to have same names"""

import asyncio
import asyncpg

async def normalize_villar():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # Find all Villar entries for Camille and Mark
        entries = await conn.fetch('''
            SELECT id, first_name, middle_name, last_name, position, year, unified_person_id
            FROM political_dynasties
            WHERE UPPER(last_name) = 'VILLAR'
              AND (UPPER(first_name) LIKE '%CAMILLE%' OR UPPER(first_name) LIKE '%MARK%')
            ORDER BY first_name, id
        ''')
        
        # Group by normalized first+last (ignoring middle name variations)
        # Extract just the first word of first_name to handle "CAMILLE" vs "CAMILLE A."
        groups = {}
        for e in entries:
            first_name_parts = e["first_name"].strip().upper().split()
            # Use first word of first name + last name as key
            base_first = first_name_parts[0] if first_name_parts else ""
            key = f'{base_first} {e["last_name"].strip().upper()}'
            if key not in groups:
                groups[key] = []
            groups[key].append(e)
        
        for key, group in groups.items():
            if len(group) > 1:
                print(f'\n{key}: {len(group)} entries')
                # Use lowest ID as canonical
                group.sort(key=lambda x: x['id'])
                canonical_id = group[0]['id']
                # Use the first word of first name (without middle initial fragments)
                canonical_first_parts = group[0]['first_name'].strip().upper().split()
                canonical_first = canonical_first_parts[0] if canonical_first_parts else group[0]['first_name'].strip().upper()
                canonical_last = group[0]['last_name'].strip().upper()
                canonical_middle = None  # Remove middle name fragments
                
                for entry in group:
                    old = f'{entry["first_name"]} {entry["middle_name"] or ""} {entry["last_name"]}'
                    await conn.execute('''
                        UPDATE political_dynasties
                        SET first_name = $1, middle_name = $2, last_name = $3, unified_person_id = $4
                        WHERE id = $5
                    ''', canonical_first, canonical_middle, canonical_last, canonical_id, entry['id'])
                    new = f'{canonical_first} {canonical_middle or ""} {canonical_last}'
                    print(f'  ID {entry["id"]}: "{old}" -> "{new}" ({entry["position"]}, {entry["year"]})')
        
        print('\n✅ Done!')
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(normalize_villar())


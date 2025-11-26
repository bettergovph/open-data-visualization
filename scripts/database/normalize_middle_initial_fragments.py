#!/usr/bin/env python3
"""Normalize names with middle initial fragments like 'A. A.' and identify duplicates as same person"""

import asyncio
import asyncpg
import re

async def normalize_middle_initial_fragments():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        # Pattern to match middle initial fragments like "A. A.", "A.", "B. B.", etc.
        fragment_pattern = re.compile(r'\b([A-Z])\.\s*([A-Z])\.\s*([A-Z])\.\s*|\b([A-Z])\.\s*([A-Z])\.\s*|\b([A-Z])\.\s*', re.IGNORECASE)
        
        # Find entries that need normalization:
        # 1. Entries with middle name fragments (A., A. A., etc.)
        # 2. Entries with same first+last name but different middle names
        # This will find "CAMILLE VILLAR" and "CAMILLE A. VILLAR" as the same person
        entries_with_fragments = await conn.fetch('''
            SELECT id, first_name, middle_name, last_name, position, year, unified_person_id
            FROM political_dynasties
            WHERE first_name IS NOT NULL
              AND last_name IS NOT NULL
              AND first_name != ''
              AND last_name != ''
              AND (
                -- Has middle name fragments
                (middle_name IS NOT NULL AND middle_name != '' AND (
                  middle_name ~* '^[A-Z]\.\s*([A-Z]\.\s*)*$' OR
                  middle_name ~* '^[A-Z]\.\s*[A-Z]\.\s*$'
                ))
                OR
                -- Has middle name (to check for duplicates)
                middle_name IS NOT NULL
              )
            ORDER BY UPPER(last_name), UPPER(first_name), id
        ''')
        
        # Also get entries without middle names that might match
        entries_without_middle = await conn.fetch('''
            SELECT id, first_name, middle_name, last_name, position, year, unified_person_id
            FROM political_dynasties
            WHERE first_name IS NOT NULL
              AND last_name IS NOT NULL
              AND first_name != ''
              AND last_name != ''
              AND (middle_name IS NULL OR middle_name = '')
            ORDER BY UPPER(last_name), UPPER(first_name), id
        ''')
        
        print(f'🔍 Found {len(entries_with_fragments)} entries with middle names and {len(entries_without_middle)} without middle names')
        
        # Combine and process
        all_entries = list(entries_with_fragments) + list(entries_without_middle)
        print(f'🔍 Processing {len(all_entries)} entries to find duplicates...')
        
        # Group by normalized name (first + last, ignoring middle fragments)
        normalized_groups = {}
        
        for entry in all_entries:
            first_name = (entry['first_name'] or '').strip().upper()
            middle_name = (entry['middle_name'] or '').strip() if entry['middle_name'] else ''
            last_name = (entry['last_name'] or '').strip().upper()
            
            if not first_name or not last_name:
                continue
            
            # Normalize middle name by removing fragments
            normalized_middle = None
            if middle_name:
                # Check if it's just a fragment pattern
                if re.match(r'^[A-Z]\.\s*([A-Z]\.\s*)*$', middle_name, re.IGNORECASE):
                    # It's just fragments, remove it
                    normalized_middle = None
                else:
                    # Remove fragment patterns but keep real middle names
                    normalized_middle = fragment_pattern.sub('', middle_name).strip()
                    if not normalized_middle:
                        normalized_middle = None
            
            # Create normalized key (first word of first name + last name, ignoring middle name variations)
            # This handles "CAMILLE" vs "CAMILLE A." as the same person
            first_name_parts = first_name.split()
            base_first = first_name_parts[0] if first_name_parts else first_name
            normalized_key = f"{base_first} {last_name}"
            
            if normalized_key not in normalized_groups:
                normalized_groups[normalized_key] = []
            
            normalized_groups[normalized_key].append({
                'id': entry['id'],
                'first_name': entry['first_name'],
                'middle_name': entry['middle_name'],
                'normalized_middle': normalized_middle,
                'last_name': entry['last_name'],
                'position': entry['position'],
                'year': entry['year'],
                'unified_person_id': entry['unified_person_id']
            })
        
        # Process groups with multiple entries (normalize names to be exactly the same, preserve all positions)
        unified_count = 0
        normalized_count = 0
        
        for normalized_key, group in normalized_groups.items():
            if len(group) > 1:
                # Multiple entries with same normalized name - normalize all to exact same name
                print(f'\n📋 Found {len(group)} entries for: {normalized_key} (same person, different positions/times)')
                
                # Sort by ID to use the lowest ID as the unified_person_id and canonical name
                group.sort(key=lambda x: x['id'])
                canonical_entry = group[0]
                canonical_id = canonical_entry['id']
                
                # Determine canonical name (use first word of first name, no middle fragments)
                # Extract just the first word to handle "CAMILLE" vs "CAMILLE A."
                canonical_first_parts = canonical_entry['first_name'].strip().upper().split()
                canonical_first = canonical_first_parts[0] if canonical_first_parts else canonical_entry['first_name'].strip().upper()
                canonical_last = canonical_entry['last_name'].strip().upper()
                canonical_middle = None  # Remove all middle name fragments
                
                print(f'  ✅ Using canonical name: {canonical_first} {canonical_middle or ""} {canonical_last} (unified_person_id: {canonical_id})')
                
                # Normalize all entries to have the exact same name (for self-connection)
                for entry in group:
                    old_name = f'{entry["first_name"]} {entry["middle_name"] or ""} {entry["last_name"]}'.strip()
                    new_name = f'{canonical_first} {canonical_middle or ""} {canonical_last}'.strip()
                    
                    print(f'  🔗 Normalizing: ID {entry["id"]} - "{old_name}" -> "{new_name}" ({entry["position"]}, {entry["year"]})')
                    
                    # Update to canonical name (exact same for all entries)
                    await conn.execute('''
                        UPDATE political_dynasties
                        SET first_name = $1,
                            middle_name = $2,
                            last_name = $3,
                            unified_person_id = $4
                        WHERE id = $5
                    ''', canonical_first, canonical_middle, canonical_last, canonical_id, entry['id'])
                    
                    unified_count += 1
                    normalized_count += 1
            else:
                # Single entry - just normalize the middle name (remove fragments)
                entry = group[0]
                if entry['normalized_middle'] != entry['middle_name']:
                    old_name = f'{entry["first_name"]} {entry["middle_name"] or ""} {entry["last_name"]}'.strip()
                    
                    if entry['normalized_middle']:
                        await conn.execute('''
                            UPDATE political_dynasties
                            SET middle_name = $1
                            WHERE id = $2
                        ''', entry['normalized_middle'], entry['id'])
                        new_name = f'{entry["first_name"]} {entry["normalized_middle"]} {entry["last_name"]}'.strip()
                        print(f'  ✏️  Normalized: ID {entry["id"]} - "{old_name}" -> "{new_name}"')
                    else:
                        await conn.execute('''
                            UPDATE political_dynasties
                            SET middle_name = NULL
                            WHERE id = $1
                        ''', entry['id'])
                        new_name = f'{entry["first_name"]} {entry["last_name"]}'.strip()
                        print(f'  ✏️  Removed fragment: ID {entry["id"]} - "{old_name}" -> "{new_name}"')
                    normalized_count += 1
        
        print(f'\n✅ Summary:')
        print(f'  - Unified {unified_count} entries as same person (preserved all positions over time)')
        print(f'  - Normalized {normalized_count} entries (removed middle name fragments)')
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(normalize_middle_initial_fragments())


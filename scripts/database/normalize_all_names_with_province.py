#!/usr/bin/env python3
"""
Normalize all names in the database, handling nicknames, suffixes, and name variations
Grouping by canonical name components AND province to avoid merging unrelated people

This script:
1. Parses names into: first_name, nickname, middle_name, last_name, suffix
2. Handles variations like:
   - "Ferdinand 'Bongbong' R. Marcos Jr." -> first: FERDINAND, nickname: BONGBONG, middle: R, last: MARCOS, suffix: JR
   - "Bongbong Marcos" -> matches to canonical "FERDINAND BONGBONG R. MARCOS JR"
   - "Ferdinand Jr. Marcos" -> extracts suffix and matches
3. Groups by: (canonical_first, canonical_last, province) - using most complete entry as canonical
4. Normalizes all entries in group to canonical form
5. Sets unified_person_id to link same person across different positions/times
6. Preserves all historical positions
"""

import asyncio
import asyncpg
import re
from collections import defaultdict
from typing import Dict, Optional, Tuple

def parse_name_components(first_name: str, middle_name: Optional[str], last_name: str, 
                          nickname: Optional[str], suffix: Optional[str]) -> Dict[str, Optional[str]]:
    """
    Parse name into canonical components: first, nickname, middle, last, suffix
    Handles variations like:
    - "Ferdinand 'Bongbong' R. Marcos Jr."
    - "Bongbong Marcos" 
    - "Ferdinand Jr. Marcos"
    """
    # Normalize inputs
    first = (first_name or '').strip().upper()
    middle = (middle_name or '').strip().upper() if middle_name else ''
    last = (last_name or '').strip().upper()
    nick = (nickname or '').strip().upper() if nickname else ''
    suff = (suffix or '').strip().upper() if suffix else ''
    
    # Extract suffix from first_name or last_name if not in suffix field
    # Patterns: "FERDINAND JR", "MARCOS JR", "FERDINAND JR.", etc.
    suffix_patterns = [
        r'\b(JR\.?|SR\.?|II|III|IV|V)\s*$',
        r'\b(JUNIOR|SENIOR)\s*$'
    ]
    
    # Check first_name for suffix
    for pattern in suffix_patterns:
        match = re.search(pattern, first, re.IGNORECASE)
        if match:
            suff = match.group(1).replace('.', '').upper()
            first = re.sub(pattern, '', first, flags=re.IGNORECASE).strip()
            break
    
    # Check last_name for suffix
    if not suff:
        for pattern in suffix_patterns:
            match = re.search(pattern, last, re.IGNORECASE)
            if match:
                suff = match.group(1).replace('.', '').upper()
                last = re.sub(pattern, '', last, flags=re.IGNORECASE).strip()
                break
    
    # Extract nickname from first_name (quotes, parentheses, or common patterns)
    # Patterns: "FERDINAND 'BONGBONG'", "FERDINAND (BONGBONG)", "BONGBONG" (if short)
    if not nick:
        # Check for quotes or parentheses in first_name
        quote_patterns = [
            r"['\"]([^'\"]+)['\"]",  # 'Bongbong' or "Bongbong"
            r'\(([^)]+)\)',  # (Bongbong)
        ]
        
        for pattern in quote_patterns:
            match = re.search(pattern, first)
            if match:
                potential_nick = match.group(1).strip().upper()
                # Validate it's a reasonable nickname (not too long, not a suffix)
                if 2 <= len(potential_nick) <= 20 and potential_nick not in ['JR', 'SR', 'II', 'III', 'IV', 'V']:
                    nick = potential_nick
                    first = re.sub(pattern, '', first).strip()
                    break
        
        # If first_name is short and looks like a nickname, it might be the nickname
        # But we need to be careful - only if it's a single word and short
        if not nick and len(first.split()) == 1 and 2 <= len(first) <= 15:
            # This could be a nickname, but we'll keep it as first_name for now
            # The matching logic will handle it
            pass
    
    # Extract middle initial/name
    # Remove fragment patterns like "A.", "A. A.", etc.
    fragment_pattern = re.compile(r'\b([A-Z])\.\s*([A-Z])\.\s*([A-Z])\.\s*|\b([A-Z])\.\s*([A-Z])\.\s*|\b([A-Z])\.\s*', re.IGNORECASE)
    if middle:
        # Check if it's just fragments
        if re.match(r'^[A-Z]\.\s*([A-Z]\.\s*)*$', middle, re.IGNORECASE):
            middle = None
        else:
            # Remove fragment patterns but keep real middle names
            middle = fragment_pattern.sub('', middle).strip()
            if not middle:
                middle = None
    
    # Extract middle from first_name if it contains multiple words
    # e.g., "FERDINAND R" -> first: FERDINAND, middle: R
    if not middle and len(first.split()) > 1:
        first_parts = first.split()
        # If last part is a single letter or initial, it might be middle
        if len(first_parts[-1]) == 1 or (len(first_parts[-1]) == 2 and first_parts[-1].endswith('.')):
            middle = first_parts[-1].replace('.', '')
            first = ' '.join(first_parts[:-1])
    
    return {
        'first_name': first or None,
        'nickname': nick or None,
        'middle_name': middle or None,
        'last_name': last or None,
        'suffix': suff or None
    }

def get_canonical_key(components: Dict[str, Optional[str]], province: str) -> Tuple[str, str, str, str]:
    """
    Get grouping key for matching entries as same person
    Uses: (canonical_first, canonical_last, suffix, province)
    - canonical_first: base first name OR nickname (for matching "FERDINAND" with "BONGBONG")
    - suffix: important to distinguish SR vs JR (different people)
    """
    # For matching, we need to handle nickname variations
    # If entry has nickname, we can match by either first_name OR nickname
    # But we'll use first_name as primary, and handle nickname matching in grouping logic
    canonical_first = components['first_name'] or ''
    canonical_last = components['last_name'] or ''
    suffix = components['suffix'] or ''  # Important: SR and JR are different people
    province_key = (province or 'UNKNOWN').strip().upper()
    
    return (canonical_first, canonical_last, suffix, province_key)

def entries_match_same_person(entry1: Dict, entry2: Dict) -> bool:
    """
    Check if two entries represent the same person
    Handles nickname variations: "FERDINAND" can match "BONGBONG" if nickname matches
    """
    comp1 = entry1['components']
    comp2 = entry2['components']
    
    # Must have same last name
    if comp1['last_name'] != comp2['last_name']:
        return False
    
    # Suffix matching: must be same if both have one, or one can be missing
    # But if both have different suffixes (SR vs JR), they're different people
    suff1 = comp1['suffix'] or ''
    suff2 = comp2['suffix'] or ''
    if suff1 and suff2 and suff1 != suff2:
        return False  # Different suffixes = different people (SR vs JR)
    # If one has suffix and other doesn't, still consider matching (might be missing data)
    
    # Must be in same province
    if entry1['group_key'][3] != entry2['group_key'][3]:  # province is 4th element
        return False
    
    # Match if:
    # 1. First names match exactly, OR
    # 2. One's first_name matches other's nickname, OR
    # 3. One's nickname matches other's first_name, OR
    # 4. Both have same nickname
    first1 = comp1['first_name'] or ''
    nick1 = comp1['nickname'] or ''
    first2 = comp2['first_name'] or ''
    nick2 = comp2['nickname'] or ''
    
    if first1 == first2:
        return True
    if first1 == nick2:
        return True
    if nick1 == first2:
        return True
    if nick1 and nick2 and nick1 == nick2:
        return True
    
    return False

async def normalize_all_names():
    conn = await asyncpg.connect(
        host='localhost', port=5432, user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu', database='dynasty'
    )
    try:
        print('🔍 Loading all entries from database...')
        
        # Get all entries including nickname and suffix fields
        all_entries = await conn.fetch('''
            SELECT id, first_name, middle_name, last_name, nickname, suffix, position, year, 
                   province, municipality_city, region, unified_person_id
            FROM political_dynasties
            WHERE first_name IS NOT NULL
              AND last_name IS NOT NULL
              AND first_name != ''
              AND last_name != ''
            ORDER BY UPPER(last_name), UPPER(first_name), province, id
        ''')
        
        print(f'📊 Processing {len(all_entries)} entries...')
        
        # Parse all entries into name components
        parsed_entries = []
        for entry in all_entries:
            components = parse_name_components(
                entry['first_name'],
                entry['middle_name'],
                entry['last_name'],
                entry['nickname'],
                entry['suffix']
            )
            
            province = (entry['province'] or '').strip().upper() if entry['province'] else 'UNKNOWN'
            group_key = get_canonical_key(components, province)
            
            parsed_entries.append({
                'id': entry['id'],
                'components': components,
                'group_key': group_key,
                'province': entry['province'],
                'position': entry['position'],
                'year': entry['year'],
                'municipality_city': entry['municipality_city'],
                'region': entry['region'],
                'unified_person_id': entry['unified_person_id'],
                'original': {
                    'first_name': entry['first_name'],
                    'middle_name': entry['middle_name'],
                    'last_name': entry['last_name'],
                    'nickname': entry['nickname'],
                    'suffix': entry['suffix']
                }
            })
        
        # Group by canonical key, but also merge groups that represent same person
        # (handles nickname variations)
        groups = defaultdict(list)
        for entry in parsed_entries:
            groups[entry['group_key']].append(entry)
        
        # Merge groups that represent the same person (nickname variations)
        # e.g., "FERDINAND MARCOS JR" and "BONGBONG MARCOS" (if BONGBONG is nickname)
        merged_groups = {}
        group_keys = list(groups.keys())
        
        for i, key1 in enumerate(group_keys):
            if key1 in merged_groups:
                continue
            
            # Check if this group matches any other group
            group1 = groups[key1]
            merged_with = [key1]
            
            for j, key2 in enumerate(group_keys[i+1:], start=i+1):
                if key2 in merged_groups:
                    continue
                
                group2 = groups[key2]
                
                # Check if any entry in group1 matches any entry in group2
                matches = False
                for e1 in group1:
                    for e2 in group2:
                        if entries_match_same_person(e1, e2):
                            matches = True
                            break
                    if matches:
                        break
                
                if matches:
                    merged_with.append(key2)
            
            # Merge all matching groups
            if len(merged_with) > 1:
                merged_group = []
                for key in merged_with:
                    merged_group.extend(groups[key])
                    merged_groups[key] = key1  # Mark as merged into key1
                groups[key1] = merged_group
        
        print(f'📋 Found {len(groups)} unique name+province groups')
        
        # Process groups with multiple entries (same person, different positions/times)
        unified_count = 0
        normalized_count = 0
        processed_groups = 0
        
        # Filter out merged groups (keep only the primary key)
        # merged_groups maps secondary keys to primary keys
        final_groups = {}
        for key, group in groups.items():
            if key not in merged_groups:  # This is a primary key (not merged into another)
                final_groups[key] = group
        
        for group_key, group in final_groups.items():
            canonical_first, canonical_last, suffix_key, province_key = group_key
            
            if len(group) > 1:
                processed_groups += 1
                if processed_groups % 100 == 0:
                    print(f'  Processed {processed_groups} groups...')
                
                # Find the most complete entry as canonical (has nickname, middle, suffix)
                # Score: nickname=3, middle=2, suffix=2, more fields = better
                def completeness_score(entry):
                    score = 0
                    comp = entry['components']
                    if comp.get('nickname'): score += 3
                    if comp.get('middle_name'): score += 2
                    if comp.get('suffix'): score += 2
                    return score
                
                # Sort by completeness (desc) then by ID (asc)
                group.sort(key=lambda x: (-completeness_score(x), x['id']))
                canonical_entry = group[0]
                canonical_id = canonical_entry['id']
                canonical_components = canonical_entry['components']
                
                # Use canonical components (most complete entry)
                canonical_first_name = canonical_components['first_name']
                canonical_nickname = canonical_components['nickname']
                canonical_middle_name = canonical_components['middle_name']
                canonical_last_name = canonical_components['last_name']
                canonical_suffix = canonical_components['suffix']
                
                # Normalize all entries to have the exact same canonical name
                for entry in group:
                    old_comp = entry['original']
                    old_name = f'{old_comp["first_name"]} {old_comp["middle_name"] or ""} {old_comp["last_name"]} {old_comp["suffix"] or ""}'.strip()
                    
                    # Update to canonical name components and set unified_person_id
                    await conn.execute('''
                        UPDATE political_dynasties
                        SET first_name = $1,
                            nickname = $2,
                            middle_name = $3,
                            last_name = $4,
                            suffix = $5,
                            unified_person_id = $6
                        WHERE id = $7
                    ''', canonical_first_name, canonical_nickname, canonical_middle_name, 
                        canonical_last_name, canonical_suffix, canonical_id, entry['id'])
                    
                    unified_count += 1
                    normalized_count += 1
            else:
                # Single entry - normalize to canonical form
                entry = group[0]
                components = entry['components']
                original = entry['original']
                
                # Check if normalization is needed
                needs_update = (
                    (original['first_name'] or '').strip().upper() != (components['first_name'] or '') or
                    (original['middle_name'] or '').strip().upper() != (components['middle_name'] or '') or
                    (original['last_name'] or '').strip().upper() != (components['last_name'] or '') or
                    (original['nickname'] or '').strip().upper() != (components['nickname'] or '') or
                    (original['suffix'] or '').strip().upper() != (components['suffix'] or '')
                )
                
                if needs_update:
                    await conn.execute('''
                        UPDATE political_dynasties
                        SET first_name = $1,
                            nickname = $2,
                            middle_name = $3,
                            last_name = $4,
                            suffix = $5
                        WHERE id = $6
                    ''', components['first_name'], components['nickname'], 
                        components['middle_name'], components['last_name'], 
                        components['suffix'], entry['id'])
                    normalized_count += 1
        
        print(f'\n✅ Summary:')
        print(f'  - Processed {processed_groups} groups with multiple entries')
        print(f'  - Unified {unified_count} entries as same person (preserved all positions over time)')
        print(f'  - Normalized {normalized_count} entries total')
        print(f'  - Province-based disambiguation prevents merging unrelated people with common surnames')
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(normalize_all_names())


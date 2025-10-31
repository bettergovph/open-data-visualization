#!/usr/bin/env python3
"""
Normalize person names by analyzing relationship patterns.

Key insight: If two people with similar names have the same relationships
(e.g., both are fathers of the same child, or both are spouses of the same person),
they are likely the same person with name variations.

Examples:
- "Juan A. Dela Cruz" and "Juan B. Dela Cruz" both listed as father of "Maria Dela Cruz"
- "John Reyes" and "J. Reyes" both married to "Mary Tan"
- "Jose M. Santos" and "Jose Santos" both have same children

This script:
1. Queries all relationships
2. Groups people by their relationships (who they're related to)
3. Finds people with fuzzy-similar names who share the same relationships
4. Creates normalization mappings
5. Optionally applies the normalization
"""

import asyncio
import asyncpg
import os
import re
from collections import defaultdict
from typing import Dict, List, Set, Tuple, Optional
from pathlib import Path
from dotenv import load_dotenv


def load_env_from_dotenv():
    """Load environment variables from .env file"""
    root = Path(__file__).resolve().parents[2]
    env_path = root / '.env'
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def normalize_name_for_comparison(full_name: str) -> str:
    """Normalize name for fuzzy matching (remove middle initials, extra spaces)"""
    if not full_name:
        return ""
    # Remove middle initials like "A.", "B.", "C."
    name = re.sub(r'\b[A-Z]\.\s*', ' ', full_name.upper())
    # Remove extra spaces
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def fuzzy_name_match(name1: str, name2: str, threshold: float = 0.7) -> bool:
    """
    Check if two names are likely the same person.
    Uses normalized comparison and checks if first/last names match closely.
    """
    norm1 = normalize_name_for_comparison(name1)
    norm2 = normalize_name_for_comparison(name2)
    
    if not norm1 or not norm2:
        return False
    
    # Exact match on normalized
    if norm1 == norm2:
        return True
    
    # Split into parts
    parts1 = norm1.split()
    parts2 = norm2.split()
    
    if len(parts1) < 2 or len(parts2) < 2:
        return False
    
    # Last name must match (case-insensitive, normalized)
    last1 = parts1[-1].strip()
    last2 = parts2[-1].strip()
    if last1 != last2:
        return False
    
    # First name should be similar
    first1 = parts1[0].strip()
    first2 = parts2[0].strip()
    
    # Exact first name match
    if first1 == first2:
        return True
    
    # First initial match (e.g., "J" matches "JOHN", "JOSE")
    if len(first1) == 1 and first2.startswith(first1):
        return True
    if len(first2) == 1 and first1.startswith(first2):
        return True
    
    # Check if one is a prefix of the other (e.g., "JOHN" vs "JOHNNY")
    min_len = min(len(first1), len(first2))
    if min_len >= 3:
        if first1[:min_len] == first2[:min_len]:
            return True
    
    return False


async def analyze_relationships_for_name_variations(conn, dry_run: bool = True):
    """Analyze relationships to find name variations of the same person"""
    
    print("🔍 Analyzing relationships for name variations...")
    
    # Get all relationships with person details
    # Check table structure first - some might use person1_id/person2_id
    table_info = await conn.fetch("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'relationships' 
        AND column_name IN ('person_id', 'related_person_id', 'person1_id', 'person2_id')
        ORDER BY column_name
    """)
    
    column_names = [row['column_name'] for row in table_info]
    
    if 'person_id' in column_names and 'related_person_id' in column_names:
        # New structure
        relationships = await conn.fetch("""
            SELECT 
                r.id,
                r.person_id,
                r.related_person_id,
                r.relationship_type,
                ct.name as relationship_type_name,
                p1.id as p1_id,
                p1.first_name as p1_first,
                p1.last_name as p1_last,
                CONCAT(COALESCE(p1.first_name, ''), ' ', COALESCE(p1.last_name, '')) as p1_full,
                p2.id as p2_id,
                p2.first_name as p2_first,
                p2.last_name as p2_last,
                CONCAT(COALESCE(p2.first_name, ''), ' ', COALESCE(p2.last_name, '')) as p2_full
            FROM relationships r
            JOIN connection_types ct ON r.relationship_type = ct.id
            JOIN political_dynasties p1 ON r.person_id = p1.id
            JOIN political_dynasties p2 ON r.related_person_id = p2.id
            WHERE ct.category = 'family'
            ORDER BY r.relationship_type, r.person_id
        """)
    elif 'person1_id' in column_names and 'person2_id' in column_names:
        # Old structure
        relationships = await conn.fetch("""
            SELECT 
                r.id,
                r.person1_id as person_id,
                r.person2_id as related_person_id,
                r.relationship_type_id as relationship_type,
                ct.name as relationship_type_name,
                p1.id as p1_id,
                p1.first_name as p1_first,
                p1.last_name as p1_last,
                CONCAT(COALESCE(p1.first_name, ''), ' ', COALESCE(p1.last_name, '')) as p1_full,
                p2.id as p2_id,
                p2.first_name as p2_first,
                p2.last_name as p2_last,
                CONCAT(COALESCE(p2.first_name, ''), ' ', COALESCE(p2.last_name, '')) as p2_full
            FROM relationships r
            JOIN connection_types ct ON r.relationship_type_id = ct.id
            JOIN political_dynasties p1 ON r.person1_id = p1.id
            JOIN political_dynasties p2 ON r.person2_id = p2.id
            WHERE ct.category = 'family'
            ORDER BY r.relationship_type_id, r.person1_id
        """)
    else:
        print(f"❌ Unknown relationships table structure. Columns found: {column_names}")
        return {}
    
    print(f"📊 Loaded {len(relationships)} family relationships")
    
    # Build relationship signature for each person
    # Signature = set of (relationship_type, related_person_id) pairs
    person_signatures = defaultdict(set)
    person_details = {}
    
    for rel in relationships:
        p1_id = rel['p1_id']
        p2_id = rel['p2_id']
        rel_type = rel['relationship_type_name']
        
        # Store person details
        person_details[p1_id] = {
            'first_name': rel['p1_first'],
            'last_name': rel['p1_last'],
            'full_name': rel['p1_full']
        }
        person_details[p2_id] = {
            'first_name': rel['p2_first'],
            'last_name': rel['p2_last'],
            'full_name': rel['p2_full']
        }
        
        # Build signature: who is this person related to, and how?
        # Example: "Father of person_123", "Husband of person_456"
        signature_key = (rel_type, p2_id)
        person_signatures[p1_id].add(signature_key)
    
    print(f"📊 Analyzed {len(person_signatures)} people with relationships")
    
    # Group people by their relationship signatures
    # People with similar signatures who have similar names are likely duplicates
    signature_groups = defaultdict(list)
    
    for person_id, signature in person_signatures.items():
        # Create a sorted, hashable signature
        signature_key = tuple(sorted(signature))
        signature_groups[signature_key].append(person_id)
    
    print(f"📊 Found {len(signature_groups)} unique relationship signature groups")
    
    # Find potential duplicates within each group
    potential_duplicates = []
    
    for signature_key, person_ids in signature_groups.items():
        if len(person_ids) < 2:
            continue  # Need at least 2 people to compare
        
        # Compare all pairs in this group
        for i in range(len(person_ids)):
            for j in range(i + 1, len(person_ids)):
                id1, id2 = person_ids[i], person_ids[j]
                
                if id1 not in person_details or id2 not in person_details:
                    continue
                
                name1 = person_details[id1]['full_name']
                name2 = person_details[id2]['full_name']
                
                # Check if names are similar
                if fuzzy_name_match(name1, name2):
                    # Found a potential duplicate!
                    rel_types = [rt for rt, _ in signature_key]
                    related_ids = [rid for _, rid in signature_key]
                    
                    potential_duplicates.append({
                        'id1': id1,
                        'id2': id2,
                        'name1': name1,
                        'name2': name2,
                        'relationship_signature': rel_types,
                        'shared_relationships': len(signature_key),
                        'related_people_count': len(related_ids)
                    })
    
    print(f"\n📊 Found {len(potential_duplicates)} potential duplicate pairs")
    
    # Group duplicates by relationship type for better reporting
    print("\n📋 Analyzing duplicates by relationship type...")
    print("=" * 100)
    
    # Get relationship type names for reporting
    rel_type_names = await conn.fetch("SELECT id, name FROM connection_types WHERE category = 'family'")
    rel_type_map = {rt['id']: rt['name'] for rt in rel_type_names}
    
    # Analyze by specific relationship patterns
    father_duplicates = []
    spouse_duplicates = []
    child_duplicates = []
    other_duplicates = []
    
    for dup in potential_duplicates:
        rel_types = dup['relationship_signature']
        
        if 'Father' in rel_types:
            father_duplicates.append(dup)
        elif 'Husband' in rel_types or 'Wife' in rel_types:
            spouse_duplicates.append(dup)
        elif 'Son' in rel_types or 'Daughter' in rel_types:
            child_duplicates.append(dup)
        else:
            other_duplicates.append(dup)
    
    # Report findings
    print(f"\n👨 Found {len(father_duplicates)} duplicate fathers (same person, different name variations)")
    print(f"💑 Found {len(spouse_duplicates)} duplicate spouses (same person, different name variations)")
    print(f"👶 Found {len(child_duplicates)} duplicate children (same person, different name variations)")
    print(f"🔗 Found {len(other_duplicates)} other duplicate relationships")
    
    # Show examples
    print("\n" + "=" * 100)
    print("TOP 20 DUPLICATE EXAMPLES:")
    print("=" * 100)
    
    all_duplicates_sorted = sorted(potential_duplicates, key=lambda x: -x['shared_relationships'])
    
    for i, dup in enumerate(all_duplicates_sorted[:20], 1):
        print(f"\n{i}. Shared {dup['shared_relationships']} relationship(s)")
        print(f"   ID {dup['id1']}: {dup['name1']}")
        print(f"   ID {dup['id2']}: {dup['name2']}")
        print(f"   Relationship types: {', '.join(dup['relationship_signature'][:3])}")
        print(f"   → Likely the same person! Should normalize/merge.")
    
    # Create normalization mappings
    # Choose the "best" name (usually the longer, more complete one)
    normalization_mappings = {}
    reverse_mappings = {}
    
    for dup in all_duplicates_sorted:
        id1, id2 = dup['id1'], dup['id2']
        name1, name2 = dup['name1'], dup['name2']
        
        # Decide which ID to keep (canonical) and which to map from
        # Prefer the longer name (more complete), or the one with middle initial
        # Also prefer the lower ID (usually older entry)
        
        name1_norm = normalize_name_for_comparison(name1)
        name2_norm = normalize_name_for_comparison(name2)
        
        # Check if one has middle initial
        has_middle1 = bool(re.search(r'\b[A-Z]\.\s*', name1))
        has_middle2 = bool(re.search(r'\b[A-Z]\.\s*', name2))
        
        if has_middle1 and not has_middle2:
            canonical_id, variant_id = id1, id2
            canonical_name, variant_name = name1, name2
        elif has_middle2 and not has_middle1:
            canonical_id, variant_id = id2, id1
            canonical_name, variant_name = name2, name1
        elif len(name1_norm) > len(name2_norm):
            canonical_id, variant_id = id1, id2
            canonical_name, variant_name = name1, name2
        elif len(name2_norm) > len(name1_norm):
            canonical_id, variant_id = id2, id1
            canonical_name, variant_name = name2, name1
        else:
            # Same length, use lower ID
            if id1 < id2:
                canonical_id, variant_id = id1, id2
                canonical_name, variant_name = name1, name2
            else:
                canonical_id, variant_id = id2, id1
                canonical_name, variant_name = name2, name1
        
        # Only add if not already mapped
        if variant_id not in normalization_mappings:
            normalization_mappings[variant_id] = {
                'canonical_id': canonical_id,
                'variant_name': variant_name,
                'canonical_name': canonical_name,
                'shared_relationships': dup['shared_relationships']
            }
            reverse_mappings.setdefault(canonical_id, []).append({
                'variant_id': variant_id,
                'variant_name': variant_name
            })
    
    print(f"\n📋 Created {len(normalization_mappings)} normalization mappings")
    
    # Show mapping summary
    print("\n" + "=" * 100)
    print("NORMALIZATION MAPPINGS (Top 30):")
    print("=" * 100)
    
    mappings_sorted = sorted(normalization_mappings.items(), 
                            key=lambda x: -x[1]['shared_relationships'])
    
    for i, (variant_id, mapping) in enumerate(mappings_sorted[:30], 1):
        print(f"\n{i}. Variant ID {variant_id}: '{mapping['variant_name']}'")
        print(f"   → Canonical ID {mapping['canonical_id']}: '{mapping['canonical_name']}'")
        print(f"   Shared {mapping['shared_relationships']} relationship(s)")
    
    if dry_run:
        print("\n⚠️  DRY RUN MODE - No changes will be made.")
        print("   Run with --execute to apply normalization.")
        return normalization_mappings
    
    # Apply normalization
    print("\n🔄 Applying normalization...")
    
    applied_count = 0
    for variant_id, mapping in normalization_mappings.items():
        canonical_id = mapping['canonical_id']
        
        try:
            # Get table structure
            column_info = await conn.fetch("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'relationships' 
                AND column_name IN ('person_id', 'related_person_id')
                ORDER BY column_name
            """)
            
            has_person_id = any(row['column_name'] == 'person_id' for row in column_info)
            
            if has_person_id:
                # New structure: person_id, related_person_id
                await conn.execute("""
                    UPDATE relationships
                    SET person_id = $1
                    WHERE person_id = $2
                    AND NOT EXISTS (
                        SELECT 1 FROM relationships r2
                        WHERE r2.person_id = $1
                        AND r2.related_person_id = relationships.related_person_id
                        AND r2.relationship_type = relationships.relationship_type
                    )
                """, canonical_id, variant_id)
                
                await conn.execute("""
                    UPDATE relationships
                    SET related_person_id = $1
                    WHERE related_person_id = $2
                    AND NOT EXISTS (
                        SELECT 1 FROM relationships r2
                        WHERE r2.person_id = relationships.person_id
                        AND r2.related_person_id = $1
                        AND r2.relationship_type = relationships.relationship_type
                    )
                """, canonical_id, variant_id)
            else:
                # Old structure: person1_id, person2_id
                await conn.execute("""
                    UPDATE relationships
                    SET person1_id = $1
                    WHERE person1_id = $2
                    AND NOT EXISTS (
                        SELECT 1 FROM relationships r2
                        WHERE r2.person1_id = $1
                        AND r2.person2_id = relationships.person2_id
                        AND r2.relationship_type_id = relationships.relationship_type_id
                    )
                """, canonical_id, variant_id)
                
                await conn.execute("""
                    UPDATE relationships
                    SET person2_id = $1
                    WHERE person2_id = $2
                    AND NOT EXISTS (
                        SELECT 1 FROM relationships r2
                        WHERE r2.person1_id = relationships.person1_id
                        AND r2.person2_id = $1
                        AND r2.relationship_type_id = relationships.relationship_type_id
                    )
                """, canonical_id, variant_id)
            
            # Option 2: Merge person records (update variant to point to canonical)
            # This is more complex - you might want to merge all attributes
            # For now, we'll just update the name to match canonical
            
            canonical_person = await conn.fetchrow("""
                SELECT first_name, last_name, middle_name
                FROM political_dynasties WHERE id = $1
            """, canonical_id)
            
            if canonical_person:
                await conn.execute("""
                    UPDATE political_dynasties
                    SET 
                        first_name = $1,
                        middle_name = $2,
                        last_name = $3
                    WHERE id = $4
                """, 
                canonical_person['first_name'],
                canonical_person['middle_name'],
                canonical_person['last_name'],
                variant_id)
            
            applied_count += 1
            
            if applied_count % 10 == 0:
                print(f"   ✅ Applied {applied_count} normalizations...")
                
        except Exception as e:
            print(f"   ❌ Error normalizing variant_id {variant_id}: {e}")
    
    print(f"\n✅ Applied {applied_count} normalizations")
    
    return normalization_mappings


async def main():
    import sys
    dry_run = '--execute' not in sys.argv
    
    load_env_from_dotenv()
    load_dotenv()
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        await analyze_relationships_for_name_variations(conn, dry_run=dry_run)
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())


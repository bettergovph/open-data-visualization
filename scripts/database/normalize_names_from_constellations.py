#!/usr/bin/env python3
"""
Normalize person names by analyzing relationship constellations.

When the same person appears in multiple constellations with slightly different names,
we can identify them as the same person and suggest normalization/merging.
"""

import asyncio
import asyncpg
import json
import os
from collections import defaultdict
from dotenv import load_dotenv
from pathlib import Path


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


def normalize_name_for_comparison(full_name):
    """Normalize name for comparison (remove middle initials, extra spaces)"""
    import re
    if not full_name:
        return ""
    # Remove middle initials like "A.", "B.", "C."
    name = re.sub(r'\b[A-Z]\.\s*', ' ', full_name.upper())
    # Remove extra spaces
    name = re.sub(r'\s+', ' ', name).strip()
    return name


async def analyze_constellations_for_duplicates(conn):
    """Analyze relationship constellations to find potential duplicate names"""
    
    print("🔍 Loading relationship constellations cache...")
    
    # Load cached JSON data
    cache_file = "static/data/relationship_chains_cache.json"
    if not os.path.exists(cache_file):
        print(f"❌ Cache file not found: {cache_file}")
        return
    
    with open(cache_file, 'r', encoding='utf-8') as f:
        cache_data = json.load(f)
    
    chains = cache_data.get('chains', [])
    print(f"📊 Loaded {len(chains)} constellations")
    
    # Group people by normalized name
    name_groups = defaultdict(list)
    
    # Collect all people from all constellations
    for chain in chains:
        for person in chain.get('path', []):
            person_id = person.get('id')
            first_name = person.get('first_name', '').strip()
            last_name = person.get('last_name', '').strip()
            full_name = f"{first_name} {last_name}".strip()
            
            if not full_name or not person_id:
                continue
            
            normalized = normalize_name_for_comparison(full_name)
            name_groups[normalized].append({
                'id': person_id,
                'first_name': first_name,
                'last_name': last_name,
                'full_name': full_name,
                'position': person.get('position', ''),
                'province': person.get('province', ''),
                'year': person.get('year')
            })
    
    # Find potential duplicates (same normalized name but different IDs)
    potential_duplicates = []
    for normalized_name, people in name_groups.items():
        # Get unique IDs
        unique_ids = set(p['id'] for p in people)
        if len(unique_ids) > 1:
            # Multiple IDs for same normalized name - potential duplicates!
            potential_duplicates.append({
                'normalized_name': normalized_name,
                'people': people,
                'count': len(people),
                'unique_ids': len(unique_ids)
            })
    
    print(f"\n📊 Found {len(potential_duplicates)} potential duplicate groups")
    
    # Sort by count (most frequent first)
    potential_duplicates.sort(key=lambda x: -x['count'])
    
    # Show top 50
    print("\n📋 Top 50 potential duplicate groups:")
    print("=" * 100)
    
    for i, dup_group in enumerate(potential_duplicates[:50], 1):
        print(f"\n{i}. Normalized name: {dup_group['normalized_name']}")
        print(f"   Found {dup_group['count']} occurrences with {dup_group['unique_ids']} unique IDs:")
        
        # Group by ID to show variations
        by_id = defaultdict(list)
        for person in dup_group['people']:
            by_id[person['id']].append(person)
        
        for person_id, variants in sorted(by_id.items()):
            # Get most common variant for this ID
            most_common = max(variants, key=lambda p: variants.count(p))
            print(f"      ID {person_id}: {most_common['full_name']} ({len(variants)} occurrences)")
            print(f"          Position: {most_common['position'][:50]}")
            print(f"          Province: {most_common['province']}")
    
    # Also check for people who appear in the same constellations together
    # (if two people with similar names appear together in many constellations, they might be the same)
    print("\n\n🔗 Finding people with similar names that appear together in constellations...")
    
    # Build a graph of who appears with whom
    person_cooccurrences = defaultdict(lambda: defaultdict(int))
    
    for chain in chains:
        path = chain.get('path', [])
        path_ids = [p.get('id') for p in path if p.get('id')]
        
        # For each pair in the chain, record co-occurrence
        for i in range(len(path_ids)):
            for j in range(i + 1, len(path_ids)):
                id1, id2 = path_ids[i], path_ids[j]
                if id1 and id2 and id1 != id2:
                    person_cooccurrences[id1][id2] += 1
                    person_cooccurrences[id2][id1] += 1
    
    # Find people who co-occur frequently and have similar names
    similar_cooccurring = []
    
    # Get person details
    all_ids = set()
    for dup_group in potential_duplicates:
        for person in dup_group['people']:
            all_ids.add(person['id'])
    
    if all_ids:
        person_details = {}
        ids_list = list(all_ids)
        for i in range(0, len(ids_list), 1000):
            batch = ids_list[i:i+1000]
            query = """
                SELECT id, first_name, last_name, CONCAT(first_name, ' ', last_name) as full_name
                FROM political_dynasties
                WHERE id = ANY($1)
            """
            rows = await conn.fetch(query, batch)
            for row in rows:
                person_details[row['id']] = {
                    'first_name': row['first_name'],
                    'last_name': row['last_name'],
                    'full_name': row['full_name']
                }
        
        # Check pairs with similar normalized names
        checked_pairs = set()
        for dup_group in potential_duplicates[:100]:  # Check top 100
            people = dup_group['people']
            for i in range(len(people)):
                for j in range(i + 1, len(people)):
                    id1, id2 = people[i]['id'], people[j]['id']
                    
                    if (id1, id2) in checked_pairs or (id2, id1) in checked_pairs:
                        continue
                    checked_pairs.add((id1, id2))
                    
                    # Check if they co-occur in constellations
                    cooccur_count = person_cooccurrences.get(id1, {}).get(id2, 0)
                    if cooccur_count > 0:
                        name1 = person_details.get(id1, {}).get('full_name', 'Unknown')
                        name2 = person_details.get(id2, {}).get('full_name', 'Unknown')
                        
                        similar_cooccurring.append({
                            'id1': id1,
                            'id2': id2,
                            'name1': name1,
                            'name2': name2,
                            'normalized': dup_group['normalized_name'],
                            'cooccur_count': cooccur_count
                        })
        
        similar_cooccurring.sort(key=lambda x: -x['cooccur_count'])
        
        print(f"\n📊 Found {len(similar_cooccurring)} pairs with similar names that co-occur in constellations")
        print("\nTop 20 similar names that appear together:")
        print("=" * 100)
        
        for i, pair in enumerate(similar_cooccurring[:20], 1):
            print(f"\n{i}. Appear together in {pair['cooccur_count']} constellation(s):")
            print(f"   ID {pair['id1']}: {pair['name1']}")
            print(f"   ID {pair['id2']}: {pair['name2']}")
            print(f"   Normalized: {pair['normalized']}")
            print("   → Likely the same person! Should be merged.")
    
    return potential_duplicates, similar_cooccurring


async def main():
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
        await analyze_constellations_for_duplicates(conn)
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())


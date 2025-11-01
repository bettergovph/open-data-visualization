#!/usr/bin/env python3
"""
Find and merge duplicate/similar names in political_dynasties using Perplexity API.

Flow:
1) Delete document fragments (all caps, common fragments, etc.)
2) Resolve obvious close matches by renaming to longer names
3) Group remaining similar names into sets
4) Send top 300 unresolved name sets (30 per batch) to Perplexity
5) Rename records (UPDATE), don't delete them
"""

import os
import re
import asyncio
import asyncpg
import requests
import json
from typing import List, Dict, Tuple, Optional, Set
from pathlib import Path
from dotenv import load_dotenv
from difflib import SequenceMatcher
from collections import defaultdict


def load_env_from_dotenv() -> None:
    """Load environment variables from .env file"""
    root = Path(__file__).resolve().parents[3]
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


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def is_document_fragment(first_name: str, last_name: str) -> bool:
    """Check if a name is likely a document fragment"""
    first = (first_name or '').strip().upper()
    last = (last_name or '').strip().upper()
    full = f"{first} {last}".strip()
    
    # Known fragment words
    fragment_words = {
        'STAFF', 'LOBBY', 'FLOODS', 'PLAN', 'SIDE', 'SSP', 'DESCRIPTION',
        'STORAGE', 'CLOSET', 'DEPARTMENT', 'PUBLIC', 'WORKS', 'HIGHWAYS',
        'LOCATION', 'DUTY', 'PNCO', 'CONTROL', 'PROVISIONS', 'BOREHOLE',
        'PARTMENT', 'PPAARRTTMMEENNTT'
    }
    
    # Check for fragment words
    for word in fragment_words:
        if word in full:
            return True
    
    # All caps and very long (likely document text)
    if full.isupper() and len(full.replace(' ', '')) > 40:
        return True
    
    # Repeated characters (like "PPAARRTTMMEENNTT")
    if re.search(r'([A-Z])\1{2,}', full):
        return True
    
    # No vowels (very unlikely for names)
    if full and not re.search(r'[AEIOU]', full.replace(' ', '')):
        return True
    
    # Contains only special characters or numbers
    if re.match(r'^[^A-Za-z]*$', full.replace(' ', '')):
        return True
    
    # Very short single letters or numbers
    if len(full.replace(' ', '')) <= 1:
        return True
    
    # Contains common document phrases
    document_phrases = [
        'DEPARTMENT OF', 'PROVINCE OF', 'CITY OF', 'MUNICIPALITY OF',
        'OFFICE OF', 'BUREAU OF', 'COMMISSION ON'
    ]
    for phrase in document_phrases:
        if phrase in full:
            return True
    
    return False


def calculate_name_completeness_score(first_name: str, last_name: str) -> int:
    """Calculate a score for name completeness (higher = more complete/longer)"""
    first = (first_name or '').strip()
    last = (last_name or '').strip()
    
    # Count parts (more parts = more complete)
    first_parts = len(first.split())
    last_parts = len(last.split())
    
    # Count characters (longer = more detailed, includes middle names)
    first_chars = len(first.replace(' ', ''))
    last_chars = len(last.replace(' ', ''))
    
    # Check for middle names/initials (K., MARIE, etc.)
    has_middle = bool(re.search(r'\b[A-Z]\.?\b|\b(MARIE|MA|MARY|ANN|ANNA|CRISTINA|CRISTINE)\b', first.upper()))
    
    # Score: prioritize parts, then length, then middle names
    score = (first_parts * 1000) + (last_parts * 100) + (first_chars * 10) + (last_chars) + (100 if has_middle else 0)
    
    return score


def calculate_name_similarity(name1: str, name2: str) -> float:
    """Calculate similarity between two names"""
    if not name1 or not name2:
        return 0.0
    
    norm1 = name1.upper().strip()
    norm2 = name2.upper().strip()
    
    if norm1 == norm2:
        return 1.0
    
    # Use sequence matcher
    similarity = SequenceMatcher(None, norm1, norm2).ratio()
    
    # Boost if one contains the other
    if norm1 in norm2 or norm2 in norm1:
        similarity = max(similarity, 0.85)
    
    return similarity


async def delete_document_fragments(conn):
    """Delete document fragments from the database"""
    print("\n" + "="*60)
    print("🗑️  Step 1: Deleting document fragments...")
    print("="*60 + "\n")
    
    records = await conn.fetch('''
        SELECT id, first_name, last_name
        FROM political_dynasties
        WHERE first_name IS NOT NULL AND last_name IS NOT NULL
    ''')
    
    fragment_ids = []
    for rec in records:
        if is_document_fragment(rec['first_name'], rec['last_name']):
            fragment_ids.append(rec['id'])
    
    if fragment_ids:
        # Delete relationships first
        await conn.execute('''
            DELETE FROM relationships
            WHERE person_id = ANY($1) OR related_person_id = ANY($1)
        ''', fragment_ids)
        
        # Delete the records
        deleted = await conn.execute('''
            DELETE FROM political_dynasties
            WHERE id = ANY($1)
        ''', fragment_ids)
        
        print(f"✅ Deleted {len(fragment_ids)} document fragments")
    else:
        print("✅ No document fragments found")


async def resolve_obvious_matches(conn):
    """Resolve obvious close matches by renaming to longer names"""
    print("\n" + "="*60)
    print("🔄 Step 2: Resolving obvious close matches...")
    print("="*60 + "\n")
    
    # Find records grouped by surname
    records = await conn.fetch('''
        SELECT id, first_name, last_name
        FROM political_dynasties
        WHERE first_name IS NOT NULL AND last_name IS NOT NULL
        ORDER BY last_name, first_name
    ''')
    
    # Group by surname
    by_surname = defaultdict(list)
    for rec in records:
        surname = (rec['last_name'] or '').upper().strip()
        if surname:
            by_surname[surname].append(dict(rec))
    
    renamed_count = 0
    
    # For each surname group, find obvious duplicates
    for surname, group in by_surname.items():
        if len(group) < 2:
            continue
        
        # Compare all pairs
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                rec1 = group[i]
                rec2 = group[j]
                
                first1 = (rec1['first_name'] or '').strip()
                first2 = (rec2['first_name'] or '').strip()
                
                if not first1 or not first2:
                    continue
                
                # Exact match or very high similarity (>= 0.95)
                similarity = calculate_name_similarity(first1, first2)
                
                if similarity >= 0.95:  # Very high similarity - obvious match
                    # Choose the longer/more complete name
                    score1 = calculate_name_completeness_score(first1, surname)
                    score2 = calculate_name_completeness_score(first2, surname)
                    
                    if score1 >= score2:
                        primary = rec1
                        to_rename = rec2
                        target_first = first1
                    else:
                        primary = rec2
                        to_rename = rec1
                        target_first = first2
                    
                    # Rename the shorter one to match the longer one
                    # Just rename - keep all records (different years/positions are preserved)
                    if to_rename['first_name'].strip() != target_first:
                        # Only rename the record - don't touch relationships
                        # All records for same person will have same name, appearing as one node
                        await conn.execute('''
                            UPDATE political_dynasties
                            SET first_name = $1
                            WHERE id = $2
                        ''', target_first, to_rename['id'])
                        
                        renamed_count += 1
                        if renamed_count % 100 == 0:
                            print(f"  Renamed {renamed_count} records...")
    
    print(f"✅ Renamed {renamed_count} records to match longer names\n")
    return renamed_count


async def group_similar_names(conn, limit: int = 900) -> List[Dict]:
    """Group similar names into sets that need Perplexity resolution"""
    print(f"🔍 Finding similar name groups (top {limit})...")
    
    records = await conn.fetch('''
        SELECT id, first_name, last_name
        FROM political_dynasties
        WHERE first_name IS NOT NULL AND last_name IS NOT NULL
        ORDER BY last_name, first_name
    ''')
    
    # Group by surname
    by_surname = defaultdict(list)
    for rec in records:
        surname = (rec['last_name'] or '').upper().strip()
        if surname:
            by_surname[surname].append(dict(rec))
    
    name_groups = []
    
    # For each surname, find similar first names
    for surname, group in by_surname.items():
        if len(group) < 2:
            continue
        
        # Compare all pairs
        processed_pairs = set()
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                rec1 = group[i]
                rec2 = group[j]
                
                first1 = (rec1['first_name'] or '').strip()
                first2 = (rec2['first_name'] or '').strip()
                
                if not first1 or not first2:
                    continue
                
                # Skip exact matches (already resolved)
                if first1.upper() == first2.upper():
                    continue
                
                # Find similar but not exact matches (0.6 - 0.95 similarity)
                similarity = calculate_name_similarity(first1, first2)
                
                if 0.6 <= similarity < 0.95:
                    pair_key = tuple(sorted([rec1['id'], rec2['id']]))
                    if pair_key not in processed_pairs:
                        processed_pairs.add(pair_key)
                        
                        score1 = calculate_name_completeness_score(first1, surname)
                        score2 = calculate_name_completeness_score(first2, surname)
                        
                        name_groups.append({
                            'records': [rec1, rec2],
                            'similarity': similarity,
                            'surname': surname,
                            'score1': score1,
                            'score2': score2,
                            'names': [f"{first1} {surname}", f"{first2} {surname}"]
                        })
    
    # Sort by similarity (highest first)
    name_groups.sort(key=lambda x: -x['similarity'])
    
    # Take top candidates
    candidates = name_groups[:limit]
    
    print(f"✅ Found {len(candidates)} similar name groups needing resolution\n")
    return candidates


async def query_perplexity_name_group(name_group: Dict, api_key: str) -> Dict:
    """Query Perplexity API to resolve a group of similar names"""
    names = name_group['names']
    
    # Create prompt with all names in the group
    names_list = '\n'.join([f"- {name}" for name in names])
    
    prompt = f"""Are these names referring to the same person in Philippine politics?

{names_list}

Please respond with ONLY a JSON object in this exact format:
{{
    "same_person": true/false,
    "confidence": 1-10,
    "reasoning": "brief explanation",
    "correct_name": "the most complete and accurate name (if same_person is true, include nickname if known)"
}}

If they are the same person, provide the correct_name field with their full complete name. If false, omit "correct_name"."""
    
    try:
        response = requests.post(
            'https://api.perplexity.ai/chat/completions',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'llama-3.1-sonar-large-128k-online',
                'messages': [
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ],
                'temperature': 0.2,
                'max_tokens': 500
            },
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"⚠️ API error: {response.status_code}")
            return {'same_person': False, 'confidence': 0, 'reasoning': f'API error: {response.status_code}'}
        
        result = response.json()
        content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        
        # Try to extract JSON from response
        json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                return parsed
            except:
                pass
        
        # Fallback: try to parse from text
        same = 'true' in content.lower() or 'yes' in content.lower()
        confidence_match = re.search(r'["\']?confidence["\']?\s*:\s*(\d+)', content, re.IGNORECASE)
        confidence = int(confidence_match.group(1)) if confidence_match else 5
        
        correct_name_match = re.search(r'["\']?correct_name["\']?\s*:\s*["\']([^"\']+)["\']', content, re.IGNORECASE)
        correct_name = correct_name_match.group(1) if correct_name_match else None
        
        return {
            'same_person': same,
            'confidence': confidence,
            'correct_name': correct_name,
            'reasoning': content[:200]
        }
        
    except Exception as e:
        print(f"❌ Error querying Perplexity: {e}")
        return {'same_person': False, 'confidence': 0, 'reasoning': f'Error: {str(e)}'}


async def rename_records(conn, primary_id: int, duplicate_ids: List[int], correct_name: Optional[str] = None):
    """Rename duplicate records to match the primary - keep all records, just standardize names"""
    # Get primary record
    primary = await conn.fetchrow('SELECT * FROM political_dynasties WHERE id = $1', primary_id)
    if not primary:
        return False
    
    # Parse correct_name if provided
    target_first_name = primary['first_name']
    target_last_name = primary['last_name']
    if correct_name:
        name_parts = correct_name.strip().split()
        if len(name_parts) >= 2:
            target_first_name = ' '.join(name_parts[:-1])
            target_last_name = name_parts[-1]
            # Update primary if correct_name is provided
            await conn.execute('''
                UPDATE political_dynasties
                SET first_name = $1, last_name = $2
                WHERE id = $3
            ''', target_first_name, target_last_name, primary_id)
    
    # Just rename duplicate records to match - don't touch relationships
    # All records for same person will have same name, appearing as one node in visualization
    for dup_id in duplicate_ids:
        await conn.execute('''
            UPDATE political_dynasties
            SET first_name = $1, last_name = $2
            WHERE id = $3
        ''', target_first_name, target_last_name, dup_id)
    
    return True


async def process_perplexity_batch(conn, name_groups: List[Dict], batch_num: int, api_key: str):
    """Process a batch of name groups through Perplexity"""
    print(f"\n{'='*60}")
    print(f"📦 Processing batch {batch_num} ({len(name_groups)} name groups)")
    print(f"{'='*60}\n")
    
    renamed_count = 0
    
    for idx, group in enumerate(name_groups, 1):
        names_str = ', '.join(group['names'])
        print(f"[{idx}/{len(name_groups)}] Checking: {names_str} (similarity: {group['similarity']:.2f})")
        
        result = await query_perplexity_name_group(group, api_key)
        
        # Require confidence >= 7
        if result.get('same_person') and result.get('confidence', 0) >= 7:
            # Determine primary (higher score wins)
            if group['score1'] >= group['score2']:
                primary_rec = group['records'][0]
                duplicate_rec = group['records'][1]
            else:
                primary_rec = group['records'][1]
                duplicate_rec = group['records'][0]
            
            correct_name = result.get('correct_name')
            if correct_name:
                print(f"     Using Perplexity's correct name: {correct_name}")
            
            print(f"  ✅ SAME PERSON (confidence: {result['confidence']}/10)")
            print(f"     Renaming {duplicate_rec['id']} to match {primary_rec['id']}")
            
            success = await rename_records(conn, primary_rec['id'], [duplicate_rec['id']], correct_name)
            
            if success:
                renamed_count += 1
        else:
            print(f"  ❌ Different persons (confidence: {result.get('confidence', 0)}/10)")
        
        # Rate limiting
        await asyncio.sleep(2)  # 2 second delay between API calls
    
    print(f"\n✅ Batch {batch_num} complete: Renamed {renamed_count} groups\n")
    return renamed_count


async def main():
    """Main function"""
    load_env_from_dotenv()
    load_dotenv()
    
    api_key = os.getenv('PERPLEXITY_API_KEY')
    if not api_key:
        print("❌ PERPLEXITY_API_KEY not found in environment")
        return
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=_int_env('POSTGRES_PORT', 5432),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        # Step 1: Delete document fragments
        await delete_document_fragments(conn)
        
        # Step 2: Resolve obvious matches
        await resolve_obvious_matches(conn)
        
        # Step 3: Get similar name groups (top 300)
        name_groups = await group_similar_names(conn, limit=300)
        
        if not name_groups:
            print("✅ No similar name groups found needing resolution")
            return
        
        # Step 4: Process in batches of 30
        batch_size = 30
        total_batches = (len(name_groups) + batch_size - 1) // batch_size
        total_renamed = 0
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(name_groups))
            batch = name_groups[start_idx:end_idx]
            
            renamed = await process_perplexity_batch(conn, batch, batch_num + 1, api_key)
            total_renamed += renamed
            
            print(f"\n📊 Progress: {end_idx}/{len(name_groups)} groups processed, {total_renamed} total renamed\n")
            
            # Small delay between batches
            await asyncio.sleep(1)
        
        print(f"\n{'='*60}")
        print(f"✅ COMPLETE: Processed {len(name_groups)} name groups, renamed {total_renamed} groups")
        print(f"{'='*60}\n")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())

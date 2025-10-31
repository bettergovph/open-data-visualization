#!/usr/bin/env python3
"""
Get current congressmen/representatives for each party-list (up to 3 names per party-list)
via Perplexity API and add them to political_dynasties table.

Flow:
1) Load all party-lists from dynasty.party_list table
2) For each party-list, query Perplexity for current congressmen/representatives (2022-2025 term)
3) Parse results and insert into political_dynasties table
4) Link to party_list table
"""

import os
import re
import csv
import asyncio
import asyncpg
import requests
from typing import List, Dict, Optional
from pathlib import Path
from dotenv import load_dotenv


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


async def get_dynasty_conn():
    """Get connection to Dynasty database"""
    return await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=_int_env('POSTGRES_PORT', 5432),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )


async def fetch_all_party_lists(conn) -> List[Dict]:
    """Get all party-lists from the database"""
    rows = await conn.fetch('''
        SELECT code, party_name, id
        FROM party_list
        ORDER BY code, party_name
    ''')
    
    party_lists = []
    for row in rows:
        party_lists.append({
            'code': row.get('code'),
            'party_name': row.get('party_name', '').strip(),
            'id': row.get('id')
        })
    
    return party_lists


def build_prompt(party_lists: List[Dict], batch_num: int, batch_size: int = 10) -> str:
    """Build Perplexity prompt for finding party-list representatives
    
    Process party-lists in batches to avoid overwhelming the API
    """
    start_idx = (batch_num - 1) * batch_size
    end_idx = start_idx + batch_size
    batch = party_lists[start_idx:end_idx]
    
    prompt = f"""# Philippine Party-List Representatives Discovery (Batch {batch_num})

You are a precise research assistant. For each Philippine party-list organization listed below, find the CURRENT (2022-2025 term) congressmen/representatives in the House of Representatives. Each party-list can have up to 3 seats.

## Party-Lists to Analyze (total {len(batch)}):
"""
    
    for i, pl in enumerate(batch, 1):
        code = pl.get('code', '')
        party_name = pl.get('party_name', '')
        prompt += f"{i}. {code}, {party_name}\n"
    
    prompt += f"""
## Your Task:
1. For each party-list, identify the CURRENT congressmen/representatives (2022-2025 term, 19th Congress).
2. Each party-list can have UP TO 3 representatives maximum.
3. Use credible sources (official House of Representatives website, COMELEC results, reputable news). Provide a source URL for each row.
4. For each person, provide their FULL NAME (including middle initials/names if available).

## Return results strictly as CSV text with EXACTLY these columns in this order:
   - party_code (the numeric code from the list above)
   - party_name (the exact party-list name from the list above)
   - person_name (full name of the congressman/representative)
   - position (use: "CONGRESSMAN" or "PARTY-LIST REPRESENTATIVE")
   - source_url (URL where this information was found)
   - confidence_level (1-10, where 10 is most confident - be conservative, only use 10 if absolutely certain from official sources)

STRICT OUTPUT RULES:
- Return a single fenced code block that begins with ```csv and ends with ```.
- Include a single header row followed by data rows.
- Only include complete rows (all columns non-empty).
- Do not include commentary outside the CSV block.
- Use the exact party_code and party_name as listed above (don't normalize or change them).
- Focus on the CURRENT term (2022-2025, 19th Congress). Do not include past or future representatives.
- Maximum 3 representatives per party-list.
- If a party-list has no current representative or you cannot find verified information, simply emit no row for that party-list.

Example:
```csv
party_code,party_name,person_name,position,source_url,confidence_level
35,ABANTE BISDAK,Juan Dela Cruz,CONGRESSMAN,https://example.com,10
35,ABANTE BISDAK,Maria Santos,CONGRESSMAN,https://example.com,9
```
"""
    
    return prompt


def call_perplexity(prompt: str) -> str:
    """Call Perplexity API with the prompt"""
    api_key = os.getenv('PERPLEXITY_API_KEY')
    if not api_key:
        raise RuntimeError('PERPLEXITY_API_KEY not set in environment')
    
    model = os.getenv('PERPLEXITY_MODEL', 'sonar-pro')
    try:
        temperature = float(os.getenv('PERPLEXITY_TEMPERATURE', '0.0'))
    except ValueError:
        temperature = 0.0
    
    url = 'https://api.perplexity.ai/chat/completions'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': model,
        'temperature': temperature,
        'top_p': 1.0,
        'max_tokens': 4000,
        'messages': [
            { 'role': 'system', 'content': 'Return only the requested CSV. Be precise and use credible sources. Focus on CURRENT (2022-2025 term) representatives only.' },
            { 'role': 'user', 'content': prompt }
        ]
    }
    
    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data.get('choices', [{}])[0].get('message', {}).get('content', '') or ''


def extract_csv_from_reply(reply: str) -> str:
    """Extract CSV from Perplexity reply"""
    m = re.search(r"```csv\s*([\s\S]*?)```", reply, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"```[a-zA-Z]*\s*([\s\S]*?)```", reply)
    if m2:
        return m2.group(1).strip()
    return reply.strip()


async def process_csv_results(conn, csv_content: str, batch_num: int):
    """Process CSV results and insert into political_dynasties table"""
    if not csv_content or not csv_content.strip():
        print(f"  ⚠️  Empty CSV content for batch {batch_num}")
        return 0
    
    lines = csv_content.strip().split('\n')
    if len(lines) < 2:
        print(f"  ⚠️  No data rows in CSV for batch {batch_num}")
        return 0
    
    reader = csv.DictReader(lines)
    inserted = 0
    
    for row in reader:
        party_code = (row.get('party_code') or '').strip()
        party_name = (row.get('party_name') or '').strip()
        person_name = (row.get('person_name') or '').strip()
        position = (row.get('position') or 'CONGRESSMAN').strip().upper()
        source_url = (row.get('source_url') or '').strip()
        
        try:
            confidence = int(row.get('confidence_level', '5') or '5')
            confidence = max(1, min(10, confidence))
        except (ValueError, TypeError):
            confidence = 5
        
        if not party_code or not party_name or not person_name:
            continue
        
        # Parse person name - assume format is "FIRST MIDDLE LAST" or "FIRST LAST"
        name_parts = [p.strip().rstrip('.') for p in person_name.strip().split() if p.strip()]
        if len(name_parts) < 2:
            print(f"    ⚠️  Skipping invalid name: {person_name}")
            continue
        
        # For party-list representatives, typically the last word is the last name
        first_name = ' '.join(name_parts[:-1]).upper()
        last_name = name_parts[-1].upper()
        
        # Construct party name for the record
        full_party_name = f"{party_code}, {party_name}".upper()
        
        # Insert into political_dynasties (or update if exists)
        try:
            # Check if already exists
            existing = await conn.fetchval('''
                SELECT id FROM political_dynasties
                WHERE UPPER(TRIM(first_name)) = UPPER($1)
                  AND UPPER(TRIM(last_name)) = UPPER($2)
                  AND UPPER(position) = $3
                  AND year = 2025
            ''', first_name.strip(), last_name.strip(), position)
            
            if existing:
                print(f"    ℹ️  Already exists: {first_name} {last_name} ({position})")
                continue
            
            await conn.execute('''
                INSERT INTO political_dynasties 
                (first_name, last_name, position, party, year, winner)
                VALUES ($1, $2, $3, $4, $5, $6)
            ''', 
            first_name.strip(), last_name.strip(), position, full_party_name, 2025, True)
            
            inserted += 1
            print(f"    ✅ Added: {first_name} {last_name} ({position}, {full_party_name})")
            
        except Exception as e:
            print(f"    ⚠️  Error inserting {person_name}: {e}")
    
    return inserted


async def main():
    """Main function"""
    load_env_from_dotenv()
    load_dotenv()
    
    print("🚀 Starting party-list representatives discovery...")
    
    conn = await get_dynasty_conn()
    
    try:
        # Get all party-lists
        print("\n📋 Fetching party-lists from database...")
        party_lists = await fetch_all_party_lists(conn)
        print(f"✅ Found {len(party_lists)} party-lists")
        
        # Process in batches of 10
        batch_size = 10
        num_batches = (len(party_lists) + batch_size - 1) // batch_size
        
        total_inserted = 0
        
        for batch_num in range(1, num_batches + 1):
            start_idx = (batch_num - 1) * batch_size
            end_idx = min(start_idx + batch_size, len(party_lists))
            batch = party_lists[start_idx:end_idx]
            
            print(f"\n{'='*80}")
            print(f"📄 Batch {batch_num}/{num_batches}: Processing {len(batch)} party-lists")
            print(f"{'='*80}")
            for pl in batch:
                print(f"  - {pl.get('code')}, {pl.get('party_name')}")
            
            # Build prompt
            prompt = build_prompt(party_lists, batch_num, batch_size)
            
            # Call Perplexity
            print(f"\n   🔍 Querying Perplexity...")
            try:
                reply = call_perplexity(prompt)
                
                # Extract CSV
                csv_content = extract_csv_from_reply(reply)
                
                if not csv_content:
                    print(f"   ⚠️  No CSV found in reply")
                    continue
                
                # Save CSV file
                csv_filename = f"party_list_representatives_batch_{batch_num:02d}.csv"
                csv_path = Path(__file__).parent / csv_filename
                
                with open(csv_path, 'w', encoding='utf-8') as f:
                    f.write(csv_content)
                
                print(f"   💾 Saved CSV: {csv_filename}")
                
                # Process results
                print(f"   📥 Processing results...")
                inserted = await process_csv_results(conn, csv_content, batch_num)
                total_inserted += inserted
                
                print(f"   ✅ Inserted {inserted} representatives")
                
                # Small delay between batches to avoid rate limiting
                if batch_num < num_batches:
                    await asyncio.sleep(2)
                
            except Exception as e:
                print(f"   ❌ Error processing batch {batch_num}: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"\n{'='*80}")
        print(f"✅ Discovery complete! Total representatives inserted: {total_inserted}")
        print(f"{'='*80}")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())


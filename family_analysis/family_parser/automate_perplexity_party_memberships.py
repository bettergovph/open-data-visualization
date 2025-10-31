#!/usr/bin/env python3
"""
Automate party membership discovery via Perplexity API and store in party_memberships table.

Steps:
1) Load DB and API credentials from .env
2) Query dynasty DB to get senator names (prioritize unprocessed)
3) Build prompt asking for party membership CSV with dates
4) Call Perplexity Chat Completions API
5) Extract CSV text, parse and insert into party_memberships table
"""

import os
import re
import csv
import asyncio
import asyncpg
import requests
from typing import List, Dict
from dotenv import load_dotenv
from datetime import datetime


def normalize_name_for_query(full_name: str) -> str:
    """Normalize name by removing middle initials and extra spaces for deduplication"""
    if not full_name:
        return ""
    name = re.sub(r"\b([A-Z])\.(?:\s*([A-Z])\.)?\b", " ", full_name.upper())
    name = re.sub(r"\s+", " ", name).strip()
    return name


async def get_db_connection():
    return await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )


async def fetch_senator_names(conn, limit: int) -> List[Dict]:
    """Fetch unique normalized senator names that haven't been processed for party data"""
    senator_rows = await conn.fetch(
        """
        SELECT DISTINCT
            id,
            CONCAT(first_name, ' ', last_name) AS full_name,
            province,
            position,
            year
        FROM political_dynasties
        WHERE first_name IS NOT NULL AND first_name <> ''
          AND last_name IS NOT NULL AND last_name <> ''
          AND position ILIKE '%SENATOR%'
          AND id NOT IN (
            SELECT DISTINCT person_id FROM party_memberships
          )
        ORDER BY year DESC
        LIMIT $1
        """,
        limit * 3,  # Get more to account for deduplication
    )
    
    # Normalize and deduplicate senators in Python
    seen_normalized = set()
    unique_senators = []
    for row in senator_rows:
        normalized = normalize_name_for_query(row['full_name'])
        if normalized and normalized not in seen_normalized:
            seen_normalized.add(normalized)
            unique_senators.append(dict(row))
            if len(unique_senators) >= limit:
                break
    
    return unique_senators


def build_party_prompt(names: List[Dict], prompt_num: int, names_per_prompt: int) -> str:
    """Build prompt for Perplexity to get party membership data"""
    name_list = [f"{n['full_name']} (ID: {n['id']})" for n in names]
    
    prompt = f"""# Philippine Senator Party Membership Research Prompt

You are a political research analyst specializing in Philippine politics. Your task is to find the political party affiliations for the following senators and return the findings in CSV format.

## Senators to Research:
"""
    
    for i in range(0, len(name_list), 10):
        batch_names = name_list[i:i+10]
        prompt += "\n".join(batch_names) + "\n"
    
    prompt += f"""
## Your Task:
1. For each senator listed above, research their political party affiliations throughout their career:
   - Current party (as of 2024-2025)
   - Previous parties (if they switched parties)
   - Dates when they joined each party (approximate year/month if available)
   - Dates when they left each party (if applicable)
   - Position within party (e.g., "Member", "Secretary", "President", "Vice President")

2. Consider that Philippine politicians often change parties based on:
   - Presidential administrations
   - Political alliances
   - Party mergers and splits

3. Return results as CSV text with EXACTLY these columns (in this order):
   - person_id (use the ID from the list above)
   - person_name (full name)
   - party_name (official party name, e.g., "Partido Demokratiko Pilipino-Lakas ng Bayan", "Nacionalista Party")
   - party_abbreviation (if known, e.g., "PDP-Laban", "NP")
   - joined_date (format: YYYY-MM-DD, use approximate dates like YYYY-01-01 if only year known)
   - left_date (format: YYYY-MM-DD, NULL if still current member)
   - is_current (TRUE or FALSE)
   - position_in_party (e.g., "Member", "Secretary General", "Chairman")
   - source_url (verifiable source for this information)
   - confidence_level (1-10, based on source reliability)

STRICT OUTPUT RULES:
- Return a single fenced code block that begins with ```csv and ends with ```.
- The CSV MUST include a single header row followed by data rows.
- Include ONLY complete rows with person_id, person_name, party_name, and source_url non-empty.
- If a senator has multiple party affiliations over time, include ONE ROW per party.
- If a senator has no verifiable party information, do NOT include them in the output.
- Use NULL (not quoted) for missing optional fields like left_date.
- Dates should be in YYYY-MM-DD format. If only year is known, use YYYY-01-01.
- If a politician switched parties multiple times, include all known party memberships as separate rows.

COVERAGE REQUIREMENT:
- You MUST research ALL {names_per_prompt} senators listed above.
- Focus on major parties like: PDP-Laban, Liberal Party, Nacionalista Party, Lakas-CMD, NPC, etc.
- Include party switches during presidential transitions (e.g., Duterte to Marcos administrations).

## Example Output (format ONLY):
```csv
person_id,person_name,party_name,party_abbreviation,joined_date,left_date,is_current,position_in_party,source_url,confidence_level
4041412,"JINGGOY EJERCITO ESTRADA","Partido Demokratiko Pilipino-Lakas ng Bayan","PDP-Laban","2022-06-01",NULL,TRUE,"Member","https://senate.gov.ph/senators/estrada",9
4041412,"JINGGOY EJERCITO ESTRADA","Pwersa ng Masang Pilipino","PMP","2004-01-01","2022-05-31",FALSE,"Member","https://example.org/pmphistory",8
3751220,"IMEE MARCOS","Partido Federal ng Pilipinas","PFP","2021-01-01",NULL,TRUE,"Member","https://example.org/pfp",9
```
"""
    
    return prompt


def call_llm(prompt: str) -> str:
    """Call Perplexity API"""
    provider = os.getenv('LLM_PROVIDER', 'perplexity').lower()
    if provider == 'openai':
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set in environment")
        model = os.getenv('OPENAI_MODEL', 'gpt-4o')
        try:
            temperature = float(os.getenv('OPENAI_TEMPERATURE', '0.0'))
        except ValueError:
            temperature = 0.0
        url = 'https://api.openai.com/v1/chat/completions'
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        payload = {
            'model': model,
            'temperature': temperature,
            'max_tokens': 4000,
            'messages': [
                { 'role': 'system', 'content': 'You are a precise research assistant. Return only the requested CSV.' },
                { 'role': 'user', 'content': prompt }
            ]
        }
    else:
        api_key = os.getenv('PERPLEXITY_API_KEY')
        if not api_key:
            raise RuntimeError("PERPLEXITY_API_KEY not set in environment")
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
                { 'role': 'system', 'content': 'You are a precise research assistant. Return only the requested CSV.' },
                { 'role': 'user', 'content': prompt }
            ]
        }

    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
    return content or ''


def extract_csv_from_reply(reply: str) -> str:
    """Extract CSV text from LLM reply"""
    m = re.search(r"```csv\s*([\s\S]*?)```", reply, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"```[a-zA-Z]*\s*([\s\S]*?)```", reply)
    if m2:
        return m2.group(1).strip()
    return reply.strip()


async def process_party_csv(conn, csv_text: str, batch_num: int) -> int:
    """Process CSV and insert party memberships into database"""
    reader = csv.DictReader(csv_text.split('\n'))
    inserted = 0
    
    for row in reader:
        try:
            person_id = int(row.get('person_id', '0'))
            person_name = (row.get('person_name') or '').strip()
            party_name = (row.get('party_name') or '').strip()
            party_abbreviation = (row.get('party_abbreviation') or '').strip() or None
            joined_date_str = (row.get('joined_date') or '').strip()
            left_date_str = (row.get('left_date') or '').strip() or None
            is_current_str = (row.get('is_current') or '').strip().upper()
            position_in_party = (row.get('position_in_party') or '').strip() or None
            source_url = (row.get('source_url') or '').strip() or None
            confidence_level = int(row.get('confidence_level') or 5)
            
            if not person_id or not party_name:
                continue
            
            # Parse dates
            joined_date = None
            if joined_date_str and joined_date_str.upper() != 'NULL':
                try:
                    joined_date = datetime.strptime(joined_date_str, '%Y-%m-%d').date()
                except ValueError:
                    # Try just year
                    try:
                        year = int(joined_date_str[:4])
                        joined_date = datetime(year, 1, 1).date()
                    except:
                        pass
            
            left_date = None
            if left_date_str and left_date_str.upper() not in ('NULL', ''):
                try:
                    left_date = datetime.strptime(left_date_str, '%Y-%m-%d').date()
                except ValueError:
                    try:
                        year = int(left_date_str[:4])
                        left_date = datetime(year, 12, 31).date()
                    except:
                        pass
            
            # Determine if current
            is_current = False
            if is_current_str in ('TRUE', '1', 'YES', 'Y'):
                is_current = True
            elif left_date is None or (left_date and left_date >= datetime.now().date()):
                is_current = True
            
            # Ensure party exists
            party_id = await conn.fetchval("""
                SELECT id FROM political_parties WHERE name = $1
            """, party_name)
            
            if not party_id:
                party_id = await conn.fetchval("""
                    INSERT INTO political_parties (name, abbreviation)
                    VALUES ($1, $2)
                    RETURNING id
                """, party_name, party_abbreviation)
                print(f"   ➕ Created party: {party_name}")
            
            # Insert membership
            try:
                await conn.execute("""
                    INSERT INTO party_memberships (
                        person_id, party_id, joined_date, left_date, is_current,
                        position_in_party, source_url, confidence_level
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (person_id, party_id, joined_date) DO NOTHING
                """, person_id, party_id, joined_date, left_date, is_current,
                    position_in_party, source_url, confidence_level)
                inserted += 1
                print(f"   ✅ Added party membership: {person_name} → {party_name}")
            except Exception as e:
                print(f"   ⚠️  Error inserting membership for {person_name}: {e}")
        
        except Exception as e:
            print(f"   ❌ Error processing row: {e}")
            continue
    
    return inserted


async def main():
    load_dotenv()
    
    senators_per_batch = int(os.getenv('SENATORS_PER_PARTY_BATCH', '40'))
    max_batches = int(os.getenv('MAX_PARTY_BATCHES', '2'))
    
    conn = await get_db_connection()
    
    try:
        # Ensure tables exist
        print("🏗️ Ensuring party tables exist...")
        from create_party_memberships_table import create_party_tables
        await create_party_tables()
        
        batch_num = 1
        batches_processed = 0
        
        while batches_processed < max_batches:
            # Fetch senators
            senator_names = await fetch_senator_names(conn, senators_per_batch)
            if not senator_names:
                print("✅ No more senators to process. Done.")
                break
            
            print(f"\n📋 Processing batch {batch_num}: {len(senator_names)} senators")
            
            # Build prompt
            prompt = build_party_prompt(senator_names, batch_num, len(senator_names))
            
            # Call Perplexity
            print(f"🚀 Sending party membership prompt to LLM (batch {batch_num})...")
            reply = call_llm(prompt)
            
            # Extract CSV
            csv_text = extract_csv_from_reply(reply)
            if not csv_text or ',' not in csv_text:
                print("❌ Could not extract CSV from reply")
                batch_num += 1
                continue
            
            # Save CSV for reference
            out_file = f"llm_party_memberships_{batch_num:03d}.csv"
            with open(out_file, 'w', encoding='utf-8', newline='') as f:
                f.write(csv_text if csv_text.endswith('\n') else csv_text + '\n')
            print(f"✅ Saved CSV to {out_file}")
            
            # Process and insert
            inserted = await process_party_csv(conn, csv_text, batch_num)
            print(f"📊 Inserted {inserted} party membership records")
            
            batches_processed += 1
            batch_num += 1
        
        # Show summary
        summary = await conn.fetch("""
            SELECT 
                COUNT(DISTINCT person_id) as unique_persons,
                COUNT(DISTINCT party_id) as unique_parties,
                COUNT(*) as total_memberships,
                COUNT(*) FILTER (WHERE is_current = TRUE) as current_memberships
            FROM party_memberships
        """)
        
        if summary:
            row = summary[0]
            print(f"\n📊 Final Party Memberships Summary:")
            print(f"   - Unique persons: {row['unique_persons']}")
            print(f"   - Unique parties: {row['unique_parties']}")
            print(f"   - Total memberships: {row['total_memberships']}")
            print(f"   - Current memberships: {row['current_memberships']}")
    
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())


#!/usr/bin/env python3
"""
Verify top 15 contractors - one contractor per page via Perplexity API.
Find owners, officers, directors for each contractor.

Flow:
1) Load top 15 contractors from file or DB
2) Process 1 contractor per page (15 pages total)
3) For each contractor, query Perplexity for owners/officers/directors
4) Save results as CSV files (verify_contractor_<page>_<company>.csv)
5) Insert into dynasty.company_affiliations table
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


async def get_sec_conn():
    """Get connection to SEC database"""
    return await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=_int_env('POSTGRES_PORT', 5432),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_SEC', 'sec')
    )


async def get_dynasty_conn():
    """Get connection to Dynasty database"""
    return await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=_int_env('POSTGRES_PORT', 5432),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )


async def ensure_aux_tables(sec_conn, dynasty_conn):
    """Ensure auxiliary tables exist for tracking processed companies"""
    # Track processed companies in SEC DB to avoid repeats
    table_exists = await sec_conn.fetchval(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'llm_processed_companies'
        )
        """
    )
    
    if not table_exists:
        await sec_conn.execute(
            """
            CREATE TABLE llm_processed_companies (
                id SERIAL PRIMARY KEY,
                contractor_name TEXT UNIQUE,
                normalized_name TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    # Store affiliations in DYNASTY DB
    await dynasty_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS company_affiliations (
            id SERIAL PRIMARY KEY,
            company_name TEXT NOT NULL,
            person_name TEXT NOT NULL,
            role TEXT,
            source_url TEXT,
            confidence_level INTEGER CHECK (confidence_level >= 1 AND confidence_level <= 10),
            sec_number TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(company_name, person_name, role)
        )
        """
    )
    
    await dynasty_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS contractor_dynasty_matches (
            id SERIAL PRIMARY KEY,
            company_name TEXT NOT NULL,
            person_name TEXT,
            role TEXT,
            dynasty_full_name TEXT,
            dynasty_first_name TEXT,
            dynasty_last_name TEXT,
            matched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source_csv_file TEXT,
            UNIQUE(company_name, dynasty_full_name)
        )
        """
    )


async def fetch_top_15_contractors(sec_conn) -> List[Dict]:
    """Get top 15 unique contractors by project count"""
    
    rows = await sec_conn.fetch(
        """
        SELECT DISTINCT ON (UPPER(contractor_name))
            contractor_name,
            MAX(COALESCE(project_count, 0)) as project_count,
            MAX(sec_number) FILTER (WHERE sec_number IS NOT NULL) as sec_number
        FROM contractors
        WHERE contractor_name IS NOT NULL 
          AND contractor_name <> ''
          AND project_count > 0
        GROUP BY UPPER(contractor_name), contractor_name
        ORDER BY UPPER(contractor_name), MAX(COALESCE(project_count, 0)) DESC
        LIMIT 15
        """
    )
    
    contractors = []
    for row in rows:
        contractors.append({
            'contractor_name': row.get('contractor_name', '').strip(),
            'project_count': row.get('project_count', 0) or 0,
            'sec_number': row.get('sec_number'),
        })
    
    # Re-sort by project count
    contractors.sort(key=lambda x: x['project_count'], reverse=True)
    return contractors[:15]


def build_prompt(contractor: Dict, page_num: int) -> str:
    """Build Perplexity prompt for finding company officers for a single contractor"""
    
    company_name = contractor['contractor_name']
    sec_info = f"\n   SEC Number: {contractor['sec_number']}" if contractor.get('sec_number') else ""
    
    prompt = f"""# Philippine Company Officers Verification (Page {page_num}/15)

You are a precise research assistant. Find verifiable details about the owners, incorporators, officers, and directors of this Philippine company. Return only a CSV in a single fenced code block.

## Company to Analyze:
1. {company_name}{sec_info}

## Your Task:
1. Identify individuals who are: owners, incorporators, directors, officers, or key personnel (e.g., President, Treasurer, Corporate Secretary, Chairman, CEO, Vice President, Manager).
2. Use credible sources (SEC submissions, SEC EDGAR, reputable news, official company documents, business registries). Provide a source URL for each row.
3. For each person found, provide their FULL NAME (including middle initials/names if available).

## Return results strictly as CSV text with EXACTLY these columns in this order:
   - company_name (use the exact company name: "{company_name}")
   - person_name (full name of the individual)
   - role (owner, director, officer, incorporator, president, treasurer, secretary, chairman, ceo, vice president, manager, etc.)
   - source_url (URL where this information was found)
   - confidence_level (1-10, where 10 is most confident - be conservative, only use 10 if absolutely certain from official SEC documents)

STRICT OUTPUT RULES:
- Return a single fenced code block that begins with ```csv and ends with ```.
- Include a single header row followed by data rows.
- Only include complete rows (all columns non-empty).
- Do not include commentary outside the CSV block.
- Use the exact company_name: "{company_name}" (don't normalize or change it).
- If a person has multiple roles, create separate rows for each role.
- Be thorough - search for all officers, directors, and key personnel.

If no data is found for this company, return only the CSV header row.
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
            { 'role': 'system', 'content': 'Return only the requested CSV. Be precise and use credible sources. Return complete information.' },
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


async def find_matching_dynasty_names(dynasty_conn, person_name: str) -> List[str]:
    """Check if person_name exists in dynasty database with flexible matching"""
    name_parts = [p.strip().rstrip('.') for p in person_name.strip().split() if p.strip()]
    if len(name_parts) < 2:
        return []
    
    matches = []
    seen_matches = set()
    
    # Try different first/last splits
    for i in range(1, len(name_parts)):
        first_name = ' '.join(name_parts[:i])
        last_name = ' '.join(name_parts[i:])
        
        if first_name and last_name:
            rows = await dynasty_conn.fetch(
                """
                SELECT DISTINCT CONCAT(first_name, ' ', last_name) as full_name,
                       first_name, last_name
                FROM political_dynasties
                WHERE UPPER(TRIM(first_name)) = UPPER($1)
                  AND UPPER(TRIM(last_name)) = UPPER($2)
                LIMIT 10
                """,
                first_name.strip(), last_name.strip()
            )
            
            for row in rows:
                full = row['full_name']
                if full and full not in seen_matches:
                    seen_matches.add(full)
                    matches.append(full)
    
    return matches


async def process_csv_results(dynasty_conn, csv_content: str, company_name: str, sec_number: Optional[str], csv_filename: str):
    """Process CSV results and insert into database"""
    if not csv_content or not csv_content.strip():
        print(f"  ⚠️  Empty CSV content for {company_name}")
        return 0, 0
    
    lines = csv_content.strip().split('\n')
    if len(lines) < 2:
        print(f"  ⚠️  No data rows in CSV for {company_name}")
        return 0, 0
    
    reader = csv.DictReader(lines)
    affiliations_inserted = 0
    matches_found = 0
    
    for row in reader:
        person_name = (row.get('person_name') or '').strip()
        role = (row.get('role') or '').strip()
        source_url = (row.get('source_url') or '').strip()
        
        try:
            confidence = int(row.get('confidence_level', '5') or '5')
            confidence = max(1, min(10, confidence))
        except (ValueError, TypeError):
            confidence = 5
        
        if not person_name or not role:
            continue
        
        # Insert into company_affiliations
        try:
            await dynasty_conn.execute(
                """
                INSERT INTO company_affiliations 
                (company_name, person_name, role, source_url, confidence_level, sec_number)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (company_name, person_name, role) DO UPDATE
                SET source_url = EXCLUDED.source_url,
                    confidence_level = EXCLUDED.confidence_level,
                    sec_number = EXCLUDED.sec_number
                """,
                company_name, person_name, role, source_url, confidence, sec_number
            )
            affiliations_inserted += 1
        except Exception as e:
            print(f"    ⚠️  Error inserting affiliation {person_name}: {e}")
        
        # Check if person matches dynasty database
        dynasty_matches = await find_matching_dynasty_names(dynasty_conn, person_name)
        
        for match in dynasty_matches:
            # Parse match to get first and last name
            name_parts = match.split(None, 1)
            if len(name_parts) >= 2:
                first_name = name_parts[0]
                last_name = name_parts[1]
            else:
                continue
            
            try:
                await dynasty_conn.execute(
                    """
                    INSERT INTO contractor_dynasty_matches
                    (company_name, person_name, role, dynasty_full_name, dynasty_first_name, dynasty_last_name, source_csv_file)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (company_name, dynasty_full_name) DO UPDATE
                    SET person_name = EXCLUDED.person_name,
                        role = EXCLUDED.role,
                        source_csv_file = EXCLUDED.source_csv_file
                    """,
                    company_name, person_name, role, match, first_name, last_name, csv_filename
                )
                matches_found += 1
                print(f"    ✅ Match: {person_name} -> {match} (role: {role})")
            except Exception as e:
                print(f"    ⚠️  Error inserting match {match}: {e}")
    
    return affiliations_inserted, matches_found


async def main():
    """Main function"""
    load_env_from_dotenv()
    load_dotenv()
    
    print("🚀 Starting contractor verification (1 contractor per page)...")
    
    sec_conn = await get_sec_conn()
    dynasty_conn = await get_dynasty_conn()
    
    try:
        await ensure_aux_tables(sec_conn, dynasty_conn)
        
        # Get top 15 contractors
        print("\n📋 Fetching top 15 contractors...")
        contractors = await fetch_top_15_contractors(sec_conn)
        print(f"✅ Found {len(contractors)} contractors")
        
        for i, contractor in enumerate(contractors, 1):
            company_name = contractor['contractor_name']
            sec_number = contractor.get('sec_number')
            
            print(f"\n{'='*80}")
            print(f"📄 Page {i}/15: Processing {company_name}")
            print(f"{'='*80}")
            print(f"   Projects: {contractor['project_count']}")
            if sec_number:
                print(f"   SEC: {sec_number}")
            
            # Build prompt
            prompt = build_prompt(contractor, i)
            
            # Call Perplexity
            print(f"   🔍 Querying Perplexity...")
            try:
                reply = call_perplexity(prompt)
                
                # Extract CSV
                csv_content = extract_csv_from_reply(reply)
                
                if not csv_content:
                    print(f"   ⚠️  No CSV found in reply")
                    continue
                
                # Save CSV file
                safe_name = re.sub(r'[^\w\s-]', '', company_name)[:50]
                csv_filename = f"verify_contractor_{i:02d}_{safe_name.replace(' ', '_')}.csv"
                csv_path = Path(__file__).parent / csv_filename
                
                with open(csv_path, 'w', encoding='utf-8') as f:
                    f.write(csv_content)
                
                print(f"   💾 Saved CSV: {csv_filename}")
                
                # Process results
                print(f"   📥 Processing results...")
                affiliations, matches = await process_csv_results(
                    dynasty_conn, csv_content, company_name, sec_number, csv_filename
                )
                
                print(f"   ✅ Inserted {affiliations} affiliations, found {matches} dynasty matches")
                
            except Exception as e:
                print(f"   ❌ Error processing {company_name}: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"\n{'='*80}")
        print("✅ Verification complete!")
        print(f"{'='*80}")
        
    finally:
        await sec_conn.close()
        await dynasty_conn.close()


if __name__ == '__main__':
    asyncio.run(main())


#!/usr/bin/env python3
"""
Get top 400 normalized contractor names (40 per page) and find owners, officers, directors
via Perplexity API.

Flow:
1) Load DB credentials from .env
2) Get top 400 normalized contractor names by project count (excluding already processed)
3) Process 40 contractors per batch/page
4) For each batch, query Perplexity for owners/officers/directors
5) Save results as CSV files (llm_contractor_officers_<page>.csv)
6) Insert into dynasty.company_affiliations table
"""

import os
import re
import csv
import asyncio
import asyncpg
import requests
from typing import List, Dict
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


def normalize_contractor_name(name: str) -> str:
    """Normalize contractor name for consistent matching"""
    if not name:
        return ""
    
    # Convert to uppercase
    normalized = name.upper().strip()
    
    # Remove common punctuation and extra spaces
    normalized = normalized.replace('.', ' ')
    normalized = normalized.replace(',', ' ')
    normalized = normalized.replace('-', ' ')
    normalized = normalized.replace('&', 'AND')
    normalized = normalized.replace("'", '')
    normalized = re.sub(r'\s+', ' ', normalized)
    normalized = normalized.strip()
    
    # Remove common suffixes for better matching
    suffixes_to_remove = [
        'CORPORATION', 'CORP', 'INC', 'INCORPORATED', 'CO', 'COMPANY',
        'LTD', 'LIMITED', 'ENTERPRISES', 'ENTERPRISE'
    ]
    
    words = normalized.split()
    filtered_words = [w for w in words if w not in suffixes_to_remove]
    
    return ' '.join(filtered_words) if filtered_words else normalized


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
    # Check if table exists and what columns it has
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
    else:
        # Check if contractor_name column exists, if not, it might be company_name
        contractor_name_col = await sec_conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.columns 
                WHERE table_schema = 'public' 
                AND table_name = 'llm_processed_companies'
                AND column_name = 'contractor_name'
            )
            """
        )
        if not contractor_name_col:
            # Try to add the column if it doesn't exist
            try:
                await sec_conn.execute(
                    """
                    ALTER TABLE llm_processed_companies 
                    ADD COLUMN IF NOT EXISTS contractor_name TEXT
                    """
                )
            except Exception:
                pass

    # Store affiliations in DYNASTY DB
    await dynasty_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS company_affiliations (
            id SERIAL PRIMARY KEY,
            company_name TEXT NOT NULL,
            person_name TEXT NOT NULL,
            role TEXT NOT NULL,
            source_url TEXT,
            confidence_level INT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    
    # Add unique constraint if it doesn't exist
    try:
        await dynasty_conn.execute(
            """
            ALTER TABLE company_affiliations 
            ADD CONSTRAINT company_affiliations_unique 
            UNIQUE (company_name, person_name, role)
            """
        )
    except Exception:
        # Constraint already exists or couldn't be created
        pass
    
    # Create table for tracking dynasty matches
    await dynasty_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS contractor_dynasty_matches (
            id SERIAL PRIMARY KEY,
            company_name TEXT NOT NULL,
            person_name TEXT NOT NULL,
            role TEXT NOT NULL,
            dynasty_full_name TEXT NOT NULL,
            dynasty_first_name TEXT NOT NULL,
            dynasty_last_name TEXT NOT NULL,
            matched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source_csv_file TEXT,
            UNIQUE(company_name, person_name, role, dynasty_full_name)
        )
        """
    )
    
    # Create index for faster lookups
    try:
        await dynasty_conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_contractor_dynasty_matches_person 
            ON contractor_dynasty_matches(person_name, dynasty_full_name)
            """
        )
    except Exception:
        pass


async def fetch_top_normalized_contractors(sec_conn, limit: int = 400) -> List[Dict]:
    """Get top normalized contractor names by project count"""
    
        # Check what column name exists in llm_processed_companies
    processed_col_exists = await sec_conn.fetchval(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = 'llm_processed_companies'
            AND column_name = 'contractor_name'
        )
        """
    )
    
    # Use the appropriate column name for filtering
    if processed_col_exists:
        exclude_clause = "c.contractor_name NOT IN (SELECT contractor_name FROM llm_processed_companies WHERE contractor_name IS NOT NULL)"
    else:
        # Fallback: check if company_name column exists (from old schema)
        company_col_exists = await sec_conn.fetchval(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.columns 
                WHERE table_schema = 'public' 
                AND table_name = 'llm_processed_companies'
                AND column_name = 'company_name'
            )
            """
        )
        if company_col_exists:
            exclude_clause = "c.contractor_name NOT IN (SELECT company_name FROM llm_processed_companies WHERE company_name IS NOT NULL)"
        else:
            # No exclusion table or different schema - process all
            exclude_clause = "1=1"
    
    # Query to get contractors, handling duplicates by taking max project_count
    rows = await sec_conn.fetch(
        f"""
        SELECT 
            contractor_name,
            MAX(COALESCE(project_count, 0)) as project_count,
            MAX(sec_number) FILTER (WHERE sec_number IS NOT NULL) as sec_number
        FROM contractors c
        WHERE c.contractor_name IS NOT NULL 
          AND c.contractor_name <> ''
          AND {exclude_clause}
        GROUP BY contractor_name
        ORDER BY MAX(COALESCE(project_count, 0)) DESC, contractor_name
        LIMIT $1
        """,
        limit * 2  # Get more to deduplicate by normalized name
    )
    
    # Process results and compute normalized names, then deduplicate
    contractors = []
    seen_normalized = set()
    
    for row in rows:
        contractor_name = row.get('contractor_name', '').strip()
        if not contractor_name:
            continue
        
        # Compute normalized name
        normalized = normalize_contractor_name(contractor_name)
        
        # Deduplicate by normalized name (keep highest project_count)
        if normalized in seen_normalized:
            continue
        seen_normalized.add(normalized)
        
        contractors.append({
            'contractor_name': contractor_name,
            'normalized_name': normalized,
            'project_count': row.get('project_count', 0) or 0,
            'sec_number': row.get('sec_number'),
            'company_name': contractor_name  # Use contractor_name as company_name
        })
    
    # Sort by project count and return top limit
    contractors.sort(key=lambda x: x['project_count'], reverse=True)
    return contractors[:limit]


def build_prompt(contractors: List[Dict], page_num: int) -> str:
    """Build Perplexity prompt for finding company officers"""
    
    prompt = f"""# Philippine Company Officers Discovery Prompt (Page {page_num})

You are a precise research assistant. For each Philippine company listed below, find verifiable details about its owners, incorporators, officers, and directors. Return only a CSV in a single fenced code block.

## Companies to Analyze (total {len(contractors)}):
"""
    
    for i, c in enumerate(contractors, 1):
        names = [c['contractor_name']]
        if c.get('company_name') and c['company_name'] != c['contractor_name']:
            names.append(c['company_name'])
        prompt += f"{i}. {', '.join(set(names))}\n"
        if c.get('sec_number'):
            prompt += f"   SEC Number: {c['sec_number']}\n"
    
    prompt += f"""
## Your Task:
1. For each company, identify individuals who are: owners, incorporators, directors, officers, or key personnel (e.g., President, Treasurer, Corporate Secretary, Chairman, CEO).
2. Use credible sources (SEC submissions, SEC EDGAR, reputable news, official company documents). Provide a source URL for each row.
3. Return results strictly as CSV text with EXACTLY these columns in this order:
   - company_name (use the exact company name from the list above)
   - person_name (full name of the individual)
   - role (owner, director, officer, incorporator, president, treasurer, secretary, etc.)
   - source_url (URL where this information was found)
   - confidence_level (1-10, where 10 is most confident)

STRICT OUTPUT RULES:
- Return a single fenced code block that begins with ```csv and ends with ```.
- Include a single header row followed by data rows.
- Only include complete rows (all columns non-empty).
- Do not include commentary outside the CSV block.
- Use the exact company_name as listed above (don't normalize or change it).

If no data is found for a company, simply emit no row for that company.
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
            { 'role': 'system', 'content': 'Return only the requested CSV. Be precise and use credible sources.' },
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
    # Clean and normalize name
    name_parts = [p.strip().rstrip('.') for p in person_name.strip().split() if p.strip()]
    if len(name_parts) < 2:
        return []
    
    matches = []
    seen_matches = set()
    
    # Strategy 1: Try exact matches with different first/last splits
    # (e.g., "Alfredo S. Lim" -> try "Alfredo" + "S Lim", "Alfredo S" + "Lim", etc.)
    for i in range(1, len(name_parts)):
        first_name = ' '.join(name_parts[:i])
        last_name = ' '.join(name_parts[i:])
        
        if first_name and last_name:
            rows = await dynasty_conn.fetch(
                """
                SELECT DISTINCT CONCAT(first_name, ' ', last_name) as full_name
                FROM political_dynasties
                WHERE UPPER(TRIM(first_name)) = UPPER(TRIM($1))
                  AND UPPER(TRIM(last_name)) = UPPER(TRIM($2))
                LIMIT 5
                """,
                first_name, last_name
            )
            for row in rows:
                if row['full_name'] not in seen_matches:
                    matches.append(row['full_name'])
                    seen_matches.add(row['full_name'])
    
    # Strategy 2: Try matching with middle initials removed
    # (e.g., "Alfredo S. Lim" -> try "Alfredo" + "Lim")
    if len(name_parts) >= 3:
        # Remove single-letter middle names/initials
        filtered_parts = [p for p in name_parts if len(p) > 1 or not p[0].isupper()]
        if len(filtered_parts) >= 2 and filtered_parts != name_parts:
            first_name = filtered_parts[0]
            last_name = ' '.join(filtered_parts[1:])
            rows = await dynasty_conn.fetch(
                """
                SELECT DISTINCT CONCAT(first_name, ' ', last_name) as full_name
                FROM political_dynasties
                WHERE UPPER(TRIM(first_name)) = UPPER(TRIM($1))
                  AND UPPER(TRIM(last_name)) = UPPER(TRIM($2))
                LIMIT 5
                """,
                first_name, last_name
            )
            for row in rows:
                if row['full_name'] not in seen_matches:
                    matches.append(row['full_name'])
                    seen_matches.add(row['full_name'])
    
    # Strategy 3: Try surname-only matching if we have a common surname
    # (Check if last name matches and first name starts with same letter)
    if len(name_parts) >= 2:
        first_part = name_parts[0]
        last_part = name_parts[-1]
        if first_part and last_part and len(first_part) >= 2:
            # Try matching last name and first name starting with same letter
            rows = await dynasty_conn.fetch(
                """
                SELECT DISTINCT CONCAT(first_name, ' ', last_name) as full_name
                FROM political_dynasties
                WHERE UPPER(TRIM(last_name)) = UPPER(TRIM($1))
                  AND UPPER(LEFT(TRIM(first_name), 1)) = UPPER(LEFT(TRIM($2), 1))
                  AND LENGTH(TRIM(first_name)) >= 2
                LIMIT 3
                """,
                last_part, first_part
            )
            for row in rows:
                if row['full_name'] not in seen_matches:
                    matches.append(row['full_name'])
                    seen_matches.add(row['full_name'])
    
    return matches


async def upsert_company_affiliations(dynasty_conn, csv_path: str) -> int:
    """Insert company affiliations from CSV into database and check for dynasty matches"""
    created = 0
    matched_count = 0
    match_details = []
    
    if not os.path.exists(csv_path):
        return created, match_details
    
    csv_filename = os.path.basename(csv_path)
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            company_name = (row.get('company_name') or '').strip()
            person_name = (row.get('person_name') or '').strip()
            role = (row.get('role') or '').strip()
            source_url = (row.get('source_url') or '').strip()
            try:
                confidence_level = int(row.get('confidence_level') or 0)
            except ValueError:
                confidence_level = 0
            
            if not company_name or not person_name or not role:
                continue
            
            # Check if person exists in dynasty database
            dynasty_matches = await find_matching_dynasty_names(dynasty_conn, person_name)
            
            # Insert into company_affiliations (try with ON CONFLICT, fallback to simple insert)
            try:
                result = await dynasty_conn.execute(
                    """
                    INSERT INTO company_affiliations (
                        company_name, person_name, role, source_url, confidence_level
                    ) VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (company_name, person_name, role) DO NOTHING
                    """,
                    company_name, person_name, role, source_url, confidence_level
                )
                # Check if row was inserted (result includes "INSERT 0 1" or "INSERT 0 0")
                if 'INSERT 0 1' in result or result.startswith('INSERT') and '0 1' in result:
                    created += 1
            except Exception:
                # Fallback: try without ON CONFLICT (check first, then insert)
                try:
                    existing = await dynasty_conn.fetchval(
                        """
                        SELECT id FROM company_affiliations
                        WHERE company_name = $1 AND person_name = $2 AND role = $3
                        """,
                        company_name, person_name, role
                    )
                    if not existing:
                        await dynasty_conn.execute(
                            """
                            INSERT INTO company_affiliations (
                                company_name, person_name, role, source_url, confidence_level
                            ) VALUES ($1, $2, $3, $4, $5)
                            """,
                            company_name, person_name, role, source_url, confidence_level
                        )
                        created += 1
                except Exception:
                    pass
            
            # Store dynasty matches in tracking table
            if dynasty_matches:
                matched_count += 1
                for dynasty_name in dynasty_matches:
                    # Parse dynasty name
                    name_parts = dynasty_name.split()
                    dynasty_first = name_parts[0] if name_parts else ''
                    dynasty_last = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
                    
                    match_details.append({
                        'company_name': company_name,
                        'person_name': person_name,
                        'role': role,
                        'dynasty_full_name': dynasty_name,
                        'dynasty_first_name': dynasty_first,
                        'dynasty_last_name': dynasty_last,
                        'source_csv': csv_filename
                    })
                    
                    try:
                        await dynasty_conn.execute(
                            """
                            INSERT INTO contractor_dynasty_matches (
                                company_name, person_name, role, 
                                dynasty_full_name, dynasty_first_name, dynasty_last_name,
                                source_csv_file
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                            ON CONFLICT (company_name, person_name, role, dynasty_full_name) DO NOTHING
                            """,
                            company_name, person_name, role, dynasty_name,
                            dynasty_first, dynasty_last, csv_filename
                        )
                    except Exception:
                        # Try without ON CONFLICT
                        try:
                            existing = await dynasty_conn.fetchval(
                                """
                                SELECT id FROM contractor_dynasty_matches
                                WHERE company_name = $1 AND person_name = $2 
                                  AND role = $3 AND dynasty_full_name = $4
                                """,
                                company_name, person_name, role, dynasty_name
                            )
                            if not existing:
                                await dynasty_conn.execute(
                                    """
                                    INSERT INTO contractor_dynasty_matches (
                                        company_name, person_name, role, 
                                        dynasty_full_name, dynasty_first_name, dynasty_last_name,
                                        source_csv_file
                                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                                    """,
                                    company_name, person_name, role, dynasty_name,
                                    dynasty_first, dynasty_last, csv_filename
                                )
                        except Exception:
                            pass
    
    if matched_count > 0:
        print(f"   🔗 Found {matched_count} person names matching dynasty database")
    
    return created, match_details


async def mark_companies_processed(sec_conn, contractors: List[Dict]):
    """Mark companies as processed"""
    # Check what column exists
    contractor_col_exists = await sec_conn.fetchval(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = 'llm_processed_companies'
            AND column_name = 'contractor_name'
        )
        """
    )
    
    for c in contractors:
        try:
            if contractor_col_exists:
                await sec_conn.execute(
                    """
                    INSERT INTO llm_processed_companies (contractor_name, normalized_name)
                    VALUES ($1, $2)
                    ON CONFLICT (contractor_name) DO NOTHING
                    """,
                    c['contractor_name'], c['normalized_name']
                )
            else:
                # Try company_name column (old schema)
                await sec_conn.execute(
                    """
                    INSERT INTO llm_processed_companies (company_name)
                    VALUES ($1)
                    ON CONFLICT (company_name) DO NOTHING
                    """,
                    c['contractor_name']
                )
        except Exception:
            pass


def get_output_dir() -> Path:
    """Get output directory for CSV files"""
    script_dir = Path(__file__).resolve().parent
    output_dir = script_dir / 'contractor_officers_csvs'
    output_dir.mkdir(exist_ok=True)
    return output_dir


async def main():
    # Load environment variables first
    load_env_from_dotenv()
    load_dotenv()  # Also try dotenv package's load_dotenv
    
    companies_per_page = _int_env('COMPANIES_PER_PAGE', 40)
    total_companies = _int_env('TOTAL_COMPANIES', 400)
    
    sec_conn = await get_sec_conn()
    dynasty_conn = await get_dynasty_conn()
    
    try:
        await ensure_aux_tables(sec_conn, dynasty_conn)
        
        # Get top normalized contractors
        print(f"🔍 Fetching top {total_companies} normalized contractors by project count...")
        all_contractors = await fetch_top_normalized_contractors(sec_conn, limit=total_companies)
        
        if not all_contractors:
            print("✅ No contractors to process.")
            return
        
        print(f"✅ Found {len(all_contractors)} contractors to process")
        print(f"📊 Top 10 by project count:")
        for i, c in enumerate(all_contractors[:10], 1):
            print(f"   {i:2d}. {c['contractor_name']:50s} ({c['project_count']} projects)")
        print()
        
        # Process in pages of 40
        output_dir = get_output_dir()
        total_pages = (len(all_contractors) + companies_per_page - 1) // companies_per_page
        
        for page in range(total_pages):
            start_idx = page * companies_per_page
            end_idx = min(start_idx + companies_per_page, len(all_contractors))
            page_contractors = all_contractors[start_idx:end_idx]
            
            print(f"\n{'='*80}")
            print(f"📄 Processing Page {page + 1}/{total_pages} (companies {start_idx + 1}-{end_idx})")
            print(f"{'='*80}")
            
            prompt = build_prompt(page_contractors, page + 1)
            print(f"🚀 Sending prompt to Perplexity for {len(page_contractors)} companies...")
            
            try:
                reply = call_perplexity(prompt)
                csv_text = extract_csv_from_reply(reply)
                
                if not csv_text or ',' not in csv_text:
                    print(f'⚠️ Could not extract CSV from reply for page {page + 1}')
                    # Mark as processed anyway to avoid infinite loops
                    await mark_companies_processed(sec_conn, page_contractors)
                    continue
                
                # Save CSV
                csv_file = output_dir / f"llm_contractor_officers_page_{page + 1:03d}.csv"
                with open(csv_file, 'w', encoding='utf-8', newline='') as f:
                    f.write(csv_text if csv_text.endswith('\n') else csv_text + '\n')
                print(f"✅ Saved CSV to {csv_file}")
                
                # Insert into database
                created, matches = await upsert_company_affiliations(dynasty_conn, csv_file)
                print(f"📊 Inserted {created} affiliations into dynasty.company_affiliations")
                
                if matches:
                    print(f"   💎 Stored {len(matches)} dynasty matches in contractor_dynasty_matches")
                
                # Mark as processed
                await mark_companies_processed(sec_conn, page_contractors)
                print(f"✅ Marked {len(page_contractors)} companies as processed")
                
            except Exception as e:
                print(f"❌ Error processing page {page + 1}: {e}")
                # Mark as processed to avoid retrying same page indefinitely
                await mark_companies_processed(sec_conn, page_contractors)
        
        print(f"\n{'='*80}")
        print("✅ Processing complete!")
        print(f"{'='*80}")
        print(f"📁 CSV files saved to: {output_dir}")
        print(f"📊 Total contractors processed: {len(all_contractors)}")
        print(f"📄 Total pages: {total_pages}")
        
    finally:
        await sec_conn.close()
        await dynasty_conn.close()


if __name__ == '__main__':
    asyncio.run(main())


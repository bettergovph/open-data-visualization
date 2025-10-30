#!/usr/bin/env python3
"""
Automate extraction of company owners/incorporators/officers via Perplexity for SEC contractors.

Flow:
1) Load DB and API credentials from .env
2) Read distinct contractor names from sec.contractors (exclude already processed)
3) Build optimized prompt asking for CSV in a fenced ```csv block
4) Call Perplexity Chat Completions API (PERPLEXITY_API_KEY)
5) Save CSV as llm_sec_officers_<N>.csv (batch of 40 companies)
6) Insert parsed rows into dynasty.company_affiliations
7) Stop when there are already 500 CSVs in this folder
"""

import os
import re
import csv
import asyncio
import asyncpg
import requests
from typing import List, Dict
from dotenv import load_dotenv


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


async def get_sec_conn():
    return await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=_int_env('POSTGRES_PORT', 5432),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_SEC', 'sec')
    )


async def get_dynasty_conn():
    return await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=_int_env('POSTGRES_PORT', 5432),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )


async def ensure_aux_tables(sec_conn, dynasty_conn):
    # Track processed companies in SEC DB to avoid repeats
    await sec_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_processed_companies (
            id SERIAL PRIMARY KEY,
            company_name TEXT UNIQUE,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Store affiliations in DYNASTY DB (minimal schema, append-only)
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


async def fetch_distinct_companies(sec_conn, limit: int) -> List[Dict]:
    rows = await sec_conn.fetch(
        """
        SELECT DISTINCT contractor_name AS company_name
        FROM contractors
        WHERE contractor_name IS NOT NULL AND contractor_name <> ''
          AND contractor_name NOT IN (SELECT company_name FROM llm_processed_companies)
        ORDER BY contractor_name
        LIMIT $1
        """,
        limit,
    )
    return [dict(r) for r in rows]


def build_prompt(companies: List[Dict], prompt_num: int, companies_per_prompt: int) -> str:
    name_list = [c['company_name'] for c in companies]

    prompt = f"""# SEC Company Officers Discovery Prompt

You are a precise research assistant. For each Philippine company listed below, find verifiable details about its owners, incorporators, and officers. Return only a CSV in a single fenced code block.

## Companies to Analyze (total {companies_per_prompt}):
"""

    for name in name_list:
        prompt += f"{name}\n"

    prompt += f"""
## Your Task:
1. For each company, identify individuals who are: owners, incorporators, directors, or officers (e.g., President, Treasurer, Corporate Secretary).
2. Use credible sources (SEC submissions, reputable news, official company docs). Provide a source URL for each row.
3. Return results strictly as CSV text with EXACTLY these columns in this order:
   - company_name
   - person_name
   - role
   - source_url
   - confidence_level (1-10)

STRICT OUTPUT RULES:
- Return a single fenced code block that begins with ```csv and ends with ```.
- Include a single header row followed by data rows.
- Only include complete rows (all columns non-empty).
- Do not include commentary outside the CSV block.

If no data is found for a company, simply emit no row for that company.
"""

    return prompt


def call_perplexity(prompt: str) -> str:
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
            { 'role': 'system', 'content': 'Return only the requested CSV.' },
            { 'role': 'user', 'content': prompt }
        ]
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data.get('choices', [{}])[0].get('message', {}).get('content', '') or ''


def extract_csv_from_reply(reply: str) -> str:
    m = re.search(r"```csv\s*([\s\S]*?)```", reply, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m2 = re.search(r"```[a-zA-Z]*\s*([\s\S]*?)```", reply)
    if m2:
        return m2.group(1).strip()
    return reply.strip()


async def upsert_company_affiliations(dynasty_conn, csv_path: str) -> int:
    created = 0
    if not os.path.exists(csv_path):
        return created
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

            try:
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
                # Best-effort insert; skip duplicates if any unique constraints are later added
                pass
    return created


async def mark_companies_processed(sec_conn, companies: List[str]):
    for name in companies:
        try:
            await sec_conn.execute(
                """
                INSERT INTO llm_processed_companies (company_name)
                VALUES ($1)
                ON CONFLICT (company_name) DO NOTHING
                """,
                name
            )
        except Exception:
            pass


def list_existing_csvs() -> List[str]:
    return [f for f in os.listdir('.') if re.match(r"llm_sec_officers_(\d{2,})\.csv$", f)]


def next_batch_index() -> int:
    existing = []
    for fname in list_existing_csvs():
        m = re.match(r"llm_sec_officers_(\d{2,})\.csv$", fname)
        if m:
            try:
                existing.append(int(m.group(1)))
            except ValueError:
                pass
    return (max(existing) + 1) if existing else 1


async def main():
    load_dotenv()

    companies_per_prompt = _int_env('SEC_COMPANIES_PER_PROMPT', 40)
    max_csv_files = _int_env('MAX_SEC_CSV_FILES', 500)

    sec_conn = await get_sec_conn()
    dynasty_conn = await get_dynasty_conn()
    try:
        await ensure_aux_tables(sec_conn, dynasty_conn)

        # Stop early if CSV cap already reached
        if len(list_existing_csvs()) >= max_csv_files:
            print(f"✅ Reached MAX_SEC_CSV_FILES limit ({max_csv_files}). Nothing to do.")
            return

        batch_idx = next_batch_index()
        while True:
            if len(list_existing_csvs()) >= max_csv_files:
                print(f"✅ Reached MAX_SEC_CSV_FILES limit ({max_csv_files}). Stopping.")
                break

            companies = await fetch_distinct_companies(sec_conn, companies_per_prompt)
            if not companies:
                print('✅ No more companies to process.')
                break

            prompt = build_prompt(companies, prompt_num=batch_idx, companies_per_prompt=companies_per_prompt)
            print(f"🚀 Sending SEC officers prompt to Perplexity (batch {batch_idx})...")
            reply = call_perplexity(prompt)
            csv_text = extract_csv_from_reply(reply)
            if not csv_text or ',' not in csv_text:
                print('❌ Could not extract CSV from reply; marking companies as processed to avoid repeats')
                await mark_companies_processed(sec_conn, [c['company_name'] for c in companies])
                batch_idx += 1
                continue

            out_file = f"llm_sec_officers_{batch_idx:03d}.csv"
            with open(out_file, 'w', encoding='utf-8', newline='') as f:
                f.write(csv_text if csv_text.endswith('\n') else csv_text + '\n')
            print(f"✅ Saved CSV to {out_file}")

            created = await upsert_company_affiliations(dynasty_conn, out_file)
            print(f"📊 Inserted {created} affiliations into dynasty.company_affiliations")

            await mark_companies_processed(sec_conn, [c['company_name'] for c in companies])
            batch_idx += 1

    finally:
        await sec_conn.close()
        await dynasty_conn.close()


if __name__ == '__main__':
    asyncio.run(main())



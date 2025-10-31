#!/usr/bin/env python3
"""
Automate dynasty relationship discovery via Perplexity API and process results.

Steps:
1) Load DB and API credentials from .env
2) Query dynasty DB to get names (first batch only for test)
3) Build optimized prompt asking for CSV as text (fenced ```csv code block)
4) Call Perplexity Chat Completions API
5) Extract CSV text, save to file
6) Process CSV with existing processor (using .env DB credentials)
"""

import os
import re
import csv
import asyncio
import asyncpg
import requests
from io import StringIO
from typing import List, Dict
from dotenv import load_dotenv

from process_llm_csv_results import LLMCSVProcessor as BaseLLMCSVProcessor


class EnvLLMCSVProcessor(BaseLLMCSVProcessor):
    async def connect(self):
        self.db_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
        )
        print("✅ Connected to dynasty database (env)")
        await self._ensure_middle_name_column()
        await self._ensure_connection_types()

    async def _ensure_connection_types(self):
        # Ensure key relationship types exist; map NAME -> id
        async def get_max_code():
            val = await self.db_conn.fetchval("SELECT COALESCE(MAX(code), 0) FROM connection_types")
            return int(val or 0)

        async def ensure_type(name: str, category: str = 'family', bidir: bool = True):
            existing = await self.db_conn.fetchrow(
                "SELECT id, code FROM connection_types WHERE UPPER(name)=UPPER($1)", name
            )
            if existing:
                return dict(existing)
            next_code = (await get_max_code()) + 1
            row = await self.db_conn.fetchrow(
                """
                INSERT INTO connection_types (code, name, description, category, bidirectional)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, code
                """,
                next_code, name, name, category, bidir
            )
            print(f"🛠️ Added connection_type: {name} (id={row['id']}, code={row['code']})")
            return dict(row)

        # Ensure core types used by normalization exist
        core_types = [
            ('Father', 'family', True), ('Mother', 'family', True),
            ('Son', 'family', True), ('Daughter', 'family', True),
            ('Husband', 'family', True), ('Wife', 'family', True),
            ('Brother', 'family', True), ('Sister', 'family', True),
            ('Political Ally', 'political', True), ('Business Partner', 'business', True),
            ('Successor', 'political', False), ('Predecessor', 'political', False)
        ]
        for name, category, bidir in core_types:
            await ensure_type(name, category, bidir)

        # Remap by NAME -> id (not code) to satisfy FK on relationships.relationship_type
        types = await self.db_conn.fetch("SELECT id, name FROM connection_types ORDER BY id")
        self.connection_type_map = {ct['name'].upper(): ct['id'] for ct in types}
        print(f"📋 Loaded {len(self.connection_type_map)} connection types (by id)")

    async def _ensure_middle_name_column(self):
        try:
            exists = await self.db_conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'political_dynasties'
                      AND column_name = 'middle_name'
                )
                """
            )
            if not exists:
                await self.db_conn.execute(
                    "ALTER TABLE political_dynasties ADD COLUMN middle_name TEXT"
                )
                print("🛠️ Added column political_dynasties.middle_name")
        except Exception as e:
            print(f"⚠️ Could not ensure middle_name column: {e}")

    def _strip_middle_initials(self, full_name: str) -> str:
        # Remove PH-style middle initials like "A." or "A.B." and collapse spaces
        name = re.sub(r"\b([A-Z])\.(?:\s*([A-Z])\.)?\b", " ", full_name.upper())
        name = re.sub(r"\s+", " ", name).strip()
        return name

    def _generate_name_variants(self, full_name: str) -> List[str]:
        variants = []
        base = self._strip_middle_initials(full_name)
        variants.append(base)

        parts = base.split(" ")
        if len(parts) >= 2:
            first = parts[0]
            last = " ".join(parts[1:])
            # Hyphenated married last names: try each side
            if "-" in last:
                last_sides = [s.strip() for s in last.split("-") if s.strip()]
                for side in last_sides:
                    variants.append(f"{first} {side}")
            # Also try without any punctuation in last name
            variants.append(f"{first} {re.sub(r'[^A-Z ]', '', last)}")

        # Deduplicate while preserving order
        seen = set()
        uniq = []
        for v in variants:
            if v not in seen:
                uniq.append(v)
                seen.add(v)
        return uniq

    async def find_person_by_name(self, full_name: str):
        # Override with PH-aware matching
        for candidate in self._generate_name_variants(full_name):
            person = await self.db_conn.fetchrow(
                """
                SELECT id, first_name, last_name, province, position, year
                FROM political_dynasties 
                WHERE CONCAT(first_name, ' ', last_name) = $1
                ORDER BY year DESC
                LIMIT 1
                """,
                candidate
            )
            if person:
                return dict(person)

        # Fallback fuzzy/ILIKE on base stripped name
        base = self._strip_middle_initials(full_name)
        person = await self.db_conn.fetchrow(
            """
            SELECT id, first_name, last_name, province, position, year
            FROM political_dynasties 
            WHERE CONCAT(first_name, ' ', last_name) ILIKE $1
            ORDER BY year DESC
            LIMIT 1
            """,
            f"%{base}%"
        )
        return dict(person) if person else None

    async def _split_name(self, full_name: str):
        parts = [p for p in full_name.strip().split(' ') if p]
        if len(parts) == 1:
            return parts[0], ''
        return ' '.join(parts[:-1]), parts[-1]

    async def ensure_person_exists(self, full_name: str):
        person = await self.find_person_by_name(full_name)
        if person:
            return person
        try:
            first_name, last_name = await self._split_name(full_name)
            row = await self.db_conn.fetchrow(
                """
                INSERT INTO political_dynasties (first_name, middle_name, last_name)
                VALUES ($1, NULL, $2)
                RETURNING id, first_name, last_name, province, position, year
                """,
                first_name, last_name
            )
            print(f"   ➕ Created person: {full_name} (ID: {row['id']})")
            return dict(row)
        except Exception as e:
            print(f"   ❌ Failed to create person '{full_name}': {e}")
            return None

    async def process_csv_file(self, csv_file: str):
        print(f"📊 Processing CSV file: {csv_file}")
        if not os.path.exists(csv_file):
            print(f"❌ File not found: {csv_file}")
            return

        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                self.processed_count += 1
                person1_name = row.get('person1_name', '').strip()
                person2_name = row.get('person2_name', '').strip()
                relationship_type = row.get('relationship_type', '').strip()
                description = row.get('relationship_description', '').strip()
                source_url = row.get('source_url', '').strip()
                confidence_level = int(row.get('confidence_level', 0)) if row.get('confidence_level') else 0

                if not person1_name or not person2_name or not relationship_type:
                    print(f"   ⚠️  Skipping incomplete row: {person1_name} → {person2_name}")
                    self.skipped_count += 1
                    continue

                print(f"🔍 Processing: {person1_name} → {relationship_type} → {person2_name}")

                person1 = await self.find_person_by_name(person1_name)
                person2 = await self.find_person_by_name(person2_name)

                if not person1:
                    person1 = await self.ensure_person_exists(person1_name)
                if not person2:
                    person2 = await self.ensure_person_exists(person2_name)
                if not person1 or not person2:
                    self.skipped_count += 1
                    continue

                # Normalize relationship type, support composite like "Father/Daughter" and "Husband/Wife"
                fwd_type, rev_type = self._normalize_relationship_type(relationship_type)
                fwd_upper = fwd_type.upper()
                rev_upper = rev_type.upper()
                if fwd_upper not in self.connection_type_map or rev_upper not in self.connection_type_map:
                    print(f"   ❌ Unknown relationship type: {relationship_type}")
                    self.skipped_count += 1
                    continue
                relationship_type_id = self.connection_type_map[fwd_upper]
                relationship_type_id_rev = self.connection_type_map[rev_upper]

                # forward
                existing = await self.db_conn.fetchrow(
                    """
                    SELECT id FROM relationships 
                    WHERE person_id = $1 AND related_person_id = $2 AND relationship_type = $3
                    """,
                    person1['id'], person2['id'], relationship_type_id
                )
                if not existing:
                    try:
                        await self.db_conn.execute(
                            """
                            INSERT INTO relationships (
                                person_id, related_person_id, relationship_type,
                                relationship_description, source_url, confidence_level,
                                verified, created_by
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                            """,
                            person1['id'], person2['id'], relationship_type_id,
                            description, source_url, confidence_level,
                            confidence_level >= 8, 'LLM_Analysis'
                        )
                        print(f"   ✅ Created relationship (ID: {person1['id']} → {person2['id']})")
                        self.created_count += 1
                    except Exception as e:
                        print(f"   ❌ Error creating relationship: {e}")
                        self.skipped_count += 1

                # reverse (bidirectional)
                existing_rev = await self.db_conn.fetchrow(
                    """
                    SELECT id FROM relationships 
                    WHERE person_id = $1 AND related_person_id = $2 AND relationship_type = $3
                    """,
                    person2['id'], person1['id'], relationship_type_id_rev
                )
                if not existing_rev:
                    try:
                        await self.db_conn.execute(
                            """
                            INSERT INTO relationships (
                                person_id, related_person_id, relationship_type,
                                relationship_description, source_url, confidence_level,
                                verified, created_by
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                            """,
                            person2['id'], person1['id'], relationship_type_id_rev,
                            description, source_url, confidence_level,
                            confidence_level >= 8, 'LLM_Analysis'
                        )
                        print(f"   ✅ Created reverse relationship (ID: {person2['id']} → {person1['id']})")
                        self.created_count += 1
                    except Exception as e:
                        print(f"   ❌ Error creating reverse relationship: {e}")
                        self.skipped_count += 1

    def _normalize_relationship_type(self, rel_type: str):
        t = (rel_type or '').strip()
        if '/' in t:
            left, right = [p.strip() for p in t.split('/', 1)]
            # Husband/Wife special case
            if {left.lower(), right.lower()} == {'husband', 'wife'}:
                return 'Husband', 'Wife'
            # Parent/Child patterns
            parent_terms = {'father', 'mother'}
            child_terms = {'son', 'daughter'}
            if left.lower() in parent_terms and right.lower() in child_terms:
                return left.title(), right.title()
            if left.lower() in child_terms and right.lower() in parent_terms:
                return left.title(), right.title()
            # Siblings variants -> same both sides
            if left.lower() in {'brother', 'sister'} and right.lower() in {'brother', 'sister'}:
                # Use specific for forward; reverse mirrors the other
                return left.title(), right.title()
            # Fallback: use left for both
            return left.title(), left.title()
        # Single type
        return t.title(), t.title()


def build_prompt(names: List[Dict], prompt_num: int, names_per_prompt: int) -> str:
    # Build name list with party information if available
    name_entries = []
    for n in names:
        name_entry = n['full_name']
        party_info = []
        if n.get('party') and n['party'].strip():
            party_info.append(f"Party: {n['party'].strip()}")
        if n.get('province') and n['province'].strip():
            party_info.append(f"Province: {n['province'].strip()}")
        if party_info:
            name_entry += f" ({', '.join(party_info)})"
        name_entries.append(name_entry)

    prompt = f"""# Philippine Political Dynasty Family Relationship Analysis Prompt

You are a political research analyst specializing in Philippine political dynasties. Your task is to analyze the FAMILY RELATIONSHIPS (biological and marriage) between the following political figures and return the findings in CSV format.

## Names to Analyze (with party affiliation and province if available):
"""

    for i in range(0, len(name_entries), 10):
        batch_names = name_entries[i:i+10]
        prompt += "\n".join(batch_names) + "\n"

    prompt += f"""
## Your Task:
1. Research each name using web sources to find VERIFIABLE FAMILY RELATIONSHIPS:
   - Biological relationships (parent-child, siblings, grandparents, cousins)
   - Marriage relationships (spouses, in-laws)
   - Focus on relationships WITHIN political families/dynasties
   
2. PRIORITY: Focus on biological and marriage relationships. Only include political/business relationships if they are clearly documented and relevant to dynasty connections.

3. Return results as CSV text with EXACTLY these columns (in this order):
   - person1_name
   - person2_name  
   - relationship_type
   - relationship_description
   - dynasty1
   - dynasty2
   - source_url
   - confidence_level (1-10)

STRICT OUTPUT RULES:
- Return a single fenced code block that begins with ```csv and ends with ```.
- The CSV MUST include a single header row followed by data rows.
- Include ONLY complete rows: person1_name, person2_name, relationship_type, and source_url must be non-empty.
- Do NOT include blank lines or placeholder rows.
- If no relationships are found, output ONLY the header row (no data rows).

COVERAGE REQUIREMENT:
- You MUST consider ALL {names_per_prompt} names listed above. If a specific name has no verifiable family relationships, simply do not emit any row for that name.

## Example Output (format ONLY):
```csv
person1_name,person2_name,relationship_type,relationship_description,dynasty1,dynasty2,source_url,confidence_level
"JUAN DELA CRUZ","MARIA DELA CRUZ","Husband/Wife","Married couple within the DELA CRUZ dynasty","DELA CRUZ","DELA CRUZ","https://example.org/source1",9
"ALFRED TAN","STEPHANY TAN","Brother/Sister","Siblings in TAN dynasty","TAN","TAN","https://example.org/source2",8
"JOSE GARCIA","CARLOS GARCIA","Father/Son","Father-son relationship in GARCIA political dynasty","GARCIA","GARCIA","https://example.org/source3",9
```

## Relationship Types to Identify (FAMILY FOCUS):
- Father/Mother (biological or adoptive)
- Son/Daughter (biological or adoptive)
- Husband/Wife (married couple)
- Brother/Sister (siblings)
- Uncle/Aunt (parent's sibling)
- Nephew/Niece (sibling's child)
- Cousin (parent's sibling's child)
- Grandfather/Grandmother
- Grandson/Granddaughter
- Father-in-law/Mother-in-law
- Son-in-law/Daughter-in-law
- Brother-in-law/Sister-in-law

NOTE: Only include Political Ally or Business Partner relationships if they are explicitly documented as part of dynasty connections. Focus primarily on biological and marriage relationships.
"""

    return prompt


def normalize_name_for_query(full_name: str) -> str:
    """Normalize name by removing middle initials and extra spaces for deduplication"""
    if not full_name:
        return ""
    # Remove PH-style middle initials like "A." or "A.B." and collapse spaces
    name = re.sub(r"\b([A-Z])\.(?:\s*([A-Z])\.)?\b", " ", full_name.upper())
    name = re.sub(r"\s+", " ", name).strip()
    return name


async def fetch_top_names(conn, limit: int) -> List[Dict]:
    """
    Fetch top priority engineer and BAC member names.
    Prioritizes by: frequency + recency.
    Returns exactly 'limit' unique normalized names (deduplicated by removing middle initials).
    """
    # Get top engineers and BAC members based on priority scoring:
    # - Frequency (how many times they appear in database = influence)
    # - Recency (most recent year)
    # - Excludes already processed names
    
    name_rows = await conn.fetch("""
        WITH name_stats AS (
            SELECT 
                CONCAT(first_name, ' ', last_name) AS full_name,
                COUNT(*) as position_count,
                MAX(year) as max_year,
                MIN(year) as min_year,
                COUNT(DISTINCT position) as unique_positions,
                -- Get most recent record details
                (array_agg(id ORDER BY year DESC))[1] as best_id,
                (array_agg(province ORDER BY year DESC))[1] as best_province,
                (array_agg(position ORDER BY year DESC))[1] as best_position,
                (array_agg(party ORDER BY year DESC))[1] as best_party
            FROM political_dynasties
            WHERE first_name IS NOT NULL AND first_name <> ''
              AND last_name IS NOT NULL AND last_name <> ''
              AND (
                position ILIKE '%ENGINEER%'
                OR position ILIKE '%BAC%'
                OR position ILIKE '%BIDS AND AWARDS%'
                OR position ILIKE '%DISTRICT ENGINEER%'
              )
              AND CONCAT(first_name, ' ', last_name) NOT IN (
                SELECT full_name FROM llm_processed_names
              )
            GROUP BY CONCAT(first_name, ' ', last_name)
        )
        SELECT 
            best_id as id,
            full_name,
            best_province as province,
            best_position as position,
            max_year as year,
            best_party as party,
            -- Calculate priority score (higher = more important)
            -- Frequency + unique positions + recency
            (position_count * 10 + 
             unique_positions * 5 +
             max_year - 1900) as priority_score
        FROM name_stats
        ORDER BY priority_score DESC
        LIMIT $1
        """,
        limit * 3,  # Get more to account for deduplication (some may be duplicates after normalization)
    )
    
    # Normalize and deduplicate in Python
    seen_normalized = set()
    unique_names = []
    for row in name_rows:
        normalized = normalize_name_for_query(row['full_name'])
        if normalized and normalized not in seen_normalized:
            seen_normalized.add(normalized)
            unique_names.append(dict(row))
            if len(unique_names) >= limit:
                break
    
    return unique_names


async def get_db_connection():
    return await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )


def call_llm(prompt: str) -> str:
    provider = os.getenv('LLM_PROVIDER', 'openai').lower()
    if provider == 'openai':
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set in environment")
        model = os.getenv('OPENAI_MODEL', 'gpt-4o')
        try:
            temperature = float(os.getenv('OPENAI_TEMPERATURE', os.getenv('PERPLEXITY_TEMPERATURE', '0.0')))
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
    m = re.search(r"```csv\s*([\s\S]*?)```", reply, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Fallback: try any fenced block
    m2 = re.search(r"```[a-zA-Z]*\s*([\s\S]*?)```", reply)
    if m2:
        return m2.group(1).strip()
    return reply.strip()


async def main():
    load_dotenv()

    names_per_list = int(os.getenv('NAMES_PER_LIST', '40'))
    target_total = int(os.getenv('TARGET_TOTAL_NAMES', '400'))  # Default: 400 names from top positions
    max_batches = (target_total + names_per_list - 1) // names_per_list  # Calculate batches needed

    # 1) Connect and fetch names (prioritize top names by influence/importance)
    conn = await get_db_connection()
    async def ensure_processed_table():
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_processed_names (
                id SERIAL PRIMARY KEY,
                full_name TEXT UNIQUE,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    async def mark_processed(full_names: List[str]):
        if not full_names:
            return
        # Use ON CONFLICT to avoid duplicates
        for fn in full_names:
            await conn.execute(
                """
                INSERT INTO llm_processed_names (full_name)
                VALUES ($1)
                ON CONFLICT (full_name) DO NOTHING
                """,
                fn
            )

    await ensure_processed_table()

    # Determine next CSV batch index based on existing files
    def list_existing_csvs():
        return [fname for fname in os.listdir('.') if re.match(r"llm_relationships_(\d{2,})\.csv$", fname)]

    def get_next_batch_index() -> int:
        existing = []
        for fname in list_existing_csvs():
            m = re.match(r"llm_relationships_(\d{2,})\.csv$", fname)
            if m:
                try:
                    existing.append(int(m.group(1)))
                except ValueError:
                    pass
        return (max(existing) + 1) if existing else 1

    max_csv = int(os.getenv('MAX_CSV_FILES', '1000'))
    existing_csvs = list_existing_csvs()
    if len(existing_csvs) >= max_csv:
        print(f"✅ Reached MAX_CSV_FILES limit ({max_csv}). Nothing to do.")
        await conn.close()
        return

    batch_index = get_next_batch_index()
    total_created = 0
    batches_processed = 0
    total_names_processed = 0
    
    while True:
        # Stop if we have reached the CSV cap
        existing_csvs = list_existing_csvs()
        if len(existing_csvs) >= max_csv:
            print(f"✅ Reached MAX_CSV_FILES limit ({max_csv}). Stopping.")
            break
        
        # Stop if we've processed the desired number of names (default: 400)
        if total_names_processed >= target_total:
            print(f"✅ Processed {total_names_processed} top priority engineers/BAC members (target: {target_total}). Stopping.")
            break
        
        # Stop if we've processed the maximum batches
        if batches_processed >= max_batches:
            print(f"✅ Processed {batches_processed} batches ({total_names_processed} names total). Stopping.")
            break
        
        # Fetch exactly 40 unique normalized names from top positions per list
        remaining_needed = target_total - total_names_processed
        batch_limit = min(names_per_list, remaining_needed)
        
        top_names = await fetch_top_names(conn, batch_limit)
        if not top_names:
            print("✅ No more engineers/BAC members to process. Done.")
            break

        if len(top_names) < batch_limit:
            print(f"⚠️  Only found {len(top_names)} unique engineers/BAC members (requested {batch_limit})")

        # Show position breakdown for this batch
        positions = {}
        for n in top_names:
            pos = n.get('position', 'Unknown')
            positions[pos] = positions.get(pos, 0) + 1
        
        print(f"📋 Processing batch {batch_index}: {len(top_names)} unique normalized top priority engineers/BAC members")
        print(f"   Position breakdown: {', '.join([f'{pos}({cnt})' for pos, cnt in sorted(positions.items(), key=lambda x: -x[1])[:5]])}")
        total_names_processed += len(top_names)

        # 2) Build prompt
        prompt = build_prompt(top_names, prompt_num=batch_index, names_per_prompt=len(top_names))

        # 3) Call Perplexity
        print(f"🚀 Sending prompt to LLM (batch {batch_index})...")
        reply = call_llm(prompt)

        # 4) Extract CSV string
        csv_text = extract_csv_from_reply(reply)
        if not csv_text or ',' not in csv_text:
            print("❌ Could not extract CSV from reply; marking names as processed to avoid repeats")
            await mark_processed([n['full_name'] for n in top_names])
            batch_index += 1
            continue

        # 5) Save CSV to file for processor compatibility
        out_file = f"llm_relationships_{batch_index:02d}.csv"
        with open(out_file, 'w', encoding='utf-8', newline='') as f:
            f.write(csv_text if csv_text.endswith('\n') else csv_text + '\n')
        print(f"✅ Saved CSV to {out_file}")

        # 6) Process CSV using existing processor (env-based connect)
        processor = EnvLLMCSVProcessor()
        try:
            await processor.connect()
            await processor.setup_connection_types()
            await processor.process_csv_file(out_file)
            await processor.show_relationship_summary()
        finally:
            await processor.close()

        # 7) Mark these names as processed to save LLM cost
        await mark_processed([n['full_name'] for n in top_names])

        batches_processed += 1
        batch_index += 1

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())



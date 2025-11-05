#!/usr/bin/env python3
"""
Process NEW HuggingFace names through Perplexity API for relationship discovery.

This script specifically targets the top 1500 names that were added from HuggingFace,
processing them in batches of 30 to discover family and political relationships.

Target: 1500 names, 30 per batch = 50 batches
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
import sys
from pathlib import Path

# Add the family_parser directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'family_analysis' / 'family_parser'))

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


def call_llm(prompt: str) -> str:
    """Call Perplexity Chat Completions API"""
    api_key = os.getenv('PERPLEXITY_API_KEY')
    if not api_key:
        raise RuntimeError("PERPLEXITY_API_KEY not found in environment")

    model = os.getenv('PERPLEXITY_MODEL', 'sonar-pro')
    try:
        temperature = float(os.getenv('PERPLEXITY_TEMPERATURE', '0.0'))
    except ValueError:
        temperature = 0.0

    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a political research assistant specializing in Philippine political dynasties."},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": 4000
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=120)
        response.raise_for_status()
        data = response.json()
        return data.get('choices', [{}])[0].get('message', {}).get('content', '')
    except Exception as e:
        print(f"❌ LLM call failed: {e}")
        return ""


def extract_csv_from_reply(reply: str) -> str:
    """Extract CSV text from fenced code block"""
    match = re.search(r'```csv\s*(.*?)\s*```', reply, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def build_prompt(names: List[Dict], prompt_num: int, names_per_prompt: int) -> str:
    """Build Perplexity prompt for relationship discovery"""
    name_list = "\n".join([
        f"{i+1}. {n['full_name']} ({n['position']}, {n['province']}, {n['party'] or 'Independent'})"
        for i, n in enumerate(names)
    ])

    prompt = f"""# Philippine Political Dynasty Relationship Discovery - Batch {prompt_num}

You are analyzing {names_per_prompt} Filipino politicians from HuggingFace dataset to identify verifiable family and political relationships.

## Politicians to Analyze:
{name_list}

## Task:
1. Research EACH person thoroughly using verifiable sources (news, government records, academic papers).
2. Identify DIRECT FAMILY RELATIONSHIPS (parent-child, siblings, spouses, etc.).
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


async def fetch_huggingface_names(conn, limit: int) -> List[Dict]:
    """
    Fetch top priority names from HuggingFace integration.
    Prioritizes by: 
    - Names from 2004-2016 range (HuggingFace data)
    - Has canonical_name (set during integration)
    - Multiple positions (dynasty indicator)
    - Not already processed
    """
    
    name_rows = await conn.fetch("""
        WITH huggingface_names AS (
            SELECT 
                CONCAT(first_name, ' ', last_name) AS full_name,
                COUNT(*) as position_count,
                MAX(year) as max_year,
                MIN(year) as min_year,
                COUNT(DISTINCT position) as unique_positions,
                COUNT(DISTINCT province) as unique_provinces,
                (array_agg(id ORDER BY year DESC))[1] as best_id,
                (array_agg(province ORDER BY year DESC))[1] as best_province,
                (array_agg(position ORDER BY year DESC))[1] as best_position,
                (array_agg(party ORDER BY year DESC))[1] as best_party
            FROM political_dynasties
            WHERE first_name IS NOT NULL AND first_name <> ''
              AND last_name IS NOT NULL AND last_name <> ''
              AND canonical_name IS NOT NULL  -- Set during HuggingFace integration
              AND year BETWEEN 2004 AND 2016  -- HuggingFace data range
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
            best_party as party,
            position_count,
            max_year,
            unique_positions,
            unique_provinces
        FROM huggingface_names
        ORDER BY 
            position_count DESC,  -- Prioritize those with multiple positions
            max_year DESC,        -- Then most recent
            unique_provinces DESC -- Then those in multiple provinces
        LIMIT $1
    """, limit)
    
    return [dict(row) for row in name_rows]


async def mark_processed(conn, names: List[str]):
    """Mark names as processed in llm_processed_names table"""
    for name in names:
        try:
            await conn.execute(
                "INSERT INTO llm_processed_names (full_name) VALUES ($1) ON CONFLICT DO NOTHING",
                name
            )
        except Exception as e:
            print(f"⚠️ Could not mark {name} as processed: {e}")


async def main():
    """Main execution"""
    # Load environment
    if Path('.env').exists():
        load_dotenv('.env')
    
    # Configuration
    target_total = 1500      # Total names to process
    names_per_batch = 30     # Names per batch
    max_batches = 50         # Maximum batches (1500/30 = 50)
    
    print("=" * 80)
    print("🚀 HUGGINGFACE NAMES PERPLEXITY RELATIONSHIP DISCOVERY")
    print("=" * 80)
    print(f"Target: {target_total} names from HuggingFace integration")
    print(f"Batch size: {names_per_batch} names per batch")
    print(f"Expected batches: {target_total // names_per_batch}")
    print("=" * 80)
    
    # Connect to database
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    # Check how many HuggingFace names are available
    total_available = await conn.fetchval("""
        SELECT COUNT(DISTINCT CONCAT(first_name, ' ', last_name))
        FROM political_dynasties
        WHERE first_name IS NOT NULL AND first_name <> ''
          AND last_name IS NOT NULL AND last_name <> ''
          AND canonical_name IS NOT NULL
          AND year BETWEEN 2004 AND 2016
          AND CONCAT(first_name, ' ', last_name) NOT IN (
            SELECT full_name FROM llm_processed_names
          )
    """)
    
    print(f"📊 Available HuggingFace names (not yet processed): {total_available}")
    
    if total_available == 0:
        print("✅ All HuggingFace names have been processed!")
        await conn.close()
        return
    
    if total_available < target_total:
        print(f"⚠️  Only {total_available} names available (target was {target_total})")
        target_total = total_available
    
    # Determine next batch index
    def get_next_batch_index():
        import glob
        existing = []
        for fname in glob.glob("llm_huggingface_*.csv"):
            m = re.match(r"llm_huggingface_(\d{2,})\.csv$", fname)
            if m:
                try:
                    existing.append(int(m.group(1)))
                except ValueError:
                    pass
        return (max(existing) + 1) if existing else 1
    
    batch_index = get_next_batch_index()
    total_created = 0
    batches_processed = 0
    total_names_processed = 0
    
    while True:
        # Stop if we've processed the desired number of names
        if total_names_processed >= target_total:
            print(f"✅ Processed {total_names_processed} HuggingFace names (target: {target_total}). Stopping.")
            break
        
        # Stop if we've processed the maximum batches
        if batches_processed >= max_batches:
            print(f"✅ Processed {batches_processed} batches ({total_names_processed} names total). Stopping.")
            break
        
        # Fetch batch
        remaining_needed = target_total - total_names_processed
        batch_limit = min(names_per_batch, remaining_needed)
        
        top_names = await fetch_huggingface_names(conn, batch_limit)
        if not top_names:
            print("✅ No more HuggingFace names to process. Done.")
            break
        
        if len(top_names) < batch_limit:
            print(f"⚠️  Only found {len(top_names)} unique names (requested {batch_limit})")
        
        # Show statistics for this batch
        positions = {}
        provinces = {}
        for n in top_names:
            pos = n.get('position', 'Unknown')
            prov = n.get('province', 'Unknown')
            positions[pos] = positions.get(pos, 0) + 1
            provinces[prov] = provinces.get(prov, 0) + 1
        
        print(f"\n{'='*80}")
        print(f"📋 Processing batch {batch_index}: {len(top_names)} HuggingFace names")
        print(f"   Top positions: {', '.join([f'{pos}({cnt})' for pos, cnt in sorted(positions.items(), key=lambda x: -x[1])[:3]])}")
        print(f"   Top provinces: {', '.join([f'{prov}({cnt})' for prov, cnt in sorted(provinces.items(), key=lambda x: -x[1])[:3]])}")
        print(f"   Progress: {total_names_processed + len(top_names)}/{target_total} names")
        print("=" * 80)
        
        total_names_processed += len(top_names)
        
        # Build prompt
        prompt = build_prompt(top_names, prompt_num=batch_index, names_per_prompt=len(top_names))
        
        # Call Perplexity
        print(f"🚀 Sending prompt to Perplexity API (batch {batch_index})...")
        reply = call_llm(prompt)
        
        # Extract CSV
        csv_text = extract_csv_from_reply(reply)
        if not csv_text or ',' not in csv_text:
            print("❌ Could not extract CSV from reply; marking names as processed to avoid repeats")
            await mark_processed(conn, [n['full_name'] for n in top_names])
            batch_index += 1
            continue
        
        # Save CSV
        out_file = f"llm_huggingface_{batch_index:02d}.csv"
        with open(out_file, 'w', encoding='utf-8', newline='') as f:
            f.write(csv_text if csv_text.endswith('\n') else csv_text + '\n')
        print(f"✅ Saved CSV to {out_file}")
        
        # Process CSV
        processor = EnvLLMCSVProcessor()
        try:
            await processor.connect()
            await processor.setup_connection_types()
            await processor.process_csv_file(out_file)
            await processor.show_relationship_summary()
        finally:
            await processor.close()
        
        # Mark as processed
        await mark_processed(conn, [n['full_name'] for n in top_names])
        
        batches_processed += 1
        batch_index += 1
        
        print(f"✅ Batch {batch_index - 1} complete!")
        print(f"   Processed: {total_names_processed}/{target_total} names")
        print(f"   Batches: {batches_processed}/{max_batches}")
    
    await conn.close()
    
    print("\n" + "=" * 80)
    print("🎉 HUGGINGFACE PERPLEXITY PROCESSING COMPLETE")
    print("=" * 80)
    print(f"Total names processed: {total_names_processed}")
    print(f"Total batches created: {batches_processed}")
    print(f"CSV files created: llm_huggingface_01.csv through llm_huggingface_{batch_index-1:02d}.csv")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())


#!/usr/bin/env python3
"""
Get top BAC position holders and find relationships/news that tie them to politicians
via Perplexity API.

Flow:
1) Load DB credentials from .env
2) Get top BAC position holders (excluding already processed)
3) Process 30 BAC holders per batch/page
4) For each batch, query Perplexity for relationships and news with politicians
5) Save results as CSV files (llm_bac_relationships_<page>.csv)
6) Insert into dynasty.bac_politician_relationships table
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


async def get_dynasty_conn():
    """Get connection to Dynasty database"""
    return await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=_int_env('POSTGRES_PORT', 5432),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )


async def ensure_aux_tables(dynasty_conn):
    """Ensure auxiliary tables exist for tracking processed BAC holders"""
    # Track processed BAC holders to avoid repeats
    await dynasty_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS llm_processed_bac_holders (
            id SERIAL PRIMARY KEY,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            position TEXT NOT NULL,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(first_name, last_name, position)
        )
        """
    )
    
    # Store BAC-politician relationships
    await dynasty_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bac_politician_relationships (
            id SERIAL PRIMARY KEY,
            bac_first_name TEXT NOT NULL,
            bac_last_name TEXT NOT NULL,
            bac_position TEXT NOT NULL,
            politician_name TEXT NOT NULL,
            politician_first_name TEXT,
            politician_last_name TEXT,
            relationship_type TEXT NOT NULL,
            relationship_description TEXT,
            news_article_title TEXT,
            source_url TEXT,
            confidence_level INT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(bac_first_name, bac_last_name, bac_position, politician_name, relationship_type)
        )
        """
    )
    
    # Create index for faster lookups
    try:
        await dynasty_conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_bac_relationships_politician 
            ON bac_politician_relationships(politician_first_name, politician_last_name)
            """
        )
    except Exception:
        pass


async def fetch_top_bac_holders(dynasty_conn, limit: int = 300) -> List[Dict]:
    """Get top BAC position holders, prioritized by position frequency"""
    
    # Get BAC holders with their position frequency, excluding already processed
    rows = await dynasty_conn.fetch(
        """
        SELECT 
            first_name,
            last_name,
            position,
            COUNT(*) as position_count,
            STRING_AGG(DISTINCT province, ', ' ORDER BY province) as provinces,
            STRING_AGG(DISTINCT municipality_city, ', ' ORDER BY municipality_city) as municipalities
        FROM political_dynasties
        WHERE UPPER(position) LIKE '%BAC%'
          AND first_name IS NOT NULL 
          AND last_name IS NOT NULL
          AND first_name != ''
          AND last_name != ''
          AND CONCAT(first_name, '|', last_name, '|', position) NOT IN (
              SELECT CONCAT(first_name, '|', last_name, '|', position)
              FROM llm_processed_bac_holders
          )
        GROUP BY first_name, last_name, position
        ORDER BY position_count DESC, last_name, first_name
        LIMIT $1
        """,
        limit * 2  # Get more to handle deduplication
    )
    
    # Deduplicate by name (keep highest position_count)
    bac_holders = []
    seen_names = set()
    
    for row in rows:
        name_key = (row['first_name'].upper().strip(), row['last_name'].upper().strip())
        if name_key in seen_names:
            continue
        seen_names.add(name_key)
        
        bac_holders.append({
            'first_name': row['first_name'].strip(),
            'last_name': row['last_name'].strip(),
            'position': row['position'].strip(),
            'position_count': row.get('position_count', 0) or 0,
            'provinces': row.get('provinces', ''),
            'municipalities': row.get('municipalities', '')
        })
    
    # Sort by position count and return top limit
    bac_holders.sort(key=lambda x: x['position_count'], reverse=True)
    return bac_holders[:limit]


def build_prompt(bac_holders: List[Dict], page_num: int) -> str:
    """Build Perplexity prompt for finding relationships with politicians"""
    
    prompt = f"""# Philippine BAC Officials - Political Relationships Discovery (Page {page_num})

You are a precise research assistant. For each BAC (Bids and Awards Committee) official listed below, find verifiable relationships, connections, and news articles that tie them to politicians, political families, or government officials.

## BAC Officials to Analyze (total {len(bac_holders)}):
"""
    
    for i, b in enumerate(bac_holders, 1):
        full_name = f"{b['first_name']} {b['last_name']}"
        prompt += f"{i}. {full_name} - {b['position']}\n"
        if b.get('provinces'):
            prompt += f"   Location: {b['provinces']}\n"
    
    prompt += f"""
## Your Task:
1. For each BAC official, identify:
   - **Political relationships**: Family connections to politicians (parent, sibling, spouse, in-laws, cousins, etc.)
   - **Political appointments**: Connections to elected officials who may have appointed them
   - **Co-attendance at events**: Both attended the same events such as:
     * Weddings (especially political family weddings)
     * Inaugurations (public office inaugurations, building inaugurations, etc.)
     * Political rallies or campaign events
     * Government ceremonies or official functions
     * Business launches or corporate events
     * Social gatherings (charity events, anniversaries, etc.)
   - **News articles**: Recent news stories linking them to politicians, corruption cases, or political controversies
   - **Business connections**: Any business ties to politicians or their families
   - **Previous positions**: Any previous government positions held before becoming BAC official

2. Use credible sources (Philippine news sites, SEC records, government websites, social media posts, event photos/coverage, reputable investigative journalism). Provide a source URL for each relationship.

3. Return results strictly as CSV text with EXACTLY these columns in this order:
   - bac_first_name (first name of the BAC official)
   - bac_last_name (last name of the BAC official)
   - bac_position (their BAC position)
   - politician_name (full name of the politician/government official they're connected to)
   - relationship_type (family, appointment, co_attendance_wedding, co_attendance_inauguration, co_attendance_rally, co_attendance_ceremony, business, controversy, previous_position, etc.)
   - relationship_description (brief description of the connection or event they both attended)
   - news_article_title (title of news article if found, otherwise blank)
   - source_url (URL where this information was found - photo gallery, news article, social media, etc.)
   - confidence_level (1-10, where 10 is most confident based on verified sources)

STRICT OUTPUT RULES:
- Return a single fenced code block that begins with ```csv and ends with ```.
- Include a single header row followed by data rows.
- **CRITICAL**: Only include rows where you found VERIFIABLE relationships or connections. Do NOT include rows with empty values.
- All required columns (bac_first_name, bac_last_name, bac_position, politician_name, relationship_type, relationship_description, source_url) must have non-empty values.
- Only news_article_title can be empty if there's no specific article.
- Do not include commentary outside the CSV block. If no relationships are found, return ONLY the header row with no data rows.
- Use the exact names as listed above (don't normalize or change them).
- Focus on connections to CURRENT or FORMER elected officials (Senators, Congressmen, Mayors, Governors, etc.)
- If you cannot find any verifiable relationships for a person, do NOT create an empty row for them.

IMPORTANT: If no relationships are found for any BAC official in this batch, return just the CSV header row with NO data rows. Do not include placeholder rows with empty values.
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
            { 'role': 'system', 'content': 'Return only the requested CSV. Be precise and use credible sources. Focus on verified relationships and news articles.' },
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


async def parse_politician_name(politician_name: str) -> tuple:
    """Parse politician name into first and last name"""
    parts = politician_name.strip().split()
    if len(parts) == 0:
        return None, None
    elif len(parts) == 1:
        return None, parts[0]
    else:
        return parts[0], ' '.join(parts[1:])


async def upsert_bac_relationships(dynasty_conn, csv_path: str) -> int:
    """Insert BAC-politician relationships from CSV into database"""
    created = 0
    skipped = 0
    
    if not os.path.exists(csv_path):
        return created
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            bac_first = (row.get('bac_first_name') or '').strip()
            bac_last = (row.get('bac_last_name') or '').strip()
            bac_position = (row.get('bac_position') or '').strip()
            politician_name = (row.get('politician_name') or '').strip()
            relationship_type = (row.get('relationship_type') or '').strip().lower()
            relationship_desc = (row.get('relationship_description') or '').strip()
            news_title = (row.get('news_article_title') or '').strip()
            source_url = (row.get('source_url') or '').strip()
            
            try:
                confidence_level = int(row.get('confidence_level') or 0)
            except ValueError:
                confidence_level = 0
            
            if not bac_first or not bac_last or not bac_position or not politician_name or not relationship_type:
                continue
            
            # Reject unnamed politicians
            if 'unnamed' in politician_name.lower():
                skipped += 1
                continue
            
            # Reject controversy relationships
            if relationship_type == 'controversy':
                skipped += 1
                continue
            
            # Minimum confidence requirement: 8/10 for all relationships
            if confidence_level < 8:
                skipped += 1
                continue
            
            # Co-attendance: Only wedding and inauguration (not ceremony/awarding), require 10/10
            valid_co_attendance_types = [
                'co_attendance_wedding', 'co-attendance_wedding',
                'co_attendance_inauguration', 'co-attendance_inauguration',
                'project_launch', 'inauguration'
            ]
            
            if relationship_type in valid_co_attendance_types:
                if confidence_level < 10:
                    skipped += 1
                    continue
            elif relationship_type in ['co_attendance_ceremony', 'co-attendance_ceremony', 'co_attendance_rally', 'co-attendance_rally']:
                # Reject awarding ceremonies and rallies
                skipped += 1
                continue
            
            # Work relationships: Record all except controversy (already filtered above)
            # This includes: appointment, project_connection, business, previous_position, etc.
            
            # Parse politician name
            pol_first, pol_last = await parse_politician_name(politician_name)
            
            # Insert into bac_politician_relationships
            try:
                result = await dynasty_conn.execute(
                    """
                    INSERT INTO bac_politician_relationships (
                        bac_first_name, bac_last_name, bac_position,
                        politician_name, politician_first_name, politician_last_name,
                        relationship_type, relationship_description,
                        news_article_title, source_url, confidence_level
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (bac_first_name, bac_last_name, bac_position, politician_name, relationship_type) DO NOTHING
                    """,
                    bac_first, bac_last, bac_position,
                    politician_name, pol_first, pol_last,
                    relationship_type, relationship_desc,
                    news_title, source_url, confidence_level
                )
                
                if 'INSERT 0 1' in result or (result.startswith('INSERT') and '0 1' in result):
                    created += 1
            except Exception as e:
                # Fallback: try without ON CONFLICT
                try:
                    existing = await dynasty_conn.fetchval(
                        """
                        SELECT id FROM bac_politician_relationships
                        WHERE bac_first_name = $1 AND bac_last_name = $2 
                          AND bac_position = $3 AND politician_name = $4
                          AND relationship_type = $5
                        """,
                        bac_first, bac_last, bac_position, politician_name, relationship_type
                    )
                    if not existing:
                        await dynasty_conn.execute(
                            """
                            INSERT INTO bac_politician_relationships (
                                bac_first_name, bac_last_name, bac_position,
                                politician_name, politician_first_name, politician_last_name,
                                relationship_type, relationship_description,
                                news_article_title, source_url, confidence_level
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                            """,
                            bac_first, bac_last, bac_position,
                            politician_name, pol_first, pol_last,
                            relationship_type, relationship_desc,
                            news_title, source_url, confidence_level
                        )
                        created += 1
                except Exception:
                    pass
    
    if skipped > 0:
        print(f"⚠️  Skipped {skipped} relationships (unnamed politicians, controversies, low confidence, or invalid co-attendance types)")
    return created


async def mark_bac_holders_processed(dynasty_conn, bac_holders: List[Dict]):
    """Mark BAC holders as processed"""
    for b in bac_holders:
        try:
            await dynasty_conn.execute(
                """
                INSERT INTO llm_processed_bac_holders (first_name, last_name, position)
                VALUES ($1, $2, $3)
                ON CONFLICT (first_name, last_name, position) DO NOTHING
                """,
                b['first_name'], b['last_name'], b['position']
            )
        except Exception:
            pass


def get_output_dir() -> Path:
    """Get output directory for CSV files"""
    script_dir = Path(__file__).resolve().parent
    output_dir = script_dir / 'bac_relationships_csvs'
    output_dir.mkdir(exist_ok=True)
    return output_dir


async def main():
    # Load environment variables first
    load_env_from_dotenv()
    load_dotenv()
    
    bac_holders_per_page = _int_env('BAC_HOLDERS_PER_PAGE', 30)
    total_bac_holders = _int_env('TOTAL_BAC_HOLDERS', 300)
    
    dynasty_conn = await get_dynasty_conn()
    
    try:
        await ensure_aux_tables(dynasty_conn)
        
        # Get top BAC holders
        print(f"🔍 Fetching top {total_bac_holders} BAC position holders...")
        all_bac_holders = await fetch_top_bac_holders(dynasty_conn, limit=total_bac_holders)
        
        if not all_bac_holders:
            print("✅ No BAC holders to process.")
            return
        
        print(f"✅ Found {len(all_bac_holders)} BAC holders to process")
        print(f"📊 Top 10 by position frequency:")
        for i, b in enumerate(all_bac_holders[:10], 1):
            full_name = f"{b['first_name']} {b['last_name']}"
            print(f"   {i:2d}. {full_name:40s} | {b['position'][:30]:30s} ({b['position_count']} records)")
        print()
        
        # Process in pages of 30
        output_dir = get_output_dir()
        total_pages = (len(all_bac_holders) + bac_holders_per_page - 1) // bac_holders_per_page
        
        for page in range(total_pages):
            start_idx = page * bac_holders_per_page
            end_idx = min(start_idx + bac_holders_per_page, len(all_bac_holders))
            page_bac_holders = all_bac_holders[start_idx:end_idx]
            
            print(f"\n{'='*80}")
            print(f"📄 Processing Page {page + 1}/{total_pages} (BAC holders {start_idx + 1}-{end_idx})")
            print(f"{'='*80}")
            
            prompt = build_prompt(page_bac_holders, page + 1)
            print(f"🚀 Sending prompt to Perplexity for {len(page_bac_holders)} BAC holders...")
            
            try:
                reply = call_perplexity(prompt)
                csv_text = extract_csv_from_reply(reply)
                
                # Log first 500 chars of reply for debugging
                if page == 0:  # Only log first page
                    print(f"📝 Perplexity reply preview (first 500 chars):")
                    print(reply[:500])
                    print()
                
                if not csv_text or ',' not in csv_text:
                    print(f'⚠️ Could not extract CSV from reply for page {page + 1}')
                    print(f'   Reply length: {len(reply)} chars')
                    # Mark as processed anyway to avoid infinite loops
                    await mark_bac_holders_processed(dynasty_conn, page_bac_holders)
                    continue
                
                # Save CSV
                csv_file = output_dir / f"llm_bac_relationships_page_{page + 1:03d}.csv"
                with open(csv_file, 'w', encoding='utf-8', newline='') as f:
                    f.write(csv_text if csv_text.endswith('\n') else csv_text + '\n')
                print(f"✅ Saved CSV to {csv_file}")
                
                # Insert into database
                created = await upsert_bac_relationships(dynasty_conn, csv_file)
                print(f"📊 Inserted {created} relationships into bac_politician_relationships")
                
                # Mark as processed
                await mark_bac_holders_processed(dynasty_conn, page_bac_holders)
                print(f"✅ Marked {len(page_bac_holders)} BAC holders as processed")
                
            except Exception as e:
                print(f"❌ Error processing page {page + 1}: {e}")
                import traceback
                traceback.print_exc()
                # Mark as processed to avoid retrying same page indefinitely
                await mark_bac_holders_processed(dynasty_conn, page_bac_holders)
        
        print(f"\n{'='*80}")
        print("✅ Processing complete!")
        print(f"{'='*80}")
        print(f"📁 CSV files saved to: {output_dir}")
        print(f"📊 Total BAC holders processed: {len(all_bac_holders)}")
        print(f"📄 Total pages: {total_pages}")
        
    finally:
        await dynasty_conn.close()


if __name__ == '__main__':
    asyncio.run(main())


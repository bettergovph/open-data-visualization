#!/usr/bin/env python3
"""
Process specific names through Perplexity to find relationships
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


async def get_dynasty_conn():
    """Get connection to Dynasty database"""
    return await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )


async def fetch_name_info(dynasty_conn, names: List[str]) -> List[Dict]:
    """Fetch name information from database"""
    name_info_list = []
    
    for name in names:
        # Split name into first and last
        parts = name.strip().split()
        if len(parts) < 2:
            continue
        
        # Try different combinations (first last, or treat all but last as first)
        first_name = parts[0]
        last_name = ' '.join(parts[1:])
        
        # Query database for this person
        records = await dynasty_conn.fetch('''
            SELECT 
                first_name,
                last_name,
                position,
                COUNT(*) as position_count,
                STRING_AGG(DISTINCT province, ', ' ORDER BY province) as provinces,
                STRING_AGG(DISTINCT municipality_city, ', ' ORDER BY municipality_city) as municipalities,
                STRING_AGG(DISTINCT region, ', ' ORDER BY region) as regions
            FROM political_dynasties
            WHERE (
                UPPER(first_name) = $1 AND UPPER(last_name) = $2
                OR UPPER(first_name) LIKE $3 AND UPPER(last_name) = $2
            )
            GROUP BY first_name, last_name, position
            ORDER BY position_count DESC
            LIMIT 1
        ''', first_name.upper(), last_name.upper(), f'{first_name.upper()}%')
        
        if records:
            record = records[0]
            name_info_list.append({
                'first_name': record['first_name'].strip(),
                'last_name': record['last_name'].strip(),
                'position': record['position'].strip(),
                'position_count': record.get('position_count', 0) or 0,
                'provinces': record.get('provinces', ''),
                'municipalities': record.get('municipalities', ''),
                'regions': record.get('regions', '')
            })
        else:
            # If not found, create entry from name provided
            name_info_list.append({
                'first_name': first_name.strip(),
                'last_name': last_name.strip(),
                'position': 'UNKNOWN',
                'position_count': 0,
                'provinces': '',
                'municipalities': '',
                'regions': ''
            })
    
    return name_info_list


def build_prompt(names: List[Dict]) -> str:
    """Build Perplexity prompt for finding relationships"""
    
    prompt = f"""# Philippine Political Figures - Relationships Discovery

You are a precise research assistant. For each person listed below, find verifiable relationships, connections, and news articles that tie them to politicians, political families, or government officials.

## People to Analyze (total {len(names)}):
"""
    
    for i, n in enumerate(names, 1):
        full_name = f"{n['first_name']} {n['last_name']}"
        prompt += f"{i}. {full_name} - {n['position']}\n"
        location_parts = []
        if n.get('regions'):
            location_parts.append(n['regions'])
        if n.get('provinces'):
            location_parts.append(n['provinces'])
        if n.get('municipalities'):
            location_parts.append(n['municipalities'])
        if location_parts:
            prompt += f"   Location: {', '.join(location_parts)}\n"
    
    prompt += f"""
## Your Task:
1. For each person, identify:
   - **Political relationships**: Family connections to politicians (parent, sibling, spouse, in-laws, cousins, etc.)
   - **Political appointments**: Connections to elected officials who may have appointed them
   - **Co-attendance at events**: Both attended the same events such as:
     * Weddings (especially political family weddings)
     * Project launches or inaugurations (building inaugurations, infrastructure inaugurations, etc.)
     * Political rallies or campaign events (only if significant, not routine public events)
   - **News articles**: Recent news stories linking them to politicians, corruption cases, infrastructure projects with political connections, or political controversies
   - **Business connections**: Any business ties to politicians or their families
   - **Project connections**: Involvement in infrastructure projects that are politically significant or linked to politicians
   - **Previous positions**: Any previous government positions held

2. Use credible sources (Philippine news sites, SEC records, government websites, social media posts, event photos/coverage, reputable investigative journalism). Provide a source URL for each relationship.

3. Return results strictly as CSV text with EXACTLY these columns in this order:
   - person_first_name (first name of the person)
   - person_last_name (last name of the person)
   - person_position (their position)
   - politician_name (full name of the politician/government official they're connected to)
   - relationship_type (family, appointment, co_attendance_wedding, co_attendance_inauguration, co_attendance_rally, business, project_connection, previous_position, etc.)
   - relationship_description (brief description of the connection or event they both attended)
   - news_article_title (title of news article if found, otherwise blank)
   - source_url (URL where this information was found - photo gallery, news article, social media, etc.)
   - confidence_level (1-10, where 10 is most confident based on verified sources)

STRICT OUTPUT RULES:
- Return a single fenced code block that begins with ```csv and ends with ```.
- Include a single header row followed by data rows.
- **CRITICAL**: Only include rows where you found VERIFIABLE relationships or connections. Do NOT include rows with empty values.
- All required columns (person_first_name, person_last_name, person_position, politician_name, relationship_type, relationship_description, source_url) must have non-empty values.
- Only news_article_title can be empty if there's no specific article.
- Do not include commentary outside the CSV block. If no relationships are found, return ONLY the header row with no data rows.
- Use the exact names as listed above (don't normalize or change them).
- Focus on connections to CURRENT or FORMER elected officials (Senators, Congressmen, Mayors, Governors, etc.)
- If you cannot find any verifiable relationships for a person, do NOT create an empty row for them.
- Do NOT include "co_attendance_ceremony" - only weddings and inaugurations for co-attendance events.

IMPORTANT: If no relationships are found for any person in this batch, return just the CSV header row with NO data rows. Do not include placeholder rows with empty values.
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


async def upsert_name_relationships(dynasty_conn, csv_path: str) -> int:
    """Insert name-politician relationships from CSV into database"""
    created = 0
    skipped = 0
    
    if not os.path.exists(csv_path):
        return created
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            person_first = (row.get('person_first_name') or '').strip()
            person_last = (row.get('person_last_name') or '').strip()
            person_position = (row.get('person_position') or '').strip()
            politician_name = (row.get('politician_name') or '').strip()
            relationship_type = (row.get('relationship_type') or '').strip().lower()
            relationship_desc = (row.get('relationship_description') or '').strip()
            news_title = (row.get('news_article_title') or '').strip()
            source_url = (row.get('source_url') or '').strip()
            
            try:
                confidence_level = int(row.get('confidence_level') or 0)
            except ValueError:
                confidence_level = 0
            
            if not person_first or not person_last or not person_position or not politician_name or not relationship_type:
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
            
            # Parse politician name
            pol_first, pol_last = await parse_politician_name(politician_name)
            
            # Insert into all_names_politician_relationships
            try:
                result = await dynasty_conn.execute(
                    """
                    INSERT INTO all_names_politician_relationships (
                        person_first_name, person_last_name, person_position,
                        politician_name, politician_first_name, politician_last_name,
                        relationship_type, relationship_description,
                        news_article_title, source_url, confidence_level
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (person_first_name, person_last_name, person_position, politician_name, relationship_type) DO NOTHING
                    """,
                    person_first, person_last, person_position,
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
                        SELECT id FROM all_names_politician_relationships
                        WHERE person_first_name = $1 AND person_last_name = $2 
                          AND person_position = $3 AND politician_name = $4
                          AND relationship_type = $5
                        """,
                        person_first, person_last, person_position, politician_name, relationship_type
                    )
                    if not existing:
                        await dynasty_conn.execute(
                            """
                            INSERT INTO all_names_politician_relationships (
                                person_first_name, person_last_name, person_position,
                                politician_name, politician_first_name, politician_last_name,
                                relationship_type, relationship_description,
                                news_article_title, source_url, confidence_level
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                            """,
                            person_first, person_last, person_position,
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


async def main():
    # Specific names to process
    target_names = [
        'zaldy co',
        'martin romualdez',
        'christopher lawrence go',
        'bong go',
        'rodante marcoleta',
        'joel villanueva',
        'jinggoy estrada',
        'francis escudero'
    ]
    
    # Load environment variables first
    load_env_from_dotenv()
    load_dotenv()
    
    dynasty_conn = await get_dynasty_conn()
    
    try:
        # Ensure table exists
        await dynasty_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS all_names_politician_relationships (
                id SERIAL PRIMARY KEY,
                person_first_name TEXT NOT NULL,
                person_last_name TEXT NOT NULL,
                person_position TEXT NOT NULL,
                politician_name TEXT NOT NULL,
                politician_first_name TEXT,
                politician_last_name TEXT,
                relationship_type TEXT NOT NULL,
                relationship_description TEXT,
                news_article_title TEXT,
                source_url TEXT,
                confidence_level INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(person_first_name, person_last_name, person_position, politician_name, relationship_type)
            )
            """
        )
        
        print(f"🔍 Fetching information for {len(target_names)} specific names...")
        name_info_list = await fetch_name_info(dynasty_conn, target_names)
        
        print(f"✅ Found information for {len(name_info_list)} names")
        print(f"📊 Names to process:")
        for i, n in enumerate(name_info_list, 1):
            print(f"   {i}. {n['first_name']} {n['last_name']} - {n['position']}")
        print()
        
        # Build prompt and query Perplexity
        prompt = build_prompt(name_info_list)
        print(f"🚀 Sending prompt to Perplexity for {len(name_info_list)} names...")
        
        try:
            reply = call_perplexity(prompt)
            csv_text = extract_csv_from_reply(reply)
            
            print(f"📝 Perplexity reply preview (first 500 chars):")
            print(reply[:500])
            print()
            
            if not csv_text or ',' not in csv_text:
                print(f'⚠️ Could not extract CSV from reply')
                print(f'   Reply length: {len(reply)} chars')
                return
            
            # Save CSV
            output_dir = Path(__file__).resolve().parent / 'all_names_relationships_csvs'
            output_dir.mkdir(exist_ok=True)
            csv_file = output_dir / "llm_specific_names_relationships.csv"
            with open(csv_file, 'w', encoding='utf-8', newline='') as f:
                f.write(csv_text if csv_text.endswith('\n') else csv_text + '\n')
            print(f"✅ Saved CSV to {csv_file}")
            
            # Insert into database (with confidence filtering)
            created = await upsert_name_relationships(dynasty_conn, csv_file)
            print(f"📊 Inserted {created} relationships into all_names_politician_relationships")
            
        except Exception as e:
            print(f"❌ Error processing names: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"\n{'='*80}")
        print("✅ Processing complete!")
        print(f"{'='*80}")
        
    finally:
        await dynasty_conn.close()


if __name__ == '__main__':
    asyncio.run(main())


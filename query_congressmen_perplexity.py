#!/usr/bin/env python3
"""
Query Perplexity API for family relationships and company ownerships for the 6 congressmen.
One query per congressman (one page each).

This script will:
1. Query Perplexity for each congressman individually
2. Get family relationships and company ownerships
3. Save results to CSV files (one per congressman)
4. Can be used to add more connections to the constellation and projects table
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
from datetime import datetime


def load_env_from_dotenv():
    """Load environment variables from .env file"""
    root = Path(__file__).resolve().parent
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


async def get_congressman_info(conn, first_name: str, last_name: str) -> Dict:
    """Get congressman information from database"""
    person = await conn.fetchrow('''
        SELECT id, first_name, last_name, province, municipality_city, region, party, position
        FROM political_dynasties
        WHERE (
            UPPER(position) LIKE '%CONGRESSMAN%' 
            OR UPPER(position) LIKE '%CONGRESSMEN%' 
            OR UPPER(position) LIKE '%MEMBER, HOUSE OF REPRESENTATIVES%'
            OR UPPER(position) LIKE '%REPRESENTATIVE%PARTY-LIST%'
            OR UPPER(position) LIKE '%REPRESENTATIVE, %PARTY-LIST%'
        )
          AND (UPPER(first_name) LIKE $1 AND UPPER(last_name) LIKE $2)
        ORDER BY id DESC
        LIMIT 1
    ''', f"%{first_name.upper()}%", f"%{last_name.upper()}%")
    
    if person:
        return {
            'id': person['id'],
            'first_name': person['first_name'],
            'last_name': person['last_name'],
            'full_name': f"{person['first_name']} {person['last_name']}",
            'province': person['province'] or '',
            'municipality': person['municipality_city'] or '',
            'region': person['region'] or '',
            'party': person['party'] or '',
            'position': person['position'] or ''
        }
    return None


def build_perplexity_prompt(congressman: Dict) -> str:
    """Build Perplexity prompt for finding relationships and company ownerships"""
    
    full_name = congressman['full_name']
    location_parts = []
    if congressman.get('region'):
        location_parts.append(congressman['region'])
    if congressman.get('province'):
        location_parts.append(congressman['province'])
    if congressman.get('municipality'):
        location_parts.append(congressman['municipality'])
    location_str = ', '.join(location_parts) if location_parts else 'Philippines'
    
    prompt = f"""# Philippine Congressman - Family Relationships and Company Ownerships

You are a precise research assistant. Research {full_name}, a Philippine congressman, and find VERIFIED family relationships and company ownerships from credible sources like Wikipedia, Rappler, SEC records, and other reputable news sites.

## Person to Research:
**Name:** {full_name}
**Position:** {congressman.get('position', 'Congressman')}
**Location:** {location_str}
**Party:** {congressman.get('party', 'N/A')}

## Your Task:
1. **Find Family Relationships:**
   - Immediate family: parents, siblings, spouse, children
   - Extended family: uncles/aunts, cousins, in-laws, nephews/nieces
   - Political family connections
   - Marriage alliances with other political families

2. **Find Company Ownerships:**
   - Companies owned directly by {full_name}
   - Companies owned by family members (spouse, children, siblings, parents)
   - Companies where {full_name} or family members are officers, directors, incorporators
   - Construction companies, real estate companies, or other businesses
   - Include SEC registration numbers if available
   - Include ownership percentages if available

3. **Use Credible Sources:**
   - Wikipedia pages
   - Rappler articles
   - SEC records and filings
   - Official government websites
   - Reputable Philippine news sites (Inquirer, Philstar, ABS-CBN News, GMA News)
   - Business registration databases

4. **Return results in CSV format with TWO separate sections:**

### Section 1: Family Relationships CSV
Columns: person1_name, person2_name, relationship_type, relationship_description, source_url, confidence_level

### Section 2: Company Ownerships CSV
Columns: person_name, company_name, relationship_to_company, ownership_percentage, sec_number, source_url, confidence_level

## STRICT OUTPUT RULES:
- Return TWO separate CSV blocks: one for relationships, one for companies
- Each CSV block must be in a fenced code block: ```csv ... ```
- Include header rows in both CSVs
- Only include VERIFIED information with source URLs
- confidence_level: 1-10 (10 = highest confidence, verified by official records)
- Use exact names as they appear in sources
- For companies: Include full legal company names, not abbreviations
- For ownership: Include "owner", "co-owner", "director", "officer", "incorporator", "president", etc. as relationship_to_company
- If no data found for a section, return only the header row

## EXAMPLE OUTPUT FORMAT:

```csv
person1_name,person2_name,relationship_type,relationship_description,source_url,confidence_level
"{full_name}","JOHN DOE","Brother","Sibling relationship","https://rappler.com/example",9
"{full_name}","JANE DOE","Spouse","Married couple","https://wikipedia.org/example",10
```

```csv
person_name,company_name,relationship_to_company,ownership_percentage,sec_number,source_url,confidence_level
"{full_name}","ABC Construction Inc","Owner","100%","CS123456789","https://sec.gov.ph/example",10
"{full_name}","XYZ Realty Corp","Director","","CS987654321","https://rappler.com/example",9
"JOHN DOE (Brother)","ABC Construction Inc","Co-owner","50%","CS123456789","https://sec.gov.ph/example",10
```

Research {full_name} thoroughly and return complete CSV data for both family relationships and company ownerships.
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
        'max_tokens': 8000,  # Increased for comprehensive results
        'messages': [
            { 'role': 'system', 'content': 'You are a precise research assistant. Return only the requested CSV data in fenced code blocks. Be thorough and use credible sources.' },
            { 'role': 'user', 'content': prompt }
        ]
    }
    
    print("   📡 Calling Perplexity API...")
    resp = requests.post(url, json=payload, headers=headers, timeout=180)
    resp.raise_for_status()
    data = resp.json()
    return data.get('choices', [{}])[0].get('message', {}).get('content', '') or ''


def extract_csv_blocks(reply: str) -> Dict[str, str]:
    """Extract both CSV blocks from Perplexity reply"""
    result = {
        'relationships': '',
        'companies': ''
    }
    
    # Find all CSV blocks
    csv_blocks = re.findall(r"```csv\s*([\s\S]*?)```", reply, re.IGNORECASE)
    
    if len(csv_blocks) >= 1:
        # First CSV block is relationships
        result['relationships'] = csv_blocks[0].strip()
    
    if len(csv_blocks) >= 2:
        # Second CSV block is companies
        result['companies'] = csv_blocks[1].strip()
    elif len(csv_blocks) == 1:
        # Only one CSV block - try to determine which one by headers
        csv_text = csv_blocks[0].strip()
        if 'person1_name' in csv_text or 'relationship_type' in csv_text:
            result['relationships'] = csv_text
        elif 'company_name' in csv_text or 'relationship_to_company' in csv_text:
            result['companies'] = csv_text
    
    # Try generic code blocks if CSV blocks not found
    if not result['relationships'] and not result['companies']:
        generic_blocks = re.findall(r"```[a-zA-Z]*\s*([\s\S]*?)```", reply)
        if generic_blocks:
            for block in generic_blocks:
                block_text = block.strip()
                if 'person1_name' in block_text or 'relationship_type' in block_text:
                    result['relationships'] = block_text
                elif 'company_name' in block_text or 'relationship_to_company' in block_text:
                    result['companies'] = block_text
    
    return result


def save_csv_file(csv_text: str, output_dir: Path, filename: str):
    """Save CSV text to file"""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename
    
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        f.write(csv_text if csv_text.endswith('\n') else csv_text + '\n')
    
    return output_path


async def query_congressman(conn, first_name: str, last_name: str, display_name: str, output_dir: Path):
    """Query Perplexity for a single congressman"""
    print(f"\n{'='*80}")
    print(f"📋 Processing: {display_name}")
    print(f"   Search pattern: {first_name} {last_name}")
    print(f"{'='*80}")
    
    # Get congressman info from database
    congressman = await get_congressman_info(conn, first_name, last_name)
    
    # If not found, try searching for party-list representatives
    if not congressman:
        # Try searching with party-list position
        person = await conn.fetchrow('''
            SELECT id, first_name, last_name, province, municipality_city, region, party, position
            FROM political_dynasties
            WHERE (
                UPPER(position) LIKE '%REPRESENTATIVE%PARTY-LIST%'
                OR UPPER(position) LIKE '%REPRESENTATIVE, %PARTY-LIST%'
                OR UPPER(position) LIKE '%CWS%'
                OR UPPER(position) LIKE '%AKO BICOL%'
            )
              AND (UPPER(first_name) LIKE $1 AND UPPER(last_name) LIKE $2)
            ORDER BY id DESC
            LIMIT 1
        ''', f"%{first_name.upper()}%", f"%{last_name.upper()}%")
        
        if person:
            congressman = {
                'id': person['id'],
                'first_name': person['first_name'],
                'last_name': person['last_name'],
                'full_name': display_name,  # Use verified full name
                'province': person['province'] or '',
                'municipality': person['municipality_city'] or '',
                'region': person['region'] or '',
                'party': person['party'] or '',
                'position': person['position'] or ''
            }
    
    if not congressman:
        print(f"⚠️  Congressman not found in database: {first_name} {last_name}")
        print(f"   Using verified name from Perplexity: {display_name}")
        # Create a minimal congressman entry for Perplexity query
        congressman = {
            'id': None,
            'first_name': first_name,
            'last_name': last_name,
            'full_name': display_name,
            'province': '',
            'municipality': '',
            'region': '',
            'party': '',
            'position': 'Congressman'
        }
    
    print(f"✅ Found: {congressman['full_name']}")
    print(f"   Position: {congressman.get('position', 'N/A')}")
    print(f"   Location: {congressman.get('province', 'N/A')}")
    print(f"   Party: {congressman.get('party', 'N/A')}")
    
    # Build prompt
    prompt = build_perplexity_prompt(congressman)
    
    # Query Perplexity
    print(f"\n🚀 Querying Perplexity API...")
    try:
        reply = call_perplexity(prompt)
        
        print(f"📝 Received reply ({len(reply)} chars)")
        
        # Extract CSV blocks
        csv_data = extract_csv_blocks(reply)
        
        # Save relationships CSV
        if csv_data['relationships']:
            safe_name = congressman['full_name'].replace(' ', '_').replace('/', '_')
            rel_filename = f"{safe_name}_relationships.csv"
            rel_path = save_csv_file(csv_data['relationships'], output_dir, rel_filename)
            print(f"✅ Saved relationships CSV: {rel_path}")
            
            # Count rows
            rows = csv_data['relationships'].split('\n')
            data_rows = [r for r in rows if r.strip() and not r.startswith('person1_name')]
            print(f"   Found {len(data_rows)} relationship records")
        else:
            print(f"⚠️  No relationships CSV found in reply")
        
        # Save companies CSV
        if csv_data['companies']:
            safe_name = congressman['full_name'].replace(' ', '_').replace('/', '_')
            comp_filename = f"{safe_name}_companies.csv"
            comp_path = save_csv_file(csv_data['companies'], output_dir, comp_filename)
            print(f"✅ Saved companies CSV: {comp_path}")
            
            # Count rows
            rows = csv_data['companies'].split('\n')
            data_rows = [r for r in rows if r.strip() and not r.startswith('person_name') and not r.startswith('company_name')]
            print(f"   Found {len(data_rows)} company records")
        else:
            print(f"⚠️  No companies CSV found in reply")
        
        # Save full reply for debugging
        safe_name = congressman['full_name'].replace(' ', '_').replace('/', '_')
        reply_filename = f"{safe_name}_full_reply.txt"
        reply_path = output_dir / reply_filename
        with open(reply_path, 'w', encoding='utf-8') as f:
            f.write(reply)
        print(f"💾 Saved full reply: {reply_path}")
        
    except Exception as e:
        print(f"❌ Error querying Perplexity: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Main function to query all 6 congressmen"""
    print("="*80)
    print("PERPLEXITY QUERY: CONGRESSMEN FAMILY RELATIONSHIPS & COMPANY OWNERSHIPS")
    print("="*80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # Load environment
    load_env_from_dotenv()
    load_dotenv()
    
    # List of 6 congressmen (using verified names from Perplexity)
    # Format: (first_name, last_name, full_display_name)
    congressmen = [
        ("FERDINAND MARTIN", "ROMUALDEZ", "Ferdinand Martin Gomez Romualdez"),  # Martin Romualdez
        ("ELIZALDY", "CO", "Elizaldy Salcedo Co"),  # Zaldy Co
        ("DAVID", "SUAREZ", "David Catarina Suarez"),  # David Suarez
        ("AURELIO", "GONZALES", "Aurelio Dueñas Gonzales Jr."),  # Aurelio Gonzales Jr
        ("MANUEL JOSE", "DALIPE", "Manuel Jose Mendoza Dalipe"),  # Mannix Dalipe
        ("EDWIN", "GARDIOLA", "Tirso Edwin Loleng Gardiola"),  # Edwin Gardiola
    ]
    
    # Create output directory
    output_dir = Path(__file__).resolve().parent / 'congressmen_perplexity_results'
    output_dir.mkdir(exist_ok=True)
    
    print(f"📁 Output directory: {output_dir}")
    print(f"📋 Processing {len(congressmen)} congressmen (one query per person)\n")
    
    # Connect to database
    conn = await get_dynasty_conn()
    
    try:
        # Process each congressman
        for i, (first_name, last_name, display_name) in enumerate(congressmen, 1):
            print(f"\n[{i}/{len(congressmen)}]")
            await query_congressman(conn, first_name, last_name, display_name, output_dir)
            
            # Small delay between queries to avoid rate limiting
            if i < len(congressmen):
                print(f"\n⏳ Waiting 5 seconds before next query...")
                await asyncio.sleep(5)
        
        print(f"\n{'='*80}")
        print("✅ ALL QUERIES COMPLETE!")
        print(f"{'='*80}")
        print(f"📁 Results saved to: {output_dir}")
        print(f"   - One relationships CSV per congressman")
        print(f"   - One companies CSV per congressman")
        print(f"   - Full reply text files for debugging")
        print(f"\nFinished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())


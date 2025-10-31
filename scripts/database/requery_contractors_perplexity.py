#!/usr/bin/env python3
"""
Re-query Perplexity API for the 15 contractors with contractor-mediated constellations.

This script will:
1. Identify the 15 contractors from contractor_dynasty_matches
2. Query Perplexity API for fresh officer/owner data for each contractor
3. Save results to CSV files
4. Optionally compare with existing data to identify discrepancies
"""

import asyncio
import asyncpg
import os
import csv
import re
import requests
from typing import List, Dict
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from io import StringIO


def load_env_from_dotenv():
    """Load environment variables from .env file"""
    root = Path(__file__).resolve().parents[2]
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


async def get_db_connection():
    load_env_from_dotenv()
    load_dotenv()
    return await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
)


async def get_top_contractors_with_constellations(conn):
    """Get the top 15 contractors that have the most contractor-mediated constellations"""
    
    print("🔍 Identifying top contractors with constellations...")
    
    # Get contractors sorted by number of connections
    contractors = await conn.fetch("""
        SELECT 
            company_name as contractor_name,
            COUNT(DISTINCT dynasty_full_name) as connection_count
        FROM contractor_dynasty_matches
        GROUP BY company_name
        ORDER BY connection_count DESC
        LIMIT 15
    """)
    
    print(f"✅ Found {len(contractors)} top contractors")
    for i, c in enumerate(contractors[:10], 1):
        print(f"   {i}. {c['contractor_name']}: {c['connection_count']} connections")
    
    return [dict(c) for c in contractors]


def build_requery_prompt(contractors: List[Dict]) -> str:
    """Build Perplexity prompt for re-querying contractor officers"""
    
    prompt = f"""# Philippine Company Officers Verification Query

You are a precise research assistant. For each Philippine company listed below, find VERIFIED and CURRENT details about its owners, incorporators, officers, and directors from official SEC records or reliable sources. Return only a CSV in a single fenced code block.

## Companies to Verify (total {len(contractors)}):
"""
    
    for i, c in enumerate(contractors, 1):
        prompt += f"{i}. {c['contractor_name']}\n"
    
    prompt += f"""
## Your Task:
1. For each company, find the CURRENT and VERIFIED individuals who are: owners, incorporators, directors, officers, or key personnel (e.g., President, Treasurer, Corporate Secretary, Chairman, CEO).
2. Use ONLY credible sources in this priority order:
   - Official SEC records and SEC EDGAR filings
   - SEC registration documents
   - Verified business registration databases
   - Official company websites
   - Reputable business news sources (as secondary verification)
3. Provide a source URL for each row that links to the verification.
4. Return results strictly as CSV text with EXACTLY these columns in this order:
   - company_name (use the exact company name from the list above)
   - person_name (full name of the individual exactly as it appears in SEC records)
   - role (owner, director, officer, incorporator, president, treasurer, secretary, etc.)
   - source_url (URL where this information was verified)
   - confidence_level (1-10, where 10 is most confident based on source reliability)
   - verification_date (YYYY-MM-DD if available, otherwise leave blank)

STRICT OUTPUT RULES:
- Return a single fenced code block that begins with ```csv and ends with ```.
- Include a single header row followed by data rows.
- Only include complete rows (all columns non-empty except verification_date).
- Do not include commentary outside the CSV block.
- Use the exact company_name as listed above (don't normalize or change it).
- If multiple roles exist for the same person, create separate rows for each role.

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
        'max_tokens': 8000,  # Increased for multiple contractors
        'messages': [
            { 'role': 'system', 'content': 'You are a precise research assistant. Return only the requested CSV with verified data.' },
            { 'role': 'user', 'content': prompt }
        ]
    }
    
    print("   📡 Calling Perplexity API...")
    resp = requests.post(url, json=payload, headers=headers, timeout=180)
    resp.raise_for_status()
    data = resp.json()
    content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
    return content or ''


def extract_csv_from_reply(reply: str) -> str:
    """Extract CSV content from Perplexity reply"""
    # Try to find CSV in fenced code block
    m = re.search(r"```csv\s*([\s\S]*?)```", reply, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    
    # Try generic code block
    m2 = re.search(r"```[a-zA-Z]*\s*([\s\S]*?)```", reply)
    if m2:
        return m2.group(1).strip()
    
    # Return raw reply if no code blocks found
    return reply.strip()


async def save_csv_results(csv_text: str, output_file: str):
    """Save CSV results to file"""
    output_dir = Path('family_analysis/family_parser/contractor_officers_csvs')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / output_file
    
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        f.write(csv_text if csv_text.endswith('\n') else csv_text + '\n')
    
    return output_path


async def compare_with_existing(conn, contractor_name: str, new_results: List[Dict]):
    """Compare new Perplexity results with existing data"""
    
    # Get existing matches for this contractor
    existing = await conn.fetch("""
        SELECT DISTINCT
            person_name,
            role,
            dynasty_full_name
        FROM contractor_dynasty_matches
        WHERE company_name = $1
    """, contractor_name)
    
    existing_map = {}
    for e in existing:
        key = f"{e['person_name']}|{e['role']}"
        if key not in existing_map:
            existing_map[key] = []
        existing_map[key].append(e['dynasty_full_name'])
    
    # Get new results
    new_map = {}
    for r in new_results:
        key = f"{r['person_name']}|{r['role']}"
        if key not in new_map:
            new_map[key] = r
    
    # Compare
    discrepancies = []
    
    # Check for new officers not in existing data
    for key, person_data in new_map.items():
        if key not in existing_map:
            discrepancies.append({
                'type': 'new_officer',
                'person_name': person_data['person_name'],
                'role': person_data['role'],
                'source_url': person_data.get('source_url', ''),
                'confidence': person_data.get('confidence_level', 0)
            })
    
    # Check for existing officers not in new data
    for key in existing_map:
        if key not in new_map:
            discrepancies.append({
                'type': 'removed_officer',
                'person_name': key.split('|')[0],
                'role': key.split('|')[1],
                'existing_dynasty_matches': existing_map[key]
            })
    
    return discrepancies


async def requery_contractors():
    """Main function to re-query Perplexity for contractors"""
    
    print("=" * 80)
    print("RE-QUERY PERPLEXITY FOR CONTRACTOR OFFICERS")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    conn = await get_db_connection()
    
    try:
        # Get the 15 contractors
        contractors = await get_top_contractors_with_constellations(conn)
        
        if not contractors:
            print("❌ No contractors found")
            return
        
        print(f"\n📋 Contractors to re-query:")
        for i, c in enumerate(contractors, 1):
            print(f"   {i}. {c['contractor_name']}")
        
        # Process all contractors in one query (or split into batches if needed)
        print(f"\n🚀 Querying Perplexity API for all {len(contractors)} contractors...")
        print("   (This may take a few minutes)")
        
        prompt = build_requery_prompt(contractors)
        reply = call_perplexity(prompt)
        csv_text = extract_csv_from_reply(reply)
        
        if not csv_text or ',' not in csv_text:
            print("❌ Could not extract CSV from Perplexity reply")
            print(f"   Reply preview: {reply[:500]}")
            return
        
        # Parse CSV
        f = StringIO(csv_text)
        reader = csv.DictReader(f)
        results = []
        
        for row in reader:
            if not row.get('company_name') or not row.get('person_name'):
                continue
            results.append({
                'company_name': row['company_name'].strip(),
                'person_name': row['person_name'].strip(),
                'role': row.get('role', '').strip(),
                'source_url': row.get('source_url', '').strip(),
                'confidence_level': int(row.get('confidence_level', 0)) if row.get('confidence_level') else 0,
                'verification_date': row.get('verification_date', '').strip()
            })
        
        print(f"✅ Received {len(results)} officer records from Perplexity")
        
        # Group by contractor
        by_contractor = {}
        for r in results:
            company = r['company_name']
            if company not in by_contractor:
                by_contractor[company] = []
            by_contractor[company].append(r)
        
        # Save results to CSV file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f'llm_contractor_officers_requery_{timestamp}.csv'
        output_path = await save_csv_results(csv_text, output_file)
        print(f"✅ Saved results to: {output_path}")
        
        # Compare with existing data for each contractor
        print(f"\n🔍 Comparing with existing data...")
        print("=" * 80)
        
        all_discrepancies = {}
        
        for contractor_name in contractors:
            contractor_name_str = contractor_name['contractor_name']
            new_results = by_contractor.get(contractor_name_str, [])
            
            discrepancies = await compare_with_existing(conn, contractor_name_str, new_results)
            
            if discrepancies:
                all_discrepancies[contractor_name_str] = discrepancies
                print(f"\n📊 {contractor_name_str}:")
                print(f"   New officers: {len([d for d in discrepancies if d['type'] == 'new_officer'])}")
                print(f"   Removed officers: {len([d for d in discrepancies if d['type'] == 'removed_officer'])}")
                
                # Show new officers
                new_officers = [d for d in discrepancies if d['type'] == 'new_officer']
                if new_officers:
                    print(f"   New officers found:")
                    for officer in new_officers[:5]:  # Show first 5
                        print(f"      • {officer['person_name']} ({officer['role']}) - Confidence: {officer['confidence']}")
                else:
                    print(f"   ✅ All officers match existing data")
            else:
                print(f"✅ {contractor_name_str}: All officers match existing data")
        
        # Generate comparison report
        if all_discrepancies:
            report_lines = []
            report_lines.append("=" * 80)
            report_lines.append("PERPLEXITY RE-QUERY COMPARISON REPORT")
            report_lines.append("=" * 80)
            report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            
            for contractor_name, discrepancies in all_discrepancies.items():
                report_lines.append(f"\n{contractor_name}")
                report_lines.append("-" * 80)
                
                new_officers = [d for d in discrepancies if d['type'] == 'new_officer']
                removed_officers = [d for d in discrepancies if d['type'] == 'removed_officer']
                
                if new_officers:
                    report_lines.append(f"\n🆕 NEW OFFICERS FOUND ({len(new_officers)}):")
                    for officer in new_officers:
                        report_lines.append(f"   • {officer['person_name']} ({officer['role']})")
                        report_lines.append(f"     Confidence: {officer['confidence']}/10")
                        report_lines.append(f"     Source: {officer['source_url']}")
                
                if removed_officers:
                    report_lines.append(f"\n❌ OFFICERS NOT FOUND IN NEW QUERY ({len(removed_officers)}):")
                    for officer in removed_officers:
                        report_lines.append(f"   • {officer['person_name']} ({officer['role']})")
                        if 'existing_dynasty_matches' in officer:
                            report_lines.append(f"     Was matched to: {', '.join(officer['existing_dynasty_matches'])}")
            
            report_content = '\n'.join(report_lines)
            report_file = f'PERPLEXITY_REQUERY_COMPARISON_{timestamp}.txt'
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report_content)
            
            print(f"\n✅ Comparison report saved to: {report_file}")
        
        print(f"\n{'=' * 80}")
        print("SUMMARY")
        print(f"{'=' * 80}")
        print(f"Total contractors queried: {len(contractors)}")
        print(f"Total officer records received: {len(results)}")
        print(f"Contractors with discrepancies: {len(all_discrepancies)}")
        print(f"\n✅ Re-query complete!")
        print(f"   CSV file: {output_path}")
        if all_discrepancies:
            print(f"   Comparison report: {report_file}")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    load_env_from_dotenv()
    load_dotenv()
    asyncio.run(requery_contractors())


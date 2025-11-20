#!/usr/bin/env python3
"""
Verify AMO positions using Perplexity Sonar API.
Queries 30 names per request to verify their government positions.
"""

import os
import json
import asyncio
import asyncpg
import requests
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Dict

load_dotenv()

def call_perplexity(prompt: str) -> str:
    """Call Perplexity API with the prompt"""
    api_key = os.getenv('PERPLEXITY_API_KEY')
    if not api_key:
        raise RuntimeError('PERPLEXITY_API_KEY not set in environment')
    
    model = 'sonar-pro'
    url = 'https://api.perplexity.ai/chat/completions'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': model,
        'temperature': 0.0,
        'top_p': 1.0,
        'max_tokens': 8000,
        'messages': [
            {'role': 'system', 'content': 'You are a precise research assistant. Return accurate, verified information about Philippine government positions from official sources like COMELEC, DILG, Wikipedia, and news sources.'},
            {'role': 'user', 'content': prompt}
        ]
    }
    
    response = requests.post(url, json=payload, headers=headers, timeout=180)
    response.raise_for_status()
    
    data = response.json()
    return data['choices'][0]['message']['content']


def build_verification_prompt(names: List[Dict]) -> str:
    """Build Perplexity prompt for verifying positions of multiple AMOs"""
    names_list = []
    for amo in names:
        name_str = f"{amo['pcab_amo']}"
        if amo.get('position'):
            name_str += f" - Current DB position: {amo['position']} ({amo.get('year', 'N/A')})"
        if amo.get('province') or amo.get('municipality_city'):
            location = f"{amo.get('province', '')}, {amo.get('municipality_city', '')}".strip(', ')
            name_str += f" - Location: {location}"
        names_list.append(name_str)
    
    prompt = f"""Please verify the current or most recent elected government positions for these Philippine individuals who are listed as PCAB Authorized Managing Officers (AMOs).

For each person, provide:
1. Their current or most recent elected government position (if any)
2. The location (province, city/municipality)
3. The year/term of that position
4. Whether they are currently holding an elected position (2025) or if it's a past position
5. If they are NOT an elected official, indicate "Not an elected official" or "Contractor only"

Use official sources like:
- COMELEC election results
- DILG masterlist of elected officials
- Wikipedia pages
- Official government websites
- Reputable news sources (Rappler, Inquirer, Philstar)

List of names to verify:
{chr(10).join(f"{i+1}. {name}" for i, name in enumerate(names_list))}

Format your response as a numbered list, one entry per person, with:
- Name
- Position (or "Not an elected official")
- Location
- Year/Term
- Status (Current 2025 / Past position / Not elected)

Be precise and cite sources when possible."""
    
    return prompt


async def verify_amo_positions():
    """Main function to verify AMO positions"""
    # Load cache
    cache_path = Path('static/data/philgeps_amo_cache.json')
    if not cache_path.exists():
        print(f"❌ Cache file not found: {cache_path}")
        return
    
    with open(cache_path, 'r') as f:
        cache = json.load(f)
    
    # Get top 30 direct AMOs (first 3 pages of chart)
    direct_amos = cache.get('top_direct', [])[:30]
    
    # Get all indirect AMOs
    indirect_amos = cache.get('top_indirect', [])
    
    print("=" * 80)
    print("VERIFYING AMO POSITIONS WITH PERPLEXITY SONAR")
    print("=" * 80)
    print(f"Direct AMOs to verify: {len(direct_amos)}")
    print(f"Indirect AMOs to verify: {len(indirect_amos)}")
    print()
    
    # Verify direct AMOs in batches of 30
    print("📋 Verifying Direct AMOs (Batch 1 of 1)...")
    prompt = build_verification_prompt(direct_amos)
    
    try:
        print("   📡 Querying Perplexity API...")
        response = call_perplexity(prompt)
        
        # Save response
        output_dir = Path('analysis/amo_verification_results')
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_file = output_dir / 'direct_amos_verification.txt'
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("DIRECT AMOs POSITION VERIFICATION\n")
            f.write("=" * 80 + "\n\n")
            f.write(response)
        
        print(f"✅ Saved verification results to: {output_file}")
        print(f"\n📝 Response preview (first 500 chars):")
        print(response[:500])
        print("...")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Verify indirect AMOs if any
    if indirect_amos:
        print(f"\n📋 Verifying Indirect AMOs ({len(indirect_amos)} names)...")
        prompt = build_verification_prompt(indirect_amos)
        
        try:
            print("   📡 Querying Perplexity API...")
            response = call_perplexity(prompt)
            
            output_file = output_dir / 'indirect_amos_verification.txt'
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write("INDIRECT AMOs POSITION VERIFICATION\n")
                f.write("=" * 80 + "\n\n")
                f.write(response)
            
            print(f"✅ Saved verification results to: {output_file}")
            print(f"\n📝 Response preview (first 500 chars):")
            print(response[:500])
            print("...")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("✅ VERIFICATION COMPLETE")
    print("=" * 80)
    print(f"📁 Results saved to: {output_dir}")
    print("\nNext steps:")
    print("1. Review the verification results")
    print("2. Update database positions as needed")
    print("3. Regenerate AMO cache")


if __name__ == '__main__':
    asyncio.run(verify_amo_positions())


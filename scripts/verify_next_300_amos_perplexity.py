#!/usr/bin/env python3
"""
Verify next 300 unchecked AMOs using Perplexity Sonar API.
Queries 30 names per batch to find government positions or family relationships.
"""

import os
import json
import requests
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Dict
import time

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
            {'role': 'system', 'content': 'You are a precise research assistant. Return accurate, verified information about Philippine government positions and family relationships from official sources like COMELEC, DILG, Wikipedia, and news sources.'},
            {'role': 'user', 'content': prompt}
        ]
    }
    
    response = requests.post(url, json=payload, headers=headers, timeout=180)
    response.raise_for_status()
    
    data = response.json()
    return data['choices'][0]['message']['content']


def build_verification_prompt(amos: List[Dict], batch_num: int) -> str:
    """Build Perplexity prompt for verifying positions of multiple AMOs"""
    names_list = []
    for amo in amos:
        name_str = f"{amo['pcab_amo']}"
        if amo.get('contract_count'):
            name_str += f" ({amo['contract_count']} contracts, ₱{amo['total_amount']:,.0f})"
        names_list.append(name_str)
    
    prompt = f"""Please verify if these Philippine individuals who are listed as PCAB Authorized Managing Officers (AMOs) have any current or past elected government positions, OR if they have family relationships to current or past elected officials.

For each person, provide:
1. Their current or most recent elected government position (if any)
2. The location (province, city/municipality)
3. The year/term of that position
4. Whether they are currently holding an elected position (2025) or if it's a past position
5. If they are NOT an elected official, check if they have family relationships (spouse, parent, sibling, child, etc.) to any current or past elected officials
6. If they have family relationships, provide the name and position of the related elected official

Use official sources like:
- COMELEC election results
- DILG masterlist of elected officials
- Wikipedia pages
- Official government websites
- Reputable news sources (Rappler, Inquirer, Philstar)

List of names to verify (Batch {batch_num}):
{chr(10).join(f"{i+1}. {name}" for i, name in enumerate(names_list))}

Format your response as a numbered list, one entry per person, with:
- Name
- Position (or "Not an elected official")
- Location
- Year/Term
- Status (Current 2025 / Past position / Not elected)
- Family relationships (if any): "Related to [Name] ([Position], [Year]) as [Relationship]"

Be precise and cite sources when possible. If no information is found, indicate "No information found in official sources"."""
    
    return prompt


def main():
    """Main function to verify next 300 AMOs"""
    # Load the top 300 unchecked AMOs
    input_path = Path('analysis/amo_verification_results/top_300_unchecked_amos.json')
    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        print("   Please run the analysis script first to generate the list.")
        return
    
    with open(input_path, 'r') as f:
        amos = json.load(f)
    
    print("=" * 80)
    print("VERIFYING NEXT 300 UNCHECKED AMOs WITH PERPLEXITY SONAR")
    print("=" * 80)
    print(f"Total AMOs to verify: {len(amos)}")
    print(f"Batches of 30: {len(amos) // 30 + (1 if len(amos) % 30 > 0 else 0)}")
    print()
    
    # Create output directory
    output_dir = Path('analysis/amo_verification_results/next_300_verification')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Process in batches of 30
    batch_size = 30
    total_batches = (len(amos) + batch_size - 1) // batch_size
    
    all_results = []
    
    for batch_idx in range(total_batches):
        start_idx = batch_idx * batch_size
        end_idx = min(start_idx + batch_size, len(amos))
        batch = amos[start_idx:end_idx]
        batch_num = batch_idx + 1
        
        print(f"📋 Batch {batch_num}/{total_batches} (AMOs {start_idx+1}-{end_idx})...")
        
        try:
            # Build prompt
            prompt = build_verification_prompt(batch, batch_num)
            
            # Call Perplexity
            print(f"   📡 Querying Perplexity API...")
            response = call_perplexity(prompt)
            
            # Save response
            batch_file = output_dir / f'batch_{batch_num:02d}_amos_{start_idx+1}_to_{end_idx}.txt'
            with open(batch_file, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write(f"BATCH {batch_num}/{total_batches} - AMOs {start_idx+1} to {end_idx}\n")
                f.write("=" * 80 + "\n\n")
                f.write("AMOs in this batch:\n")
                for i, amo in enumerate(batch, 1):
                    f.write(f"{i}. {amo['pcab_amo']} ({amo['contract_count']} contracts, ₱{amo['total_amount']:,.2f})\n")
                f.write("\n" + "=" * 80 + "\n")
                f.write("PERPLEXITY VERIFICATION RESULTS\n")
                f.write("=" * 80 + "\n\n")
                f.write(response)
            
            print(f"   ✅ Saved to: {batch_file}")
            
            # Store result
            all_results.append({
                'batch': batch_num,
                'start_idx': start_idx + 1,
                'end_idx': end_idx,
                'amos': batch,
                'response': response,
                'file': str(batch_file)
            })
            
            # Rate limiting - wait 3 seconds between batches
            if batch_idx < total_batches - 1:
                print(f"   ⏳ Waiting 3 seconds before next batch...")
                time.sleep(3)
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Save summary
    summary_file = output_dir / 'verification_summary.json'
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump({
            'total_amos': len(amos),
            'total_batches': total_batches,
            'batches_completed': len(all_results),
            'results': all_results
        }, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 80)
    print("✅ VERIFICATION COMPLETE")
    print("=" * 80)
    print(f"📁 Results saved to: {output_dir}")
    print(f"   - Individual batch files: batch_XX_amos_XX_to_XX.txt")
    print(f"   - Summary: verification_summary.json")
    print(f"\nCompleted {len(all_results)}/{total_batches} batches")


if __name__ == '__main__':
    main()




"""
PhilGEPS to DIME Matcher

Match PhilGEPS contracts to DIME projects using:
1. Fuzzy match: award_title/notice_title to project_name
2. Fuzzy match: awardee_name to contractors
3. EXACT match: contract_amount to cost

Then use DIME's meilisearch_id in PhilGEPS
"""

import asyncio
import asyncpg
import os
import sys
from typing import List, Dict, Optional
from dotenv import load_dotenv
from difflib import SequenceMatcher

load_dotenv()

# Database configuration
PHILGEPS_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': 'philgeps',
    'user': os.getenv('POSTGRES_USER', 'budget_admin'),
    'password': os.getenv('POSTGRES_PASSWORD', '')
}

DIME_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': 'dime',
    'user': os.getenv('POSTGRES_USER', 'budget_admin'),
    'password': os.getenv('POSTGRES_PASSWORD', '')
}

def normalize_text(text: str) -> str:
    """Normalize text for comparison"""
    if not text:
        return ""
    
    # Convert to uppercase
    text = text.upper().strip()
    
    # Remove common words
    remove_words = [
        "CONSTRUCTION", "OF", "THE", "PROJECT", "REHABILITATION",
        "REPAIR", "MAINTENANCE", "PHASE", "PACKAGE", "AND", "AT", "IN",
        "FLOOD", "CONTROL", "DRAINAGE", "ROAD", "BRIDGE"
    ]
    
    words = text.split()
    filtered = [w for w in words if w not in remove_words]
    
    return " ".join(filtered)

def text_similarity(text1: str, text2: str) -> float:
    """Calculate text similarity using SequenceMatcher"""
    if not text1 or not text2:
        return 0.0
    
    # Normalize
    t1 = normalize_text(text1)
    t2 = normalize_text(text2)
    
    if not t1 or not t2:
        return 0.0
    
    # Calculate similarity
    return SequenceMatcher(None, t1, t2).ratio()

def contractor_similarity(philgeps_contractor: str, dime_contractors: list) -> float:
    """Calculate contractor name similarity"""
    if not philgeps_contractor or not dime_contractors:
        return 0.0
    
    # Normalize PhilGEPS contractor
    c1 = philgeps_contractor.upper().strip()
    
    max_similarity = 0.0
    
    for contractor_json in dime_contractors:
        # DIME contractors are stored as JSON strings
        if not contractor_json:
            continue
        
        # Extract contractor name (it's in JSON format)
        import json
        try:
            contractor_data = json.loads(contractor_json)
            contractor_name = contractor_data.get('name', '')
        except:
            contractor_name = str(contractor_json)
        
        c2 = contractor_name.upper().strip()
        
        # Exact match
        if c1 == c2:
            return 1.0
        
        # Contains match
        if c1 in c2 or c2 in c1:
            max_similarity = max(max_similarity, 0.9)
            continue
        
        # Fuzzy match
        similarity = SequenceMatcher(None, c1, c2).ratio()
        max_similarity = max(max_similarity, similarity)
    
    return max_similarity

def calculate_match_score(project_sim: float, contractor_sim: float, amount_match: bool) -> float:
    """
    Calculate overall match score
    
    Requirements:
    - Amount must match EXACTLY
    - Project name OR contractor must match well
    
    Scoring:
    - Amount: Must be exact (100% or 0%)
    - Project name: 60% weight
    - Contractor: 40% weight
    """
    # Amount must match exactly
    if not amount_match:
        return 0.0
    
    # Calculate weighted score
    score = (project_sim * 0.6) + (contractor_sim * 0.4)
    
    return round(score * 100, 2)

async def match_philgeps_to_dime():
    """Main matching function"""
    print("🔗 PhilGEPS to DIME Matching Script")
    print("=" * 80)
    
    # Connect to databases
    print("\n📊 Connecting to databases...")
    philgeps_conn = await asyncpg.connect(**PHILGEPS_CONFIG)
    dime_conn = await asyncpg.connect(**DIME_CONFIG)
    
    # Get PhilGEPS contracts
    print("📋 Loading PhilGEPS contracts...")
    philgeps_query = """
        SELECT id, reference_id, contract_no, award_title, notice_title,
               awardee_name, organization_name, area_of_delivery,
               contract_amount, award_date, award_status
        FROM contracts
        WHERE contract_amount IS NOT NULL 
          AND contract_amount > 0
          AND award_status = 'active'
        ORDER BY contract_amount DESC
    """
    
    philgeps_contracts = await philgeps_conn.fetch(philgeps_query)
    print(f"✅ Loaded {len(philgeps_contracts)} PhilGEPS contracts")
    
    # Get DIME projects with meilisearch_id
    print("🏗️ Loading DIME projects with MeiliSearch links...")
    dime_query = """
        SELECT id, project_name, project_code, cost, contractors,
               province, city, barangay, status, meilisearch_id
        FROM projects
        WHERE cost IS NOT NULL 
          AND cost > 0
          AND meilisearch_id IS NOT NULL
        ORDER BY cost DESC
    """
    
    dime_projects = await dime_conn.fetch(dime_query)
    print(f"✅ Loaded {len(dime_projects)} DIME projects (with MeiliSearch links)")
    
    # Build DIME index by exact cost for fast lookup
    print("\n🔨 Building DIME cost index...")
    dime_by_cost = {}
    for project in dime_projects:
        cost = float(project['cost'])
        if cost not in dime_by_cost:
            dime_by_cost[cost] = []
        dime_by_cost[cost].append(project)
    
    print(f"   Indexed {len(dime_by_cost)} unique cost values")
    
    # Matching process
    print("\n🔍 Starting matching process...")
    print("   Criteria: EXACT amount + fuzzy project name + fuzzy contractor")
    
    matches = []
    no_match_count = 0
    multiple_match_count = 0
    
    for idx, contract in enumerate(philgeps_contracts, 1):
        if idx % 1000 == 0:
            print(f"   Processed {idx}/{len(philgeps_contracts)} contracts...")
        
        contract_amount = float(contract['contract_amount'])
        
        # Look for EXACT cost match
        if contract_amount not in dime_by_cost:
            no_match_count += 1
            continue
        
        # Find candidates with exact amount
        candidates = []
        
        for dime_project in dime_by_cost[contract_amount]:
            # Calculate project name similarity
            project_sim = max(
                text_similarity(contract['award_title'], dime_project['project_name']),
                text_similarity(contract['notice_title'], dime_project['project_name'])
            )
            
            # Calculate contractor similarity
            contractor_sim = contractor_similarity(
                contract['awardee_name'],
                dime_project['contractors'] or []
            )
            
            # Calculate match score
            score = calculate_match_score(
                project_sim,
                contractor_sim,
                amount_match=True  # We already filtered by exact amount
            )
            
            # Require minimum 60% match
            if score >= 60:
                candidates.append({
                    'dime_project': dime_project,
                    'score': score,
                    'project_sim': project_sim,
                    'contractor_sim': contractor_sim
                })
        
        # Sort by score
        candidates.sort(key=lambda x: x['score'], reverse=True)
        
        if len(candidates) == 0:
            no_match_count += 1
        elif len(candidates) > 1:
            multiple_match_count += 1
            # Take best match
            best = candidates[0]
            matches.append({
                'contract_id': contract['id'],
                'dime_project_id': best['dime_project']['id'],
                'meilisearch_id': best['dime_project']['meilisearch_id'],
                'score': best['score'],
                'project_sim': best['project_sim'],
                'contractor_sim': best['contractor_sim'],
                'contract_amount': contract_amount,
                'contract_title': contract['award_title'],
                'dime_project_name': best['dime_project']['project_name']
            })
        else:
            # Single match
            best = candidates[0]
            matches.append({
                'contract_id': contract['id'],
                'dime_project_id': best['dime_project']['id'],
                'meilisearch_id': best['dime_project']['meilisearch_id'],
                'score': best['score'],
                'project_sim': best['project_sim'],
                'contractor_sim': best['contractor_sim'],
                'contract_amount': contract_amount,
                'contract_title': contract['award_title'],
                'dime_project_name': best['dime_project']['project_name']
            })
    
    print(f"\n✅ Matching complete!")
    print(f"   Total contracts processed: {len(philgeps_contracts):,}")
    print(f"   Matches found: {len(matches):,}")
    print(f"   No matches (no exact amount): {no_match_count:,}")
    print(f"   Multiple candidates: {multiple_match_count:,}")
    
    # Show sample matches
    if matches:
        print(f"\n📋 Sample Matches (Top 5):")
        for i, match in enumerate(matches[:5], 1):
            print(f"\n   Match #{i} (Score: {match['score']:.1f}%)")
            print(f"      Amount: ₱{match['contract_amount']:,.2f}")
            print(f"      PhilGEPS: {match['contract_title'][:60]}...")
            print(f"      DIME:     {match['dime_project_name'][:60]}...")
            print(f"      Project Sim: {match['project_sim']:.2%}")
            print(f"      Contractor Sim: {match['contractor_sim']:.2%}")
    
    # Update database
    if matches:
        print(f"\n💾 Updating PhilGEPS database with {len(matches)} matches...")
        
        update_query = """
            UPDATE contracts 
            SET meilisearch_id = $2
            WHERE id = $1
        """
        
        batch_size = 1000
        for i in range(0, len(matches), batch_size):
            batch = matches[i:i + batch_size]
            
            for match in batch:
                await philgeps_conn.execute(
                    update_query,
                    match['contract_id'],
                    match['meilisearch_id']
                )
            
            print(f"   Updated {min(i + batch_size, len(matches)):,}/{len(matches):,} records...")
        
        print("✅ Database updated successfully!")
        
        # Show statistics
        print(f"\n📊 Match Quality Statistics:")
        high_quality = sum(1 for m in matches if m['score'] >= 80)
        medium_quality = sum(1 for m in matches if 70 <= m['score'] < 80)
        low_quality = sum(1 for m in matches if 60 <= m['score'] < 70)
        
        print(f"   High quality (≥80%): {high_quality:,}")
        print(f"   Medium quality (70-79%): {medium_quality:,}")
        print(f"   Low quality (60-69%): {low_quality:,}")
        
        avg_score = sum(m['score'] for m in matches) / len(matches)
        print(f"   Average score: {avg_score:.2f}%")
    
    await philgeps_conn.close()
    await dime_conn.close()
    print("\n✅ All done!")

if __name__ == "__main__":
    asyncio.run(match_philgeps_to_dime())


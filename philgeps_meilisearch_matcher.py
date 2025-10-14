"""
PhilGEPS to MeiliSearch Matcher

This script links PhilGEPS contracts to MeiliSearch flood control projects using:
1. Contract amount matching (within tolerance)
2. Location matching (area_of_delivery vs Province/Region)
3. Optional: Contractor name similarity

Similar to how DIME was connected to MeiliSearch
"""

import asyncio
import asyncpg
import os
from typing import List, Dict, Optional, Tuple
from dotenv import load_dotenv
from flood_client import FloodControlClient
from difflib import SequenceMatcher

load_dotenv()

# Database configuration
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': 'philgeps',
    'user': os.getenv('POSTGRES_USER', 'budget_admin'),
    'password': os.getenv('POSTGRES_PASSWORD', '')
}

def parse_amount(amount) -> float:
    """Parse amount to float"""
    if amount is None:
        return 0.0
    try:
        return float(amount)
    except (ValueError, TypeError):
        return 0.0

def normalize_location(location: str) -> str:
    """Normalize location string for comparison"""
    if not location:
        return ""
    
    # Convert to uppercase and remove common suffixes/prefixes
    location = location.upper().strip()
    
    # Remove common words
    remove_words = ["PROVINCE", "PROVINCE OF", "CITY OF", "MUNICIPALITY OF", "BARANGAY"]
    for word in remove_words:
        location = location.replace(word, "")
    
    # Clean up whitespace
    location = " ".join(location.split())
    
    return location

def location_match_score(philgeps_area: str, meili_province: str, meili_region: str) -> float:
    """Calculate location match score (0-1)"""
    if not philgeps_area:
        return 0.0
    
    philgeps_normalized = normalize_location(philgeps_area)
    
    # Check province match
    province_normalized = normalize_location(meili_province or "")
    if province_normalized and philgeps_normalized in province_normalized or province_normalized in philgeps_normalized:
        return 1.0
    
    # Check region match (weaker)
    region_normalized = normalize_location(meili_region or "")
    if region_normalized and philgeps_normalized in region_normalized or region_normalized in philgeps_normalized:
        return 0.7
    
    # Use sequence matching for fuzzy comparison
    province_similarity = SequenceMatcher(None, philgeps_normalized, province_normalized).ratio()
    region_similarity = SequenceMatcher(None, philgeps_normalized, region_normalized).ratio()
    
    return max(province_similarity, region_similarity * 0.7)

def amount_match_score(amount1: float, amount2: float, tolerance_percent: float = 5.0) -> float:
    """
    Calculate amount match score (0-1)
    tolerance_percent: allow up to X% difference
    """
    if amount1 == 0 or amount2 == 0:
        return 0.0
    
    if amount1 == amount2:
        return 1.0
    
    # Calculate percentage difference
    diff_percent = abs(amount1 - amount2) / max(amount1, amount2) * 100
    
    if diff_percent <= tolerance_percent:
        # Linear score: 100% match at 0% diff, 0% match at tolerance_percent diff
        score = 1.0 - (diff_percent / tolerance_percent)
        return max(0.0, score)
    
    return 0.0

def contractor_match_score(philgeps_contractor: str, meili_contractor: str) -> float:
    """Calculate contractor name similarity (0-1)"""
    if not philgeps_contractor or not meili_contractor:
        return 0.0
    
    # Normalize
    c1 = philgeps_contractor.upper().strip()
    c2 = meili_contractor.upper().strip()
    
    # Exact match
    if c1 == c2:
        return 1.0
    
    # One contains the other
    if c1 in c2 or c2 in c1:
        return 0.9
    
    # Sequence matching
    similarity = SequenceMatcher(None, c1, c2).ratio()
    return similarity if similarity > 0.6 else 0.0  # Threshold at 60%

def calculate_match_confidence(location_score: float, amount_score: float, contractor_score: float = 0.0) -> float:
    """
    Calculate overall match confidence score (0-100)
    
    Weights:
    - Location: 40%
    - Amount: 50%
    - Contractor: 10% (optional)
    """
    # If amount doesn't match well, it's likely not a match
    if amount_score < 0.8:
        return 0.0
    
    # Calculate weighted score
    confidence = (location_score * 0.4) + (amount_score * 0.5) + (contractor_score * 0.1)
    
    return round(confidence * 100, 2)

async def get_philgeps_contracts(conn):
    """Get all PhilGEPS flood control contracts"""
    query = """
        SELECT id, reference_id, contract_no, award_title, notice_title,
               awardee_name, organization_name, area_of_delivery,
               business_category, contract_amount, award_date, award_status
        FROM contracts
        WHERE contract_amount IS NOT NULL 
          AND contract_amount > 0
          AND area_of_delivery IS NOT NULL
          AND award_status = 'active'
        ORDER BY contract_amount DESC
    """
    
    rows = await conn.fetch(query)
    print(f"📋 Loaded {len(rows)} PhilGEPS contracts for matching")
    return rows

async def match_philgeps_to_meilisearch():
    """Main matching function"""
    print("🔗 PhilGEPS to MeiliSearch Matching Script")
    print("=" * 80)
    
    # Connect to PostgreSQL
    print("\n📊 Connecting to PhilGEPS database...")
    conn = await asyncpg.connect(**DB_CONFIG)
    
    # Connect to MeiliSearch
    print("🔍 Connecting to MeiliSearch...")
    meili_client = FloodControlClient()
    is_healthy = await meili_client.health_check()
    
    if not is_healthy:
        print("❌ MeiliSearch connection failed!")
        await conn.close()
        return
    
    print("✅ Connected to MeiliSearch")
    
    # Get all flood projects from MeiliSearch
    print("\n📥 Fetching all flood control projects from MeiliSearch...")
    all_projects = []
    limit = 1000
    offset = 0
    
    while True:
        projects, metadata = await meili_client.search_projects("", limit=limit, offset=offset)
        if not projects:
            break
        
        all_projects.extend(projects)
        offset += limit
        print(f"   Retrieved {len(all_projects)} projects so far...")
        
        if len(projects) < limit:
            break
    
    print(f"✅ Total MeiliSearch projects: {len(all_projects)}")
    
    # Get PhilGEPS contracts
    print("\n📋 Fetching PhilGEPS contracts...")
    philgeps_contracts = await get_philgeps_contracts(conn)
    
    # Build MeiliSearch index for faster lookups
    print("\n🔨 Building lookup indices...")
    meili_by_cost = {}
    for project in all_projects:
        cost = parse_amount(project.ContractCost)
        if cost > 0:
            if cost not in meili_by_cost:
                meili_by_cost[cost] = []
            meili_by_cost[cost].append(project)
    
    print(f"   MeiliSearch cost groups: {len(meili_by_cost)}")
    
    # Matching process
    print("\n🔍 Starting matching process...")
    matches = []
    no_match_count = 0
    multiple_match_count = 0
    
    for idx, contract in enumerate(philgeps_contracts, 1):
        if idx % 1000 == 0:
            print(f"   Processed {idx}/{len(philgeps_contracts)} contracts...")
        
        contract_amount = parse_amount(contract['contract_amount'])
        contract_location = contract['area_of_delivery']
        contract_contractor = contract['awardee_name']
        
        # Find candidate projects by amount (within 5% tolerance)
        candidates = []
        tolerance = 0.05  # 5%
        
        for cost, projects in meili_by_cost.items():
            # Check if cost is within tolerance
            if abs(contract_amount - cost) / max(contract_amount, cost) <= tolerance:
                for project in projects:
                    # Calculate match scores
                    location_score = location_match_score(
                        contract_location,
                        project.Province,
                        project.Region
                    )
                    
                    amount_score = amount_match_score(
                        contract_amount,
                        parse_amount(project.ContractCost),
                        tolerance_percent=5.0
                    )
                    
                    contractor_score = contractor_match_score(
                        contract_contractor,
                        project.Contractor
                    )
                    
                    confidence = calculate_match_confidence(
                        location_score,
                        amount_score,
                        contractor_score
                    )
                    
                    if confidence >= 70:  # Minimum 70% confidence
                        candidates.append({
                            'project': project,
                            'confidence': confidence,
                            'location_score': location_score,
                            'amount_score': amount_score,
                            'contractor_score': contractor_score
                        })
        
        # Sort candidates by confidence
        candidates.sort(key=lambda x: x['confidence'], reverse=True)
        
        if len(candidates) == 0:
            no_match_count += 1
        elif len(candidates) > 1:
            multiple_match_count += 1
            # Take best match
            best_match = candidates[0]
            matches.append({
                'contract_id': contract['id'],
                'meilisearch_id': best_match['project'].GlobalID,
                'confidence': best_match['confidence'],
                'location_score': best_match['location_score'],
                'amount_score': best_match['amount_score'],
                'contractor_score': best_match['contractor_score']
            })
        else:
            # Single match
            best_match = candidates[0]
            matches.append({
                'contract_id': contract['id'],
                'meilisearch_id': best_match['project'].GlobalID,
                'confidence': best_match['confidence'],
                'location_score': best_match['location_score'],
                'amount_score': best_match['amount_score'],
                'contractor_score': best_match['contractor_score']
            })
    
    print(f"\n✅ Matching complete!")
    print(f"   Total contracts processed: {len(philgeps_contracts)}")
    print(f"   Matches found: {len(matches)}")
    print(f"   No matches: {no_match_count}")
    print(f"   Multiple candidates: {multiple_match_count}")
    
    # Update database
    if matches:
        print(f"\n💾 Updating database with {len(matches)} matches...")
        
        # Batch update
        batch_size = 1000
        for i in range(0, len(matches), batch_size):
            batch = matches[i:i + batch_size]
            
            # Update using parameterized query
            update_query = """
                UPDATE contracts 
                SET meilisearch_id = $2
                WHERE id = $1
            """
            
            for match in batch:
                await conn.execute(
                    update_query,
                    match['contract_id'],
                    match['meilisearch_id']
                )
            
            print(f"   Updated {min(i + batch_size, len(matches))}/{len(matches)} records...")
        
        print("✅ Database updated successfully!")
        
        # Show statistics
        print(f"\n📊 Match Quality Statistics:")
        high_confidence = sum(1 for m in matches if m['confidence'] >= 90)
        medium_confidence = sum(1 for m in matches if 80 <= m['confidence'] < 90)
        low_confidence = sum(1 for m in matches if 70 <= m['confidence'] < 80)
        
        print(f"   High confidence (≥90%): {high_confidence}")
        print(f"   Medium confidence (80-89%): {medium_confidence}")
        print(f"   Low confidence (70-79%): {low_confidence}")
        
        avg_confidence = sum(m['confidence'] for m in matches) / len(matches)
        print(f"   Average confidence: {avg_confidence:.2f}%")
    
    await conn.close()
    print("\n✅ All done!")

if __name__ == "__main__":
    asyncio.run(match_philgeps_to_meilisearch())


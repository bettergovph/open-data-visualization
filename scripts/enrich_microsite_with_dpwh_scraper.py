#!/usr/bin/env python3
"""
Enrich Microsite data with DPWH scraper data
Matches microsite projects with DPWH scraper contracts (90%+ confidence)
and adds missing columns to make microsite data richer and fix errors.
"""

import pandas as pd
import numpy as np
from pathlib import Path
import re
from typing import Dict, List, Tuple, Optional
from difflib import SequenceMatcher
from datetime import datetime
import json

# Paths
DPWH_CSV = Path("/home/joebert/dpwh-infra-data-scraper/csv/contracts_all_years_all_offices.csv")
MICROSITE_PARQUET = Path(__file__).parent.parent / "data" / "parquet" / "infrawatch_projects.parquet"
OUTPUT_PARQUET = Path(__file__).parent.parent / "data" / "parquet" / "infrawatch_projects_enriched.parquet"
BACKUP_PARQUET = Path(__file__).parent.parent / "data" / "parquet" / "infrawatch_projects_backup.parquet"

def normalize_text(text: str) -> str:
    """Normalize text for matching"""
    if not text or pd.isna(text):
        return ""
    text = str(text).upper().strip()
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove special characters that might differ
    text = re.sub(r'[^\w\s]', '', text)
    return text

def similarity_score(text1: str, text2: str) -> float:
    """Calculate similarity score between two texts (0-1)"""
    if not text1 or not text2:
        return 0.0
    norm1 = normalize_text(text1)
    norm2 = normalize_text(text2)
    if not norm1 or not norm2:
        return 0.0
    return SequenceMatcher(None, norm1, norm2).ratio()

def normalize_amount(amount) -> Optional[float]:
    """Normalize amount to float for comparison"""
    if pd.isna(amount):
        return None
    if isinstance(amount, (int, float)):
        return float(amount)
    if isinstance(amount, str):
        # Remove currency symbols, commas, spaces
        cleaned = amount.replace('₱', '').replace(',', '').replace(' ', '').strip()
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None
    return None

def amount_match(amt1: Optional[float], amt2: Optional[float], tolerance: float = 0.01) -> bool:
    """Check if two amounts match within tolerance"""
    if amt1 is None or amt2 is None:
        return False
    if amt1 == 0 or amt2 == 0:
        return False
    diff = abs(amt1 - amt2)
    avg = (amt1 + amt2) / 2
    if avg == 0:
        return False
    return (diff / avg) <= tolerance

def normalize_contractor(contractor: str) -> str:
    """Normalize contractor name for matching"""
    if not contractor or pd.isna(contractor):
        return ""
    contractor = str(contractor).upper().strip()
    # Remove common suffixes
    contractor = re.sub(r'\s+(INC\.?|CORP\.?|CORPORATION|CO\.?|LTD\.?|LIMITED)$', '', contractor)
    # Remove extra whitespace
    contractor = re.sub(r'\s+', ' ', contractor)
    return contractor

def contractor_match(contractor1: str, contractor2: str) -> bool:
    """Check if two contractor names match"""
    norm1 = normalize_contractor(contractor1)
    norm2 = normalize_contractor(contractor2)
    if not norm1 or not norm2:
        return False
    # Exact match after normalization
    if norm1 == norm2:
        return True
    # Check if one contains the other (for abbreviations)
    if len(norm1) > 10 and len(norm2) > 10:
        if norm1 in norm2 or norm2 in norm1:
            return True
    return False

def match_microsite_to_dpwh(microsite_row: pd.Series, dpwh_df: pd.DataFrame, dpwh_index_by_contractor: Dict = None, dpwh_index_by_amount: Dict = None) -> Tuple[Optional[pd.Series], float]:
    """
    Match a microsite project to DPWH scraper data
    Returns: (matched_dpwh_row, confidence_score) or (None, 0.0)
    Confidence must be 90%+ (0.9) to be considered a match
    
    Uses indexed lookups for performance when indices are provided.
    """
    best_match = None
    best_score = 0.0
    
    # Extract microsite fields
    ms_description = str(microsite_row.get('project_name', '') or microsite_row.get('project_description', '') or '')
    ms_contractor = str(microsite_row.get('contractor_name', '') or microsite_row.get('Contractor', '') or '')
    ms_amount = normalize_amount(microsite_row.get('Contract Price') or microsite_row.get('Contract Amount') or microsite_row.get('Amount'))
    ms_location = str(microsite_row.get('location', '') or microsite_row.get('organization_name', '') or '')
    ms_contract_id = str(microsite_row.get('contract_id', '') or microsite_row.get('Contract ID', '') or '')
    
    # Filter DPWH data for potential matches using indices if available
    # Start with full dataset, then narrow down if indices available
    candidates = dpwh_df.copy()
    
    # Narrow down using contractor index if available
    if dpwh_index_by_contractor and ms_contractor:
        norm_contractor = normalize_contractor(ms_contractor)
        if norm_contractor in dpwh_index_by_contractor:
            contractor_candidates = dpwh_index_by_contractor[norm_contractor]
            if len(contractor_candidates) > 0:
                candidates = contractor_candidates
    # Or narrow down using amount index if contractor not available
    elif dpwh_index_by_amount and ms_amount:
        amount_key = round(ms_amount / 100000) * 100000  # Round to nearest 100k
        if amount_key in dpwh_index_by_amount:
            amount_candidates = dpwh_index_by_amount[amount_key]
            if len(amount_candidates) > 0:
                candidates = amount_candidates
    
    # Strategy 1: Contract ID exact match (highest confidence)
    if ms_contract_id and ms_contract_id != '' and ms_contract_id != 'nan':
        id_matches = candidates[candidates['contract_id'] == ms_contract_id]
        if len(id_matches) > 0:
            match = id_matches.iloc[0]
            # Verify contractor and amount match
            dpwh_contractor = str(match.get('contractor_name_1', '') or '')
            dpwh_amount = normalize_amount(match.get('cost_php'))
            
            contractor_ok = not ms_contractor or not dpwh_contractor or contractor_match(ms_contractor, dpwh_contractor)
            amount_ok = not ms_amount or not dpwh_amount or amount_match(ms_amount, dpwh_amount)
            
            if contractor_ok and amount_ok:
                return (match, 0.98)  # Very high confidence for ID match
    
    # Strategy 2: Description + Contractor + Amount match
    if ms_description and ms_contractor and ms_amount:
        for idx, dpwh_row in candidates.iterrows():
            dpwh_desc = str(dpwh_row.get('description', '') or '')
            dpwh_contractor = str(dpwh_row.get('contractor_name_1', '') or '')
            dpwh_amount = normalize_amount(dpwh_row.get('cost_php'))
            
            # Check contractor match
            if not contractor_match(ms_contractor, dpwh_contractor):
                continue
            
            # Check amount match (within 1% tolerance)
            if not amount_match(ms_amount, dpwh_amount):
                continue
            
            # Check description similarity
            desc_similarity = similarity_score(ms_description, dpwh_desc)
            
            # Combined score: description similarity weighted heavily
            score = desc_similarity * 0.7 + 0.3  # Contractor + amount already matched
            
            if score >= 0.90 and score > best_score:
                best_match = dpwh_row
                best_score = score
    
    # Strategy 3: Description + Location + Amount match (if contractor not available)
    if ms_description and ms_location and ms_amount and not ms_contractor:
        for idx, dpwh_row in candidates.iterrows():
            dpwh_desc = str(dpwh_row.get('description', '') or '')
            dpwh_location = str(dpwh_row.get('implementing_office', '') or dpwh_row.get('region', '') or '')
            dpwh_amount = normalize_amount(dpwh_row.get('cost_php'))
            
            # Check amount match
            if not amount_match(ms_amount, dpwh_amount):
                continue
            
            # Check description similarity
            desc_similarity = similarity_score(ms_description, dpwh_desc)
            
            # Check location similarity
            loc_similarity = similarity_score(ms_location, dpwh_location)
            
            # Combined score
            score = (desc_similarity * 0.6) + (loc_similarity * 0.3) + 0.1  # Amount already matched
            
            if score >= 0.90 and score > best_score:
                best_match = dpwh_row
                best_score = score
    
    # Strategy 4: Contractor + Amount + Location match (if description not reliable)
    if ms_contractor and ms_amount and ms_location:
        for idx, dpwh_row in candidates.iterrows():
            dpwh_contractor = str(dpwh_row.get('contractor_name_1', '') or '')
            dpwh_amount = normalize_amount(dpwh_row.get('cost_php'))
            dpwh_location = str(dpwh_row.get('implementing_office', '') or dpwh_row.get('region', '') or '')
            
            # Check contractor match
            if not contractor_match(ms_contractor, dpwh_contractor):
                continue
            
            # Check amount match
            if not amount_match(ms_amount, dpwh_amount):
                continue
            
            # Check location similarity
            loc_similarity = similarity_score(ms_location, dpwh_location)
            
            # Combined score
            score = (loc_similarity * 0.5) + 0.5  # Contractor + amount already matched
            
            if score >= 0.90 and score > best_score:
                best_match = dpwh_row
                best_score = score
    
    if best_score >= 0.90:
        return (best_match, best_score)
    
    return (None, 0.0)

def enrich_microsite_row(microsite_row: pd.Series, dpwh_row: Optional[pd.Series], match_score: float) -> pd.Series:
    """Enrich a microsite row with DPWH scraper data"""
    enriched = microsite_row.copy()
    
    if dpwh_row is None:
        # No match found, add metadata
        enriched['dpwh_match_confidence'] = 0.0
        enriched['dpwh_matched'] = False
        return enriched
    
    # Mark as matched
    enriched['dpwh_matched'] = True
    enriched['dpwh_match_confidence'] = match_score
    enriched['dpwh_contract_id'] = dpwh_row.get('contract_id', None)
    
    # Add contractor ID (from DPWH scraper)
    if pd.notna(dpwh_row.get('contractor_id_1')):
        enriched['contractor_id'] = dpwh_row.get('contractor_id_1')
        enriched['dpwh_contractor_id_1'] = dpwh_row.get('contractor_id_1')
    
    # Add additional contractors (joint ventures)
    if pd.notna(dpwh_row.get('contractor_name_2')):
        enriched['contractor_name_2'] = dpwh_row.get('contractor_name_2')
        enriched['contractor_id_2'] = dpwh_row.get('contractor_id_2')
    if pd.notna(dpwh_row.get('contractor_name_3')):
        enriched['contractor_name_3'] = dpwh_row.get('contractor_name_3')
        enriched['contractor_id_3'] = dpwh_row.get('contractor_id_3')
    if pd.notna(dpwh_row.get('contractor_name_4')):
        enriched['contractor_name_4'] = dpwh_row.get('contractor_name_4')
        enriched['contractor_id_4'] = dpwh_row.get('contractor_id_4')
    
    # Add dates (if missing in microsite)
    # Effectivity date (contract start)
    if pd.isna(enriched.get('effectivity_date')) and pd.notna(dpwh_row.get('effectivity_date')):
        enriched['effectivity_date'] = dpwh_row.get('effectivity_date')
        enriched['dpwh_effectivity_date'] = dpwh_row.get('effectivity_date')
    elif pd.notna(dpwh_row.get('effectivity_date')):
        # Always add DPWH version for comparison
        enriched['dpwh_effectivity_date'] = dpwh_row.get('effectivity_date')
    
    # Expiry date (contract end)
    if pd.isna(enriched.get('expiry_date')) and pd.notna(dpwh_row.get('expiry_date')):
        enriched['expiry_date'] = dpwh_row.get('expiry_date')
        enriched['dpwh_expiry_date'] = dpwh_row.get('expiry_date')
    elif pd.notna(dpwh_row.get('expiry_date')):
        # Always add DPWH version for comparison
        enriched['dpwh_expiry_date'] = dpwh_row.get('expiry_date')
    
    # Note: Bidding dates (bidding_date, award_date, notice_date) are not available in DPWH scraper CSV
    # If these exist in microsite data, they are preserved automatically
    
    # Add accomplishment percentage
    if pd.notna(dpwh_row.get('accomplishment_pct')):
        enriched['accomplishment_pct'] = dpwh_row.get('accomplishment_pct')
        enriched['dpwh_accomplishment_pct'] = dpwh_row.get('accomplishment_pct')
    
    # Add source of funds
    if pd.notna(dpwh_row.get('source_of_funds')):
        enriched['source_of_funds'] = dpwh_row.get('source_of_funds')
        enriched['dpwh_source_of_funds'] = dpwh_row.get('source_of_funds')
    
    # Add region and implementing office (if missing or to fix errors)
    if pd.notna(dpwh_row.get('region')):
        enriched['dpwh_region'] = dpwh_row.get('region')
        # Use DPWH region if microsite doesn't have one or it looks wrong
        if pd.isna(enriched.get('region')) or 'DISTRICT' in str(enriched.get('region', '')).upper():
            enriched['region'] = dpwh_row.get('region')
    
    if pd.notna(dpwh_row.get('implementing_office')):
        enriched['dpwh_implementing_office'] = dpwh_row.get('implementing_office')
        # Use DPWH implementing office if microsite doesn't have one
        if pd.isna(enriched.get('implementing_office')) or pd.isna(enriched.get('organization_name')):
            enriched['implementing_office'] = dpwh_row.get('implementing_office')
            enriched['organization_name'] = dpwh_row.get('implementing_office')
    
    # Fix/update status if DPWH has better status
    if pd.notna(dpwh_row.get('status')):
        dpwh_status = str(dpwh_row.get('status')).strip()
        ms_status = str(enriched.get('Contract Status', '') or enriched.get('status', '')).strip()
        # Use DPWH status if it's more descriptive or microsite status is missing
        if not ms_status or ms_status == 'N/A' or len(dpwh_status) > len(ms_status):
            enriched['Contract Status'] = dpwh_status
            enriched['status'] = dpwh_status
            enriched['dpwh_status'] = dpwh_status
    
    # Fix/update amount if DPWH amount is more reliable
    ms_amount = normalize_amount(enriched.get('Contract Price') or enriched.get('Contract Amount'))
    dpwh_amount = normalize_amount(dpwh_row.get('cost_php'))
    if dpwh_amount and (not ms_amount or ms_amount == 0):
        enriched['Contract Price'] = dpwh_amount
        enriched['Contract Amount'] = dpwh_amount
        enriched['Amount'] = dpwh_amount
        enriched['dpwh_cost_php'] = dpwh_amount
    
    # Fix/update description if DPWH description is more complete
    ms_desc = str(enriched.get('project_name', '') or enriched.get('project_description', '') or '')
    dpwh_desc = str(dpwh_row.get('description', '') or '')
    if len(dpwh_desc) > len(ms_desc) and len(dpwh_desc) > 20:
        # DPWH description is longer and more descriptive
        enriched['project_description'] = dpwh_desc
        if pd.isna(enriched.get('project_name')) or len(str(enriched.get('project_name', ''))) < len(dpwh_desc):
            enriched['project_name'] = dpwh_desc
        enriched['dpwh_description'] = dpwh_desc
    
    # Add year from DPWH
    if pd.notna(dpwh_row.get('year')):
        enriched['dpwh_year'] = int(dpwh_row.get('year'))
        if pd.isna(enriched.get('year')):
            enriched['year'] = int(dpwh_row.get('year'))
    
    # Note: Latitude/Longitude columns are not available in DPWH scraper CSV
    # If these exist in microsite data (e.g., latitude, longitude, lat, lng, coordinates),
    # they are preserved automatically since we copy all original columns
    
    # Preserve any existing bidding-related columns from microsite
    # (bidding_date, award_date, notice_date, pre_bid_date, etc.)
    # These are automatically preserved since we start with microsite_row.copy()
    
    # Note: Personnel columns (AMO, BAC, DE) are not available in DPWH scraper CSV
    # The DPWH scraper only extracts contract data, not personnel information
    # If these exist in microsite data (e.g., amo_name, bac_chairman, de_name, district_engineer, etc.),
    # they are preserved automatically since we copy all original columns
    
    return enriched

def main():
    print("🔍 Loading DPWH scraper data...")
    if not DPWH_CSV.exists():
        print(f"❌ DPWH CSV not found: {DPWH_CSV}")
        print("   Please ensure the DPWH scraper CSV exists at the expected path.")
        return
    
    dpwh_df = pd.read_csv(DPWH_CSV, encoding='utf-8', low_memory=False)
    print(f"✅ Loaded {len(dpwh_df)} DPWH contracts")
    
    print("\n🔍 Loading Microsite data...")
    if not MICROSITE_PARQUET.exists():
        print(f"❌ Microsite parquet not found: {MICROSITE_PARQUET}")
        return
    
    microsite_df = pd.read_parquet(MICROSITE_PARQUET)
    print(f"✅ Loaded {len(microsite_df)} Microsite projects")
    
    # Create backup
    print("\n💾 Creating backup...")
    if MICROSITE_PARQUET.exists():
        import shutil
        shutil.copy2(MICROSITE_PARQUET, BACKUP_PARQUET)
        print(f"✅ Backup created: {BACKUP_PARQUET}")
    
    print("\n🔗 Building indices for fast matching...")
    # Build contractor index
    dpwh_index_by_contractor = {}
    for idx, row in dpwh_df.iterrows():
        contractor = normalize_contractor(str(row.get('contractor_name_1', '') or ''))
        if contractor:
            if contractor not in dpwh_index_by_contractor:
                dpwh_index_by_contractor[contractor] = []
            dpwh_index_by_contractor[contractor].append(idx)
    
    # Convert to DataFrames for easier access
    for contractor in dpwh_index_by_contractor:
        dpwh_index_by_contractor[contractor] = dpwh_df.loc[dpwh_index_by_contractor[contractor]]
    
    # Build amount index (rounded to nearest 100k for approximate matching)
    dpwh_index_by_amount = {}
    for idx, row in dpwh_df.iterrows():
        amount = normalize_amount(row.get('cost_php'))
        if amount:
            amount_key = round(amount / 100000) * 100000
            if amount_key not in dpwh_index_by_amount:
                dpwh_index_by_amount[amount_key] = []
            dpwh_index_by_amount[amount_key].append(idx)
    
    # Convert to DataFrames
    for amount_key in dpwh_index_by_amount:
        dpwh_index_by_amount[amount_key] = dpwh_df.loc[dpwh_index_by_amount[amount_key]]
    
    print(f"   ✅ Built contractor index: {len(dpwh_index_by_contractor)} unique contractors")
    print(f"   ✅ Built amount index: {len(dpwh_index_by_amount)} amount ranges")
    
    print("\n🔗 Matching Microsite projects with DPWH scraper data...")
    print("   (This may take a while for large datasets)")
    
    enriched_rows = []
    match_stats = {
        'total': len(microsite_df),
        'matched': 0,
        'unmatched': 0,
        'high_confidence': 0,  # >= 0.95
        'medium_confidence': 0  # 0.90-0.95
    }
    
    for idx, microsite_row in microsite_df.iterrows():
        if (idx + 1) % 1000 == 0:
            print(f"   Processed {idx + 1}/{len(microsite_df)} projects... ({match_stats['matched']} matched so far)")
        
        dpwh_match, confidence = match_microsite_to_dpwh(
            microsite_row, 
            dpwh_df, 
            dpwh_index_by_contractor=dpwh_index_by_contractor,
            dpwh_index_by_amount=dpwh_index_by_amount
        )
        enriched_row = enrich_microsite_row(microsite_row, dpwh_match, confidence)
        enriched_rows.append(enriched_row)
        
        if dpwh_match is not None:
            match_stats['matched'] += 1
            if confidence >= 0.95:
                match_stats['high_confidence'] += 1
            else:
                match_stats['medium_confidence'] += 1
        else:
            match_stats['unmatched'] += 1
    
    print(f"\n📊 Matching Statistics:")
    print(f"   Total projects: {match_stats['total']}")
    print(f"   ✅ Matched: {match_stats['matched']} ({match_stats['matched']/match_stats['total']*100:.1f}%)")
    print(f"      - High confidence (≥95%): {match_stats['high_confidence']}")
    print(f"      - Medium confidence (90-95%): {match_stats['medium_confidence']}")
    print(f"   ❌ Unmatched: {match_stats['unmatched']} ({match_stats['unmatched']/match_stats['total']*100:.1f}%)")
    
    print("\n💾 Creating enriched dataset...")
    enriched_df = pd.DataFrame(enriched_rows)
    
    # Save enriched parquet
    enriched_df.to_parquet(OUTPUT_PARQUET, index=False, engine='pyarrow')
    print(f"✅ Saved enriched data to: {OUTPUT_PARQUET}")
    
    # Also save as backup with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    timestamped_output = OUTPUT_PARQUET.parent / f"infrawatch_projects_enriched_{timestamp}.parquet"
    enriched_df.to_parquet(timestamped_output, index=False, engine='pyarrow')
    print(f"✅ Saved timestamped backup to: {timestamped_output}")
    
    # Generate summary report
    print("\n📝 Generating summary report...")
    summary = {
        'timestamp': datetime.now().isoformat(),
        'source_files': {
            'dpwh_csv': str(DPWH_CSV),
            'microsite_parquet': str(MICROSITE_PARQUET),
            'output_parquet': str(OUTPUT_PARQUET)
        },
        'statistics': match_stats,
        'new_columns_added': [
            'dpwh_matched',
            'dpwh_match_confidence',
            'dpwh_contract_id',
            'contractor_id',
            'contractor_id_2',
            'contractor_id_3',
            'contractor_id_4',
            'contractor_name_2',
            'contractor_name_3',
            'contractor_name_4',
            'effectivity_date',
            'expiry_date',
            'accomplishment_pct',
            'source_of_funds',
            'dpwh_region',
            'dpwh_implementing_office',
            'dpwh_status',
            'dpwh_year'
        ],
        'columns_enriched': [
            'project_name',
            'project_description',
            'Contract Price',
            'Contract Status',
            'region',
            'implementing_office',
            'organization_name'
        ],
        'columns_preserved_from_microsite': [
            'All original microsite columns are preserved, including:',
            '- Bidding dates (bidding_date, award_date, notice_date, pre_bid_date, etc.) if they exist',
            '- Location coordinates (latitude, longitude, lat, lng, coordinates, etc.) if they exist',
            '- Personnel names (AMO, BAC, DE, district_engineer, amo_name, bac_chairman, etc.) if they exist',
            '- Any other custom columns from the original microsite parquet'
        ],
        'notes': {
            'bidding_columns': 'Bidding-related date columns are not in DPWH scraper CSV but are preserved from microsite if they exist',
            'location_coordinates': 'Latitude/longitude columns are not in DPWH scraper CSV but are preserved from microsite if they exist',
            'personnel_columns': 'Personnel columns (AMO, BAC, DE names) are not in DPWH scraper CSV. The scraper only extracts contract data, not personnel information. These are preserved from microsite if they exist.',
            'date_columns': 'DPWH provides effectivity_date and expiry_date. All other date columns from microsite are preserved.'
        },
        'columns_not_available_in_dpwh_scraper': [
            'AMO (Authorized Managing Officer) names',
            'BAC (Bids and Awards Committee) personnel names',
            'DE (District Engineer) names',
            'Bidding dates (bidding_date, award_date, notice_date)',
            'Location coordinates (latitude, longitude)',
            'Note: These fields are not present in the source HTML tables that the DPWH scraper parses'
        ]
    }
    
    summary_path = Path(__file__).parent.parent / "data" / "parquet" / "microsite_enrichment_summary.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"✅ Summary report saved to: {summary_path}")
    
    print("\n✅ Enrichment complete!")
    print(f"\n📋 Next steps:")
    print(f"   1. Review the enriched data: {OUTPUT_PARQUET}")
    print(f"   2. Verify match quality using dpwh_match_confidence column")
    print(f"   3. Check summary report: {summary_path}")
    print(f"\n💡 To replace the original parquet with enriched version:")
    print(f"   cp {OUTPUT_PARQUET} {MICROSITE_PARQUET}")
    print(f"\n   Then regenerate cache using:")
    print(f"   python3 scripts/generate_dynasty_projects_cache_duckdb.py --force")
    print(f"\n📝 Note: The following columns are NOT available in DPWH scraper CSV:")
    print(f"   - AMO, BAC, DE personnel names (not in source HTML)")
    print(f"   - Bidding dates (bidding_date, award_date, notice_date)")
    print(f"   - Location coordinates (latitude, longitude)")
    print(f"   These columns are preserved from microsite if they exist.")

if __name__ == "__main__":
    main()












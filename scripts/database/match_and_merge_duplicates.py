#!/usr/bin/env python3
"""
Match and merge duplicate rows across databases using strict matching criteria.

This script:
1. Loads all exported Parquet files
2. Applies strict matching logic to identify duplicates
3. Merges matched rows
4. Adds a column indicating how many sources matched
"""

import pandas as pd
from pathlib import Path
import numpy as np
from typing import Dict, List, Tuple
from datetime import datetime

OUTPUT_DIR = Path('data/parquet')
INTEGRATED_FILE = OUTPUT_DIR / 'integrated_projects.parquet'
MATCHED_FILE = OUTPUT_DIR / 'integrated_projects_matched.parquet'


def normalize_text(text):
    """Normalize text for matching (lowercase, remove extra spaces, punctuation)."""
    if pd.isna(text) or text is None:
        return ''
    text = str(text).lower().strip()
    # Remove common punctuation and extra spaces
    text = ''.join(c for c in text if c.isalnum() or c.isspace())
    text = ' '.join(text.split())  # Normalize whitespace
    return text


def normalize_amount(amount, tolerance=0.05):
    """Normalize amount for matching (within 5% tolerance)."""
    if pd.isna(amount) or amount == 0:
        return None
    # Round to nearest 1000 for tolerance matching
    return round(float(amount) / 1000) * 1000


def normalize_contractor(contractor):
    """Normalize contractor name for matching."""
    if pd.isna(contractor) or contractor is None:
        return ''
    contractor = normalize_text(contractor)
    # Remove common suffixes
    for suffix in [' inc', ' inc.', ' corporation', ' corp', ' corp.', ' company', ' co', ' co.']:
        if contractor.endswith(suffix):
            contractor = contractor[:-len(suffix)].strip()
    return contractor


def normalize_location(location):
    """Normalize location for matching."""
    if pd.isna(location) or location is None:
        return ''
    location = normalize_text(location)
    # Remove common prefixes/suffixes
    location = location.replace('province of', '').replace('city of', '').strip()
    return location


def calculate_match_score(row1: pd.Series, row2: pd.Series) -> float:
    """
    Calculate match score between two rows (0-1, higher = better match).
    
    Matching criteria (strict):
    1. Contractor name (exact or very similar) - 40% weight
    2. Amount (within 5% tolerance) - 30% weight
    3. Province (exact match) - 20% weight
    4. Year (exact match) - 10% weight
    """
    score = 0.0
    weights = {'contractor': 0.4, 'amount': 0.3, 'province': 0.2, 'year': 0.1}
    
    # 1. Contractor match (40%)
    contractor1 = normalize_contractor(row1.get('contractor_name', ''))
    contractor2 = normalize_contractor(row2.get('contractor_name', ''))
    if contractor1 and contractor2:
        if contractor1 == contractor2:
            score += weights['contractor']
        elif contractor1 in contractor2 or contractor2 in contractor1:
            # Partial match (one name contains the other)
            score += weights['contractor'] * 0.7
        else:
            # Use Levenshtein-like similarity for fuzzy matching
            from difflib import SequenceMatcher
            similarity = SequenceMatcher(None, contractor1, contractor2).ratio()
            if similarity >= 0.85:  # 85% similarity threshold
                score += weights['contractor'] * similarity
    
    # 2. Amount match (30%) - within 5% tolerance
    amount1 = row1.get('amount', 0) or 0
    amount2 = row2.get('amount', 0) or 0
    try:
        amount1 = float(amount1) if pd.notna(amount1) else 0
        amount2 = float(amount2) if pd.notna(amount2) else 0
        if amount1 > 0 and amount2 > 0:
            diff_pct = abs(amount1 - amount2) / max(amount1, amount2)
            if diff_pct <= 0.05:  # Within 5%
                score += weights['amount'] * (1 - diff_pct / 0.05)  # Higher score for closer match
            elif diff_pct <= 0.10:  # Within 10% (partial credit)
                score += weights['amount'] * 0.5 * (1 - (diff_pct - 0.05) / 0.05)
    except (ValueError, TypeError):
        pass
    
    # 3. Province match (20%)
    province1 = normalize_location(row1.get('province', ''))
    province2 = normalize_location(row2.get('province', ''))
    if province1 and province2:
        if province1 == province2:
            score += weights['province']
        elif province1 in province2 or province2 in province1:
            score += weights['province'] * 0.8
    
    # 4. Year match (10%)
    year1 = row1.get('project_year') or row1.get('contract_year')
    year2 = row2.get('project_year') or row2.get('contract_year')
    if pd.notna(year1) and pd.notna(year2):
        try:
            year1_int = int(float(year1))
            year2_int = int(float(year2))
            if year1_int == year2_int:
                score += weights['year']
            elif abs(year1_int - year2_int) == 1:
                # Within 1 year (partial credit)
                score += weights['year'] * 0.5
        except (ValueError, TypeError):
            pass
    
    return score


def find_matches(df: pd.DataFrame, min_score: float = 0.7) -> List[Tuple[int, int, float]]:
    """
    Find matching rows in the dataframe using optimized indexing.
    Returns list of (index1, index2, score) tuples.
    """
    matches = []
    n = len(df)
    
    print(f"   🔍 Finding matches (min score: {min_score})...")
    print(f"   Total rows: {n:,}")
    
    # Pre-normalize contractor names and amounts for faster matching
    print("   Pre-processing data for matching...")
    df = df.copy()
    df['_norm_contractor'] = df['contractor_name'].apply(normalize_contractor)
    df['_norm_amount'] = df['amount'].apply(lambda x: normalize_amount(x) if pd.notna(x) and x > 0 else None)
    df['_norm_province'] = df['province'].apply(normalize_location)
    df['_norm_year'] = df['project_year'].fillna(df['contract_year'])
    
    # Group by source to avoid matching within same source
    sources = df['source'].unique()
    
    for i, source1 in enumerate(sources):
        for source2 in sources[i+1:]:  # Only compare different sources
            df1 = df[df['source'] == source1].copy()
            df2 = df[df['source'] == source2].copy()
            
            print(f"      Comparing {source1} ({len(df1):,} rows) vs {source2} ({len(df2):,} rows)...")
            
            # Create index for df2 by contractor + amount bucket for faster lookup
            df2_indexed = {}
            for idx2, row2 in df2.iterrows():
                contractor = row2['_norm_contractor']
                amount = row2['_norm_amount']
                if contractor and amount:
                    key = (contractor, amount)
                    if key not in df2_indexed:
                        df2_indexed[key] = []
                    df2_indexed[key].append(idx2)
            
            # Compare df1 rows with indexed df2
            batch_matches = []
            for idx1, row1 in df1.iterrows():
                contractor1 = row1['_norm_contractor']
                amount1 = row1['_norm_amount']
                
                if not contractor1 or not amount1:
                    continue
                
                # Find potential matches in df2
                candidates = []
                key = (contractor1, amount1)
                if key in df2_indexed:
                    candidates.extend(df2_indexed[key])
                
                # Also check similar amounts (±10%)
                if amount1:
                    for amount2_key in df2_indexed.keys():
                        if amount2_key[0] == contractor1:  # Same contractor
                            amount2 = amount2_key[1]
                            if amount2 and abs(amount1 - amount2) / max(amount1, amount2) <= 0.10:
                                candidates.extend(df2_indexed[amount2_key])
                
                # Compare with candidates
                for idx2 in set(candidates):  # Remove duplicates
                    if idx2 in df2.index:
                        row2 = df2.loc[idx2]
                        score = calculate_match_score(row1, row2)
                        if score >= min_score:
                            batch_matches.append((idx1, idx2, score))
            
            matches.extend(batch_matches)
            print(f"         Found {len(batch_matches):,} matches")
    
    print(f"   ✅ Found {len(matches):,} total matches")
    return matches


def merge_matched_rows(df: pd.DataFrame, matches: List[Tuple[int, int, float]]) -> pd.DataFrame:
    """
    Merge matched rows into single rows with combined data.
    """
    print(f"\n🔗 Merging {len(matches):,} matched rows...")
    
    # Create a mapping of row indices to their match groups
    match_groups = {}
    group_id = 0
    
    for idx1, idx2, score in matches:
        # Find which groups these indices belong to
        group1 = None
        group2 = None
        
        for gid, indices in match_groups.items():
            if idx1 in indices:
                group1 = gid
            if idx2 in indices:
                group2 = gid
        
        if group1 is None and group2 is None:
            # New group
            match_groups[group_id] = {idx1, idx2}
            group_id += 1
        elif group1 is not None and group2 is None:
            # Add idx2 to group1
            match_groups[group1].add(idx2)
        elif group1 is None and group2 is not None:
            # Add idx1 to group2
            match_groups[group2].add(idx1)
        elif group1 != group2:
            # Merge two groups
            match_groups[group1].update(match_groups[group2])
            del match_groups[group2]
    
    print(f"   Created {len(match_groups):,} match groups")
    
    # Create merged rows
    merged_rows = []
    matched_indices = set()
    
    for group_id, indices in match_groups.items():
        matched_indices.update(indices)
        group_rows = df.loc[list(indices)]
        
        # Create merged row
        merged_row = {}
        
        # Get all sources in this match
        sources = group_rows['source'].unique().tolist()
        merged_row['matched_sources'] = ','.join(sorted(sources))
        merged_row['source_count'] = len(sources)
        
        # For each column, use the best available value
        for col in df.columns:
            if col in ['matched_sources', 'source_count']:
                continue
            
            # Get non-null values from all rows
            values = group_rows[col].dropna().unique()
            
            if len(values) == 0:
                merged_row[col] = None
            elif len(values) == 1:
                merged_row[col] = values[0]
            else:
                # Multiple values - use priority logic
                if col == 'source':
                    # Keep all sources as comma-separated
                    merged_row[col] = ','.join(sorted(sources))
                elif col in ['amount', 'contract_amount']:
                    # Use maximum amount (most complete)
                    merged_row[col] = max([v for v in values if pd.notna(v) and v > 0], default=None)
                elif col in ['project_name', 'project_description']:
                    # Use longest description (most detailed)
                    merged_row[col] = max([str(v) for v in values if pd.notna(v)], key=len, default=None)
                elif col in ['contractor_name']:
                    # Use most complete contractor name
                    merged_row[col] = max([str(v) for v in values if pd.notna(v)], key=len, default=None)
                else:
                    # Use first non-null value
                    merged_row[col] = next((v for v in values if pd.notna(v)), None)
        
        merged_rows.append(merged_row)
    
    # Keep unmatched rows
    unmatched_df = df[~df.index.isin(matched_indices)].copy()
    unmatched_df['matched_sources'] = unmatched_df['source']
    unmatched_df['source_count'] = 1
    
    # Combine merged and unmatched
    if merged_rows:
        merged_df = pd.DataFrame(merged_rows)
        result_df = pd.concat([merged_df, unmatched_df], ignore_index=True)
    else:
        result_df = unmatched_df
    
    print(f"   ✅ Merged into {len(merged_rows):,} rows")
    print(f"   ✅ Kept {len(unmatched_df):,} unmatched rows")
    print(f"   ✅ Total: {len(result_df):,} rows (down from {len(df):,})")
    
    return result_df


def main():
    """Main matching and merging function."""
    print("🚀 Starting strict matching and merging...")
    print(f"📊 Input: {INTEGRATED_FILE}")
    print(f"📊 Output: {MATCHED_FILE}\n")
    
    if not INTEGRATED_FILE.exists():
        print(f"❌ Input file not found: {INTEGRATED_FILE}")
        return
    
    # Load integrated data
    print("📂 Loading integrated Parquet file...")
    df = pd.read_parquet(INTEGRATED_FILE)
    print(f"   Loaded {len(df):,} rows, {len(df.columns)} columns")
    
    # Show source distribution
    print(f"\n📊 Source distribution:")
    source_counts = df['source'].value_counts()
    for source, count in source_counts.items():
        print(f"   {source}: {count:,} rows")
    
    # Find matches
    matches = find_matches(df, min_score=0.7)
    
    if not matches:
        print("\n⚠️  No matches found. Saving with source_count=1 for all rows.")
        df['matched_sources'] = df['source']
        df['source_count'] = 1
        result_df = df
    else:
        # Merge matched rows
        result_df = merge_matched_rows(df, matches)
    
    # Add summary statistics
    print(f"\n📈 Final Statistics:")
    print(f"   Total rows: {len(result_df):,}")
    print(f"   Matched rows (source_count > 1): {len(result_df[result_df['source_count'] > 1]):,}")
    print(f"   Unmatched rows (source_count = 1): {len(result_df[result_df['source_count'] == 1]):,}")
    
    if 'source_count' in result_df.columns:
        print(f"\n   Source count distribution:")
        count_dist = result_df['source_count'].value_counts().sort_index()
        for count, num_rows in count_dist.items():
            print(f"      {count} source(s): {num_rows:,} rows")
    
    # Save matched file
    print(f"\n💾 Saving matched file...")
    result_df.to_parquet(MATCHED_FILE, compression='snappy', engine='pyarrow', index=False)
    size_mb = MATCHED_FILE.stat().st_size / 1024 / 1024
    print(f"   ✅ Saved: {MATCHED_FILE} ({size_mb:.2f} MB)")
    
    # Show sample matched rows
    if len(result_df[result_df['source_count'] > 1]) > 0:
        print(f"\n📋 Sample matched rows (source_count > 1):")
        matched_sample = result_df[result_df['source_count'] > 1].head(5)
        for idx, row in matched_sample.iterrows():
            print(f"   Row {idx}: {row.get('contractor_name', 'N/A')} - {row.get('amount', 0):,.2f} - Sources: {row.get('matched_sources', 'N/A')} ({row.get('source_count', 0)} sources)")
    
    print("\n✅ Matching and merging complete!")


if __name__ == "__main__":
    main()

import pandas as pd
from pathlib import Path
import numpy as np
from typing import Dict, List, Tuple
from datetime import datetime

OUTPUT_DIR = Path('data/parquet')
INTEGRATED_FILE = OUTPUT_DIR / 'integrated_projects.parquet'
MATCHED_FILE = OUTPUT_DIR / 'integrated_projects_matched.parquet'


def normalize_text(text):
    """Normalize text for matching (lowercase, remove extra spaces, punctuation)."""
    if pd.isna(text) or text is None:
        return ''
    text = str(text).lower().strip()
    # Remove common punctuation and extra spaces
    text = ''.join(c for c in text if c.isalnum() or c.isspace())
    text = ' '.join(text.split())  # Normalize whitespace
    return text


def normalize_amount(amount, tolerance=0.05):
    """Normalize amount for matching (within 5% tolerance)."""
    if pd.isna(amount) or amount == 0:
        return None
    # Round to nearest 1000 for tolerance matching
    return round(float(amount) / 1000) * 1000


def normalize_contractor(contractor):
    """Normalize contractor name for matching."""
    if pd.isna(contractor) or contractor is None:
        return ''
    contractor = normalize_text(contractor)
    # Remove common suffixes
    for suffix in [' inc', ' inc.', ' corporation', ' corp', ' corp.', ' company', ' co', ' co.']:
        if contractor.endswith(suffix):
            contractor = contractor[:-len(suffix)].strip()
    return contractor


def normalize_location(location):
    """Normalize location for matching."""
    if pd.isna(location) or location is None:
        return ''
    location = normalize_text(location)
    # Remove common prefixes/suffixes
    location = location.replace('province of', '').replace('city of', '').strip()
    return location


def calculate_match_score(row1: pd.Series, row2: pd.Series) -> float:
    """
    Calculate match score between two rows (0-1, higher = better match).
    
    Matching criteria (strict):
    1. Contractor name (exact or very similar) - 40% weight
    2. Amount (within 5% tolerance) - 30% weight
    3. Province (exact match) - 20% weight
    4. Year (exact match) - 10% weight
    """
    score = 0.0
    weights = {'contractor': 0.4, 'amount': 0.3, 'province': 0.2, 'year': 0.1}
    
    # 1. Contractor match (40%)
    contractor1 = normalize_contractor(row1.get('contractor_name', ''))
    contractor2 = normalize_contractor(row2.get('contractor_name', ''))
    if contractor1 and contractor2:
        if contractor1 == contractor2:
            score += weights['contractor']
        elif contractor1 in contractor2 or contractor2 in contractor1:
            # Partial match (one name contains the other)
            score += weights['contractor'] * 0.7
        else:
            # Use Levenshtein-like similarity for fuzzy matching
            from difflib import SequenceMatcher
            similarity = SequenceMatcher(None, contractor1, contractor2).ratio()
            if similarity >= 0.85:  # 85% similarity threshold
                score += weights['contractor'] * similarity
    
    # 2. Amount match (30%) - within 5% tolerance
    amount1 = row1.get('amount', 0) or 0
    amount2 = row2.get('amount', 0) or 0
    try:
        amount1 = float(amount1) if pd.notna(amount1) else 0
        amount2 = float(amount2) if pd.notna(amount2) else 0
        if amount1 > 0 and amount2 > 0:
            diff_pct = abs(amount1 - amount2) / max(amount1, amount2)
            if diff_pct <= 0.05:  # Within 5%
                score += weights['amount'] * (1 - diff_pct / 0.05)  # Higher score for closer match
            elif diff_pct <= 0.10:  # Within 10% (partial credit)
                score += weights['amount'] * 0.5 * (1 - (diff_pct - 0.05) / 0.05)
    except (ValueError, TypeError):
        pass
    
    # 3. Province match (20%)
    province1 = normalize_location(row1.get('province', ''))
    province2 = normalize_location(row2.get('province', ''))
    if province1 and province2:
        if province1 == province2:
            score += weights['province']
        elif province1 in province2 or province2 in province1:
            score += weights['province'] * 0.8
    
    # 4. Year match (10%)
    year1 = row1.get('project_year') or row1.get('contract_year')
    year2 = row2.get('project_year') or row2.get('contract_year')
    if pd.notna(year1) and pd.notna(year2):
        try:
            year1_int = int(float(year1))
            year2_int = int(float(year2))
            if year1_int == year2_int:
                score += weights['year']
            elif abs(year1_int - year2_int) == 1:
                # Within 1 year (partial credit)
                score += weights['year'] * 0.5
        except (ValueError, TypeError):
            pass
    
    return score


def find_matches(df: pd.DataFrame, min_score: float = 0.7) -> List[Tuple[int, int, float]]:
    """
    Find matching rows in the dataframe using optimized indexing.
    Returns list of (index1, index2, score) tuples.
    """
    matches = []
    n = len(df)
    
    print(f"   🔍 Finding matches (min score: {min_score})...")
    print(f"   Total rows: {n:,}")
    
    # Pre-normalize contractor names and amounts for faster matching
    print("   Pre-processing data for matching...")
    df = df.copy()
    df['_norm_contractor'] = df['contractor_name'].apply(normalize_contractor)
    df['_norm_amount'] = df['amount'].apply(lambda x: normalize_amount(x) if pd.notna(x) and x > 0 else None)
    df['_norm_province'] = df['province'].apply(normalize_location)
    df['_norm_year'] = df['project_year'].fillna(df['contract_year'])
    
    # Group by source to avoid matching within same source
    sources = df['source'].unique()
    
    for i, source1 in enumerate(sources):
        for source2 in sources[i+1:]:  # Only compare different sources
            df1 = df[df['source'] == source1].copy()
            df2 = df[df['source'] == source2].copy()
            
            print(f"      Comparing {source1} ({len(df1):,} rows) vs {source2} ({len(df2):,} rows)...")
            
            # Create index for df2 by contractor + amount bucket for faster lookup
            df2_indexed = {}
            for idx2, row2 in df2.iterrows():
                contractor = row2['_norm_contractor']
                amount = row2['_norm_amount']
                if contractor and amount:
                    key = (contractor, amount)
                    if key not in df2_indexed:
                        df2_indexed[key] = []
                    df2_indexed[key].append(idx2)
            
            # Compare df1 rows with indexed df2
            batch_matches = []
            for idx1, row1 in df1.iterrows():
                contractor1 = row1['_norm_contractor']
                amount1 = row1['_norm_amount']
                
                if not contractor1 or not amount1:
                    continue
                
                # Find potential matches in df2
                candidates = []
                key = (contractor1, amount1)
                if key in df2_indexed:
                    candidates.extend(df2_indexed[key])
                
                # Also check similar amounts (±10%)
                if amount1:
                    for amount2_key in df2_indexed.keys():
                        if amount2_key[0] == contractor1:  # Same contractor
                            amount2 = amount2_key[1]
                            if amount2 and abs(amount1 - amount2) / max(amount1, amount2) <= 0.10:
                                candidates.extend(df2_indexed[amount2_key])
                
                # Compare with candidates
                for idx2 in set(candidates):  # Remove duplicates
                    if idx2 in df2.index:
                        row2 = df2.loc[idx2]
                        score = calculate_match_score(row1, row2)
                        if score >= min_score:
                            batch_matches.append((idx1, idx2, score))
            
            matches.extend(batch_matches)
            print(f"         Found {len(batch_matches):,} matches")
    
    print(f"   ✅ Found {len(matches):,} total matches")
    return matches


def merge_matched_rows(df: pd.DataFrame, matches: List[Tuple[int, int, float]]) -> pd.DataFrame:
    """
    Merge matched rows into single rows with combined data.
    """
    print(f"\n🔗 Merging {len(matches):,} matched rows...")
    
    # Create a mapping of row indices to their match groups
    match_groups = {}
    group_id = 0
    
    for idx1, idx2, score in matches:
        # Find which groups these indices belong to
        group1 = None
        group2 = None
        
        for gid, indices in match_groups.items():
            if idx1 in indices:
                group1 = gid
            if idx2 in indices:
                group2 = gid
        
        if group1 is None and group2 is None:
            # New group
            match_groups[group_id] = {idx1, idx2}
            group_id += 1
        elif group1 is not None and group2 is None:
            # Add idx2 to group1
            match_groups[group1].add(idx2)
        elif group1 is None and group2 is not None:
            # Add idx1 to group2
            match_groups[group2].add(idx1)
        elif group1 != group2:
            # Merge two groups
            match_groups[group1].update(match_groups[group2])
            del match_groups[group2]
    
    print(f"   Created {len(match_groups):,} match groups")
    
    # Create merged rows
    merged_rows = []
    matched_indices = set()
    
    for group_id, indices in match_groups.items():
        matched_indices.update(indices)
        group_rows = df.loc[list(indices)]
        
        # Create merged row
        merged_row = {}
        
        # Get all sources in this match
        sources = group_rows['source'].unique().tolist()
        merged_row['matched_sources'] = ','.join(sorted(sources))
        merged_row['source_count'] = len(sources)
        
        # For each column, use the best available value
        for col in df.columns:
            if col in ['matched_sources', 'source_count']:
                continue
            
            # Get non-null values from all rows
            values = group_rows[col].dropna().unique()
            
            if len(values) == 0:
                merged_row[col] = None
            elif len(values) == 1:
                merged_row[col] = values[0]
            else:
                # Multiple values - use priority logic
                if col == 'source':
                    # Keep all sources as comma-separated
                    merged_row[col] = ','.join(sorted(sources))
                elif col in ['amount', 'contract_amount']:
                    # Use maximum amount (most complete)
                    merged_row[col] = max([v for v in values if pd.notna(v) and v > 0], default=None)
                elif col in ['project_name', 'project_description']:
                    # Use longest description (most detailed)
                    merged_row[col] = max([str(v) for v in values if pd.notna(v)], key=len, default=None)
                elif col in ['contractor_name']:
                    # Use most complete contractor name
                    merged_row[col] = max([str(v) for v in values if pd.notna(v)], key=len, default=None)
                else:
                    # Use first non-null value
                    merged_row[col] = next((v for v in values if pd.notna(v)), None)
        
        merged_rows.append(merged_row)
    
    # Keep unmatched rows
    unmatched_df = df[~df.index.isin(matched_indices)].copy()
    unmatched_df['matched_sources'] = unmatched_df['source']
    unmatched_df['source_count'] = 1
    
    # Combine merged and unmatched
    if merged_rows:
        merged_df = pd.DataFrame(merged_rows)
        result_df = pd.concat([merged_df, unmatched_df], ignore_index=True)
    else:
        result_df = unmatched_df
    
    print(f"   ✅ Merged into {len(merged_rows):,} rows")
    print(f"   ✅ Kept {len(unmatched_df):,} unmatched rows")
    print(f"   ✅ Total: {len(result_df):,} rows (down from {len(df):,})")
    
    return result_df


def main():
    """Main matching and merging function."""
    print("🚀 Starting strict matching and merging...")
    print(f"📊 Input: {INTEGRATED_FILE}")
    print(f"📊 Output: {MATCHED_FILE}\n")
    
    if not INTEGRATED_FILE.exists():
        print(f"❌ Input file not found: {INTEGRATED_FILE}")
        return
    
    # Load integrated data
    print("📂 Loading integrated Parquet file...")
    df = pd.read_parquet(INTEGRATED_FILE)
    print(f"   Loaded {len(df):,} rows, {len(df.columns)} columns")
    
    # Show source distribution
    print(f"\n📊 Source distribution:")
    source_counts = df['source'].value_counts()
    for source, count in source_counts.items():
        print(f"   {source}: {count:,} rows")
    
    # Find matches
    matches = find_matches(df, min_score=0.7)
    
    if not matches:
        print("\n⚠️  No matches found. Saving with source_count=1 for all rows.")
        df['matched_sources'] = df['source']
        df['source_count'] = 1
        result_df = df
    else:
        # Merge matched rows
        result_df = merge_matched_rows(df, matches)
    
    # Add summary statistics
    print(f"\n📈 Final Statistics:")
    print(f"   Total rows: {len(result_df):,}")
    print(f"   Matched rows (source_count > 1): {len(result_df[result_df['source_count'] > 1]):,}")
    print(f"   Unmatched rows (source_count = 1): {len(result_df[result_df['source_count'] == 1]):,}")
    
    if 'source_count' in result_df.columns:
        print(f"\n   Source count distribution:")
        count_dist = result_df['source_count'].value_counts().sort_index()
        for count, num_rows in count_dist.items():
            print(f"      {count} source(s): {num_rows:,} rows")
    
    # Save matched file
    print(f"\n💾 Saving matched file...")
    result_df.to_parquet(MATCHED_FILE, compression='snappy', engine='pyarrow', index=False)
    size_mb = MATCHED_FILE.stat().st_size / 1024 / 1024
    print(f"   ✅ Saved: {MATCHED_FILE} ({size_mb:.2f} MB)")
    
    # Show sample matched rows
    if len(result_df[result_df['source_count'] > 1]) > 0:
        print(f"\n📋 Sample matched rows (source_count > 1):")
        matched_sample = result_df[result_df['source_count'] > 1].head(5)
        for idx, row in matched_sample.iterrows():
            print(f"   Row {idx}: {row.get('contractor_name', 'N/A')} - {row.get('amount', 0):,.2f} - Sources: {row.get('matched_sources', 'N/A')} ({row.get('source_count', 0)} sources)")
    
    print("\n✅ Matching and merging complete!")


if __name__ == "__main__":
    main()












#!/usr/bin/env python3
"""
Convert DPWH scraper CSV to parquet format for use in dynasty projects cache generation.
This creates a transparency parquet file from the DPWH infra data scraper CSV.
"""

import pandas as pd
from pathlib import Path
import sys

# Paths
DPWH_CSV = Path("/home/joebert/dpwh-infra-data-scraper/csv/contracts_all_years_all_offices.csv")
OUTPUT_PARQUET = Path(__file__).parent.parent / "data" / "parquet" / "transparency_projects.parquet"

def main():
    print("🔍 Loading DPWH scraper CSV...")
    if not DPWH_CSV.exists():
        print(f"❌ DPWH CSV not found: {DPWH_CSV}")
        print("   Please ensure the DPWH scraper CSV exists at the expected path.")
        return 1
    
    print(f"   Reading from: {DPWH_CSV}")
    try:
        df = pd.read_csv(DPWH_CSV, encoding='utf-8', low_memory=False)
        print(f"✅ Loaded {len(df)} contracts")
        
        if len(df) == 0:
            print("⚠️  WARNING: CSV file is empty!")
            return 1
        
        # Check if required columns exist
        required_columns = ['contract_id', 'description', 'contractor_name_1', 'cost_php']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            print(f"❌ Missing required columns: {missing_columns}")
            print(f"   Available columns: {sorted(df.columns.tolist())}")
            return 1
        
        print(f"   Columns found: {len(df.columns)}")
        print(f"   Sample columns: {list(df.columns[:10])}")
    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Standardize column names to match expected format
    # Map DPWH scraper columns to standard project format
    print("\n🔄 Standardizing column names...")
    
    # Create standardized dataframe
    standardized_df = pd.DataFrame()
    
    # Core identification
    if 'contract_id' not in df.columns:
        print("⚠️  WARNING: 'contract_id' column not found, creating from index")
        standardized_df['contract_id'] = df.index.astype(str)
    else:
        standardized_df['contract_id'] = df['contract_id']
    
    if 'description' not in df.columns:
        print("❌ ERROR: 'description' column is required but not found")
        print(f"   Available columns: {sorted(df.columns.tolist())}")
        return 1
    
    standardized_df['description'] = df['description']
    standardized_df['project_name'] = df['description']  # Use description as project name
    standardized_df['project_description'] = df['description']
    
    # Contractor information (primary contractor)
    if 'contractor_name_1' in df.columns:
        standardized_df['contractor_name'] = df['contractor_name_1']
    else:
        print("⚠️  WARNING: 'contractor_name_1' not found, using empty values")
        standardized_df['contractor_name'] = None
    
    if 'contractor_id_1' in df.columns:
        standardized_df['contractor_id'] = df['contractor_id_1']
    else:
        standardized_df['contractor_id'] = None
    
    # Additional contractors (joint ventures) - store as JSON-like strings or separate columns
    # For now, we'll keep them as separate columns
    standardized_df['contractor_name_2'] = df.get('contractor_name_2', None)
    standardized_df['contractor_id_2'] = df.get('contractor_id_2', None)
    standardized_df['contractor_name_3'] = df.get('contractor_name_3', None)
    standardized_df['contractor_id_3'] = df.get('contractor_id_3', None)
    standardized_df['contractor_name_4'] = df.get('contractor_name_4', None)
    standardized_df['contractor_id_4'] = df.get('contractor_id_4', None)
    
    # Location & Office
    standardized_df['region'] = df['region']
    standardized_df['implementing_office'] = df['implementing_office']
    standardized_df['organization_name'] = df['implementing_office']  # Alias for compatibility
    standardized_df['location'] = df['implementing_office']  # Use implementing office as location
    
    # Financial
    if 'cost_php' not in df.columns:
        print("⚠️  WARNING: 'cost_php' column not found, checking for alternatives...")
        # Try alternative column names
        amount_col = None
        for col in ['amount', 'cost', 'contract_amount', 'Contract Price', 'Contract Amount']:
            if col in df.columns:
                amount_col = col
                break
        if amount_col:
            print(f"   Using '{amount_col}' as amount column")
            standardized_df['cost_php'] = df[amount_col]
        else:
            print("❌ ERROR: No amount column found")
            return 1
    else:
        standardized_df['cost_php'] = df['cost_php']
    
    standardized_df['amount'] = standardized_df['cost_php']
    standardized_df['contract_amount'] = standardized_df['cost_php']
    standardized_df['Contract Price'] = standardized_df['cost_php']
    standardized_df['Contract Amount'] = standardized_df['cost_php']
    
    # Dates
    standardized_df['effectivity_date'] = pd.to_datetime(df['effectivity_date'], errors='coerce')
    standardized_df['expiry_date'] = pd.to_datetime(df['expiry_date'], errors='coerce')
    
    # Extract year from effectivity_date or year column
    standardized_df['year'] = df.get('year', None)
    if standardized_df['year'].isna().any():
        # Fill missing years from effectivity_date
        standardized_df['year'] = standardized_df['year'].fillna(
            standardized_df['effectivity_date'].dt.year
        )
    
    # Status & Progress
    standardized_df['status'] = df['status']
    standardized_df['Contract Status'] = df['status']
    standardized_df['accomplishment_pct'] = df['accomplishment_pct']
    
    # Source of funds
    standardized_df['source_of_funds'] = df['source_of_funds']
    standardized_df['infrawatch_fund_source'] = df['source_of_funds']  # Alias for compatibility
    
    # Source identifier
    standardized_df['_source'] = 'Transparency'
    standardized_df['source'] = 'Transparency'
    
    # Metadata
    standardized_df['source_office'] = df.get('source_office', None)
    standardized_df['file_source'] = df.get('file_source', None)
    standardized_df['row_number'] = df.get('row_number', None)
    
    # Data quality tracking (preserve for reference)
    standardized_df['critical_errors'] = df.get('critical_errors', None)
    standardized_df['errors'] = df.get('errors', None)
    standardized_df['warnings'] = df.get('warnings', None)
    standardized_df['info_notes'] = df.get('info_notes', None)
    
    # Add empty columns that might be expected by the processing script
    # (These will be None/NaN but won't cause errors)
    expected_columns = [
        'province', 'city', 'municipality', 'barangay',
        'meilisearch_id', 'global_id', 'award_title', 'award_description',
        'notice_title', 'project_title', 'awardee_name', 'philgeps_award_title',
        'philgeps_awardee_name', 'philgeps_area_of_delivery'
    ]
    for col in expected_columns:
        if col not in standardized_df.columns:
            standardized_df[col] = None
    
    print(f"✅ Standardized {len(standardized_df.columns)} columns")
    
    # Save to parquet
    print(f"\n💾 Saving to parquet: {OUTPUT_PARQUET}")
    OUTPUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        standardized_df.to_parquet(OUTPUT_PARQUET, index=False, engine='pyarrow')
        print(f"✅ Saved {len(standardized_df)} projects to: {OUTPUT_PARQUET}")
        
        # Verify the file was created and has data
        if not OUTPUT_PARQUET.exists():
            print("❌ ERROR: Parquet file was not created!")
            return 1
        
        # Read it back to verify
        verify_df = pd.read_parquet(OUTPUT_PARQUET)
        if len(verify_df) != len(standardized_df):
            print(f"⚠️  WARNING: Verification failed - saved {len(standardized_df)} but read back {len(verify_df)}")
        else:
            print(f"✅ Verified: File contains {len(verify_df)} records")
        
    except Exception as e:
        print(f"❌ Error saving parquet file: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Print summary
    print(f"\n📊 Summary:")
    print(f"   Total contracts: {len(standardized_df)}")
    print(f"   With contractor: {standardized_df['contractor_name'].notna().sum()}")
    print(f"   With amount: {standardized_df['amount'].notna().sum()}")
    if standardized_df['year'].notna().any():
        print(f"   Years range: {standardized_df['year'].min():.0f} - {standardized_df['year'].max():.0f}")
    else:
        print(f"   Years: No year data available")
    print(f"   Source field: {standardized_df['source'].unique()}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())












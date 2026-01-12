import pandas as pd
import os
import sys

def convert_to_parquet():
    base_dir = '/home/joebert/open-data-visualization/database/dpwh/contract splitting'
    
    # File 1: Projects List
    projects_excel = os.path.join(base_dir, 'Contract Splitting 2021-2024_for ANs.xlsx')
    projects_parquet = os.path.join(base_dir, 'dpwh_projects_2021_2024.parquet')
    
    print(f"Reading {projects_excel} (Sheet: OVERALL)...")
    try:
        df_projects = pd.read_excel(projects_excel, sheet_name='OVERALL')
        # Fix mixed types in completion/date columns
        for col in ['completion', 'completi_1', 'startdate']:
            if col in df_projects.columns:
                df_projects[col] = df_projects[col].astype(str)
        df_projects.to_parquet(projects_parquet, index=False)
        print(f"Success! Saved to {projects_parquet}")
        print(f"Stats: {len(df_projects)} rows, {len(df_projects.columns)} columns")
    except Exception as e:
        print(f"Failed to process project file: {e}")
        sys.exit(1)
        
    print("-" * 30)

    # File 2: Contractor Candidates
    candidates_excel = os.path.join(base_dir, 'contract splitting candidates.xlsx')
    candidates_parquet = os.path.join(base_dir, 'contract_splitting_candidates.parquet')
    
    print(f"Reading {candidates_excel}...")
    try:
        df_candidates = pd.read_excel(candidates_excel)
        # Drop rows where the contractor name is NaN (cleaning)
        initial_len = len(df_candidates)
        df_candidates = df_candidates.dropna(subset=['Contract splitting candidates'])
        dropped_len = initial_len - len(df_candidates)
        
        df_candidates.to_parquet(candidates_parquet, index=False)
        print(f"Success! Saved to {candidates_parquet}")
        print(f"Stats: {len(df_candidates)} rows, {len(df_candidates.columns)} columns (Dropped {dropped_len} NaN rows)")
    except Exception as e:
        print(f"Failed to process candidates file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    convert_to_parquet()

import pandas as pd
import os

base_dir = '/home/joebert/open-data-visualization/database/dpwh/contract splitting'
projects_parquet = os.path.join(base_dir, 'dpwh_projects_2021_2024.parquet')
candidates_parquet = os.path.join(base_dir, 'contract_splitting_candidates.parquet')

def analyze_data():
    try:
        df_projects = pd.read_parquet(projects_parquet)
        df_candidates = pd.read_parquet(candidates_parquet)
        
        print("--- Projects Data ---")
        print("Columns:", df_projects.columns.tolist())
        if 'cluster_id' in df_projects.columns:
            print(f"Unique Cluster IDs: {df_projects['cluster_id'].nunique()}")
            print("Sample Cluster IDs:", df_projects['cluster_id'].unique()[:10])
            
            # Check for clusters with multiple projects
            cluster_counts = df_projects['cluster_id'].value_counts()
            print("\nClusters with > 1 projects:", (cluster_counts > 1).sum())
            print("Sample large cluster:", cluster_counts.index[0], "count:", cluster_counts.iloc[0])
            
            # Show a sample cluster
            sample_cluster_id = cluster_counts.index[0]
            print(f"\nData for Cluster {sample_cluster_id}:")
            print(df_projects[df_projects['cluster_id'] == sample_cluster_id][['contractid', 'contractor', 'abc', 'contractco']].to_string())

        else:
            print("WARNING: 'cluster_id' column not found!")

        print("\n--- Candidates Data ---")
        print("First 5 candidates:")
        print(df_candidates.head(5))

    except Exception as e:
        print(f"Error: {e}")

analyze_data()

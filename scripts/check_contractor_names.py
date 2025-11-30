import duckdb
from pathlib import Path
import pandas as pd

# Connect to DuckDB
con = duckdb.connect()
root_dir = Path('data/parquet')

# Gardiola's contractor patterns
gardiola_contractors = [
    "CHIARA2300",
    "LOUREL DEVELOPMENT",
    "NEWINGTON BUILDERS",
    "E. GARDIOLA",
    "S-ANG CONSTRUCTION"
]

# Zaldy Co's contractor patterns
zaldy_contractors = [
    "CENTERWAYS CONSTRUCTION",
    "FS CO BUILDERS",
    "HI-TONE CONSTRUCTION",
    "SUNWEST"
]

print("\n===== GARDIOLA CONTRACTOR SEARCH =====\n")

# Search for Gardiola in each database
databases = [
    ('DIME', 'data/parquet/dime_projects.parquet', 'contractor_name'),
    ('PhilGEPS', 'data/parquet/philgeps_contracts.parquet', 'philgeps_awardee_name'),
    ('Transparency', 'data/parquet/transparency_projects.parquet', 'contractor_name'),
    ('Microsite', 'data/parquet/infrawatch_projects_enriched.parquet', 'contractor_name'),
    ('Flood/SSP', 'data/parquet/flood_projects.parquet', 'Contractor')
]

for db_name, parquet_file, contractor_column in databases:
    try:
        # Try to find matches
        query = f"""
            SELECT DISTINCT {contractor_column} as contractor, COUNT(*) as count
            FROM read_parquet('{parquet_file}')
            WHERE {contractor_column} IS NOT NULL 
                AND (
                    UPPER({contractor_column}) LIKE '%GARDIOLA%' OR
                    UPPER({contractor_column}) LIKE '%CHIARA%' OR
                    UPPER({contractor_column}) LIKE '%LOUREL%' OR
                    UPPER({contractor_column}) LIKE '%NEWINGTON%' OR
                    UPPER({contractor_column}) LIKE '%S-ANG%'
                )
            GROUP BY {contractor_column}
            ORDER BY count DESC
            LIMIT 20
        """
        
        df = con.execute(query).df()
        
        if not df.empty:
            print(f"\n{db_name} ({len(df)} matches):")
            print(df.to_string(index=False))
        else:
            print(f"\n{db_name}: No matches found")
            
    except Exception as e:
        print(f"\n{db_name}: Error - {e}")

print("\n\n===== ZALDY CO CONTRACTOR SEARCH =====\n")

for db_name, parquet_file, contractor_column in databases:
    try:
        query = f"""
            SELECT DISTINCT {contractor_column} as contractor, COUNT(*) as count
            FROM read_parquet('{parquet_file}')
            WHERE {contractor_column} IS NOT NULL 
                AND (
                    UPPER({contractor_column}) LIKE '%CENTERWAYS%' OR
                    UPPER({contractor_column}) LIKE '%FS CO%' OR
                    UPPER({contractor_column}) LIKE '%HI-TONE%' OR
                    UPPER({contractor_column}) LIKE '%SUNWEST%'
                )
            GROUP BY {contractor_column}
            ORDER BY count DESC
            LIMIT 20
        """
        
        df = con.execute(query).df()
        
        if not df.empty:
            print(f"\n{db_name} ({len(df)} matches):")
            print(df.to_string(index=False))
        else:
            print(f"\n{db_name}: No matches found")
            
    except Exception as e:
        print(f"\n{db_name}: Error - {e}")

print("\n\n===== SAMPLE: Check if contractor field is even populated =====\n")

for db_name, parquet_file, contractor_column in databases:
    try:
        query = f"""
            SELECT 
                COUNT(*) as total_projects,
                COUNT({contractor_column}) as with_contractor,
                COUNT(*) - COUNT({contractor_column}) as without_contractor
            FROM read_parquet('{parquet_file}')
        """
        
        df = con.execute(query).df()
        print(f"\n{db_name}:")
        print(df.to_string(index=False))
            
    except Exception as e:
        print(f"\n{db_name}: Error - {e}")

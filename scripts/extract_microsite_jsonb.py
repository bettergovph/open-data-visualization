#!/usr/bin/env python3
"""
Extract JSONB columns from Microsite parquet file or PostgreSQL database.
Creates a parquet file with extracted columns if they don't exist.
"""
import duckdb
import pandas as pd
from pathlib import Path
import os
import asyncio
import asyncpg

PARQUET_DIR = Path('data/parquet')
OUTPUT_FILE = PARQUET_DIR / 'infrawatch_projects_extracted.parquet'

def check_existing_extracted():
    """Check if extracted parquet already exists"""
    if OUTPUT_FILE.exists():
        conn = duckdb.connect()
        try:
            count = conn.execute(f'SELECT COUNT(*) FROM "{OUTPUT_FILE}"').fetchone()[0]
            cols = [row[0] for row in conn.execute(f'DESCRIBE SELECT * FROM "{OUTPUT_FILE}" LIMIT 1').fetchall()]
            print(f"✓ Found existing extracted file: {OUTPUT_FILE}")
            print(f"  Rows: {count:,}")
            print(f"  Columns: {len(cols)}")
            # Check if it has the right columns
            has_extracted = any('project_name' in c.lower() or 'project_description' in c.lower() for c in cols)
            if has_extracted:
                print(f"  ✓ Has extracted columns (project_name, project_description, etc.)")
                return True
            else:
                print(f"  ⚠️  Missing extracted columns")
                return False
        except Exception as e:
            print(f"  Error checking file: {e}")
            return False
        finally:
            conn.close()
    return False

async def extract_from_postgresql():
    """Extract from PostgreSQL infrawatch database"""
    print("\n=== Extracting from PostgreSQL ===")
    PG_CONFIG = {
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('POSTGRES_PORT', 5432)),
        'user': os.getenv('POSTGRES_USER', 'budget_admin'),
        'password': os.getenv('POSTGRES_PASSWORD', 'wuQ5gBYCKkZiOGb61chLcByMu'),
    }
    
    try:
        conn = await asyncpg.connect(
            host=PG_CONFIG['host'],
            port=PG_CONFIG['port'],
            user=PG_CONFIG['user'],
            password=PG_CONFIG['password'],
            database='infrawatch'
        )
        
        # Check if table exists
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'infrawatch_projects_rows'
            )
        """)
        
        if not table_exists:
            print("⚠️  Table infrawatch_projects_rows not found")
            await conn.close()
            return None
        
        count = await conn.fetchval('SELECT COUNT(*) FROM infrawatch_projects_rows')
        print(f"Found {count:,} rows in PostgreSQL")
        
        # Extract JSONB data - same query as export_to_parquet.py
        query = """
            SELECT 
                COALESCE(data->>'Contract ID', data->>'ContractID', data->>'contract_id', id::text) as contract_id,
                COALESCE(data->>'Contract ID', data->>'ContractID', data->>'contract_id', id::text) as project_id,
                COALESCE(data->>'Contract Details', data->>'ContractDetails', data->>'contract_details', 
                         data->>'Project Name', data->>'ProjectName', data->>'project_name', 
                         data->>'Title', data->>'title') as project_name,
                COALESCE(data->>'Contract Details', data->>'ContractDetails', data->>'contract_details', 
                         data->>'Project Description', data->>'ProjectDescription', data->>'project_description',
                         data->>'Title', data->>'title') as project_description,
                COALESCE(data->>'Contractor', data->>'Contractor Name', data->>'ContractorName', 
                         data->>'contractor', data->>'contractor_name') as contractor_name,
                COALESCE(
                    NULLIF((data->>'Contract Price')::numeric, 0),
                    NULLIF((data->>'ContractPrice')::numeric, 0),
                    NULLIF((data->>'contract_price')::numeric, 0),
                    NULLIF((data->>'Amount')::numeric, 0),
                    NULLIF((data->>'amount')::numeric, 0),
                    NULLIF((data->>'Cost')::numeric, 0),
                    NULLIF((data->>'cost')::numeric, 0)
                ) as amount,
                COALESCE(data->>'Implementing Agency', data->>'ImplementingAgency', 
                         data->>'implementing_agency', data->>'Organization', data->>'organization') as organization_name,
                COALESCE(data->>'Implementing Agency', data->>'ImplementingAgency', 
                         data->>'implementing_agency') as infrawatch_implementing_agency,
                COALESCE(data->>'Fund Source', data->>'FundSource', data->>'fund_source') as infrawatch_fund_source,
                COALESCE(data->>'Region', data->>'region') as region,
                COALESCE(data->>'Province', data->>'province') as province,
                COALESCE(data->>'Municipality', data->>'municipality') as municipality,
                COALESCE(data->>'City', data->>'city') as city,
                COALESCE(data->>'Barangay', data->>'barangay') as barangay,
                COALESCE(data->>'Legislative District', data->>'LegislativeDistrict', 
                         data->>'legislative_district', data->>'District', data->>'district') as legislative_district,
                COALESCE(data->>'Contract Status', data->>'ContractStatus', 
                         data->>'contract_status', data->>'Status', data->>'status') as contractor_status,
                'Microsite' as source
            FROM infrawatch_projects_rows
            WHERE (
                NULLIF((data->>'Contract Price')::numeric, 0) IS NOT NULL OR
                NULLIF((data->>'ContractPrice')::numeric, 0) IS NOT NULL OR
                NULLIF((data->>'contract_price')::numeric, 0) IS NOT NULL OR
                NULLIF((data->>'Amount')::numeric, 0) IS NOT NULL OR
                NULLIF((data->>'amount')::numeric, 0) IS NOT NULL OR
                NULLIF((data->>'Cost')::numeric, 0) IS NOT NULL OR
                NULLIF((data->>'cost')::numeric, 0) IS NOT NULL
            )
        """
        
        rows = await conn.fetch(query)
        await conn.close()
        
        if not rows:
            print("⚠️  No rows extracted")
            return None
        
        # Convert to DataFrame
        col_names = list(rows[0].keys())
        data = [list(row.values()) for row in rows]
        df = pd.DataFrame(data, columns=col_names)
        
        print(f"✓ Extracted {len(df):,} rows, {len(df.columns)} columns")
        print(f"  Columns: {col_names[:10]}...")
        
        return df
        
    except Exception as e:
        print(f"❌ Error extracting from PostgreSQL: {e}")
        import traceback
        traceback.print_exc()
        return None

def extract_from_parquet():
    """Extract from existing infrawatch_projects.parquet if it has JSONB data"""
    print("\n=== Checking existing parquet file ===")
    infrawatch_path = PARQUET_DIR / 'infrawatch_projects.parquet'
    
    if not infrawatch_path.exists():
        print("⚠️  infrawatch_projects.parquet not found")
        return None
    
    conn = duckdb.connect()
    try:
        # Check if it has JSONB/data column
        cols = [row[0] for row in conn.execute(f'DESCRIBE SELECT * FROM "{infrawatch_path}" LIMIT 1').fetchall()]
        
        # Check for JSONB column
        jsonb_cols = [c for c in cols if 'data' in c.lower() and ('jsonb' in c.lower() or 'json' in c.lower())]
        
        if jsonb_cols:
            print(f"✓ Found JSONB column: {jsonb_cols}")
            print("  Extracting JSONB data...")
            # Would need to extract JSONB here if needed
            # For now, return None to extract from PostgreSQL
            return None
        else:
            # Check if columns are already extracted
            has_extracted = any('project_name' in c.lower() or 'project_description' in c.lower() for c in cols)
            if has_extracted:
                print(f"✓ Parquet already has extracted columns")
                # Load and return
                count = conn.execute(f'SELECT COUNT(*) FROM "{infrawatch_path}"').fetchone()[0]
                print(f"  Rows: {count:,}")
                return infrawatch_path
            else:
                print(f"⚠️  Parquet exists but columns not extracted")
                return None
    except Exception as e:
        print(f"Error: {e}")
        return None
    finally:
        conn.close()

async def main():
    print("🔍 Checking for Microsite parquet with extracted columns...")
    
    # Check if extracted file already exists
    if check_existing_extracted():
        print("\n✅ Extracted file already exists!")
        return
    
    # Try to extract from PostgreSQL
    df = await extract_from_postgresql()
    
    if df is not None and not df.empty:
        # Save to parquet
        PARQUET_DIR.mkdir(parents=True, exist_ok=True)
        df.to_parquet(OUTPUT_FILE, compression='snappy', engine='pyarrow', index=False)
        size_mb = OUTPUT_FILE.stat().st_size / 1024 / 1024
        print(f"\n✅ Saved extracted data to: {OUTPUT_FILE}")
        print(f"   Size: {size_mb:.2f} MB")
        print(f"   Rows: {len(df):,}")
        print(f"   Columns: {len(df.columns)}")
    else:
        print("\n⚠️  Could not extract data. Please check:")
        print("   1. PostgreSQL connection")
        print("   2. infrawatch database exists")
        print("   3. infrawatch_projects_rows table exists")

if __name__ == '__main__':
    asyncio.run(main())

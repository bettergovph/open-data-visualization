#!/usr/bin/env python3
"""
Create structured infrawatch_projects table from infrawatch_projects_rows JSONB data.

This script creates a normalized table structure from the JSONB data stored in
infrawatch_projects_rows, making it easier to query and export.
"""

import asyncio
import asyncpg
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# PostgreSQL connection config
PG_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'user': os.getenv('POSTGRES_USER', 'budget_admin'),
    'password': os.getenv('POSTGRES_PASSWORD', 'wuQ5gBYCKkZiOGb61chLcByMu'),
    'database': os.getenv('POSTGRES_DB_INFRAWATCH', 'infrawatch'),
}


async def create_infrawatch_projects_table():
    """Create structured infrawatch_projects table from infrawatch_projects_rows."""
    print("🚀 Creating infrawatch_projects table from infrawatch_projects_rows...")
    
    conn = await asyncpg.connect(**PG_CONFIG)
    
    try:
        # Check if infrawatch_projects_rows exists
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'infrawatch_projects_rows'
            )
        """)
        
        if not table_exists:
            print("❌ infrawatch_projects_rows table does not exist!")
            print("   Please run analysis/load_infrawatch_projects.py first")
            return
        
        print("✅ Found infrawatch_projects_rows table")
        
        # Drop existing table if it exists
        print("🗑️  Dropping existing infrawatch_projects table if it exists...")
        await conn.execute("DROP TABLE IF EXISTS infrawatch_projects CASCADE")
        
        # Create the structured table
        print("📊 Creating infrawatch_projects table...")
        await conn.execute("""
            CREATE TABLE infrawatch_projects (
                id BIGSERIAL PRIMARY KEY,
                infrawatch_row_id BIGINT REFERENCES infrawatch_projects_rows(id),
                contract_id TEXT,
                project_id TEXT,
                project_name TEXT,
                project_description TEXT,
                contractor_name TEXT,
                amount NUMERIC(20, 2),
                contract_amount NUMERIC(20, 2),
                infrawatch_contract_price NUMERIC(20, 2),
                organization_name TEXT,
                infrawatch_implementing_agency TEXT,
                infrawatch_fund_source TEXT,
                start_date DATE,
                project_year INTEGER,
                contract_year INTEGER,
                end_date DATE,
                contractor_status TEXT,
                infrawatch_contract_status TEXT,
                global_id TEXT,
                project_type TEXT,
                work_type TEXT,
                budget_amount NUMERIC(20, 2),
                region TEXT,
                province TEXT,
                municipality TEXT,
                city TEXT,
                barangay TEXT,
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                legislative_district TEXT,
                award_date DATE,
                contractor_sec_number TEXT,
                contractor_role TEXT DEFAULT 'main',
                is_joint_venture BOOLEAN DEFAULT false,
                department TEXT,
                district_engineering_office TEXT,
                congressman_name TEXT,
                dynasty_member_id INTEGER DEFAULT 0,
                dynasty_relationship TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                source_created_at TIMESTAMP WITH TIME ZONE,
                source TEXT DEFAULT 'Microsite'
            )
        """)
        
        # Create indexes
        print("📇 Creating indexes...")
        await conn.execute("CREATE INDEX idx_infrawatch_projects_contract_id ON infrawatch_projects(contract_id)")
        await conn.execute("CREATE INDEX idx_infrawatch_projects_contractor ON infrawatch_projects(contractor_name)")
        await conn.execute("CREATE INDEX idx_infrawatch_projects_amount ON infrawatch_projects(amount)")
        await conn.execute("CREATE INDEX idx_infrawatch_projects_province ON infrawatch_projects(province)")
        await conn.execute("CREATE INDEX idx_infrawatch_projects_year ON infrawatch_projects(project_year)")
        
        # Populate the table from JSONB data
        print("📥 Populating infrawatch_projects from infrawatch_projects_rows...")
        await conn.execute("""
            INSERT INTO infrawatch_projects (
                infrawatch_row_id,
                contract_id,
                project_id,
                project_name,
                project_description,
                contractor_name,
                amount,
                contract_amount,
                infrawatch_contract_price,
                organization_name,
                infrawatch_implementing_agency,
                infrawatch_fund_source,
                start_date,
                project_year,
                contract_year,
                end_date,
                contractor_status,
                infrawatch_contract_status,
                region,
                province,
                municipality,
                city,
                barangay,
                latitude,
                longitude,
                legislative_district,
                district_engineering_office,
                source_created_at
            )
            SELECT 
                r.id as infrawatch_row_id,
                COALESCE(r.data->>'Contract ID', r.data->>'ContractID', r.data->>'contract_id', r.id::text) as contract_id,
                COALESCE(r.data->>'Contract ID', r.data->>'ContractID', r.data->>'contract_id', r.id::text) as project_id,
                COALESCE(
                    r.data->>'Contract Details',
                    r.data->>'ContractDetails',
                    r.data->>'contract_details',
                    r.data->>'Project Name',
                    r.data->>'ProjectName',
                    r.data->>'project_name',
                    r.data->>'Title',
                    r.data->>'title'
                ) as project_name,
                COALESCE(
                    r.data->>'Contract Details',
                    r.data->>'ContractDetails',
                    r.data->>'contract_details',
                    r.data->>'Project Description',
                    r.data->>'ProjectDescription',
                    r.data->>'project_description',
                    r.data->>'Title',
                    r.data->>'title'
                ) as project_description,
                COALESCE(
                    r.data->>'Contractor',
                    r.data->>'Contractor Name',
                    r.data->>'ContractorName',
                    r.data->>'contractor',
                    r.data->>'contractor_name'
                ) as contractor_name,
                COALESCE(
                    NULLIF((r.data->>'Contract Price')::numeric, 0),
                    NULLIF((r.data->>'ContractPrice')::numeric, 0),
                    NULLIF((r.data->>'contract_price')::numeric, 0),
                    NULLIF((r.data->>'Amount')::numeric, 0),
                    NULLIF((r.data->>'amount')::numeric, 0),
                    NULLIF((r.data->>'Cost')::numeric, 0),
                    NULLIF((r.data->>'cost')::numeric, 0)
                ) as amount,
                COALESCE(
                    NULLIF((r.data->>'Contract Price')::numeric, 0),
                    NULLIF((r.data->>'ContractPrice')::numeric, 0),
                    NULLIF((r.data->>'contract_price')::numeric, 0),
                    NULLIF((r.data->>'Amount')::numeric, 0),
                    NULLIF((r.data->>'amount')::numeric, 0),
                    NULLIF((r.data->>'Cost')::numeric, 0),
                    NULLIF((r.data->>'cost')::numeric, 0)
                ) as contract_amount,
                COALESCE(
                    NULLIF((r.data->>'Contract Price')::numeric, 0),
                    NULLIF((r.data->>'ContractPrice')::numeric, 0),
                    NULLIF((r.data->>'contract_price')::numeric, 0)
                ) as infrawatch_contract_price,
                COALESCE(
                    r.data->>'Implementing Agency',
                    r.data->>'ImplementingAgency',
                    r.data->>'implementing_agency',
                    r.data->>'Organization',
                    r.data->>'organization'
                ) as organization_name,
                COALESCE(
                    r.data->>'Implementing Agency',
                    r.data->>'ImplementingAgency',
                    r.data->>'implementing_agency'
                ) as infrawatch_implementing_agency,
                COALESCE(
                    r.data->>'Fund Source',
                    r.data->>'FundSource',
                    r.data->>'fund_source'
                ) as infrawatch_fund_source,
                NULLIF(COALESCE(
                    (r.data->>'Effectivity Date')::date,
                    (r.data->>'EffectivityDate')::date,
                    (r.data->>'effectivity_date')::date,
                    (r.data->>'Start Date')::date,
                    (r.data->>'StartDate')::date,
                    (r.data->>'start_date')::date
                ), NULL) as start_date,
                EXTRACT(YEAR FROM COALESCE(
                    (r.data->>'Effectivity Date')::date,
                    (r.data->>'EffectivityDate')::date,
                    (r.data->>'effectivity_date')::date,
                    (r.data->>'Start Date')::date,
                    (r.data->>'StartDate')::date,
                    (r.data->>'start_date')::date
                ))::integer as project_year,
                EXTRACT(YEAR FROM COALESCE(
                    (r.data->>'Effectivity Date')::date,
                    (r.data->>'EffectivityDate')::date,
                    (r.data->>'effectivity_date')::date,
                    (r.data->>'Start Date')::date,
                    (r.data->>'StartDate')::date,
                    (r.data->>'start_date')::date
                ))::integer as contract_year,
                NULLIF(COALESCE(
                    (r.data->>'Expiry Date')::date,
                    (r.data->>'ExpiryDate')::date,
                    (r.data->>'expiry_date')::date,
                    (r.data->>'End Date')::date,
                    (r.data->>'EndDate')::date,
                    (r.data->>'end_date')::date
                ), NULL) as end_date,
                COALESCE(
                    r.data->>'Contract Status',
                    r.data->>'ContractStatus',
                    r.data->>'contract_status',
                    r.data->>'Status',
                    r.data->>'status'
                ) as contractor_status,
                COALESCE(
                    r.data->>'Contract Status',
                    r.data->>'ContractStatus',
                    r.data->>'contract_status'
                ) as infrawatch_contract_status,
                COALESCE(r.data->>'Region', r.data->>'region') as region,
                COALESCE(r.data->>'Province', r.data->>'province') as province,
                COALESCE(r.data->>'Municipality', r.data->>'municipality') as municipality,
                COALESCE(r.data->>'City', r.data->>'city') as city,
                COALESCE(r.data->>'Barangay', r.data->>'barangay') as barangay,
                NULLIF((r.data->>'Latitude')::double precision, 0) as latitude,
                NULLIF((r.data->>'Longitude')::double precision, 0) as longitude,
                COALESCE(
                    r.data->>'Legislative District',
                    r.data->>'LegislativeDistrict',
                    r.data->>'legislative_district',
                    r.data->>'District',
                    r.data->>'district'
                ) as legislative_district,
                COALESCE(
                    r.data->>'District Engineering Office',
                    r.data->>'DistrictEngineeringOffice',
                    r.data->>'district_engineering_office',
                    r.data->>'DEO',
                    r.data->>'deo'
                ) as district_engineering_office,
                r.created_at as source_created_at
            FROM infrawatch_projects_rows r
            WHERE (
                NULLIF((r.data->>'Contract Price')::numeric, 0) IS NOT NULL OR
                NULLIF((r.data->>'ContractPrice')::numeric, 0) IS NOT NULL OR
                NULLIF((r.data->>'contract_price')::numeric, 0) IS NOT NULL OR
                NULLIF((r.data->>'Amount')::numeric, 0) IS NOT NULL OR
                NULLIF((r.data->>'amount')::numeric, 0) IS NOT NULL OR
                NULLIF((r.data->>'Cost')::numeric, 0) IS NOT NULL OR
                NULLIF((r.data->>'cost')::numeric, 0) IS NOT NULL
            )
        """)
        
        # Get count
        count = await conn.fetchval("SELECT COUNT(*) FROM infrawatch_projects")
        
        print(f"✅ Successfully created infrawatch_projects table with {count:,} rows")
        print(f"\n💡 The table is now ready for export_to_parquet.py")
        
    except Exception as e:
        print(f"❌ Error creating table: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(create_infrawatch_projects_table())


#!/usr/bin/env python3
"""
Export integrated data from PostgreSQL to Parquet files with intelligent column merging.

Strategy:
- Merge columns with same semantic meaning (e.g., "contractor" = "contractor_name")
- Keep both columns when uncertain (e.g., "contract_cost" and "total_cost" both kept)
- Preserve all data - never lose information
"""

import asyncio
import asyncpg
import pandas as pd
from pathlib import Path
import os
from datetime import datetime
from typing import Dict, List, Set, Any

# PostgreSQL connection config
PG_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'user': os.getenv('POSTGRES_USER', 'budget_admin'),
    'password': os.getenv('POSTGRES_PASSWORD', 'wuQ5gBYCKkZiOGb61chLcByMu'),
}

# Output directory
OUTPUT_DIR = Path('data/parquet')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def get_pg_connection(db_name: str):
    """Get PostgreSQL connection for a specific database."""
    return await asyncpg.connect(
        host=PG_CONFIG['host'],
        port=PG_CONFIG['port'],
        user=PG_CONFIG['user'],
        password=PG_CONFIG['password'],
        database=db_name
    )


async def get_table_columns(conn: asyncpg.Connection, table_name: str) -> List[str]:
    """Get column names from a table."""
    try:
        query = """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = $1
            ORDER BY ordinal_position
        """
        rows = await conn.fetch(query, table_name)
        return [row['column_name'] for row in rows]
    except Exception as e:
        print(f"⚠️  Could not get columns for {table_name}: {e}")
        return []


def normalize_column_name(col: str) -> str:
    """Normalize column name for comparison (lowercase, remove underscores)."""
    return col.lower().replace('_', '').replace('-', '')


# Column mapping: maps source columns to unified column names
# Format: {source_db: {source_column: unified_column}}
COLUMN_MAPPINGS = {
    'flood': {
        # Identifiers
        'global_id': 'global_id',
        'contract_id': 'contract_id',
        'project_id': 'project_id',
        # Names/Descriptions
        'project_description': 'project_name',  # Merge: project_description -> project_name
        'project_description': 'project_description',  # Also keep original
        'type_of_work': 'project_type',
        'type_of_work': 'work_type',  # Keep both
        # Financial - KEEP BOTH when different
        'contract_cost': 'amount',  # Unified
        'contract_cost': 'contract_amount',  # Also keep as contract_amount
        # Geographic
        'region': 'region',
        'province': 'province',
        'municipality': 'municipality',
        'legislative_district': 'legislative_district',
        'latitude': 'latitude',
        'longitude': 'longitude',
        # Temporal
        'infra_year': 'project_year',
        'infra_year': 'contract_year',  # Keep both
        # Contractors
        'contractor': 'contractor_name',
        # Organization
        'district_engineering_office': 'organization_name',
        'district_engineering_office': 'district_engineering_office',  # Keep both
    },
    'dime': {
        'project_id': 'project_id',
        'contract_id': 'contract_id',
        'project_name': 'project_name',
        'project_description': 'project_description',
        'project_type': 'project_type',
        'work_type': 'work_type',
        'total_cost': 'amount',  # Merge: total_cost -> amount
        'total_cost': 'contract_amount',  # Also keep as contract_amount
        'region': 'region',
        'province': 'province',
        'municipality': 'municipality',
        'city': 'city',
        'barangay': 'barangay',
        'latitude': 'latitude',
        'longitude': 'longitude',
        'legislative_district': 'legislative_district',
        'project_year': 'project_year',
        'project_year': 'contract_year',
        'award_date': 'award_date',
        'start_date': 'start_date',
        'end_date': 'end_date',
        'contractor_name': 'contractor_name',
        'implementing_agency': 'organization_name',
        'department': 'department',
    },
    'philgeps': {
        'reference_id': 'project_id',
        'contract_no': 'contract_id',
        'award_title': 'project_name',
        'award_title': 'project_description',  # Keep both
        'business_category': 'project_type',
        'business_category': 'work_type',  # Keep both
        'contract_amount': 'amount',
        'contract_amount': 'contract_amount',  # Keep both
        'area_of_delivery': 'province',  # Merge: area_of_delivery -> province
        'area_of_delivery': 'area_of_delivery',  # Also keep original
        'award_date': 'award_date',
        'awardee_name': 'contractor_name',
        'organization_name': 'organization_name',
        'award_status': 'contractor_status',
        'meilisearch_id': 'global_id',  # Link to flood projects
    }
}


async def export_flood_projects() -> pd.DataFrame:
    """Export flood control projects from PostgreSQL to DataFrame."""
    print("🌊 Exporting flood control projects...")
    
    conn = await get_pg_connection('flood')
    
    try:
        columns = await get_table_columns(conn, 'flagged_flood_projects')
        if not columns:
            print("⚠️  Could not find flagged_flood_projects table")
            return pd.DataFrame()
        
        print(f"   Found table: flagged_flood_projects with {len(columns)} columns")
        
        select_parts = []
        added_columns = set()
        
        # Map columns from flagged_flood_projects
        if 'project_global_id' in columns:
            select_parts.append("project_global_id::text as global_id")
            select_parts.append("project_global_id::text as project_id")
            added_columns.add('global_id')
            added_columns.add('project_id')
        elif 'meilisearch_global_id' in columns:
            select_parts.append("meilisearch_global_id::text as global_id")
            select_parts.append("meilisearch_global_id::text as project_id")
            added_columns.add('global_id')
            added_columns.add('project_id')
        
        if 'project_name' in columns:
            select_parts.append("project_name as project_name")
            select_parts.append("project_name as project_description")
            added_columns.add('project_name')
            added_columns.add('project_description')
        
        if 'contractor' in columns:
            select_parts.append("contractor as contractor_name")
            added_columns.add('contractor_name')
        
        if 'contract_amount' in columns:
            if 'amount' not in added_columns:
                select_parts.append("contract_amount as amount")
                added_columns.add('amount')
            if 'contract_amount' not in added_columns:
                select_parts.append("contract_amount as contract_amount")
                added_columns.add('contract_amount')
        
        if 'province' in columns:
            select_parts.append("province as province")
            added_columns.add('province')
        
        if 'municipality' in columns:
            select_parts.append("municipality as municipality")
            added_columns.add('municipality')
        
        select_parts.append("'SSP' as source")
        
        # NULLs for missing columns
        if 'contract_id' not in added_columns:
            select_parts.append("NULL::text as contract_id")
        if 'project_type' not in added_columns:
            select_parts.append("NULL::text as project_type")
        if 'work_type' not in added_columns:
            select_parts.append("NULL::text as work_type")
        if 'budget_amount' not in added_columns:
            select_parts.append("NULL::numeric as budget_amount")
        if 'region' not in added_columns:
            select_parts.append("NULL::text as region")
        if 'city' not in added_columns:
            select_parts.append("NULL::text as city")
        if 'barangay' not in added_columns:
            select_parts.append("NULL::text as barangay")
        if 'latitude' not in added_columns:
            select_parts.append("NULL::double precision as latitude")
        if 'longitude' not in added_columns:
            select_parts.append("NULL::double precision as longitude")
        if 'legislative_district' not in added_columns:
            select_parts.append("NULL::text as legislative_district")
        if 'project_year' not in added_columns:
            select_parts.append("NULL::integer as project_year")
        if 'contract_year' not in added_columns:
            select_parts.append("NULL::integer as contract_year")
        if 'award_date' not in added_columns:
            select_parts.append("NULL::date as award_date")
        if 'start_date' not in added_columns:
            select_parts.append("NULL::date as start_date")
        if 'end_date' not in added_columns:
            select_parts.append("NULL::date as end_date")
        if 'contractor_sec_number' not in added_columns:
            select_parts.append("NULL::text as contractor_sec_number")
        if 'contractor_status' not in added_columns:
            select_parts.append("NULL::text as contractor_status")
        select_parts.append("'main' as contractor_role")
        select_parts.append("false as is_joint_venture")
        if 'organization_name' not in added_columns:
            select_parts.append("NULL::text as organization_name")
        if 'department' not in added_columns:
            select_parts.append("'DPWH' as department")
        if 'district_engineering_office' not in added_columns:
            select_parts.append("NULL::text as district_engineering_office")
        if 'congressman_name' not in added_columns:
            select_parts.append("NULL::text as congressman_name")
        if 'dynasty_member_id' not in added_columns:
            select_parts.append("0::integer as dynasty_member_id")
        if 'dynasty_relationship' not in added_columns:
            select_parts.append("NULL::text as dynasty_relationship")
        select_parts.append("now() as created_at")
        select_parts.append("now() as updated_at")
        if 'source_created_at' not in added_columns:
            select_parts.append("NULL::timestamp as source_created_at")
        
        query = f"SELECT {', '.join(select_parts)} FROM flagged_flood_projects WHERE contract_amount > 0"
        
        rows = await conn.fetch(query)
        
        if not rows:
            print("⚠️  No flood projects found")
            return pd.DataFrame()
        
        # Convert to DataFrame preserving column names
        if rows:
            col_names = list(rows[0].keys())
            data = [list(row.values()) for row in rows]
            df = pd.DataFrame(data, columns=col_names)
        else:
            df = pd.DataFrame()
        
        print(f"✅ Exported {len(df):,} rows, {len(df.columns)} columns")
        return df
        
    except Exception as e:
        print(f"⚠️  Error exporting flood projects: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()
    finally:
        await conn.close()


async def export_dime_projects() -> pd.DataFrame:
    """Export DIME projects to DataFrame with all columns preserved."""
    print("📊 Exporting DIME projects...")
    
    conn = await get_pg_connection('dime')
    
    try:
        columns = await get_table_columns(conn, 'dime_projects')
        if not columns:
            for alt_name in ['projects', 'dime']:
                columns = await get_table_columns(conn, alt_name)
                if columns:
                    table_name = alt_name
                    break
            else:
                print("⚠️  Could not find DIME projects table")
                return pd.DataFrame()
        else:
            table_name = 'dime_projects'
        
        print(f"   Found table: {table_name} with {len(columns)} columns")
        
        select_parts = []
        
        # Track which unified columns we've added to avoid duplicates
        added_columns = set()
        
        # Map columns, keeping originals when different
        if 'project_id' in columns:
            select_parts.append("project_id::text as project_id")
            added_columns.add('project_id')
        if 'contract_id' in columns:
            select_parts.append("contract_id::text as contract_id")
            added_columns.add('contract_id')
        if 'project_name' in columns:
            select_parts.append("project_name as project_name")
            added_columns.add('project_name')
        if 'description' in columns and 'project_description' not in added_columns:
            select_parts.append("description as project_description")
            added_columns.add('project_description')
        elif 'project_description' in columns and 'project_description' not in added_columns:
            select_parts.append("project_description as project_description")
            added_columns.add('project_description')
        if 'program' in columns:
            select_parts.append("program as program")
        if 'status' in columns:
            select_parts.append("status as status")
        if 'latest_progress' in columns:
            select_parts.append("latest_progress as latest_progress")
        if 'source_of_funds' in columns:
            select_parts.append("source_of_funds as source_of_funds")
        if 'project_type' in columns:
            select_parts.append("project_type as project_type")
        if 'work_type' in columns:
            select_parts.append("work_type as work_type")
        if 'cost' in columns:
            if 'amount' not in added_columns:
                select_parts.append("COALESCE(cost, 0) as amount")
                added_columns.add('amount')
            if 'contract_amount' not in added_columns:
                select_parts.append("COALESCE(cost, 0) as contract_amount")
                added_columns.add('contract_amount')
            select_parts.append("cost as dime_cost")  # Keep original
        elif 'total_cost' in columns:
            if 'amount' not in added_columns:
                select_parts.append("total_cost as amount")
                added_columns.add('amount')
            if 'contract_amount' not in added_columns:
                select_parts.append("total_cost as contract_amount")
                added_columns.add('contract_amount')
            select_parts.append("total_cost as dime_total_cost")  # Keep original
        if 'region' in columns:
            select_parts.append("region as region")
        if 'province' in columns:
            select_parts.append("province as province")
        if 'municipality' in columns:
            select_parts.append("municipality as municipality")
        if 'city' in columns:
            select_parts.append("city as city")
        if 'barangay' in columns:
            select_parts.append("barangay as barangay")
        if 'latitude' in columns:
            select_parts.append("latitude as latitude")
        if 'longitude' in columns:
            select_parts.append("longitude as longitude")
        if 'legislative_district' in columns:
            select_parts.append("legislative_district as legislative_district")
        if 'date_started' in columns:
            if 'project_year' not in added_columns:
                select_parts.append("EXTRACT(YEAR FROM date_started)::integer as project_year")
                added_columns.add('project_year')
            if 'contract_year' not in added_columns:
                select_parts.append("EXTRACT(YEAR FROM date_started)::integer as contract_year")
                added_columns.add('contract_year')
            if 'start_date' not in added_columns:
                select_parts.append("date_started as start_date")
                added_columns.add('start_date')
        elif 'project_year' in columns:
            if 'project_year' not in added_columns:
                select_parts.append("project_year::integer as project_year")
                added_columns.add('project_year')
            if 'contract_year' not in added_columns:
                select_parts.append("project_year::integer as contract_year")
                added_columns.add('contract_year')
        if 'award_date' in columns:
            select_parts.append("award_date as award_date")
        if 'start_date' in columns:
            select_parts.append("start_date as start_date")
        if 'end_date' in columns:
            select_parts.append("end_date as end_date")
        if 'contract_completion_date' in columns:
            select_parts.append("contract_completion_date as contract_end_date")
        if 'actual_contract_completion_date' in columns:
            select_parts.append("actual_contract_completion_date as actual_completion_date")
        if 'actual_date_started' in columns:
            select_parts.append("actual_date_started as actual_start_date")
        if 'last_updated_project_cost' in columns:
            select_parts.append("last_updated_project_cost as last_updated_cost")
        if 'utilized_amount' in columns:
            select_parts.append("utilized_amount as utilized_amount")
        if 'meilisearch_id' in columns and 'global_id' not in added_columns:
            select_parts.append("meilisearch_id as global_id")
            added_columns.add('global_id')
        if 'project_code' in columns:
            select_parts.append("project_code as project_code")
        if 'contractors' in columns and 'contractor_name' not in added_columns:
            # Handle array column - take first contractor, convert to text
            select_parts.append("CASE WHEN array_length(contractors, 1) > 0 THEN contractors[1]::text ELSE NULL END as contractor_name")
            added_columns.add('contractor_name')
        elif 'contractor_name' in columns and 'contractor_name' not in added_columns:
            select_parts.append("contractor_name as contractor_name")
            added_columns.add('contractor_name')
        if 'implementing_offices' in columns and 'organization_name' not in added_columns:
            # Handle array - take first office, convert to text
            select_parts.append("CASE WHEN array_length(implementing_offices, 1) > 0 THEN implementing_offices[1]::text ELSE NULL END as organization_name")
            added_columns.add('organization_name')
        elif 'implementing_agency' in columns and 'organization_name' not in added_columns:
            select_parts.append("implementing_agency as organization_name")
            added_columns.add('organization_name')
            select_parts.append("implementing_agency as dime_implementing_agency")  # Keep original
        if 'department' in columns:
            select_parts.append("department as department")
        
        select_parts.append("'DIME' as source")
        
        # NULLs for missing columns (only if not already added)
        if 'global_id' not in added_columns:
            select_parts.append("NULL::text as global_id")
        if 'budget_amount' not in added_columns:
            select_parts.append("NULL::numeric as budget_amount")
        select_parts.append("NULL::text as contractor_sec_number")
        select_parts.append("NULL::text as contractor_status")
        select_parts.append("'main' as contractor_role")
        select_parts.append("false as is_joint_venture")
        select_parts.append("NULL::text as district_engineering_office")
        select_parts.append("NULL::text as congressman_name")
        select_parts.append("0::integer as dynasty_member_id")
        select_parts.append("NULL::text as dynasty_relationship")
        select_parts.append("now() as created_at")
        select_parts.append("now() as updated_at")
        if 'created_at' in columns:
            select_parts.append("created_at as source_created_at")
        else:
            select_parts.append("NULL::timestamp as source_created_at")
        
        # Build WHERE clause based on available cost column
        if 'cost' in columns:
            where_clause = "cost IS NOT NULL AND cost > 0"
        elif 'total_cost' in columns:
            where_clause = "total_cost IS NOT NULL AND total_cost > 0"
        else:
            where_clause = "1=1"
        query = f"SELECT {', '.join(select_parts)} FROM {table_name} WHERE {where_clause}"
        
        rows = await conn.fetch(query)
        
        if not rows:
            print("⚠️  No DIME projects found")
            return pd.DataFrame()
        
        # Convert to DataFrame preserving column names
        if rows:
            # Get column names from first row
            col_names = list(rows[0].keys())
            data = [list(row.values()) for row in rows]
            df = pd.DataFrame(data, columns=col_names)
        else:
            df = pd.DataFrame()
        
        print(f"✅ Exported {len(df):,} rows, {len(df.columns)} columns")
        return df
        
    except Exception as e:
        print(f"⚠️  Error exporting DIME projects: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()
    finally:
        await conn.close()


async def export_philgeps_contracts() -> pd.DataFrame:
    """Export PhilGEPS contracts to DataFrame with all columns preserved."""
    print("📋 Exporting PhilGEPS contracts...")
    
    conn = await get_pg_connection('philgeps')
    
    try:
        columns = await get_table_columns(conn, 'contracts')
        if not columns:
            print("⚠️  Could not find contracts table")
            return pd.DataFrame()
        
        print(f"   Found table: contracts with {len(columns)} columns")
        
        select_parts = []
        
        # Map columns, keeping originals
        if 'reference_id' in columns:
            select_parts.append("reference_id as project_id")
            select_parts.append("reference_id as philgeps_reference_id")  # Keep original
        if 'contract_no' in columns:
            select_parts.append("contract_no as contract_id")
            select_parts.append("contract_no as philgeps_contract_no")  # Keep original
        if 'award_title' in columns:
            select_parts.append("award_title as project_name")
            select_parts.append("award_title as project_description")
            select_parts.append("award_title as philgeps_award_title")  # Keep original
        if 'business_category' in columns:
            select_parts.append("business_category as project_type")
            select_parts.append("business_category as work_type")
            select_parts.append("business_category as philgeps_business_category")  # Keep original
        if 'contract_amount' in columns:
            select_parts.append("contract_amount as amount")
            select_parts.append("contract_amount as contract_amount")
        if 'area_of_delivery' in columns:
            select_parts.append("area_of_delivery as province")
            select_parts.append("area_of_delivery as philgeps_area_of_delivery")  # Keep original
        if 'award_date' in columns:
            select_parts.append("award_date as award_date")
            select_parts.append("EXTRACT(YEAR FROM award_date)::integer as project_year")
            select_parts.append("EXTRACT(YEAR FROM award_date)::integer as contract_year")
        if 'awardee_name' in columns:
            select_parts.append("awardee_name as contractor_name")
            select_parts.append("awardee_name as philgeps_awardee_name")  # Keep original
        if 'organization_name' in columns:
            select_parts.append("organization_name as organization_name")
        if 'award_status' in columns:
            select_parts.append("award_status as contractor_status")
            select_parts.append("award_status as philgeps_award_status")  # Keep original
        if 'meilisearch_id' in columns:
            select_parts.append("meilisearch_id as global_id")
        
        select_parts.append("'PhilGEPS' as source")
        
        # NULLs for missing columns
        select_parts.append("NULL::text as city")
        select_parts.append("NULL::text as barangay")
        select_parts.append("NULL::numeric as budget_amount")
        select_parts.append("NULL::date as start_date")
        select_parts.append("NULL::date as end_date")
        select_parts.append("NULL::text as contractor_sec_number")
        select_parts.append("'main' as contractor_role")
        select_parts.append("false as is_joint_venture")
        select_parts.append("NULL::text as department")
        select_parts.append("NULL::text as district_engineering_office")
        select_parts.append("NULL::text as region")
        select_parts.append("NULL::text as municipality")
        select_parts.append("NULL::text as legislative_district")
        select_parts.append("NULL::double precision as latitude")
        select_parts.append("NULL::double precision as longitude")
        select_parts.append("NULL::text as congressman_name")
        select_parts.append("0::integer as dynasty_member_id")
        select_parts.append("NULL::text as dynasty_relationship")
        select_parts.append("now() as created_at")
        select_parts.append("now() as updated_at")
        if 'created_at' in columns:
            select_parts.append("created_at as source_created_at")
        else:
            select_parts.append("NULL::timestamp as source_created_at")
        
        query = f"SELECT {', '.join(select_parts)} FROM contracts WHERE contract_amount > 0 LIMIT 100000"
        
        rows = await conn.fetch(query)
        
        if not rows:
            print("⚠️  No PhilGEPS contracts found")
            return pd.DataFrame()
        
        # Convert to DataFrame preserving column names
        if rows:
            # Get column names from first row
            col_names = list(rows[0].keys())
            data = [list(row.values()) for row in rows]
            df = pd.DataFrame(data, columns=col_names)
        else:
            df = pd.DataFrame()
        
        print(f"✅ Exported {len(df):,} rows, {len(df.columns)} columns")
        return df
        
    except Exception as e:
        print(f"⚠️  Error exporting PhilGEPS contracts: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()
    finally:
        await conn.close()


async def export_infrawatch_projects() -> pd.DataFrame:
    """Export Infrawatch (Microsite) projects from PostgreSQL to DataFrame."""
    print("🏗️  Exporting Infrawatch (Microsite) projects...")
    
    conn = await get_pg_connection('infrawatch')
    
    try:
        columns = await get_table_columns(conn, 'infrawatch_projects')
        if not columns:
            print("⚠️  Could not find infrawatch_projects table")
            return pd.DataFrame()
        
        print(f"   Found table: infrawatch_projects with {len(columns)} columns")
        
        select_parts = []
        added_columns = set()
        
        # Map columns from infrawatch_projects
        if 'contract_id' in columns:
            select_parts.append("contract_id::text as contract_id")
            select_parts.append("contract_id::text as project_id")
            added_columns.add('contract_id')
            added_columns.add('project_id')
        
        if 'contract_details' in columns:
            select_parts.append("contract_details as project_name")
            select_parts.append("contract_details as project_description")
            added_columns.add('project_name')
            added_columns.add('project_description')
        
        if 'contractor' in columns:
            select_parts.append("contractor as contractor_name")
            added_columns.add('contractor_name')
        
        if 'contract_price' in columns:
            if 'amount' not in added_columns:
                select_parts.append("contract_price as amount")
                added_columns.add('amount')
            if 'contract_amount' not in added_columns:
                select_parts.append("contract_price as contract_amount")
                added_columns.add('contract_amount')
            select_parts.append("contract_price as infrawatch_contract_price")  # Keep original
        
        if 'implementing_agency' in columns:
            select_parts.append("implementing_agency as organization_name")
            added_columns.add('organization_name')
            select_parts.append("implementing_agency as infrawatch_implementing_agency")  # Keep original
        
        if 'fund_source' in columns:
            select_parts.append("fund_source as source_of_funds")
            select_parts.append("fund_source as infrawatch_fund_source")  # Keep original
        
        if 'effectivity_date' in columns:
            select_parts.append("effectivity_date as start_date")
            select_parts.append("EXTRACT(YEAR FROM effectivity_date)::integer as project_year")
            select_parts.append("EXTRACT(YEAR FROM effectivity_date)::integer as contract_year")
            added_columns.add('start_date')
            added_columns.add('project_year')
            added_columns.add('contract_year')
        
        if 'expiry_date' in columns:
            select_parts.append("expiry_date as end_date")
            added_columns.add('end_date')
        
        if 'contract_status' in columns:
            select_parts.append("contract_status as contractor_status")
            select_parts.append("contract_status as infrawatch_contract_status")  # Keep original
            added_columns.add('contractor_status')
        
        if 'accomplishment_pct' in columns:
            select_parts.append("accomplishment_pct as accomplishment_pct")
        
        select_parts.append("'Microsite' as source")  # Renamed from Infrawatch
        
        # NULLs for missing columns
        if 'global_id' not in added_columns:
            select_parts.append("NULL::text as global_id")
        if 'project_type' not in added_columns:
            select_parts.append("NULL::text as project_type")
        if 'work_type' not in added_columns:
            select_parts.append("NULL::text as work_type")
        if 'budget_amount' not in added_columns:
            select_parts.append("NULL::numeric as budget_amount")
        if 'region' not in added_columns:
            select_parts.append("NULL::text as region")
        if 'province' not in added_columns:
            select_parts.append("NULL::text as province")
        if 'municipality' not in added_columns:
            select_parts.append("NULL::text as municipality")
        if 'city' not in added_columns:
            select_parts.append("NULL::text as city")
        if 'barangay' not in added_columns:
            select_parts.append("NULL::text as barangay")
        if 'latitude' not in added_columns:
            select_parts.append("NULL::double precision as latitude")
        if 'longitude' not in added_columns:
            select_parts.append("NULL::double precision as longitude")
        if 'legislative_district' not in added_columns:
            select_parts.append("NULL::text as legislative_district")
        if 'award_date' not in added_columns:
            select_parts.append("NULL::date as award_date")
        if 'contractor_sec_number' not in added_columns:
            select_parts.append("NULL::text as contractor_sec_number")
        select_parts.append("'main' as contractor_role")
        select_parts.append("false as is_joint_venture")
        if 'department' not in added_columns:
            select_parts.append("NULL::text as department")
        if 'district_engineering_office' not in added_columns:
            select_parts.append("NULL::text as district_engineering_office")
        if 'congressman_name' not in added_columns:
            select_parts.append("NULL::text as congressman_name")
        if 'dynasty_member_id' not in added_columns:
            select_parts.append("0::integer as dynasty_member_id")
        if 'dynasty_relationship' not in added_columns:
            select_parts.append("NULL::text as dynasty_relationship")
        select_parts.append("now() as created_at")
        select_parts.append("now() as updated_at")
        if 'created_at' in columns:
            select_parts.append("created_at as source_created_at")
        else:
            select_parts.append("NULL::timestamp as source_created_at")
        
        query = f"SELECT {', '.join(select_parts)} FROM infrawatch_projects WHERE contract_price > 0"
        
        rows = await conn.fetch(query)
        
        if not rows:
            print("⚠️  No Infrawatch projects found")
            return pd.DataFrame()
        
        # Convert to DataFrame preserving column names
        if rows:
            col_names = list(rows[0].keys())
            data = [list(row.values()) for row in rows]
            df = pd.DataFrame(data, columns=col_names)
        else:
            df = pd.DataFrame()
        
        print(f"✅ Exported {len(df):,} rows, {len(df.columns)} columns")
        return df
        
    except Exception as e:
        print(f"⚠️  Error exporting Infrawatch projects: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()
    finally:
        await conn.close()


def combine_dataframes(dfs: List[pd.DataFrame]) -> pd.DataFrame:
    """Combine multiple DataFrames, aligning columns intelligently."""
    if not dfs:
        return pd.DataFrame()
    
    if len(dfs) == 1:
        return dfs[0]
    
    print("\n🔗 Combining DataFrames...")
    
    # Get all unique columns
    all_columns = set()
    for df in dfs:
        all_columns.update(df.columns)
    
    print(f"   Total unique columns: {len(all_columns)}")
    
    # Align all DataFrames to have the same columns (fill missing with None)
    aligned_dfs = []
    for i, df in enumerate(dfs):
        missing_cols = all_columns - set(df.columns)
        if missing_cols:
            for col in missing_cols:
                df[col] = None
        # Reorder columns consistently
        df = df[sorted(all_columns)]
        aligned_dfs.append(df)
    
    # Concatenate
    combined = pd.concat(aligned_dfs, ignore_index=True)
    
    # Fix type issues for Parquet compatibility
    print("   Fixing column types for Parquet compatibility...")
    for col in combined.columns:
        if combined[col].dtype == 'object':
            # Try to convert numeric columns
            try:
                # Try converting to numeric, keeping non-numeric as string
                numeric_vals = pd.to_numeric(combined[col], errors='coerce')
                if numeric_vals.notna().sum() > len(combined) * 0.5:  # If >50% numeric
                    combined[col] = numeric_vals
                else:
                    # Keep as string
                    combined[col] = combined[col].astype(str).replace('None', None)
            except:
                # Keep as string
                combined[col] = combined[col].astype(str).replace('None', None)
    
    print(f"✅ Combined {len(combined):,} rows, {len(combined.columns)} columns")
    return combined


async def main():
    """Main export function."""
    print("🚀 Starting Parquet export with intelligent column merging...")
    print(f"📊 Output directory: {OUTPUT_DIR}")
    print(f"🐘 PostgreSQL: {PG_CONFIG['host']}:{PG_CONFIG['port']}\n")
    
    # Export from each source
    flood_df = await export_flood_projects()
    dime_df = await export_dime_projects()
    philgeps_df = await export_philgeps_contracts()
    infrawatch_df = await export_infrawatch_projects()
    
    # Save individual files
    if not flood_df.empty:
        flood_path = OUTPUT_DIR / 'flood_projects.parquet'
        flood_df.to_parquet(flood_path, compression='snappy', engine='pyarrow', index=False)
        size_mb = flood_path.stat().st_size / 1024 / 1024
        print(f"💾 Saved: {flood_path} ({size_mb:.2f} MB)")
    
    if not dime_df.empty:
        dime_path = OUTPUT_DIR / 'dime_projects.parquet'
        dime_df.to_parquet(dime_path, compression='snappy', engine='pyarrow', index=False)
        size_mb = dime_path.stat().st_size / 1024 / 1024
        print(f"💾 Saved: {dime_path} ({size_mb:.2f} MB)")
    
    if not philgeps_df.empty:
        philgeps_path = OUTPUT_DIR / 'philgeps_contracts.parquet'
        philgeps_df.to_parquet(philgeps_path, compression='snappy', engine='pyarrow', index=False)
        size_mb = philgeps_path.stat().st_size / 1024 / 1024
        print(f"💾 Saved: {philgeps_path} ({size_mb:.2f} MB)")
    
    if not infrawatch_df.empty:
        infrawatch_path = OUTPUT_DIR / 'infrawatch_projects.parquet'
        infrawatch_df.to_parquet(infrawatch_path, compression='snappy', engine='pyarrow', index=False)
        size_mb = infrawatch_path.stat().st_size / 1024 / 1024
        print(f"💾 Saved: {infrawatch_path} ({size_mb:.2f} MB)")
    
    # Combine into integrated file
    all_dfs = [df for df in [flood_df, dime_df, philgeps_df, infrawatch_df] if not df.empty]
    if all_dfs:
        combined_df = combine_dataframes(all_dfs)
        
        if not combined_df.empty:
            # Save combined file
            integrated_path = OUTPUT_DIR / 'integrated_projects.parquet'
            combined_df.to_parquet(integrated_path, compression='snappy', engine='pyarrow', index=False)
            size_mb = integrated_path.stat().st_size / 1024 / 1024
            print(f"\n💾 Saved: {integrated_path} ({size_mb:.2f} MB)")
            
            # Show column summary
            print(f"\n📊 Column Summary:")
            unified_cols = [str(c) for c in combined_df.columns if not str(c).startswith(('flood_', 'dime_', 'philgeps_'))]
            source_cols = [str(c) for c in combined_df.columns if str(c).startswith(('flood_', 'dime_', 'philgeps_'))]
            print(f"   Unified columns: {len(unified_cols)}")
            print(f"   Source-specific columns: {len(source_cols)}")
            print(f"   Total columns: {len(combined_df.columns)}")
            print(f"\n   Sample unified columns: {', '.join(unified_cols[:10])}")
            if source_cols:
                print(f"   Sample source columns: {', '.join(source_cols[:10])}")
            
            # Create year-partitioned files
            print(f"\n📅 Creating year-partitioned files...")
            if 'project_year' in combined_df.columns:
                for year in range(2020, 2026):
                    year_df = combined_df[combined_df['project_year'] == year]
                    if not year_df.empty:
                        year_path = OUTPUT_DIR / f'integrated_projects_{year}.parquet'
                        year_df.to_parquet(year_path, compression='snappy', engine='pyarrow', index=False)
                        year_size_mb = year_path.stat().st_size / 1024 / 1024
                        print(f"   {year}: {len(year_df):,} rows, {year_size_mb:.2f} MB")
    
    print("\n✅ Export complete!")
    print("\n💡 Query Parquet files directly with DuckDB:")
    print("   import duckdb")
    print("   conn = duckdb.connect()")
    print("   result = conn.execute(\"SELECT * FROM 'data/parquet/integrated_projects.parquet' LIMIT 10\").fetchall()")


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
Generate JSON cache files for budget data to avoid direct PostgreSQL queries.
This script generates:
1. Budget columns metadata for all years (2020-2026)
2. Budget duplicates data for all years (if available)
"""

import asyncio
import asyncpg
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, List, Any

# Load environment variables
load_dotenv()

# Output directory
OUTPUT_DIR = Path(__file__).parent.parent / "static" / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Years to process
YEARS = ["2020", "2021", "2022", "2023", "2024", "2025", "2026"]


async def get_db_connection():
    """Get PostgreSQL connection for NEP database"""
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_NEP', 'nep')
        )
        return conn
    except Exception as e:
        print(f"❌ Error connecting to database: {e}")
        return None


async def generate_budget_columns_cache(year: str, conn) -> Dict[str, Any]:
    """Generate columns metadata cache for a specific year"""
    try:
        table_name = f"budget_{year}"
        columns_view = f"{table_name}_columns_metadata"
        
        # Check if table exists
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = $1
            )
        """, table_name)
        
        if not table_exists:
            print(f"  ⚠️  Table {table_name} does not exist, skipping columns cache")
            return {"success": False, "error": f"Table {table_name} not found"}
        
        # Check if metadata view exists
        view_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.views 
                WHERE table_schema = 'public' 
                AND table_name = $1
            )
        """, columns_view)
        
        if view_exists:
            # Use metadata view
            rows = await conn.fetch(f"""
                SELECT column_name, data_type, is_nullable
                FROM {columns_view}
                ORDER BY ordinal_position
            """)
        else:
            # Fallback: query information_schema directly
            rows = await conn.fetch("""
                SELECT column_name, data_type, is_nullable, ordinal_position
                FROM information_schema.columns 
                WHERE table_name = $1 AND table_schema = 'public'
                AND column_name NOT IN ('id', 'source_file', 'created_at', 'updated_at')
                ORDER BY ordinal_position
            """, table_name)
        
        # Column mapping for descriptions
        column_descriptions = {
            "sorder": "Sort Order - Sequential numbering of budget items",
            "department": "Department Code - Government department identifier",
            "uacs_dpt_dsc": "Department Description - Full name of the government department",
            "agency": "Agency Code - Specific agency within the department",
            "uacs_agy_dsc": "Agency Description - Full name of the government agency",
            "uacs_func_dsc": "Function Description - Budget function classification",
            "uacs_obj_dsc": "Object Description - Budget object classification",
            "uacs_prog_dsc": "Program Description - Specific program name",
            "uacs_proj_dsc": "Project Description - Specific project name",
            "uacs_act_dsc": "Activity Description - Specific activity name",
            "uacs_spec_dsc": "Special Purpose Description - Special purpose classification",
            "uacs_loc_dsc": "Location Description - Geographic location",
            "uacs_reg_dsc": "Region Description - Administrative region",
            "uacs_prov_dsc": "Province Description - Province name",
            "uacs_city_dsc": "City Description - City or municipality name",
            "uacs_brgy_dsc": "Barangay Description - Barangay (village) name",
            "uacs_reg_id": "Region ID - Philippine administrative region (1-15)",
            "uacs_operdiv_id": "Division ID - Administrative division identifier",
            "uacs_div_dsc": "Division Description - Administrative division name",
            "fundcd": "Fund Code - Budget fund classification code",
            "operunit": "Operation Unit Code - Specific operation unit identifier",
            "uacs_oper_dsc": "Operation Unit Description - Specific operation unit name",
            "uacs_exp_cd": "Expense Code - Budget expense classification code",
            "amt": "Amount - Budget allocation amount in Philippine Peso",
            "year": "Fiscal Year - Budget year",
            "dsc": "Description - Budget item description",
            "type": "Budget Type - Type of budget allocation",
            "status": "Status - Budget item status"
        }
        
        columns = []
        for row in rows:
            col_name = row['column_name']
            col_type = row['data_type']
            
            # Determine display type
            display_type = "text"
            if col_type in ['integer', 'bigint']:
                display_type = "number"
            elif col_type in ['numeric', 'decimal']:
                display_type = "currency"
            elif col_type in ['date', 'timestamp']:
                display_type = "date"
            elif 'code' in col_name.lower() or col_name.lower() in ['sorder', 'department', 'agency']:
                display_type = "code"
            
            columns.append({
                "name": col_name,
                "description": column_descriptions.get(col_name, f"Budget data field: {col_name}"),
                "type": display_type,
                "significance": f"Budget data field from {year} GAA documents"
            })
        
        result = {
            "success": True,
            "columns": columns,
            "count": len(columns)
        }
        
        print(f"  ✅ Generated columns cache: {len(columns)} columns")
        return result
        
    except Exception as e:
        print(f"  ❌ Error generating columns cache for {year}: {e}")
        return {"success": False, "error": str(e)}


async def generate_budget_duplicates_cache(year: str, conn, limit: int = 1000) -> Dict[str, Any]:
    """Generate duplicates cache for a specific year"""
    try:
        table_name = f"budget_{year}"
        view_name = f"{table_name}_potential_duplicates"
        
        # Check if table exists
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = $1
            )
        """, table_name)
        
        if not table_exists:
            print(f"  ⚠️  Table {table_name} does not exist, skipping duplicates cache")
            return {"success": False, "error": f"Table {table_name} not found"}
        
        # Check if view exists
        view_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.views 
                WHERE table_schema = 'public' 
                AND table_name = $1
            )
        """, view_name)
        
        if view_exists:
            # Use view
            duplicates_query = f"""
            SELECT 
                dsc, amt, agency, department, fundcd, uacs_exp_cd, operunit, uacs_operdiv_id, uacs_reg_id,
                COUNT(*) as duplicate_count
            FROM {view_name}
            GROUP BY dsc, amt, agency, department, fundcd, uacs_exp_cd, operunit, uacs_operdiv_id, uacs_reg_id
            ORDER BY duplicate_count DESC
            LIMIT {limit}
            """
            rows = await conn.fetch(duplicates_query)
        else:
            # Fallback: use duplicate detection query
            duplicates_query = f"""
            WITH duplicate_groups AS (
                SELECT 
                    dsc, amt, agency, department, fundcd, uacs_exp_cd, operunit, uacs_operdiv_id, uacs_reg_id,
                    COUNT(*) as duplicate_count
                FROM {table_name}
                GROUP BY dsc, amt, agency, department, fundcd, uacs_exp_cd, operunit, uacs_operdiv_id, uacs_reg_id
                HAVING COUNT(*) > 1
            )
            SELECT 
                dsc, amt, agency, department, fundcd, uacs_exp_cd, operunit, uacs_operdiv_id, uacs_reg_id,
                duplicate_count
            FROM duplicate_groups
            ORDER BY duplicate_count DESC
            LIMIT {limit}
            """
            rows = await conn.fetch(duplicates_query)
        
        duplicates = []
        for row in rows:
            duplicates.append({
                "description": row.get('dsc', ''),
                "amount": float(row.get('amt', 0)) if row.get('amt') else 0,
                "agency": row.get('agency', ''),
                "department": row.get('department', ''),
                "fundcd": row.get('fundcd', ''),
                "duplicate_count": row.get('duplicate_count', 0)
            })
        
        result = {
            "success": True,
            "duplicates": duplicates,
            "count": len(duplicates),
            "year": year
        }
        
        print(f"  ✅ Generated duplicates cache: {len(duplicates)} duplicates")
        return result
        
    except Exception as e:
        print(f"  ❌ Error generating duplicates cache for {year}: {e}")
        return {"success": False, "error": str(e)}


async def main():
    """Main function to generate all budget caches"""
    print("🚀 Generating budget cache files...")
    print(f"📁 Output directory: {OUTPUT_DIR}")
    
    conn = await get_db_connection()
    if not conn:
        print("❌ Failed to connect to database. Exiting.")
        return
    
    try:
        # Generate columns cache for all years
        print("\n📊 Generating budget columns cache...")
        columns_cache = {}
        
        for year in YEARS:
            print(f"  Processing {year}...")
            columns_data = await generate_budget_columns_cache(year, conn)
            if columns_data.get("success"):
                columns_cache[year] = columns_data
        
        # Save columns cache
        columns_file = OUTPUT_DIR / "budget_columns_cache.json"
        with open(columns_file, 'w') as f:
            json.dump(columns_cache, f, indent=2)
        print(f"\n✅ Saved columns cache to {columns_file}")
        
        # Generate duplicates cache for all years
        print("\n🔍 Generating budget duplicates cache...")
        duplicates_cache = {}
        
        for year in YEARS:
            print(f"  Processing {year}...")
            duplicates_data = await generate_budget_duplicates_cache(year, conn)
            if duplicates_data.get("success"):
                duplicates_cache[year] = duplicates_data
        
        # Save duplicates cache
        duplicates_file = OUTPUT_DIR / "budget_duplicates_cache.json"
        with open(duplicates_file, 'w') as f:
            json.dump(duplicates_cache, f, indent=2)
        print(f"\n✅ Saved duplicates cache to {duplicates_file}")
        
        print("\n✅ All budget cache files generated successfully!")
        print(f"   - Columns: {len(columns_cache)} years")
        print(f"   - Duplicates: {len(duplicates_cache)} years")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())


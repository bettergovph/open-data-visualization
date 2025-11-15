#!/usr/bin/env python3
"""
Migrate integrated data from PostgreSQL to DuckDB columnar database.

DuckDB is an embedded columnar database perfect for analytics.
- No separate server needed
- Reads PostgreSQL directly
- Reads Parquet files natively
- Fast analytical queries
"""

import asyncio
import asyncpg
import os
import sys
from pathlib import Path

# DuckDB (install: pip install duckdb)
try:
    import duckdb
except ImportError:
    print("❌ duckdb not installed. Install with: pip install duckdb")
    sys.exit(1)

# PostgreSQL connection config
PG_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'user': os.getenv('POSTGRES_USER', 'budget_admin'),
    'password': os.getenv('POSTGRES_PASSWORD', 'wuQ5gBYCKkZiOGb61chLcByMu'),
}

# DuckDB database path
DUCKDB_PATH = os.getenv('DUCKDB_PATH', 'database/integrated.duckdb')


async def get_pg_connection(db_name: str):
    """Get PostgreSQL connection for a specific database."""
    return await asyncpg.connect(
        host=PG_CONFIG['host'],
        port=PG_CONFIG['port'],
        user=PG_CONFIG['user'],
        password=PG_CONFIG['password'],
        database=db_name
    )


def create_duckdb_schema(conn: duckdb.DuckDBPyConnection):
    """Create DuckDB schema for integrated data."""
    print("📊 Creating DuckDB schema...")
    
    # Create integrated_projects table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS integrated_projects (
            project_id VARCHAR,
            source VARCHAR,
            global_id VARCHAR,
            contract_id VARCHAR,
            project_name VARCHAR,
            project_description VARCHAR,
            project_type VARCHAR,
            work_type VARCHAR,
            amount DECIMAL(20, 2),
            contract_amount DECIMAL(20, 2),
            budget_amount DECIMAL(20, 2),
            region VARCHAR,
            province VARCHAR,
            municipality VARCHAR,
            city VARCHAR,
            barangay VARCHAR,
            latitude DOUBLE,
            longitude DOUBLE,
            legislative_district VARCHAR,
            project_year INTEGER,
            contract_year INTEGER,
            award_date DATE,
            start_date DATE,
            end_date DATE,
            contractor_name VARCHAR,
            contractor_sec_number VARCHAR,
            contractor_status VARCHAR,
            contractor_role VARCHAR,
            is_joint_venture BOOLEAN,
            organization_name VARCHAR,
            department VARCHAR,
            district_engineering_office VARCHAR,
            congressman_name VARCHAR,
            dynasty_member_id INTEGER,
            dynasty_relationship VARCHAR,
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            source_created_at TIMESTAMP
        )
    """)
    
    # Create indexes (DuckDB automatically creates indexes on primary keys)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON integrated_projects(source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_province ON integrated_projects(province)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contractor ON integrated_projects(contractor_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_year ON integrated_projects(project_year)")
    
    print("✅ DuckDB schema created")


async def migrate_flood_projects(duckdb_conn: duckdb.DuckDBPyConnection):
    """Migrate flood control projects from flood database."""
    print("🌊 Migrating flood control projects...")
    
    pg_conn = await get_pg_connection('flood')
    
    try:
        # Query flood projects
        # Note: Adjust table/column names based on your actual schema
        rows = await pg_conn.fetch("""
            SELECT 
                global_id::text as project_id,
                'SSP' as source,
                global_id::text as global_id,
                contract_id::text as contract_id,
                project_description as project_name,
                project_description,
                type_of_work as project_type,
                type_of_work as work_type,
                contract_cost as amount,
                contract_cost as contract_amount,
                NULL::numeric as budget_amount,
                region,
                province,
                municipality,
                NULL::text as city,
                NULL::text as barangay,
                latitude,
                longitude,
                legislative_district,
                infra_year::integer as project_year,
                infra_year::integer as contract_year,
                NULL::date as award_date,
                NULL::date as start_date,
                NULL::date as end_date,
                contractor as contractor_name,
                NULL::text as contractor_sec_number,
                NULL::text as contractor_status,
                'main' as contractor_role,
                false as is_joint_venture,
                district_engineering_office as organization_name,
                'DPWH' as department,
                district_engineering_office,
                NULL::text as congressman_name,
                0::integer as dynasty_member_id,
                NULL::text as dynasty_relationship,
                now() as created_at,
                now() as updated_at,
                NULL::timestamp as source_created_at
            FROM flood_projects
            WHERE contract_cost > 0
            LIMIT 100000
        """)
        
        if not rows:
            print("⚠️  No flood projects found (table might not exist or have different name)")
            return
        
        # Convert to list of tuples for DuckDB insert
        data = [tuple(row.values()) for row in rows]
        
        # Insert into DuckDB
        duckdb_conn.executemany("""
            INSERT INTO integrated_projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, data)
        
        print(f"✅ Migrated {len(data)} flood projects")
        
    except Exception as e:
        print(f"⚠️  Error migrating flood projects: {e}")
        print("   (This is OK if the table doesn't exist or has different schema)")
    finally:
        await pg_conn.close()


async def migrate_dime_projects(duckdb_conn: duckdb.DuckDBPyConnection):
    """Migrate DIME projects from dime database."""
    print("📊 Migrating DIME projects...")
    
    pg_conn = await get_pg_connection('dime')
    
    try:
        # Query DIME projects
        rows = await pg_conn.fetch("""
            SELECT 
                project_id::text,
                'DIME' as source,
                NULL::text as global_id,
                contract_id::text,
                project_name,
                project_description,
                project_type,
                work_type,
                total_cost as amount,
                total_cost as contract_amount,
                NULL::numeric as budget_amount,
                region,
                province,
                municipality,
                city,
                barangay,
                latitude,
                longitude,
                legislative_district,
                project_year::integer,
                project_year::integer as contract_year,
                award_date,
                start_date,
                end_date,
                contractor_name,
                NULL::text as contractor_sec_number,
                NULL::text as contractor_status,
                'main' as contractor_role,
                false as is_joint_venture,
                implementing_agency as organization_name,
                department,
                NULL::text as district_engineering_office,
                NULL::text as congressman_name,
                0::integer as dynasty_member_id,
                NULL::text as dynasty_relationship,
                now() as created_at,
                now() as updated_at,
                created_at as source_created_at
            FROM dime_projects
            WHERE total_cost > 0
            LIMIT 100000
        """)
        
        if not rows:
            print("⚠️  No DIME projects found")
            return
        
        data = [tuple(row.values()) for row in rows]
        
        duckdb_conn.executemany("""
            INSERT INTO integrated_projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, data)
        
        print(f"✅ Migrated {len(data)} DIME projects")
        
    except Exception as e:
        print(f"⚠️  Error migrating DIME projects: {e}")
    finally:
        await pg_conn.close()


async def migrate_philgeps_contracts(duckdb_conn: duckdb.DuckDBPyConnection):
    """Migrate PhilGEPS contracts from philgeps database."""
    print("📋 Migrating PhilGEPS contracts...")
    
    pg_conn = await get_pg_connection('philgeps')
    
    try:
        # Query PhilGEPS contracts
        rows = await pg_conn.fetch("""
            SELECT 
                reference_id as project_id,
                'PhilGEPS' as source,
                meilisearch_id as global_id,
                contract_no as contract_id,
                award_title as project_name,
                award_title as project_description,
                business_category as project_type,
                business_category as work_type,
                contract_amount as amount,
                contract_amount as contract_amount,
                NULL::numeric as budget_amount,
                NULL::text as region,
                area_of_delivery as province,
                NULL::text as municipality,
                NULL::text as city,
                NULL::text as barangay,
                NULL::double precision as latitude,
                NULL::double precision as longitude,
                NULL::text as legislative_district,
                EXTRACT(YEAR FROM award_date)::integer as project_year,
                EXTRACT(YEAR FROM award_date)::integer as contract_year,
                award_date,
                NULL::date as start_date,
                NULL::date as end_date,
                awardee_name as contractor_name,
                NULL::text as contractor_sec_number,
                award_status as contractor_status,
                'main' as contractor_role,
                false as is_joint_venture,
                organization_name,
                NULL::text as department,
                NULL::text as district_engineering_office,
                NULL::text as congressman_name,
                0::integer as dynasty_member_id,
                NULL::text as dynasty_relationship,
                now() as created_at,
                now() as updated_at,
                created_at as source_created_at
            FROM contracts
            WHERE contract_amount > 0
            LIMIT 100000
        """)
        
        if not rows:
            print("⚠️  No PhilGEPS contracts found")
            return
        
        data = [tuple(row.values()) for row in rows]
        
        duckdb_conn.executemany("""
            INSERT INTO integrated_projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, data)
        
        print(f"✅ Migrated {len(data)} PhilGEPS contracts")
        
    except Exception as e:
        print(f"⚠️  Error migrating PhilGEPS contracts: {e}")
    finally:
        await pg_conn.close()


async def main():
    """Main migration function."""
    print("🚀 Starting DuckDB migration...")
    print(f"📊 DuckDB: {DUCKDB_PATH}")
    print(f"🐘 PostgreSQL: {PG_CONFIG['host']}:{PG_CONFIG['port']}\n")
    
    # Ensure database directory exists
    Path(DUCKDB_PATH).parent.mkdir(parents=True, exist_ok=True)
    
    # Connect to DuckDB
    duckdb_conn = duckdb.connect(DUCKDB_PATH)
    
    try:
        # Create schema
        create_duckdb_schema(duckdb_conn)
        
        # Migrate data from each source
        await migrate_flood_projects(duckdb_conn)
        await migrate_dime_projects(duckdb_conn)
        await migrate_philgeps_contracts(duckdb_conn)
        
        # Get final count
        result = duckdb_conn.execute("SELECT count() FROM integrated_projects").fetchone()
        total_count = result[0] if result else 0
        
        # Get statistics
        stats = duckdb_conn.execute("""
            SELECT 
                source,
                count() as count,
                sum(amount) as total_amount
            FROM integrated_projects
            GROUP BY source
            ORDER BY source
        """).fetchall()
        
        print(f"\n✅ Migration complete!")
        print(f"📊 Total records in DuckDB: {total_count:,}")
        print(f"\n📈 Breakdown by source:")
        for source, count, total in stats:
            print(f"   {source}: {count:,} projects, ₱{total:,.2f}")
        
        # Example query
        print(f"\n💡 Example query:")
        print(f"   duckdb {DUCKDB_PATH} -c \"SELECT * FROM integrated_projects LIMIT 5\"")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        duckdb_conn.close()


if __name__ == "__main__":
    asyncio.run(main())

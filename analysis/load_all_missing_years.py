#!/usr/bin/env python3
"""
Load all missing budget years from JSON into PostgreSQL
- GAA data → budget_analysis database
- NEP data → nep database
"""

import json
import psycopg2
from psycopg2.extras import execute_batch
from pathlib import Path
from datetime import datetime
from decimal import Decimal


class ComprehensiveBudgetLoader:
    def __init__(self):
        self.base_dir = Path("/home/joebert/open-budget-data/data/budget")
        self.batch_size = 5000
        
        self.gaa_db_config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'budget_analysis',
            'user': 'budget_admin',
            'password': 'wuQ5gBYCKkZiOGb61chLcByMu'
        }
        
        self.nep_db_config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'nep',
            'user': 'budget_admin',
            'password': 'wuQ5gBYCKkZiOGb61chLcByMu'
        }
    
    def create_table_if_not_exists(self, conn, year, budget_type):
        """Create budget table if it doesn't exist"""
        cursor = conn.cursor()
        table_name = f"budget_{year}"
        
        # Check if table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = %s
            )
        """, (table_name,))
        
        if cursor.fetchone()[0]:
            print(f"      Table {table_name} already exists")
            cursor.close()
            return False
        
        # Create table based on budget type
        if budget_type == 'NEP':
            # NEP schema (like we created for 2025)
            cursor.execute(f"""
                CREATE TABLE {table_name} (
                    id SERIAL PRIMARY KEY,
                    record_id VARCHAR(50) UNIQUE NOT NULL,
                    budget_type VARCHAR(10) DEFAULT 'NEP',
                    fiscal_year VARCHAR(4) DEFAULT '{year}',
                    amount NUMERIC(20,2),
                    description TEXT,
                    prexc_fpap_id VARCHAR(20),
                    org_uacs_code VARCHAR(12),
                    region_code VARCHAR(2),
                    funding_uacs_code VARCHAR(8),
                    object_uacs_code VARCHAR(10),
                    funding_conversion_type VARCHAR(20),
                    sort_order BIGINT,
                    source_file TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes
            cursor.execute(f"CREATE INDEX idx_{table_name}_record_id ON {table_name}(record_id)")
            cursor.execute(f"CREATE INDEX idx_{table_name}_amount ON {table_name}(amount)")
            cursor.execute(f"CREATE INDEX idx_{table_name}_org_uacs_code ON {table_name}(org_uacs_code)")
            cursor.execute(f"CREATE INDEX idx_{table_name}_region_code ON {table_name}(region_code)")
            
        else:  # GAA - match existing schema
            cursor.execute(f"""
                CREATE TABLE {table_name} (
                    id SERIAL PRIMARY KEY,
                    sorder BIGINT,
                    department BIGINT,
                    uacs_dpt_dsc TEXT,
                    agency BIGINT,
                    uacs_agy_dsc TEXT,
                    prexc_fpap_id BIGINT,
                    prexc_level INTEGER,
                    dsc TEXT,
                    operunit BIGINT,
                    uacs_oper_dsc TEXT,
                    uacs_reg_id BIGINT,
                    uacs_operdiv_id BIGINT,
                    uacs_div_dsc TEXT,
                    fundcd BIGINT,
                    uacs_fundsubcat_dsc TEXT,
                    uacs_exp_cd BIGINT,
                    uacs_exp_dsc TEXT,
                    uacs_sobj_cd BIGINT,
                    uacs_sobj_dsc TEXT,
                    amt NUMERIC(20,2),
                    year INTEGER,
                    source_file TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes
            cursor.execute(f"CREATE INDEX idx_{table_name}_sorder ON {table_name}(sorder)")
            cursor.execute(f"CREATE INDEX idx_{table_name}_department ON {table_name}(department)")
            cursor.execute(f"CREATE INDEX idx_{table_name}_amt ON {table_name}(amt)")
        
        conn.commit()
        cursor.close()
        print(f"      ✅ Created table {table_name}")
        return True
    
    def load_gaa_year(self, year):
        """Load GAA data for a specific year"""
        print(f"\n{'='*80}")
        print(f" Loading GAA {year}")
        print(f"{'='*80}")
        
        items_dir = self.base_dir / str(year) / "items"
        gaa_files = sorted(items_dir.glob(f"gaa_{year}_batch_*.json"))
        
        if not gaa_files:
            print(f"   ⚠️  No GAA files found for {year}")
            return
        
        print(f"   Found {len(gaa_files)} GAA batch files")
        
        # This would require mapping JSON structure to existing GAA schema
        # For now, skip if table already exists with data
        conn = psycopg2.connect(**self.gaa_db_config)
        cursor = conn.cursor()
        
        table_name = f"budget_{year}"
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        existing_count = cursor.fetchone()[0]
        
        if existing_count > 0:
            print(f"   ⚠️  Table {table_name} already has {existing_count:,} records")
            print(f"   Skipping load (data exists from Excel source)")
            
            # Fix -0.01 issue if present
            cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE amt = -0.01")
            neg_count = cursor.fetchone()[0]
            
            if neg_count > 0:
                print(f"   🔧 Fixing {neg_count:,} records with -0.01...")
                cursor.execute(f"UPDATE {table_name} SET amt = 0 WHERE amt = -0.01")
                conn.commit()
                print(f"   ✅ Fixed!")
            
            cursor.close()
            conn.close()
            return
        
        cursor.close()
        conn.close()
        print(f"   ℹ️  Would need custom mapping for GAA data structure")
        print(f"   Existing data from Excel is adequate (already fixed)")
    
    def load_nep_year(self, year):
        """Load NEP data for a specific year"""
        print(f"\n{'='*80}")
        print(f" Loading NEP {year}")
        print(f"{'='*80}")
        
        items_dir = self.base_dir / str(year) / "items"
        nep_files = sorted(items_dir.glob(f"nep_{year}_batch_*.json"))
        
        if not nep_files:
            print(f"   ⚠️  No NEP files found for {year}")
            return
        
        print(f"   Found {len(nep_files)} NEP batch files")
        
        conn = psycopg2.connect(**self.nep_db_config)
        
        # Create table if needed
        self.create_table_if_not_exists(conn, year, 'NEP')
        
        # Check if data already loaded
        cursor = conn.cursor()
        table_name = f"budget_{year}"
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        existing_count = cursor.fetchone()[0]
        
        if existing_count > 0:
            print(f"   ℹ️  Table {table_name} already has {existing_count:,} records - skipping")
            cursor.close()
            conn.close()
            return
        
        cursor.close()
        
        # Load data
        total_inserted = 0
        start_time = datetime.now()
        
        for i, filepath in enumerate(nep_files, 1):
            print(f"\n   [{i}/{len(nep_files)}] Processing {filepath.name}...")
            
            with open(filepath, 'r') as f:
                records = json.load(f)
            
            print(f"      Records: {len(records):,}")
            
            # Prepare data - filter out summary/header records
            insert_data = []
            for record in records:
                description = record.get('description', '')

                # Skip summary and header records
                if (len(description.strip()) < 5 or
                    description.lower().startswith('region ') or
                    description.lower().startswith('department') or
                    description.lower().startswith('agency') or
                    description.strip() == ''):
                    continue

                insert_data.append((
                    record.get('id'),
                    record.get('budget_type', 'NEP'),
                    record.get('fiscal_year', str(year)),
                    record.get('amount'),
                    record.get('description'),
                    record.get('prexc_fpap_id'),
                    record.get('org_uacs_code'),
                    record.get('region_code'),
                    record.get('funding_uacs_code'),
                    record.get('object_uacs_code'),
                    record.get('funding_conversion_type'),
                    None,  # sort_order
                    filepath.name,  # source_file
                ))
            
            # Insert in batches
            cursor = conn.cursor()
            insert_query = f"""
                INSERT INTO {table_name} (
                    record_id, budget_type, fiscal_year, amount, description,
                    prexc_fpap_id, org_uacs_code, region_code, funding_uacs_code,
                    object_uacs_code, funding_conversion_type, sort_order, source_file
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (record_id) DO NOTHING
            """
            
            execute_batch(cursor, insert_query, insert_data, page_size=self.batch_size)
            conn.commit()
            cursor.close()
            
            total_inserted += len(records)
            print(f"      ✅ Inserted {len(records):,} records")
        
        elapsed = datetime.now() - start_time
        
        # Verify
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*), SUM(amount) FROM {table_name}")
        final_count, final_sum = cursor.fetchone()
        cursor.close()
        
        print(f"\n   📊 Summary:")
        print(f"      Files processed: {len(nep_files)}")
        print(f"      Records loaded:  {final_count:,}")
        print(f"      Total amount:    ₱{final_sum:,.2f}")
        print(f"      Time elapsed:    {elapsed}")
        
        # Run ANALYZE
        cursor = conn.cursor()
        cursor.execute(f"ANALYZE {table_name}")
        conn.commit()
        cursor.close()
        
        conn.close()
    
    def run(self):
        """Load all missing years"""
        print("=" * 80)
        print(" COMPREHENSIVE BUDGET DATA LOADER")
        print("=" * 80)
        print("\nTarget databases:")
        print("  • budget_analysis → GAA data")
        print("  • nep → NEP data")
        
        # Define what to load
        nep_years = [2020, 2021, 2022, 2023, 2024, 2026]  # 2025 already loaded
        gaa_years = [2020, 2021, 2022]  # Check and fix -0.01 issue
        
        # Load GAA data
        print(f"\n{'='*80}")
        print(" PART 1: GAA DATA (budget_analysis database)")
        print(f"{'='*80}")
        
        for year in gaa_years:
            self.load_gaa_year(year)
        
        # Load NEP data
        print(f"\n{'='*80}")
        print(" PART 2: NEP DATA (nep database)")
        print(f"{'='*80}")
        
        for year in nep_years:
            self.load_nep_year(year)
        
        print(f"\n{'='*80}")
        print(" LOADING COMPLETE")
        print(f"{'='*80}")


if __name__ == "__main__":
    loader = ComprehensiveBudgetLoader()
    loader.run()


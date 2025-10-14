#!/usr/bin/env python3
"""
Reload GAA 2020-2022 from JSON files
Maps JSON structure to existing database schema
"""

import json
import psycopg2
from psycopg2.extras import execute_batch
from pathlib import Path
from datetime import datetime


class GAAReloader:
    def __init__(self):
        self.base_dir = Path("/home/joebert/open-budget-data/data/budget")
        self.batch_size = 5000
        
        self.db_config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'budget_analysis',
            'user': 'budget_admin',
            'password': 'wuQ5gBYCKkZiOGb61chLcByMu'
        }
    
    def parse_org_code(self, org_uacs_code):
        """Parse 12-digit org code into components"""
        if not org_uacs_code or org_uacs_code == '000000000000':
            return None, None, None
        
        code_str = str(org_uacs_code).zfill(12)
        department = int(code_str[0:2]) if code_str[0:2] != '00' else None
        agency = int(code_str[2:5]) if code_str[2:5] != '000' else None
        operunit = int(code_str) if code_str != '000000000000' else None
        
        return department, agency, operunit
    
    def get_table_columns(self, cursor, table_name):
        """Get list of columns for a table"""
        cursor.execute(f"""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = '{table_name}' 
            AND table_schema = 'public'
            ORDER BY ordinal_position
        """)
        return [row[0] for row in cursor.fetchall()]
    
    def reload_year(self, year):
        """Reload GAA data for a specific year"""
        print(f"\n{'='*80}")
        print(f" RELOADING GAA {year} FROM JSON")
        print(f"{'='*80}")
        
        items_dir = self.base_dir / str(year) / "items"
        gaa_files = sorted(items_dir.glob(f"gaa_{year}_batch_*.json"))
        
        if not gaa_files:
            print(f"   ❌ No GAA files found for {year}")
            return
        
        print(f"   Found {len(gaa_files)} GAA batch files")
        
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()
        
        table_name = f"budget_{year}"
        
        # Get actual columns for this table
        columns = self.get_table_columns(cursor, table_name)
        has_sorder = 'sorder' in columns
        has_operdiv = 'uacs_operdiv_id' in columns and 'uacs_div_dsc' in columns
        
        print(f"   Table schema: sorder={has_sorder}, operdiv={has_operdiv}")
        
        # Get current count
        cursor.execute(f"SELECT COUNT(*), COALESCE(SUM(amt), 0) FROM {table_name}")
        old_count, old_sum = cursor.fetchone()
        print(f"   Current data: {old_count:,} records, ₱{float(old_sum):,.2f}")
        
        # Truncate table
        print(f"   🗑️  Truncating table {table_name}...")
        cursor.execute(f"TRUNCATE TABLE {table_name} RESTART IDENTITY")
        conn.commit()
        print(f"   ✅ Table cleared")
        
        # Load new data
        total_inserted = 0
        start_time = datetime.now()
        
        for i, filepath in enumerate(gaa_files, 1):
            print(f"\n   [{i}/{len(gaa_files)}] Processing {filepath.name}...")
            
            with open(filepath, 'r') as f:
                records = json.load(f)
            
            print(f"      Records: {len(records):,}")
            
            # Prepare data
            insert_data = []
            for record in records:
                org_code = record.get('org_uacs_code')
                department, agency, operunit = self.parse_org_code(org_code)
                
                # Build data tuple based on schema
                row_data = []
                if has_sorder:
                    row_data.append(None)  # sorder
                row_data.extend([
                    department,
                    None,  # uacs_dpt_dsc
                    agency,
                    None,  # uacs_agy_dsc
                    int(record.get('prexc_fpap_id')) if record.get('prexc_fpap_id') else None,
                    None,  # prexc_level
                    record.get('description'),  # dsc
                    operunit,
                    None,  # uacs_oper_dsc
                    int(record.get('region_code')) if record.get('region_code') else None,
                ])
                if has_operdiv:
                    row_data.extend([
                        None,  # uacs_operdiv_id
                        None,  # uacs_div_dsc
                    ])
                row_data.extend([
                    int(record.get('funding_uacs_code')) if record.get('funding_uacs_code') else None,
                    None,  # uacs_fundsubcat_dsc
                    int(record.get('object_uacs_code')) if record.get('object_uacs_code') else None,
                    None,  # uacs_exp_dsc
                    None,  # uacs_sobj_cd
                    None,  # uacs_sobj_dsc
                    record.get('amount'),  # amt
                    year,
                    filepath.name,  # source_file
                ])
                insert_data.append(tuple(row_data))
            
            # Build insert query based on schema
            cols = []
            if has_sorder:
                cols.append('sorder')
            cols.extend(['department', 'uacs_dpt_dsc', 'agency', 'uacs_agy_dsc',
                        'prexc_fpap_id', 'prexc_level', 'dsc', 'operunit', 'uacs_oper_dsc',
                        'uacs_reg_id'])
            if has_operdiv:
                cols.extend(['uacs_operdiv_id', 'uacs_div_dsc'])
            cols.extend(['fundcd', 'uacs_fundsubcat_dsc',
                        'uacs_exp_cd', 'uacs_exp_dsc', 'uacs_sobj_cd', 'uacs_sobj_dsc',
                        'amt', 'year', 'source_file'])
            
            placeholders = ', '.join(['%s'] * len(cols))
            cols_str = ', '.join(cols)
            
            insert_query = f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders})"
            
            execute_batch(cursor, insert_query, insert_data, page_size=self.batch_size)
            conn.commit()
            
            total_inserted += len(records)
            print(f"      ✅ Inserted {len(records):,} records")
        
        elapsed = datetime.now() - start_time
        
        # Verify
        cursor.execute(f"SELECT COUNT(*), SUM(amt) FROM {table_name}")
        new_count, new_sum = cursor.fetchone()
        
        print(f"\n   📊 Summary:")
        print(f"      Old count: {old_count:,} records, ₱{old_sum:,.2f}")
        print(f"      New count: {new_count:,} records, ₱{new_sum:,.2f}")
        print(f"      Difference: {new_count - old_count:,} records")
        print(f"      Time elapsed: {elapsed}")
        
        # Run ANALYZE
        print(f"\n   ⚙️  Running ANALYZE...")
        cursor.execute(f"ANALYZE {table_name}")
        conn.commit()
        print(f"   ✅ Complete")
        
        cursor.close()
        conn.close()
    
    def run(self):
        """Reload all GAA years"""
        print("=" * 80)
        print(" GAA DATA RELOAD FROM JSON (2020-2022)")
        print("=" * 80)
        print("\nReloading years with potentially unreliable Excel-sourced data...")
        
        for year in [2020, 2021, 2022]:
            self.reload_year(year)
        
        print(f"\n{'='*80}")
        print(" RELOAD COMPLETE")
        print(f"{'='*80}")
        
        # Final verification
        print(f"\n📊 FINAL VERIFICATION:")
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()
        
        for year in [2020, 2021, 2022]:
            cursor.execute(f"SELECT COUNT(*), SUM(amt) FROM budget_{year}")
            count, total = cursor.fetchone()
            print(f"   {year}: {count:,} records, ₱{total:,.2f}")
        
        cursor.close()
        conn.close()


if __name__ == "__main__":
    loader = GAAReloader()
    loader.run()


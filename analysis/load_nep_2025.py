#!/usr/bin/env python3
"""
Load NEP 2025 Budget Data into PostgreSQL
Processes all NEP 2025 batch files and inserts into the nep database
"""

import json
import os
from pathlib import Path
import psycopg2
from psycopg2.extras import execute_batch
from datetime import datetime


class NEPDataLoader:
    def __init__(self, db_config):
        self.db_config = db_config
        self.data_dir = Path("/home/joebert/open-budget-data/data/budget/2025/items")
        self.batch_size = 5000  # Insert 5000 records at a time
        
    def connect_db(self):
        """Connect to PostgreSQL database"""
        return psycopg2.connect(**self.db_config)
    
    def get_batch_files(self):
        """Get all NEP 2025 batch files"""
        return sorted(self.data_dir.glob("nep_2025_batch_*.json"))
    
    def load_batch_file(self, filepath, conn):
        """Load a single batch file into database"""
        print(f"\n📄 Processing: {filepath.name}")
        
        # Read JSON data
        with open(filepath, 'r') as f:
            records = json.load(f)
        
        print(f"   Records in file: {len(records):,}")
        
        # Prepare data for insertion
        insert_data = []
        for record in records:
            insert_data.append((
                record.get('id'),
                record.get('budget_type', 'NEP'),
                record.get('fiscal_year', '2025'),
                record.get('amount'),
                record.get('description'),
                record.get('prexc_fpap_id'),
                record.get('org_uacs_code'),
                record.get('region_code'),
                record.get('funding_uacs_code'),
                record.get('object_uacs_code'),
                record.get('funding_conversion_type'),
                None,  # sort_order (not in JSON)
                filepath.name,  # source_file
            ))
        
        # Insert in batches
        cursor = conn.cursor()
        
        insert_query = """
            INSERT INTO budget_2025 (
                record_id, budget_type, fiscal_year, amount, description,
                prexc_fpap_id, org_uacs_code, region_code, funding_uacs_code,
                object_uacs_code, funding_conversion_type, sort_order, source_file
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (record_id) DO NOTHING
        """
        
        inserted_count = 0
        for i in range(0, len(insert_data), self.batch_size):
            batch = insert_data[i:i + self.batch_size]
            execute_batch(cursor, insert_query, batch)
            inserted_count += len(batch)
            
            # Progress indicator
            if inserted_count % 50000 == 0:
                print(f"   ⏳ Inserted {inserted_count:,} / {len(records):,} records...")
        
        conn.commit()
        cursor.close()
        
        print(f"   ✅ Completed: {inserted_count:,} records inserted")
        
        return inserted_count
    
    def load_all_data(self):
        """Load all NEP 2025 batch files"""
        print("=" * 80)
        print(" NEP 2025 DATA LOADER")
        print("=" * 80)
        print(f"\nDatabase: {self.db_config['database']}")
        print(f"Host: {self.db_config['host']}:{self.db_config['port']}")
        print(f"Data Directory: {self.data_dir}")
        
        # Get all batch files
        batch_files = self.get_batch_files()
        print(f"\n📦 Found {len(batch_files)} batch files to process")
        
        if not batch_files:
            print("❌ No NEP batch files found!")
            return
        
        # Connect to database
        print(f"\n🔌 Connecting to database...")
        conn = self.connect_db()
        
        try:
            # Check current record count
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM budget_2025")
            initial_count = cursor.fetchone()[0]
            cursor.close()
            
            print(f"📊 Initial record count: {initial_count:,}")
            
            # Process each batch file
            total_inserted = 0
            start_time = datetime.now()
            
            for i, filepath in enumerate(batch_files, 1):
                print(f"\n[{i}/{len(batch_files)}]")
                inserted = self.load_batch_file(filepath, conn)
                total_inserted += inserted
            
            # Get final count
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM budget_2025")
            final_count = cursor.fetchone()[0]
            cursor.close()
            
            # Summary
            elapsed = datetime.now() - start_time
            print("\n" + "=" * 80)
            print(" LOADING COMPLETE")
            print("=" * 80)
            print(f"\n📊 Summary:")
            print(f"   Files processed:   {len(batch_files)}")
            print(f"   Records inserted:  {total_inserted:,}")
            print(f"   Initial count:     {initial_count:,}")
            print(f"   Final count:       {final_count:,}")
            print(f"   New records:       {final_count - initial_count:,}")
            print(f"   Time elapsed:      {elapsed}")
            print(f"   Average rate:      {total_inserted / elapsed.total_seconds():.0f} records/sec")
            
            # Verify data
            print(f"\n🔍 Verification:")
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT budget_type, COUNT(*), SUM(amount)
                FROM budget_2025
                GROUP BY budget_type
            """)
            for row in cursor.fetchall():
                print(f"   {row[0]}: {row[1]:,} records, ₱{row[2]:,.2f}")
            
            cursor.execute("""
                SELECT fiscal_year, COUNT(*), SUM(amount)
                FROM budget_2025
                GROUP BY fiscal_year
            """)
            for row in cursor.fetchall():
                print(f"   FY {row[0]}: {row[1]:,} records, ₱{row[2]:,.2f}")
            
            cursor.execute("""
                SELECT source_file, COUNT(*)
                FROM budget_2025
                GROUP BY source_file
                ORDER BY source_file
            """)
            print(f"\n📁 Records by source file:")
            for row in cursor.fetchall():
                print(f"   {row[0]}: {row[1]:,}")
            
            cursor.close()
            
            # Run ANALYZE for query optimization
            print(f"\n⚙️  Running ANALYZE for query optimization...")
            cursor = conn.cursor()
            cursor.execute("ANALYZE budget_2025")
            conn.commit()
            cursor.close()
            print(f"   ✅ ANALYZE complete")
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            conn.rollback()
        finally:
            conn.close()
            print(f"\n🔌 Database connection closed")
        
        print("\n" + "=" * 80)


def main():
    """Main execution"""
    db_config = {
        'host': 'localhost',
        'port': 5432,
        'database': 'nep',
        'user': 'budget_admin',
        'password': 'wuQ5gBYCKkZiOGb61chLcByMu'
    }
    
    loader = NEPDataLoader(db_config)
    loader.load_all_data()


if __name__ == "__main__":
    main()


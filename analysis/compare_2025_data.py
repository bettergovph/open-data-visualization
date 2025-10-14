#!/usr/bin/env python3
"""
Compare 2025 Budget Data: File System vs PostgreSQL Database
Provides detailed analysis of data coverage and identifies gaps
"""

import json
import os
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
from collections import defaultdict
from decimal import Decimal


class BudgetDataComparator:
    def __init__(self, db_config):
        self.db_config = db_config
        self.data_dir = Path("/home/joebert/open-budget-data/data/budget/2025/items")
        self.results = {}
        
    def connect_db(self):
        """Connect to PostgreSQL database"""
        return psycopg2.connect(**self.db_config)
    
    def count_json_records(self, file_pattern):
        """Count total records in JSON batch files"""
        files = sorted(self.data_dir.glob(file_pattern))
        total = 0
        details = []
        
        for filepath in files:
            with open(filepath, 'r') as f:
                data = json.load(f)
                count = len(data)
                total += count
                details.append({
                    'file': filepath.name,
                    'count': count
                })
        
        return total, details
    
    def analyze_json_sample(self, file_pattern, sample_size=5):
        """Get sample records from JSON files"""
        files = sorted(self.data_dir.glob(file_pattern))
        samples = []
        
        if files:
            with open(files[0], 'r') as f:
                data = json.load(f)
                samples = data[:sample_size]
        
        return samples
    
    def get_db_stats(self):
        """Get comprehensive database statistics"""
        conn = self.connect_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        stats = {}
        
        # Total count
        cursor.execute("SELECT COUNT(*) as total FROM budget_2025")
        stats['total_records'] = cursor.fetchone()['total']
        
        # By source file
        cursor.execute("""
            SELECT source_file, COUNT(*) as count 
            FROM budget_2025 
            GROUP BY source_file
        """)
        stats['by_source'] = cursor.fetchall()
        
        # Total amount
        cursor.execute("SELECT SUM(amt) as total_amount FROM budget_2025")
        stats['total_amount'] = cursor.fetchone()['total_amount']
        
        # By department (top 10)
        cursor.execute("""
            SELECT department, uacs_dpt_dsc, COUNT(*) as count, SUM(amt) as total_amt
            FROM budget_2025
            WHERE department IS NOT NULL
            GROUP BY department, uacs_dpt_dsc
            ORDER BY total_amt DESC
            LIMIT 10
        """)
        stats['top_departments'] = cursor.fetchall()
        
        # By agency (top 10)
        cursor.execute("""
            SELECT agency, uacs_agy_dsc, COUNT(*) as count, SUM(amt) as total_amt
            FROM budget_2025
            WHERE agency IS NOT NULL
            GROUP BY agency, uacs_agy_dsc
            ORDER BY total_amt DESC
            LIMIT 10
        """)
        stats['top_agencies'] = cursor.fetchall()
        
        # Sample records
        cursor.execute("SELECT * FROM budget_2025 LIMIT 3")
        stats['sample_records'] = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return stats
    
    def compare_data(self):
        """Perform comprehensive comparison"""
        print("=" * 80)
        print(" 2025 BUDGET DATA COMPARISON: File System vs PostgreSQL")
        print("=" * 80)
        
        # 1. File System Analysis
        print("\n" + "=" * 80)
        print(" FILE SYSTEM DATA (~/open-budget-data)")
        print("=" * 80)
        
        # Count NEP records
        nep_total, nep_details = self.count_json_records("nep_2025_*.json")
        print(f"\n📊 NEP 2025 Records")
        print(f"   Total: {nep_total:,}")
        for detail in nep_details:
            print(f"   - {detail['file']}: {detail['count']:,}")
        
        # Count GAA records
        gaa_total, gaa_details = self.count_json_records("gaa_2025_*.json")
        print(f"\n📊 GAA 2025 Records")
        print(f"   Total: {gaa_total:,}")
        for detail in gaa_details:
            print(f"   - {detail['file']}: {detail['count']:,}")
        
        # Total from file system
        fs_total = nep_total + gaa_total
        print(f"\n✅ TOTAL FILE SYSTEM RECORDS: {fs_total:,}")
        print(f"   - NEP: {nep_total:,} ({nep_total/fs_total*100:.1f}%)")
        print(f"   - GAA: {gaa_total:,} ({gaa_total/fs_total*100:.1f}%)")
        
        # Sample data structure
        print("\n📋 Sample NEP Record Structure:")
        nep_samples = self.analyze_json_sample("nep_2025_*.json", 1)
        if nep_samples:
            for key, value in nep_samples[0].items():
                print(f"   - {key}: {value}")
        
        # 2. Database Analysis
        print("\n" + "=" * 80)
        print(" POSTGRESQL DATABASE")
        print("=" * 80)
        
        db_stats = self.get_db_stats()
        
        print(f"\n📊 Database Statistics")
        print(f"   Total Records: {db_stats['total_records']:,}")
        print(f"   Total Amount: ₱{db_stats['total_amount']:,.2f}")
        
        print(f"\n📁 Source Files in Database:")
        for source in db_stats['by_source']:
            print(f"   - {source['source_file']}: {source['count']:,}")
        
        print(f"\n🏛️ Top 10 Departments by Budget:")
        for i, dept in enumerate(db_stats['top_departments'], 1):
            dept_name = dept['uacs_dpt_dsc'] or 'Unknown'
            print(f"   {i:2d}. {dept_name[:50]}")
            print(f"       Records: {dept['count']:,} | Amount: ₱{dept['total_amt']:,.2f}")
        
        # 3. Comparison & Gap Analysis
        print("\n" + "=" * 80)
        print(" GAP ANALYSIS")
        print("=" * 80)
        
        gap = fs_total - db_stats['total_records']
        coverage_pct = (db_stats['total_records'] / fs_total * 100) if fs_total > 0 else 0
        
        print(f"\n📊 Coverage Summary:")
        print(f"   File System Total: {fs_total:,}")
        print(f"   Database Total:    {db_stats['total_records']:,}")
        print(f"   Missing Records:   {gap:,}")
        print(f"   Coverage:          {coverage_pct:.1f}%")
        
        print(f"\n⚠️  Missing Data Breakdown:")
        
        # Check if NEP data exists
        if db_stats['total_records'] == gaa_total:
            print(f"   ❌ ALL NEP 2025 data is MISSING ({nep_total:,} records)")
            print(f"   ✅ GAA 2025 data is complete ({gaa_total:,} records)")
        elif db_stats['total_records'] == nep_total:
            print(f"   ❌ ALL GAA 2025 data is MISSING ({gaa_total:,} records)")
            print(f"   ✅ NEP 2025 data is complete ({nep_total:,} records)")
        elif db_stats['total_records'] < fs_total:
            print(f"   ⚠️  Partial data loaded")
            print(f"   Missing: {gap:,} records ({gap/fs_total*100:.1f}%)")
        else:
            print(f"   ✅ All data appears to be loaded")
        
        # 4. Recommendations
        print("\n" + "=" * 80)
        print(" RECOMMENDATIONS")
        print("=" * 80)
        
        if gap > 0:
            print(f"\n📝 Action Items:")
            if db_stats['total_records'] == gaa_total:
                print(f"   1. Load NEP 2025 data into PostgreSQL")
                print(f"      - {len(nep_details)} batch files to process")
                print(f"      - {nep_total:,} records to insert")
                print(f"      - Estimated final total: {fs_total:,} records")
                print(f"\n   2. Verify data integrity after loading")
                print(f"      - Check for duplicates")
                print(f"      - Validate UACS codes")
                print(f"      - Compare totals with file system")
                print(f"\n   3. Update database indexes")
                print(f"      - Reindex after bulk insert")
                print(f"      - Analyze tables for query optimization")
        else:
            print(f"\n✅ Database is up-to-date with file system data")
        
        # 5. Data Quality Checks
        print("\n" + "=" * 80)
        print(" DATA QUALITY INDICATORS")
        print("=" * 80)
        
        conn = self.connect_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check for nulls in key fields
        cursor.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE department IS NULL) as null_dept,
                COUNT(*) FILTER (WHERE agency IS NULL) as null_agency,
                COUNT(*) FILTER (WHERE amt IS NULL) as null_amt,
                COUNT(*) FILTER (WHERE amt = 0) as zero_amt,
                COUNT(*) FILTER (WHERE dsc IS NULL OR dsc = '') as null_dsc
            FROM budget_2025
        """)
        quality = cursor.fetchone()
        
        print(f"\n🔍 Data Quality Metrics:")
        print(f"   Records with null department:    {quality['null_dept']:,}")
        print(f"   Records with null agency:        {quality['null_agency']:,}")
        print(f"   Records with null amount:        {quality['null_amt']:,}")
        print(f"   Records with zero amount:        {quality['zero_amt']:,}")
        print(f"   Records with missing description:{quality['null_dsc']:,}")
        
        cursor.close()
        conn.close()
        
        print("\n" + "=" * 80)
        print(" COMPARISON COMPLETE")
        print("=" * 80)
        

def main():
    """Main execution"""
    db_config = {
        'host': 'localhost',
        'port': 5432,
        'database': 'budget_analysis',
        'user': 'budget_admin',
        'password': 'wuQ5gBYCKkZiOGb61chLcByMu'
    }
    
    try:
        comparator = BudgetDataComparator(db_config)
        comparator.compare_data()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()


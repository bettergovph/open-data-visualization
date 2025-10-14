#!/usr/bin/env python3
"""
Compare GAA Data for Multiple Years (2023-2025)
Validates file system data against PostgreSQL database
"""

import json
import os
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
from collections import defaultdict


class MultiYearGAAComparator:
    def __init__(self, db_config):
        self.db_config = db_config
        self.base_dir = Path("/home/joebert/open-budget-data/data/budget")
        self.years = [2023, 2024, 2025]
        
    def connect_db(self):
        """Connect to PostgreSQL database"""
        return psycopg2.connect(**self.db_config)
    
    def count_json_records(self, year):
        """Count total records in GAA JSON batch files for a given year"""
        data_dir = self.base_dir / str(year) / "items"
        files = sorted(data_dir.glob(f"gaa_{year}_batch_*.json"))
        
        total = 0
        total_amount = 0.0
        details = []
        
        for filepath in files:
            with open(filepath, 'r') as f:
                data = json.load(f)
                count = len(data)
                amount = sum(record.get('amount', 0) for record in data)
                total += count
                total_amount += amount
                details.append({
                    'file': filepath.name,
                    'count': count,
                    'amount': amount
                })
        
        return {
            'total_records': total,
            'total_amount': total_amount,
            'files': details,
            'file_count': len(files)
        }
    
    def get_db_stats(self, year):
        """Get database statistics for a given year"""
        conn = self.connect_db()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        table_name = f"budget_{year}"
        
        # Check if table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = %s
            )
        """, (table_name,))
        
        if not cursor.fetchone()['exists']:
            cursor.close()
            conn.close()
            return None
        
        # Get stats
        cursor.execute(f"""
            SELECT 
                COUNT(*) as total_records,
                SUM(amt) as total_amount,
                COUNT(DISTINCT source_file) as source_file_count
            FROM {table_name}
        """)
        stats = cursor.fetchone()
        
        # Get by source file
        cursor.execute(f"""
            SELECT source_file, COUNT(*) as count, SUM(amt) as amount
            FROM {table_name}
            GROUP BY source_file
            ORDER BY source_file
        """)
        stats['files'] = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return stats
    
    def compare_all_years(self):
        """Compare all years"""
        print("=" * 100)
        print(" GAA DATA COMPARISON: File System vs PostgreSQL (2023-2025)")
        print("=" * 100)
        
        results = {}
        
        for year in self.years:
            print(f"\n{'=' * 100}")
            print(f" YEAR {year}")
            print(f"{'=' * 100}")
            
            # Get file system data
            print(f"\n📁 File System Data (~/open-budget-data/data/budget/{year}/items/)")
            fs_data = self.count_json_records(year)
            
            print(f"   Total Records: {fs_data['total_records']:,}")
            print(f"   Total Amount:  ₱{fs_data['total_amount']:,.2f}")
            print(f"   Batch Files:   {fs_data['file_count']}")
            print(f"\n   File Breakdown:")
            for f in fs_data['files']:
                print(f"      - {f['file']}: {f['count']:,} records, ₱{f['amount']:,.2f}")
            
            # Get database data
            print(f"\n💾 PostgreSQL Database (budget_analysis.budget_{year})")
            db_data = self.get_db_stats(year)
            
            if db_data is None:
                print(f"   ❌ Table budget_{year} does NOT exist!")
                results[year] = {
                    'status': 'MISSING',
                    'fs_records': fs_data['total_records'],
                    'db_records': 0,
                    'match': False
                }
                continue
            
            print(f"   Total Records: {db_data['total_records']:,}")
            print(f"   Total Amount:  ₱{db_data['total_amount']:,.2f}")
            print(f"   Source Files:  {db_data['source_file_count']}")
            print(f"\n   Source File Breakdown:")
            for f in db_data['files']:
                print(f"      - {f['source_file']}: {f['count']:,} records, ₱{f['amount']:,.2f}")
            
            # Comparison
            record_match = fs_data['total_records'] == db_data['total_records']
            amount_diff = abs(fs_data['total_amount'] - float(db_data['total_amount']))
            amount_match = amount_diff < 1.0  # Within ₱1 due to rounding
            
            print(f"\n🔍 Comparison:")
            print(f"   Record Count Match: {'✅ YES' if record_match else '❌ NO'}")
            if not record_match:
                diff = fs_data['total_records'] - db_data['total_records']
                print(f"   Difference: {diff:,} records ({'more in FS' if diff > 0 else 'more in DB'})")
            
            print(f"   Amount Match: {'✅ YES' if amount_match else '❌ NO'}")
            if not amount_match:
                print(f"   Difference: ₱{amount_diff:,.2f}")
            
            status = "✅ PERFECT MATCH" if (record_match and amount_match) else "⚠️ MISMATCH"
            print(f"\n   Status: {status}")
            
            results[year] = {
                'status': 'MATCH' if (record_match and amount_match) else 'MISMATCH',
                'fs_records': fs_data['total_records'],
                'fs_amount': fs_data['total_amount'],
                'db_records': db_data['total_records'],
                'db_amount': float(db_data['total_amount']),
                'record_match': record_match,
                'amount_match': amount_match
            }
        
        # Summary
        print(f"\n\n{'=' * 100}")
        print(" SUMMARY: GAA DATA VALIDATION")
        print(f"{'=' * 100}")
        
        print(f"\n{'Year':<10} {'File System':>20} {'PostgreSQL':>20} {'Status':>15} {'Match':>10}")
        print("-" * 100)
        
        for year in self.years:
            if year not in results:
                continue
            r = results[year]
            status_icon = "✅" if r['status'] == 'MATCH' else "❌"
            print(f"{year:<10} {r['fs_records']:>20,} {r['db_records']:>20,} {r['status']:>15} {status_icon:>10}")
        
        # Grand totals
        total_fs = sum(r['fs_records'] for r in results.values())
        total_db = sum(r['db_records'] for r in results.values())
        total_fs_amt = sum(r.get('fs_amount', 0) for r in results.values())
        total_db_amt = sum(r.get('db_amount', 0) for r in results.values())
        
        print("-" * 100)
        print(f"{'TOTAL':<10} {total_fs:>20,} {total_db:>20,}")
        
        print(f"\n📊 Overall Statistics:")
        print(f"   Total File System Records: {total_fs:,}")
        print(f"   Total Database Records:    {total_db:,}")
        print(f"   Total File System Amount:  ₱{total_fs_amt:,.2f}")
        print(f"   Total Database Amount:     ₱{total_db_amt:,.2f}")
        
        all_match = all(r['status'] == 'MATCH' for r in results.values())
        
        print(f"\n🎯 Validation Result:")
        if all_match:
            print(f"   ✅ ALL YEARS MATCH PERFECTLY!")
            print(f"   File system data is fully synchronized with PostgreSQL database.")
        else:
            mismatches = [year for year, r in results.items() if r['status'] != 'MATCH']
            print(f"   ⚠️  Found mismatches in years: {', '.join(map(str, mismatches))}")
            print(f"   Please investigate and resolve discrepancies.")
        
        print(f"\n{'=' * 100}")
        
        return results


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
        comparator = MultiYearGAAComparator(db_config)
        comparator.compare_all_years()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()


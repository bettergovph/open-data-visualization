#!/usr/bin/env python3
"""
Find the source of amount differences between JSON and PostgreSQL
Identifies specific records with discrepancies
"""

import json
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
from decimal import Decimal
from collections import defaultdict


def analyze_2025_differences():
    """Analyze GAA 2025 amount differences"""
    
    db_config = {
        'host': 'localhost',
        'port': 5432,
        'database': 'budget_analysis',
        'user': 'budget_admin',
        'password': 'wuQ5gBYCKkZiOGb61chLcByMu'
    }
    
    print("=" * 100)
    print(" ANALYZING GAA 2025 AMOUNT DIFFERENCES")
    print("=" * 100)
    
    # Step 1: Load all JSON data into a dictionary
    print("\n📁 Loading JSON data...")
    data_dir = Path("/home/joebert/open-budget-data/data/budget/2025/items")
    
    json_records = {}
    json_total = Decimal(0)
    
    for i in range(1, 9):
        filename = f'gaa_2025_batch_{i:04d}.json'
        filepath = data_dir / filename
        
        with open(filepath, 'r') as f:
            batch_data = json.load(f)
            for record in batch_data:
                record_id = record.get('id')
                amount = Decimal(str(record.get('amount', 0)))
                json_records[record_id] = {
                    'amount': amount,
                    'description': record.get('description'),
                    'org_code': record.get('org_uacs_code'),
                    'source_file': filename
                }
                json_total += amount
    
    print(f"   Loaded {len(json_records):,} records from JSON")
    print(f"   Total amount: ₱{json_total:,.2f}")
    
    # Step 2: Load all database data
    print("\n💾 Loading PostgreSQL data...")
    conn = psycopg2.connect(**db_config)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get all records from database
    # Note: We need to figure out how JSON IDs map to database records
    # The database doesn't have the JSON ID field, so we'll match by amount + description
    
    cursor.execute("""
        SELECT 
            id,
            amt,
            dsc,
            operunit,
            source_file,
            sorder,
            department,
            agency,
            prexc_fpap_id
        FROM budget_2025
        ORDER BY sorder, id
    """)
    
    db_records = cursor.fetchall()
    db_total = sum(Decimal(str(r['amt'])) for r in db_records)
    
    print(f"   Loaded {len(db_records):,} records from database")
    print(f"   Total amount: ₱{db_total:,.2f}")
    
    # Step 3: Calculate differences
    print("\n🔍 Analyzing differences...")
    
    json_total_actual = json_total
    db_total_actual = db_total
    difference = json_total_actual - db_total_actual
    
    print(f"\n   JSON Total:     ₱{json_total_actual:,.2f}")
    print(f"   Database Total: ₱{db_total_actual:,.2f}")
    print(f"   Difference:     ₱{difference:,.2f}")
    
    # Step 4: Try to match records by position (assuming same order)
    print("\n🔎 Matching records by position...")
    
    # First, let's create a mapping by sorting JSON records by their ID
    json_list = []
    for batch_num in range(1, 9):
        filename = f'gaa_2025_batch_{batch_num:04d}.json'
        filepath = data_dir / filename
        with open(filepath, 'r') as f:
            batch_data = json.load(f)
            json_list.extend(batch_data)
    
    print(f"   Total JSON records: {len(json_list):,}")
    print(f"   Total DB records:   {len(db_records):,}")
    
    if len(json_list) != len(db_records):
        print(f"   ⚠️  Record count mismatch!")
        return
    
    # Compare record by record
    mismatches = []
    total_diff = Decimal(0)
    rounding_diffs = []
    significant_diffs = []
    
    for i, (json_rec, db_rec) in enumerate(zip(json_list, db_records)):
        json_amt = Decimal(str(json_rec.get('amount', 0)))
        db_amt = Decimal(str(db_rec['amt']))
        
        diff = json_amt - db_amt
        
        if diff != 0:
            total_diff += diff
            
            diff_info = {
                'position': i + 1,
                'json_amt': json_amt,
                'db_amt': db_amt,
                'difference': diff,
                'json_desc': json_rec.get('description', '')[:50],
                'db_desc': db_rec['dsc'][:50] if db_rec['dsc'] else '',
                'json_id': json_rec.get('id'),
                'db_id': db_rec['id']
            }
            
            # Categorize differences
            if abs(diff) < 0.01:  # Very small rounding
                rounding_diffs.append(diff_info)
            else:
                significant_diffs.append(diff_info)
            
            mismatches.append(diff_info)
    
    # Report findings
    print(f"\n📊 FINDINGS:")
    print(f"   Total records compared: {len(json_list):,}")
    print(f"   Records with differences: {len(mismatches):,}")
    print(f"   Cumulative difference: ₱{total_diff:,.2f}")
    
    if rounding_diffs:
        print(f"\n   💫 Rounding differences (< ₱0.01): {len(rounding_diffs):,}")
        rounding_total = sum(d['difference'] for d in rounding_diffs)
        print(f"      Total from rounding: ₱{rounding_total:,.10f}")
    
    if significant_diffs:
        print(f"\n   ⚠️  Significant differences (≥ ₱0.01): {len(significant_diffs):,}")
        sig_total = sum(d['difference'] for d in significant_diffs)
        print(f"      Total from significant diffs: ₱{sig_total:,.2f}")
        
        print(f"\n   📋 Top 20 largest differences:")
        significant_diffs.sort(key=lambda x: abs(x['difference']), reverse=True)
        
        for i, diff in enumerate(significant_diffs[:20], 1):
            print(f"\n      {i}. Position {diff['position']:,}")
            print(f"         JSON Amount: ₱{diff['json_amt']:,.2f}")
            print(f"         DB Amount:   ₱{diff['db_amt']:,.2f}")
            print(f"         Difference:  ₱{diff['difference']:,.2f}")
            print(f"         Description: {diff['json_desc']}")
    
    # Statistical summary
    if mismatches:
        diffs_list = [abs(m['difference']) for m in mismatches]
        avg_diff = sum(diffs_list) / len(diffs_list)
        max_diff = max(diffs_list)
        min_diff = min(diffs_list)
        
        print(f"\n   📈 Statistical Summary:")
        print(f"      Average difference: ₱{avg_diff:,.2f}")
        print(f"      Maximum difference: ₱{max_diff:,.2f}")
        print(f"      Minimum difference: ₱{min_diff:,.10f}")
        
        # Distribution analysis
        ranges = {
            '< 0.01': 0,
            '0.01 - 1': 0,
            '1 - 10': 0,
            '10 - 100': 0,
            '100 - 1000': 0,
            '> 1000': 0
        }
        
        for diff in diffs_list:
            if diff < Decimal('0.01'):
                ranges['< 0.01'] += 1
            elif diff < Decimal('1'):
                ranges['0.01 - 1'] += 1
            elif diff < Decimal('10'):
                ranges['1 - 10'] += 1
            elif diff < Decimal('100'):
                ranges['10 - 100'] += 1
            elif diff < Decimal('1000'):
                ranges['100 - 1000'] += 1
            else:
                ranges['> 1000'] += 1
        
        print(f"\n   📊 Difference Distribution:")
        for range_label, count in ranges.items():
            if count > 0:
                pct = (count / len(mismatches)) * 100
                print(f"      {range_label:>15}: {count:>6,} records ({pct:>5.1f}%)")
    
    # Conclusion
    print(f"\n{'=' * 100}")
    print(" CONCLUSION")
    print(f"{'=' * 100}")
    
    if not mismatches:
        print("\n✅ NO DIFFERENCES FOUND - Data matches perfectly!")
    elif len(rounding_diffs) == len(mismatches):
        print(f"\n✅ All {len(mismatches):,} differences are tiny rounding errors (< ₱0.01)")
        print(f"   This is normal and acceptable for floating-point arithmetic.")
    else:
        print(f"\n⚠️  Found {len(significant_diffs):,} records with significant differences")
        print(f"   Total discrepancy: ₱{sig_total:,.2f}")
        print(f"   This requires investigation - possible data quality issue.")
    
    cursor.close()
    conn.close()
    
    print(f"\n{'=' * 100}")


if __name__ == "__main__":
    analyze_2025_differences()


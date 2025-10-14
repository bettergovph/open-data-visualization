#!/usr/bin/env python3
"""
Compare NEP vs GAA 2025 Data
Shows side-by-side comparison of proposed vs enacted budget
"""

import psycopg2
from psycopg2.extras import RealDictCursor


def compare_databases():
    """Compare NEP and GAA databases"""
    
    nep_config = {
        'host': 'localhost',
        'port': 5432,
        'database': 'nep',
        'user': 'budget_admin',
        'password': 'wuQ5gBYCKkZiOGb61chLcByMu'
    }
    
    gaa_config = {
        'host': 'localhost',
        'port': 5432,
        'database': 'budget_analysis',
        'user': 'budget_admin',
        'password': 'wuQ5gBYCKkZiOGb61chLcByMu'
    }
    
    print("=" * 100)
    print(" NEP vs GAA 2025 COMPARISON")
    print("=" * 100)
    
    # Connect to both databases
    nep_conn = psycopg2.connect(**nep_config)
    gaa_conn = psycopg2.connect(**gaa_config)
    
    # Get NEP stats
    nep_cursor = nep_conn.cursor(cursor_factory=RealDictCursor)
    nep_cursor.execute("""
        SELECT 
            COUNT(*) as total_records,
            SUM(amount) as total_amount,
            AVG(amount) as avg_amount,
            MIN(amount) as min_amount,
            MAX(amount) as max_amount
        FROM budget_2025
    """)
    nep_stats = nep_cursor.fetchone()
    
    # Get GAA stats
    gaa_cursor = gaa_conn.cursor(cursor_factory=RealDictCursor)
    gaa_cursor.execute("""
        SELECT 
            COUNT(*) as total_records,
            SUM(amt) as total_amount,
            AVG(amt) as avg_amount,
            MIN(amt) as min_amount,
            MAX(amt) as max_amount
        FROM budget_2025
    """)
    gaa_stats = gaa_cursor.fetchone()
    
    # Overall comparison
    print("\n📊 OVERALL STATISTICS")
    print("-" * 100)
    print(f"{'Metric':<30} {'NEP (Proposed)':>25} {'GAA (Enacted)':>25} {'Difference':>15}")
    print("-" * 100)
    
    print(f"{'Total Records':<30} {nep_stats['total_records']:>25,} {gaa_stats['total_records']:>25,} {nep_stats['total_records'] - gaa_stats['total_records']:>15,}")
    print(f"{'Total Amount (₱)':<30} {nep_stats['total_amount']:>25,.2f} {gaa_stats['total_amount']:>25,.2f} {nep_stats['total_amount'] - gaa_stats['total_amount']:>15,.2f}")
    print(f"{'Average Amount (₱)':<30} {nep_stats['avg_amount']:>25,.2f} {gaa_stats['avg_amount']:>25,.2f} {nep_stats['avg_amount'] - gaa_stats['avg_amount']:>15,.2f}")
    print(f"{'Min Amount (₱)':<30} {nep_stats['min_amount']:>25,.2f} {gaa_stats['min_amount']:>25,.2f}")
    print(f"{'Max Amount (₱)':<30} {nep_stats['max_amount']:>25,.2f} {gaa_stats['max_amount']:>25,.2f}")
    
    # Regional comparison
    print("\n\n🗺️  REGIONAL DISTRIBUTION COMPARISON (Top 10)")
    print("-" * 100)
    
    nep_cursor.execute("""
        SELECT region_code, COUNT(*) as count, SUM(amount) as total
        FROM budget_2025
        GROUP BY region_code
        ORDER BY total DESC NULLS LAST
        LIMIT 10
    """)
    nep_regions = {r['region_code']: r for r in nep_cursor.fetchall()}
    
    gaa_cursor.execute("""
        SELECT uacs_reg_id::text as region_code, COUNT(*) as count, SUM(amt) as total
        FROM budget_2025
        GROUP BY uacs_reg_id
        ORDER BY total DESC NULLS LAST
        LIMIT 10
    """)
    gaa_regions = {r['region_code']: r for r in gaa_cursor.fetchall()}
    
    all_regions = set(nep_regions.keys()) | set(gaa_regions.keys())
    
    print(f"{'Region':<15} {'NEP Records':>15} {'NEP Amount (₱)':>20} {'GAA Records':>15} {'GAA Amount (₱)':>20}")
    print("-" * 100)
    
    for region in sorted(all_regions, key=lambda x: (x is None, x)):
        region_label = region if region else 'National/NA'
        nep_count = nep_regions.get(region, {}).get('count', 0)
        nep_total = nep_regions.get(region, {}).get('total', 0) or 0
        gaa_count = gaa_regions.get(region, {}).get('count', 0)
        gaa_total = gaa_regions.get(region, {}).get('total', 0) or 0
        
        print(f"{region_label:<15} {nep_count:>15,} {nep_total:>20,.2f} {gaa_count:>15,} {gaa_total:>20,.2f}")
    
    # Summary
    print("\n\n" + "=" * 100)
    print(" SUMMARY")
    print("=" * 100)
    
    record_diff = nep_stats['total_records'] - gaa_stats['total_records']
    amount_diff = nep_stats['total_amount'] - gaa_stats['total_amount']
    
    print(f"\n📈 Key Findings:")
    print(f"   • NEP has {abs(record_diff):,} {'more' if record_diff > 0 else 'fewer'} records than GAA")
    print(f"   • NEP total is ₱{abs(amount_diff):,.2f} {'higher' if amount_diff > 0 else 'lower'} than GAA")
    print(f"   • Combined 2025 budget data: {nep_stats['total_records'] + gaa_stats['total_records']:,} records")
    print(f"   • Combined total amount: ₱{nep_stats['total_amount'] + gaa_stats['total_amount']:,.2f}")
    
    print(f"\n💡 Interpretation:")
    print(f"   • NEP = National Expenditure Program (Executive proposal)")
    print(f"   • GAA = General Appropriations Act (Legislative enactment)")
    print(f"   • Differences reflect legislative budget adjustments")
    print(f"   • Both datasets now available for comprehensive analysis")
    
    print("\n" + "=" * 100)
    
    nep_cursor.close()
    gaa_cursor.close()
    nep_conn.close()
    gaa_conn.close()


if __name__ == "__main__":
    compare_databases()


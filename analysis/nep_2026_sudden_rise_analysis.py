#!/usr/bin/env python3
"""
NEP 2026 Sudden Rise Analysis
Identifies sudden increases in NEP 2026 compared to historical trends (2020-2025)
Similar to the flood control budget spike pattern
"""

import asyncio
import os
import json
from collections import defaultdict
from decimal import Decimal
import asyncpg

# Keywords for infrastructure categories
INFRASTRUCTURE_CATEGORIES = {
    'flood_control': ['flood', 'drainage', 'pumping', 'estero', 'river control', 'creek'],
    'road_bridge': ['road', 'bridge', 'highway', 'avenue', 'street'],
    'water_systems': ['water', 'irrigation', 'dam', 'canal', 'pipeline'],
    'building_construction': ['building', 'construction', 'facility', 'structure'],
    'rehabilitation': ['rehabilitation', 'upgrading', 'improvement', 'repair', 'restoration'],
    'development': ['development', 'project', 'program', 'mitigation']
}

async def get_db_connection():
    """Get PostgreSQL connection to NEP database"""
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'joebert'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_NEP', 'nep')
        )
        return conn
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return None

async def analyze_year_over_year_total():
    """
    Compare total budget across years to identify overall trends
    """
    print("\n" + "="*80)
    print("📈 YEAR-OVER-YEAR TOTAL BUDGET ANALYSIS (2020-2026)")
    print("="*80)
    
    conn = await get_db_connection()
    if not conn:
        return None
    
    try:
        years_data = []
        
        for year in range(2020, 2027):
            query = f"""
            SELECT 
                COUNT(*) as item_count,
                SUM(amount) as total_amount,
                AVG(amount) as avg_amount
            FROM budget_{year}
            WHERE amount IS NOT NULL AND amount > 0
            """
            
            result = await conn.fetchrow(query)
            
            if result:
                years_data.append({
                    'year': year,
                    'count': result['item_count'],
                    'total': float(result['total_amount']),
                    'average': float(result['avg_amount'])
                })
        
        # Display and calculate growth rates
        print(f"\n{'Year':<8} {'Items':<12} {'Total Budget':<20} {'YoY Growth':<15} {'Avg Amount':<18}")
        print("-" * 85)
        
        for i, data in enumerate(years_data):
            if i > 0:
                prev_total = years_data[i-1]['total']
                growth = ((data['total'] - prev_total) / prev_total * 100) if prev_total > 0 else 0
                growth_str = f"{growth:+.1f}%"
            else:
                growth_str = "baseline"
            
            print(f"{data['year']:<8} {data['count']:<12,} ₱{data['total']:>17,.0f} {growth_str:<15} ₱{data['average']:>15,.0f}")
        
        # Identify sudden rises
        print("\n" + "="*80)
        print("🚨 SUDDEN RISE DETECTION:")
        print("="*80)
        
        for i in range(1, len(years_data)):
            prev = years_data[i-1]
            curr = years_data[i]
            growth = ((curr['total'] - prev['total']) / prev['total'] * 100) if prev['total'] > 0 else 0
            
            if growth >= 20:  # 20% or more increase
                print(f"\n⚠️  {curr['year']}: +{growth:.1f}% increase (₱{curr['total'] - prev['total']:,.0f})")
                print(f"   Previous: ₱{prev['total']:,.0f} → Current: ₱{curr['total']:,.0f}")
                
                if curr['year'] == 2026:
                    print(f"   🔴 ALERT: NEP 2026 shows significant increase!")
        
        return years_data
        
    finally:
        await conn.close()

async def analyze_regional_sudden_rises():
    """
    Identify regions with sudden budget increases in 2026 vs 2025
    """
    print("\n" + "="*80)
    print("🗺️  REGIONAL SUDDEN RISE ANALYSIS (2025 vs 2026)")
    print("="*80)
    
    conn = await get_db_connection()
    if not conn:
        return None
    
    try:
        # Get 2025 regional totals
        query_2025 = """
        SELECT 
            COALESCE(region_code, 'UNKNOWN') as region,
            COUNT(*) as item_count,
            SUM(amount) as total_amount
        FROM budget_2025
        WHERE amount IS NOT NULL AND amount > 0
        GROUP BY region_code
        """
        
        results_2025 = await conn.fetch(query_2025)
        data_2025 = {r['region']: {'count': r['item_count'], 'total': float(r['total_amount'])} for r in results_2025}
        
        # Get 2026 regional totals
        query_2026 = """
        SELECT 
            COALESCE(region_code, 'UNKNOWN') as region,
            COUNT(*) as item_count,
            SUM(amount) as total_amount
        FROM budget_2026
        WHERE amount IS NOT NULL AND amount > 0
        GROUP BY region_code
        ORDER BY SUM(amount) DESC
        """
        
        results_2026 = await conn.fetch(query_2026)
        
        # Calculate growth rates
        comparisons = []
        for r in results_2026:
            region = r['region']
            count_2026 = r['item_count']
            total_2026 = float(r['total_amount'])
            
            if region in data_2025:
                count_2025 = data_2025[region]['count']
                total_2025 = data_2025[region]['total']
                
                count_growth = ((count_2026 - count_2025) / count_2025 * 100) if count_2025 > 0 else 0
                amount_growth = ((total_2026 - total_2025) / total_2025 * 100) if total_2025 > 0 else 0
                
                comparisons.append({
                    'region': region,
                    'count_2025': count_2025,
                    'count_2026': count_2026,
                    'total_2025': total_2025,
                    'total_2026': total_2026,
                    'count_growth': count_growth,
                    'amount_growth': amount_growth,
                    'amount_increase': total_2026 - total_2025
                })
            else:
                # New region in 2026
                comparisons.append({
                    'region': region,
                    'count_2025': 0,
                    'count_2026': count_2026,
                    'total_2025': 0,
                    'total_2026': total_2026,
                    'count_growth': float('inf'),
                    'amount_growth': float('inf'),
                    'amount_increase': total_2026
                })
        
        # Sort by amount growth (highest first)
        comparisons.sort(key=lambda x: x['amount_growth'] if x['amount_growth'] != float('inf') else 999999, reverse=True)
        
        print(f"\n{'Region':<15} {'2025 Budget':<18} {'2026 Budget':<18} {'Growth':<12} {'Increase':<18}")
        print("-" * 95)
        
        sudden_rises = []
        for comp in comparisons[:25]:  # Top 25
            if comp['amount_growth'] == float('inf'):
                growth_str = "NEW"
                if comp['total_2026'] >= 1000000:  # At least 1M
                    sudden_rises.append(comp)
            else:
                growth_str = f"{comp['amount_growth']:+.1f}%"
                if comp['amount_growth'] >= 50:  # 50% or more increase
                    sudden_rises.append(comp)
            
            print(f"{comp['region']:<15} ₱{comp['total_2025']:>15,.0f} ₱{comp['total_2026']:>15,.0f} "
                  f"{growth_str:<12} ₱{comp['amount_increase']:>15,.0f}")
        
        # Highlight sudden rises
        if sudden_rises:
            print("\n" + "="*80)
            print("🚨 REGIONS WITH SUDDEN RISES (≥50% increase or NEW with ≥₱1M):")
            print("="*80)
            
            for comp in sudden_rises:
                if comp['amount_growth'] == float('inf'):
                    print(f"\n🔴 {comp['region']}: NEW region with ₱{comp['total_2026']:,.0f}")
                else:
                    print(f"\n⚠️  {comp['region']}: +{comp['amount_growth']:.1f}% increase (₱{comp['amount_increase']:,.0f})")
                    print(f"   2025: ₱{comp['total_2025']:,.0f} → 2026: ₱{comp['total_2026']:,.0f}")
        
        return comparisons
        
    finally:
        await conn.close()

async def analyze_department_sudden_rises():
    """
    Identify departments with sudden budget increases in 2026 vs 2025
    """
    print("\n" + "="*80)
    print("🏛️  DEPARTMENT SUDDEN RISE ANALYSIS (2025 vs 2026)")
    print("="*80)
    
    conn = await get_db_connection()
    if not conn:
        return None
    
    try:
        # Get 2025 department totals
        query_2025 = """
        SELECT 
            COALESCE(org_uacs_code, 'UNKNOWN') as department,
            COUNT(*) as item_count,
            SUM(amount) as total_amount
        FROM budget_2025
        WHERE amount IS NOT NULL AND amount > 0
        GROUP BY org_uacs_code
        """
        
        results_2025 = await conn.fetch(query_2025)
        data_2025 = {r['department']: {'count': r['item_count'], 'total': float(r['total_amount'])} for r in results_2025}
        
        # Get 2026 department totals
        query_2026 = """
        SELECT 
            COALESCE(org_uacs_code, 'UNKNOWN') as department,
            COUNT(*) as item_count,
            SUM(amount) as total_amount
        FROM budget_2026
        WHERE amount IS NOT NULL AND amount > 0
        GROUP BY org_uacs_code
        ORDER BY SUM(amount) DESC
        """
        
        results_2026 = await conn.fetch(query_2026)
        
        # Calculate growth rates
        comparisons = []
        for r in results_2026:
            dept = r['department']
            count_2026 = r['item_count']
            total_2026 = float(r['total_amount'])
            
            if dept in data_2025:
                count_2025 = data_2025[dept]['count']
                total_2025 = data_2025[dept]['total']
                
                amount_growth = ((total_2026 - total_2025) / total_2025 * 100) if total_2025 > 0 else 0
                
                comparisons.append({
                    'department': dept,
                    'count_2025': count_2025,
                    'count_2026': count_2026,
                    'total_2025': total_2025,
                    'total_2026': total_2026,
                    'amount_growth': amount_growth,
                    'amount_increase': total_2026 - total_2025
                })
            else:
                # New department in 2026
                comparisons.append({
                    'department': dept,
                    'count_2025': 0,
                    'count_2026': count_2026,
                    'total_2025': 0,
                    'total_2026': total_2026,
                    'amount_growth': float('inf'),
                    'amount_increase': total_2026
                })
        
        # Sort by amount growth
        comparisons.sort(key=lambda x: x['amount_growth'] if x['amount_growth'] != float('inf') else 999999, reverse=True)
        
        print(f"\n{'Department':<15} {'2025 Budget':<18} {'2026 Budget':<18} {'Growth':<12} {'Increase':<18}")
        print("-" * 95)
        
        sudden_rises = []
        for comp in comparisons[:25]:  # Top 25
            if comp['amount_growth'] == float('inf'):
                growth_str = "NEW"
                if comp['total_2026'] >= 10000000:  # At least 10M
                    sudden_rises.append(comp)
            else:
                growth_str = f"{comp['amount_growth']:+.1f}%"
                if comp['amount_growth'] >= 50 and comp['total_2026'] >= 10000000:
                    sudden_rises.append(comp)
            
            print(f"{comp['department']:<15} ₱{comp['total_2025']:>15,.0f} ₱{comp['total_2026']:>15,.0f} "
                  f"{growth_str:<12} ₱{comp['amount_increase']:>15,.0f}")
        
        # Highlight sudden rises
        if sudden_rises:
            print("\n" + "="*80)
            print("🚨 DEPARTMENTS WITH SUDDEN RISES (≥50% increase, ≥₱10M):")
            print("="*80)
            
            for comp in sudden_rises[:10]:
                if comp['amount_growth'] == float('inf'):
                    print(f"\n🔴 {comp['department']}: NEW department with ₱{comp['total_2026']:,.0f}")
                else:
                    print(f"\n⚠️  {comp['department']}: +{comp['amount_growth']:.1f}% increase (₱{comp['amount_increase']:,.0f})")
                    print(f"   2025: ₱{comp['total_2025']:,.0f} → 2026: ₱{comp['total_2026']:,.0f}")
        
        return comparisons
        
    finally:
        await conn.close()

async def analyze_infrastructure_category_rises():
    """
    Identify sudden rises in specific infrastructure categories (flood control, roads, etc.)
    """
    print("\n" + "="*80)
    print("🏗️  INFRASTRUCTURE CATEGORY SUDDEN RISE ANALYSIS (2020-2026)")
    print("="*80)
    
    conn = await get_db_connection()
    if not conn:
        return None
    
    try:
        category_trends = {}
        
        for category, keywords in INFRASTRUCTURE_CATEGORIES.items():
            print(f"\n📊 Analyzing: {category.replace('_', ' ').title()}")
            print("-" * 80)
            
            yearly_data = []
            
            for year in range(2020, 2027):
                # Build WHERE clause with keywords
                keyword_conditions = " OR ".join([f"LOWER(description) LIKE LOWER('%{kw}%')" for kw in keywords])
                
                query = f"""
                SELECT 
                    COUNT(*) as item_count,
                    SUM(amount) as total_amount,
                    AVG(amount) as avg_amount
                FROM budget_{year}
                WHERE ({keyword_conditions})
                AND amount IS NOT NULL AND amount > 0
                """
                
                result = await conn.fetchrow(query)
                
                if result and result['item_count'] > 0:
                    yearly_data.append({
                        'year': year,
                        'count': result['item_count'],
                        'total': float(result['total_amount']),
                        'average': float(result['avg_amount'])
                    })
                else:
                    yearly_data.append({
                        'year': year,
                        'count': 0,
                        'total': 0.0,
                        'average': 0.0
                    })
            
            # Display trend
            print(f"{'Year':<8} {'Items':<10} {'Total Budget':<20} {'YoY Growth':<15}")
            print("-" * 65)
            
            max_growth = 0
            max_growth_year = None
            
            for i, data in enumerate(yearly_data):
                if i > 0 and yearly_data[i-1]['total'] > 0:
                    prev_total = yearly_data[i-1]['total']
                    growth = ((data['total'] - prev_total) / prev_total * 100)
                    growth_str = f"{growth:+.1f}%"
                    
                    if growth > max_growth:
                        max_growth = growth
                        max_growth_year = data['year']
                else:
                    growth_str = "baseline" if i == 0 else "new"
                
                marker = "🔴" if data['year'] == 2026 and i > 0 and yearly_data[i-1]['total'] > 0 else "  "
                print(f"{marker} {data['year']:<6} {data['count']:<10,} ₱{data['total']:>17,.0f} {growth_str:<15}")
            
            # Check for sudden rise in 2026
            if len(yearly_data) >= 2:
                data_2025 = yearly_data[-2]
                data_2026 = yearly_data[-1]
                
                if data_2025['total'] > 0:
                    growth_2026 = ((data_2026['total'] - data_2025['total']) / data_2025['total'] * 100)
                    
                    if growth_2026 >= 30:  # 30% or more increase
                        print(f"\n⚠️  SUDDEN RISE DETECTED in {category}:")
                        print(f"   2025: ₱{data_2025['total']:,.0f} ({data_2025['count']} items)")
                        print(f"   2026: ₱{data_2026['total']:,.0f} ({data_2026['count']} items)")
                        print(f"   Growth: +{growth_2026:.1f}% (₱{data_2026['total'] - data_2025['total']:,.0f})")
            
            category_trends[category] = yearly_data
        
        return category_trends
        
    finally:
        await conn.close()

async def analyze_new_large_line_items():
    """
    Find new large budget line items in 2026 that don't exist in 2025
    These could indicate new discretionary spending channels
    """
    print("\n" + "="*80)
    print("💰 NEW LARGE BUDGET LINE ITEMS IN 2026")
    print("="*80)
    
    conn = await get_db_connection()
    if not conn:
        return None
    
    try:
        # Get high-value items from 2026
        query_2026 = """
        SELECT 
            description,
            amount,
            region_code,
            org_uacs_code,
            COUNT(*) as occurrence_count
        FROM budget_2026
        WHERE amount >= 5000000  -- At least 5M pesos
        AND amount IS NOT NULL 
        AND description IS NOT NULL
        GROUP BY description, amount, region_code, org_uacs_code
        ORDER BY amount DESC
        LIMIT 100
        """
        
        items_2026 = await conn.fetch(query_2026)
        
        # Check if similar descriptions exist in 2025
        new_items = []
        
        for item in items_2026:
            desc = item['description']
            
            # Check for similar description in 2025 (exact match first)
            check_query = """
            SELECT COUNT(*) as count
            FROM budget_2025
            WHERE description = $1
            """
            
            result = await conn.fetchrow(check_query, desc)
            
            if result['count'] == 0:
                # New description not found in 2025
                new_items.append(item)
        
        print(f"\n🔍 Found {len(new_items)} new large budget items (≥₱5M) not in 2025:")
        print(f"\n{'Amount':<18} {'Count':<8} {'Region':<12} {'Dept':<12} {'Description'[:45]}")
        print("-" * 120)
        
        for item in new_items[:30]:
            desc = item['description'][:45] if item['description'] else 'N/A'
            region = item['region_code'] if item['region_code'] else 'N/A'
            dept = item['org_uacs_code'] if item['org_uacs_code'] else 'N/A'
            
            print(f"₱{float(item['amount']):>15,.0f} {item['occurrence_count']:<8} {region:<12} {dept:<12} {desc}")
        
        # Calculate total of new items
        total_new = sum(float(item['amount']) * item['occurrence_count'] for item in new_items)
        
        print(f"\n💸 Total value of new large items: ₱{total_new:,.0f}")
        
        return new_items
        
    finally:
        await conn.close()

async def generate_sudden_rise_summary(total_data, regional_data, dept_data, category_data, new_items):
    """
    Generate comprehensive summary of sudden rise patterns
    """
    print("\n" + "="*80)
    print("📑 SUDDEN RISE PATTERN SUMMARY - NEP 2026")
    print("="*80)
    
    alerts = []
    
    # Check overall budget increase
    if total_data and len(total_data) >= 2:
        data_2025 = total_data[-2]
        data_2026 = total_data[-1]
        
        if data_2025['total'] > 0:
            overall_growth = ((data_2026['total'] - data_2025['total']) / data_2025['total'] * 100)
            
            print(f"\n1️⃣  OVERALL BUDGET CHANGE (2025 → 2026):")
            print(f"   2025: ₱{data_2025['total']:,.0f}")
            print(f"   2026: ₱{data_2026['total']:,.0f}")
            print(f"   Change: {overall_growth:+.1f}% (₱{data_2026['total'] - data_2025['total']:,.0f})")
            
            if overall_growth >= 15:
                alerts.append(f"Overall budget increased by {overall_growth:.1f}%")
    
    # Check regional sudden rises
    if regional_data:
        sudden_regional = [r for r in regional_data if r['amount_growth'] >= 50 or r['amount_growth'] == float('inf')]
        
        print(f"\n2️⃣  REGIONAL SUDDEN RISES:")
        print(f"   {len(sudden_regional)} regions with ≥50% increase or NEW")
        
        if sudden_regional:
            top_3 = sudden_regional[:3]
            for r in top_3:
                if r['amount_growth'] == float('inf'):
                    print(f"   • {r['region']}: NEW (₱{r['total_2026']:,.0f})")
                else:
                    print(f"   • {r['region']}: +{r['amount_growth']:.1f}% (₱{r['amount_increase']:,.0f})")
            
            if len(sudden_regional) >= 5:
                alerts.append(f"{len(sudden_regional)} regions with sudden budget increases")
    
    # Check department sudden rises
    if dept_data:
        sudden_depts = [d for d in dept_data if (d['amount_growth'] >= 50 or d['amount_growth'] == float('inf')) and d['total_2026'] >= 10000000]
        
        print(f"\n3️⃣  DEPARTMENT SUDDEN RISES:")
        print(f"   {len(sudden_depts)} departments with ≥50% increase (≥₱10M)")
        
        if sudden_depts:
            top_3 = sudden_depts[:3]
            for d in top_3:
                if d['amount_growth'] == float('inf'):
                    print(f"   • {d['department']}: NEW (₱{d['total_2026']:,.0f})")
                else:
                    print(f"   • {d['department']}: +{d['amount_growth']:.1f}% (₱{d['amount_increase']:,.0f})")
            
            if len(sudden_depts) >= 3:
                alerts.append(f"{len(sudden_depts)} departments with sudden budget increases")
    
    # Check category increases
    if category_data:
        print(f"\n4️⃣  INFRASTRUCTURE CATEGORY RISES:")
        
        for category, yearly_data in category_data.items():
            if len(yearly_data) >= 2:
                data_2025 = yearly_data[-2]
                data_2026 = yearly_data[-1]
                
                if data_2025['total'] > 0:
                    growth = ((data_2026['total'] - data_2025['total']) / data_2025['total'] * 100)
                    
                    if growth >= 30:
                        cat_name = category.replace('_', ' ').title()
                        print(f"   • {cat_name}: +{growth:.1f}% (₱{data_2026['total'] - data_2025['total']:,.0f})")
                        alerts.append(f"{cat_name} category increased by {growth:.1f}%")
    
    # Check new large items
    if new_items:
        total_new = sum(float(item['amount']) * item['occurrence_count'] for item in new_items)
        print(f"\n5️⃣  NEW LARGE BUDGET ITEMS:")
        print(f"   {len(new_items)} new items ≥₱5M (total: ₱{total_new:,.0f})")
        
        if len(new_items) >= 10:
            alerts.append(f"{len(new_items)} new large budget items (₱{total_new:,.0f})")
    
    # Final assessment
    print("\n" + "="*80)
    print("⚠️  RISK ASSESSMENT")
    print("="*80)
    
    if alerts:
        print(f"\n🚨 {len(alerts)} ALERT INDICATORS DETECTED:\n")
        for i, alert in enumerate(alerts, 1):
            print(f"   {i}. {alert}")
        
        risk_level = "HIGH" if len(alerts) >= 4 else "MODERATE" if len(alerts) >= 2 else "LOW"
        print(f"\n📊 Risk Level: {risk_level}")
        print(f"   Similar to flood control sudden rise pattern: {'YES' if len(alerts) >= 3 else 'POSSIBLE' if len(alerts) >= 2 else 'NO'}")
    else:
        print("\n✅ No significant sudden rise patterns detected in NEP 2026")
    
    print("\n" + "="*80)

async def main():
    """
    Main analysis function
    """
    print("\n" + "="*80)
    print("🔬 NEP 2026 SUDDEN RISE PATTERN ANALYSIS")
    print("   Identifying unusual budget increases similar to flood control scheme")
    print("="*80)
    
    # Run all analyses
    total_data = await analyze_year_over_year_total()
    regional_data = await analyze_regional_sudden_rises()
    dept_data = await analyze_department_sudden_rises()
    category_data = await analyze_infrastructure_category_rises()
    new_items = await analyze_new_large_line_items()
    
    # Generate comprehensive summary
    await generate_sudden_rise_summary(total_data, regional_data, dept_data, category_data, new_items)
    
    print("\n✅ Analysis complete!")
    print("\n💡 Interpretation Guide:")
    print("   • Sudden rises (≥30-50%) warrant detailed investigation")
    print("   • Multiple concurrent increases across regions/departments = higher risk")
    print("   • New large budget items without historical precedent = red flag")
    print("   • Compare patterns to actual project implementation and outcomes")

if __name__ == "__main__":
    asyncio.run(main())


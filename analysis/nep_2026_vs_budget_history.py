#!/usr/bin/env python3
"""
NEP 2026 vs Budget History Analysis
Compares NEP 2026 (proposed budget) against actual Budget data (2017-2025)
to identify sudden rises similar to the flood control pattern
"""

import asyncio
import os
import json
from collections import defaultdict
from decimal import Decimal
import asyncpg
from dotenv import load_dotenv

load_dotenv()

# Keywords for infrastructure categories
INFRASTRUCTURE_CATEGORIES = {
    'flood_control': ['flood', 'drainage', 'pumping', 'estero', 'river control', 'creek', 'dike', 'revetment'],
    'road_bridge': ['road', 'bridge', 'highway', 'avenue', 'street', 'expressway'],
    'water_systems': ['water', 'irrigation', 'dam', 'canal', 'pipeline', 'waterworks'],
    'building_construction': ['building', 'construction', 'facility', 'structure', 'edifice'],
    'rehabilitation': ['rehabilitation', 'upgrading', 'improvement', 'repair', 'restoration', 'renovation'],
}

async def get_budget_db_connection():
    """Get PostgreSQL connection to Budget database"""
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_BUDGET', 'budget_analysis')
        )
        return conn
    except Exception as e:
        print(f"❌ Budget database connection failed: {e}")
        return None

async def get_nep_db_connection():
    """Get PostgreSQL connection to NEP database"""
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_NEP', 'nep')
        )
        return conn
    except Exception as e:
        print(f"❌ NEP database connection failed: {e}")
        return None

async def compare_total_budget():
    """
    Compare NEP 2026 total against Budget history (2017-2025)
    """
    print("\n" + "="*80)
    print("📈 NEP 2026 vs BUDGET HISTORY TOTAL COMPARISON")
    print("="*80)
    
    budget_conn = await get_budget_db_connection()
    nep_conn = await get_nep_db_connection()
    
    if not budget_conn or not nep_conn:
        return None
    
    try:
        years_data = []
        
        # Get Budget data for 2017-2025
        for year in range(2017, 2026):
            query = f"""
            SELECT 
                COUNT(*) as item_count,
                SUM(amt) as total_amount,
                AVG(amt) as avg_amount
            FROM budget_{year}
            WHERE amt IS NOT NULL AND amt > 0
            """
            
            result = await budget_conn.fetchrow(query)
            
            if result:
                years_data.append({
                    'year': year,
                    'count': result['item_count'],
                    'total': float(result['total_amount']),
                    'average': float(result['avg_amount']),
                    'source': 'Budget (Actual)'
                })
        
        # Get NEP 2026 data
        query_2026 = """
        SELECT 
            COUNT(*) as item_count,
            SUM(amount) as total_amount,
            AVG(amount) as avg_amount
        FROM budget_2026
        WHERE amount IS NOT NULL AND amount > 0
        """
        
        result_2026 = await nep_conn.fetchrow(query_2026)
        
        if result_2026:
            years_data.append({
                'year': 2026,
                'count': result_2026['item_count'],
                'total': float(result_2026['total_amount']),
                'average': float(result_2026['avg_amount']),
                'source': 'NEP (Proposed)'
            })
        
        # Display comparison
        print(f"\n{'Year':<8} {'Source':<18} {'Items':<12} {'Total Budget':<20} {'YoY Growth':<15} {'Avg Amount':<18}")
        print("-" * 115)
        
        max_growth = 0
        max_growth_year = None
        
        for i, data in enumerate(years_data):
            if i > 0:
                prev_total = years_data[i-1]['total']
                growth = ((data['total'] - prev_total) / prev_total * 100) if prev_total > 0 else 0
                growth_str = f"{growth:+.1f}%"
                
                if abs(growth) > abs(max_growth):
                    max_growth = growth
                    max_growth_year = data['year']
            else:
                growth_str = "baseline"
            
            marker = "🔴" if data['year'] == 2026 else "  "
            print(f"{marker} {data['year']:<6} {data['source']:<18} {data['count']:<12,} ₱{data['total']:>17,.0f} {growth_str:<15} ₱{data['average']:>15,.0f}")
        
        # Analyze 2026 vs historical average
        if len(years_data) >= 2:
            budget_years = [d for d in years_data if d['year'] < 2026]
            avg_historical = sum(d['total'] for d in budget_years) / len(budget_years)
            
            nep_2026 = years_data[-1]
            vs_avg = ((nep_2026['total'] - avg_historical) / avg_historical * 100)
            vs_2025 = ((nep_2026['total'] - years_data[-2]['total']) / years_data[-2]['total'] * 100)
            
            print("\n" + "="*80)
            print("🚨 NEP 2026 ANALYSIS:")
            print("="*80)
            print(f"Historical Average (2017-2025): ₱{avg_historical:,.0f}")
            print(f"NEP 2026 Proposed: ₱{nep_2026['total']:,.0f}")
            print(f"vs Historical Average: {vs_avg:+.1f}%")
            print(f"vs 2025 Budget: {vs_2025:+.1f}%")
            
            if vs_avg >= 20 or vs_2025 >= 20:
                print(f"\n⚠️  WARNING: NEP 2026 shows significant increase!")
                print(f"   This pattern is similar to the flood control budget spike")
        
        return years_data
        
    finally:
        await budget_conn.close()
        await nep_conn.close()

async def compare_infrastructure_categories():
    """
    Compare infrastructure spending: NEP 2026 vs Budget history
    """
    print("\n" + "="*80)
    print("🏗️  INFRASTRUCTURE CATEGORY COMPARISON (Budget 2017-2025 vs NEP 2026)")
    print("="*80)
    
    budget_conn = await get_budget_db_connection()
    nep_conn = await get_nep_db_connection()
    
    if not budget_conn or not nep_conn:
        return None
    
    try:
        category_analysis = {}
        
        for category, keywords in INFRASTRUCTURE_CATEGORIES.items():
            print(f"\n📊 {category.replace('_', ' ').title()}")
            print("-" * 80)
            
            yearly_data = []
            
            # Get Budget historical data (2017-2025)
            for year in range(2017, 2026):
                keyword_conditions = " OR ".join([f"LOWER(dsc) LIKE LOWER('%{kw}%')" for kw in keywords])
                
                query = f"""
                SELECT 
                    COUNT(*) as item_count,
                    SUM(amt) as total_amount
                FROM budget_{year}
                WHERE ({keyword_conditions})
                AND amt IS NOT NULL AND amt > 0
                """
                
                result = await budget_conn.fetchrow(query)
                
                if result and result['item_count'] > 0:
                    yearly_data.append({
                        'year': year,
                        'count': result['item_count'],
                        'total': float(result['total_amount']),
                        'source': 'Budget'
                    })
                else:
                    yearly_data.append({
                        'year': year,
                        'count': 0,
                        'total': 0.0,
                        'source': 'Budget'
                    })
            
            # Get NEP 2026 data
            keyword_conditions = " OR ".join([f"LOWER(description) LIKE LOWER('%{kw}%')" for kw in keywords])
            
            query_2026 = f"""
            SELECT 
                COUNT(*) as item_count,
                SUM(amount) as total_amount
            FROM budget_2026
            WHERE ({keyword_conditions})
            AND amount IS NOT NULL AND amount > 0
            """
            
            result_2026 = await nep_conn.fetchrow(query_2026)
            
            if result_2026 and result_2026['item_count'] > 0:
                yearly_data.append({
                    'year': 2026,
                    'count': result_2026['item_count'],
                    'total': float(result_2026['total_amount']),
                    'source': 'NEP'
                })
            else:
                yearly_data.append({
                    'year': 2026,
                    'count': 0,
                    'total': 0.0,
                    'source': 'NEP'
                })
            
            # Display trend
            print(f"{'Year':<8} {'Source':<10} {'Items':<10} {'Total Budget':<20} {'YoY Growth':<15}")
            print("-" * 75)
            
            for i, data in enumerate(yearly_data):
                if i > 0 and yearly_data[i-1]['total'] > 0:
                    prev_total = yearly_data[i-1]['total']
                    growth = ((data['total'] - prev_total) / prev_total * 100)
                    growth_str = f"{growth:+.1f}%"
                else:
                    growth_str = "baseline" if i == 0 else ("new" if data['total'] > 0 else "0")
                
                marker = "🔴" if data['year'] == 2026 else "  "
                print(f"{marker} {data['year']:<6} {data['source']:<10} {data['count']:<10,} ₱{data['total']:>17,.0f} {growth_str:<15}")
            
            # Analyze 2026 vs historical
            if len(yearly_data) >= 2:
                budget_years = [d for d in yearly_data if d['year'] < 2026 and d['total'] > 0]
                
                if budget_years:
                    avg_historical = sum(d['total'] for d in budget_years) / len(budget_years)
                    nep_2026 = yearly_data[-1]
                    data_2025 = yearly_data[-2]
                    
                    if avg_historical > 0 and nep_2026['total'] > 0:
                        vs_avg = ((nep_2026['total'] - avg_historical) / avg_historical * 100)
                        
                        if data_2025['total'] > 0:
                            vs_2025 = ((nep_2026['total'] - data_2025['total']) / data_2025['total'] * 100)
                        else:
                            vs_2025 = float('inf')
                        
                        print(f"\n   Historical Avg: ₱{avg_historical:,.0f}")
                        print(f"   NEP 2026: ₱{nep_2026['total']:,.0f}")
                        print(f"   vs Avg: {vs_avg:+.1f}%")
                        if vs_2025 != float('inf'):
                            print(f"   vs 2025: {vs_2025:+.1f}%")
                        
                        if vs_avg >= 50 or (vs_2025 >= 50 and vs_2025 != float('inf')):
                            print(f"\n   ⚠️  SUDDEN RISE DETECTED in {category}!")
            
            category_analysis[category] = yearly_data
        
        return category_analysis
        
    finally:
        await budget_conn.close()
        await nep_conn.close()

async def compare_regional_distribution():
    """
    Compare regional budget distribution: NEP 2026 vs Budget 2025
    """
    print("\n" + "="*80)
    print("🗺️  REGIONAL DISTRIBUTION COMPARISON (Budget 2025 vs NEP 2026)")
    print("="*80)
    
    budget_conn = await get_budget_db_connection()
    nep_conn = await get_nep_db_connection()
    
    if not budget_conn or not nep_conn:
        return None
    
    try:
        # Note: Budget database uses 'agency' field, NEP uses 'region_code'
        # We'll do a best-effort comparison
        
        # Get Budget 2025 by agency (closest to region)
        query_2025 = """
        SELECT 
            COALESCE(CAST(agency AS TEXT), 'UNKNOWN') as region,
            COUNT(*) as item_count,
            SUM(amt) as total_amount
        FROM budget_2025
        WHERE amt IS NOT NULL AND amt > 0
        GROUP BY agency
        ORDER BY SUM(amt) DESC
        LIMIT 20
        """
        
        results_2025 = await budget_conn.fetch(query_2025)
        data_2025 = {r['region']: {'count': r['item_count'], 'total': float(r['total_amount'])} for r in results_2025}
        
        # Get NEP 2026 by region
        query_2026 = """
        SELECT 
            COALESCE(region_code, 'UNKNOWN') as region,
            COUNT(*) as item_count,
            SUM(amount) as total_amount
        FROM budget_2026
        WHERE amount IS NOT NULL AND amount > 0
        GROUP BY region_code
        ORDER BY SUM(amount) DESC
        LIMIT 20
        """
        
        results_2026 = await nep_conn.fetch(query_2026)
        
        print(f"\n{'Region/Agency':<20} {'2025 Budget':<18} {'2026 NEP':<18} {'Change':<15}")
        print("-" * 85)
        
        significant_increases = []
        
        for r in results_2026[:15]:
            region = r['region']
            count_2026 = r['item_count']
            total_2026 = float(r['total_amount'])
            
            if region in data_2025:
                total_2025 = data_2025[region]['total']
                change = ((total_2026 - total_2025) / total_2025 * 100) if total_2025 > 0 else 0
                change_str = f"{change:+.1f}%"
                
                if change >= 50:
                    significant_increases.append({
                        'region': region,
                        'total_2025': total_2025,
                        'total_2026': total_2026,
                        'change': change
                    })
            else:
                change_str = "NEW"
                if total_2026 >= 1000000:
                    significant_increases.append({
                        'region': region,
                        'total_2025': 0,
                        'total_2026': total_2026,
                        'change': float('inf')
                    })
            
            budget_2025 = data_2025.get(region, {'total': 0})['total']
            print(f"{region:<20} ₱{budget_2025:>15,.0f} ₱{total_2026:>15,.0f} {change_str:<15}")
        
        if significant_increases:
            print(f"\n⚠️  {len(significant_increases)} regions/agencies show significant increases (≥50%)")
        
        return {'data_2025': data_2025, 'data_2026': results_2026, 'significant': significant_increases}
        
    finally:
        await budget_conn.close()
        await nep_conn.close()

async def find_new_large_items_2026():
    """
    Find new large budget items in NEP 2026 that don't have precedent in Budget history
    """
    print("\n" + "="*80)
    print("💰 NEW LARGE BUDGET ITEMS IN NEP 2026 (Not in Budget 2025)")
    print("="*80)
    
    budget_conn = await get_budget_db_connection()
    nep_conn = await get_nep_db_connection()
    
    if not budget_conn or not nep_conn:
        return None
    
    try:
        # Get unique descriptions from Budget 2025
        query_2025 = """
        SELECT DISTINCT LOWER(dsc) as description
        FROM budget_2025
        WHERE dsc IS NOT NULL
        """
        
        results_2025 = await budget_conn.fetch(query_2025)
        descriptions_2025 = set(r['description'] for r in results_2025)
        
        # Get high-value items from NEP 2026
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
        
        items_2026 = await nep_conn.fetch(query_2026)
        
        # Check which items are new
        new_items = []
        
        for item in items_2026:
            desc_lower = item['description'].lower() if item['description'] else ''
            
            if desc_lower not in descriptions_2025:
                new_items.append(item)
        
        print(f"\n🔍 Found {len(new_items)} new large budget items (≥₱5M) not in Budget 2025:")
        print(f"\n{'Amount':<18} {'Count':<8} {'Region':<12} {'Dept':<15} {'Description'[:40]}")
        print("-" * 115)
        
        for item in new_items[:30]:
            desc = item['description'][:40] if item['description'] else 'N/A'
            region = item['region_code'] if item['region_code'] else 'N/A'
            dept = item['org_uacs_code'] if item['org_uacs_code'] else 'N/A'
            
            print(f"₱{float(item['amount']):>15,.0f} {item['occurrence_count']:<8} {region:<12} {dept:<15} {desc}")
        
        # Calculate total of new items
        total_new = sum(float(item['amount']) * item['occurrence_count'] for item in new_items)
        
        print(f"\n💸 Total value of new large items: ₱{total_new:,.0f}")
        
        return new_items
        
    finally:
        await budget_conn.close()
        await nep_conn.close()

async def generate_comprehensive_report(total_data, category_data, regional_data, new_items):
    """
    Generate final comprehensive report
    """
    print("\n" + "="*80)
    print("📑 COMPREHENSIVE ANALYSIS REPORT: NEP 2026 vs BUDGET HISTORY")
    print("="*80)
    
    alerts = []
    
    # Overall budget analysis
    if total_data and len(total_data) >= 2:
        budget_years = [d for d in total_data if d['year'] < 2026]
        avg_historical = sum(d['total'] for d in budget_years) / len(budget_years)
        nep_2026 = total_data[-1]
        budget_2025 = total_data[-2]
        
        vs_avg = ((nep_2026['total'] - avg_historical) / avg_historical * 100)
        vs_2025 = ((nep_2026['total'] - budget_2025['total']) / budget_2025['total'] * 100)
        
        print(f"\n1️⃣  OVERALL BUDGET COMPARISON:")
        print(f"   Historical Avg (2017-2025): ₱{avg_historical:,.0f}")
        print(f"   Budget 2025 (Actual): ₱{budget_2025['total']:,.0f}")
        print(f"   NEP 2026 (Proposed): ₱{nep_2026['total']:,.0f}")
        print(f"   vs Historical Avg: {vs_avg:+.1f}%")
        print(f"   vs Budget 2025: {vs_2025:+.1f}%")
        
        if vs_avg >= 15:
            alerts.append(f"NEP 2026 is {vs_avg:.1f}% higher than historical average")
        if vs_2025 >= 20:
            alerts.append(f"NEP 2026 is {vs_2025:.1f}% higher than Budget 2025")
    
    # Infrastructure categories
    if category_data:
        print(f"\n2️⃣  INFRASTRUCTURE CATEGORY SUDDEN RISES:")
        
        categories_with_rises = []
        for category, yearly_data in category_data.items():
            if len(yearly_data) >= 2:
                budget_years = [d for d in yearly_data if d['year'] < 2026 and d['total'] > 0]
                if budget_years:
                    avg_historical = sum(d['total'] for d in budget_years) / len(budget_years)
                    nep_2026 = yearly_data[-1]
                    
                    if avg_historical > 0 and nep_2026['total'] > 0:
                        vs_avg = ((nep_2026['total'] - avg_historical) / avg_historical * 100)
                        
                        if vs_avg >= 50:
                            cat_name = category.replace('_', ' ').title()
                            categories_with_rises.append({
                                'category': cat_name,
                                'increase': vs_avg,
                                'historical_avg': avg_historical,
                                'nep_2026': nep_2026['total']
                            })
        
        if categories_with_rises:
            for cat in categories_with_rises:
                print(f"   • {cat['category']}: +{cat['increase']:.1f}%")
                print(f"     Historical: ₱{cat['historical_avg']:,.0f} → NEP 2026: ₱{cat['nep_2026']:,.0f}")
            
            alerts.append(f"{len(categories_with_rises)} infrastructure categories show ≥50% increase")
        else:
            print(f"   No significant rises detected")
    
    # Regional changes
    if regional_data and regional_data.get('significant'):
        print(f"\n3️⃣  REGIONAL/AGENCY DISTRIBUTION:")
        print(f"   {len(regional_data['significant'])} regions/agencies show significant increases")
        
        if len(regional_data['significant']) >= 5:
            alerts.append(f"{len(regional_data['significant'])} regions with sudden increases")
    
    # New large items
    if new_items:
        total_new = sum(float(item['amount']) * item['occurrence_count'] for item in new_items)
        print(f"\n4️⃣  NEW LARGE BUDGET ITEMS:")
        print(f"   {len(new_items)} new items ≥₱5M (total: ₱{total_new:,.0f})")
        
        if len(new_items) >= 15:
            alerts.append(f"{len(new_items)} new large budget items (₱{total_new:,.0f})")
    
    # Final risk assessment
    print("\n" + "="*80)
    print("⚠️  FINAL RISK ASSESSMENT")
    print("="*80)
    
    if alerts:
        print(f"\n🚨 {len(alerts)} ALERT INDICATORS DETECTED:\n")
        for i, alert in enumerate(alerts, 1):
            print(f"   {i}. {alert}")
        
        risk_level = "HIGH" if len(alerts) >= 4 else "MODERATE" if len(alerts) >= 2 else "LOW"
        print(f"\n📊 Risk Level: {risk_level}")
        
        if len(alerts) >= 3:
            print(f"\n🔴 PATTERN MATCH: NEP 2026 shows similar sudden rise patterns to flood control scheme")
            print(f"   Recommend detailed investigation of:")
            print(f"   • Geographic distribution and clustering")
            print(f"   • Specific project descriptions and justifications")
            print(f"   • Contractor selection patterns")
            print(f"   • Implementation timelines and milestones")
    else:
        print("\n✅ No significant sudden rise patterns detected")
    
    print("\n" + "="*80)

async def main():
    """
    Main analysis function
    """
    print("\n" + "="*80)
    print("🔬 NEP 2026 vs BUDGET HISTORY ANALYSIS")
    print("   Comparing proposed NEP 2026 against actual Budget data (2017-2025)")
    print("   Looking for sudden rises similar to flood control pattern")
    print("="*80)
    
    # Run all analyses
    total_data = await compare_total_budget()
    category_data = await compare_infrastructure_categories()
    regional_data = await compare_regional_distribution()
    new_items = await find_new_large_items_2026()
    
    # Generate comprehensive report
    await generate_comprehensive_report(total_data, category_data, regional_data, new_items)
    
    print("\n✅ Analysis complete!")
    print("\n💡 Key Insight:")
    print("   NEP 2026 is the PROPOSED budget, while Budget 2017-2025 are ACTUAL enacted budgets.")
    print("   Sudden rises in NEP 2026 compared to historical actuals may indicate")
    print("   new discretionary spending channels requiring further scrutiny.")

if __name__ == "__main__":
    asyncio.run(main())


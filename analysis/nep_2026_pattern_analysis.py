#!/usr/bin/env python3
"""
NEP 2026 Pattern Analysis Script
Analyzes NEP 2026 budget data for patterns similar to flood control budget clustering
"""

import asyncio
import os
import json
from collections import defaultdict
from decimal import Decimal
import asyncpg

# Keywords that might indicate infrastructure projects prone to discretionary spending
INFRASTRUCTURE_KEYWORDS = [
    'flood', 'drainage', 'pumping', 'river', 'estero', 'creek', 'canal', 
    'road', 'bridge', 'infrastructure', 'construction', 'rehabilitation',
    'upgrading', 'improvement', 'development', 'mitigation', 'control',
    'facility', 'structure', 'system', 'project', 'program', 'slope protection',
    'river bank', 'dam', 'irrigation', 'water', 'dike', 'revetment'
]

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

async def analyze_geographic_clustering():
    """
    Analyze geographic clustering patterns in NEP 2026
    Similar to the 60% concentration in 3 provinces pattern
    """
    print("\n" + "="*80)
    print("🗺️  GEOGRAPHIC CLUSTERING ANALYSIS - NEP 2026")
    print("="*80)
    
    conn = await get_db_connection()
    if not conn:
        return None
    
    try:
        # Get regional distribution
        query = """
        SELECT 
            COALESCE(region_code, 'UNKNOWN') as region,
            COUNT(*) as project_count,
            SUM(amount) as total_amount,
            AVG(amount) as avg_amount,
            MIN(amount) as min_amount,
            MAX(amount) as max_amount
        FROM budget_2026
        WHERE amount IS NOT NULL AND amount > 0
        GROUP BY region_code
        ORDER BY total_amount DESC
        LIMIT 20
        """
        
        results = await conn.fetch(query)
        
        if not results:
            print("❌ No data found")
            return None
        
        # Calculate total for percentage
        total_count = sum(r['project_count'] for r in results)
        total_amount = sum(float(r['total_amount']) for r in results)
        
        # Check for clustering pattern (top 3 regions)
        top_3_count = sum(r['project_count'] for r in results[:3])
        top_3_amount = sum(float(r['total_amount']) for r in results[:3])
        top_3_percentage = (top_3_count / total_count * 100) if total_count > 0 else 0
        top_3_amount_percentage = (top_3_amount / total_amount * 100) if total_amount > 0 else 0
        
        print(f"\n📊 Top 20 Regions by Budget Allocation:")
        print(f"\n{'Rank':<6} {'Region':<15} {'Projects':<12} {'Total Budget':<20} {'Avg Budget':<18} {'% of Total'}")
        print("-" * 95)
        
        for idx, row in enumerate(results, 1):
            count_pct = (row['project_count'] / total_count * 100) if total_count > 0 else 0
            amount_pct = (float(row['total_amount']) / total_amount * 100) if total_amount > 0 else 0
            
            print(f"{idx:<6} {row['region']:<15} {row['project_count']:<12,} ₱{float(row['total_amount']):>17,.0f} ₱{float(row['avg_amount']):>15,.0f} {amount_pct:>6.1f}%")
        
        print("\n" + "="*80)
        print("🚨 CLUSTERING PATTERN ANALYSIS:")
        print("="*80)
        print(f"Top 3 regions: {top_3_percentage:.1f}% of all projects ({top_3_count:,} items)")
        print(f"Top 3 regions: {top_3_amount_percentage:.1f}% of total budget (₱{top_3_amount:,.0f})")
        
        # Flag if similar to flood control pattern (60% in 3 regions)
        if top_3_percentage >= 50:
            print(f"\n⚠️  WARNING: High geographic concentration detected!")
            print(f"   Similar to flood control pattern: {top_3_percentage:.1f}% vs 60% benchmark")
        
        return {
            'top_3_percentage': top_3_percentage,
            'top_3_amount_percentage': top_3_amount_percentage,
            'top_regions': results[:3],
            'all_regions': results
        }
        
    finally:
        await conn.close()

async def analyze_infrastructure_keywords():
    """
    Find budget items with infrastructure-related keywords
    These could be similar to flood control projects
    """
    print("\n" + "="*80)
    print("🏗️  INFRASTRUCTURE KEYWORD ANALYSIS - NEP 2026")
    print("="*80)
    
    conn = await get_db_connection()
    if not conn:
        return None
    
    try:
        keyword_results = {}
        
        for keyword in INFRASTRUCTURE_KEYWORDS:
            query = f"""
            SELECT 
                description,
                amount,
                org_uacs_code,
                region_code
            FROM budget_2026
            WHERE LOWER(description) LIKE LOWER('%{keyword}%')
            AND amount IS NOT NULL AND amount > 0
            ORDER BY amount DESC
            LIMIT 5
            """
            
            results = await conn.fetch(query)
            
            if results:
                keyword_results[keyword] = {
                    'count': len(results),
                    'total': sum(float(r['amount']) for r in results),
                    'examples': results[:3]
                }
        
        # Get overall statistics for infrastructure items
        all_keywords_condition = " OR ".join([f"LOWER(description) LIKE LOWER('%{kw}%')" for kw in INFRASTRUCTURE_KEYWORDS])
        
        stats_query = f"""
        SELECT 
            COUNT(*) as total_items,
            SUM(amount) as total_amount,
            AVG(amount) as avg_amount,
            MAX(amount) as max_amount,
            COUNT(DISTINCT region_code) as regions_count,
            COUNT(DISTINCT org_uacs_code) as departments_count
        FROM budget_2026
        WHERE ({all_keywords_condition})
        AND amount IS NOT NULL AND amount > 0
        """
        
        overall_stats = await conn.fetchrow(stats_query)
        
        # Get total budget for comparison
        total_query = """
        SELECT 
            COUNT(*) as all_items,
            SUM(amount) as all_amount
        FROM budget_2026
        WHERE amount IS NOT NULL AND amount > 0
        """
        total_stats = await conn.fetchrow(total_query)
        
        print(f"\n📊 Infrastructure-Related Budget Items:")
        print(f"\nTotal Items Found: {overall_stats['total_items']:,}")
        print(f"Total Budget: ₱{float(overall_stats['total_amount']):,.0f}")
        print(f"Average Amount: ₱{float(overall_stats['avg_amount']):,.0f}")
        print(f"Max Amount: ₱{float(overall_stats['max_amount']):,.0f}")
        print(f"Regions Involved: {overall_stats['regions_count']}")
        print(f"Departments Involved: {overall_stats['departments_count']}")
        
        infra_percentage = (overall_stats['total_items'] / total_stats['all_items'] * 100) if total_stats['all_items'] > 0 else 0
        infra_amount_percentage = (float(overall_stats['total_amount']) / float(total_stats['all_amount']) * 100) if total_stats['all_amount'] > 0 else 0
        
        print(f"\n% of Total Items: {infra_percentage:.2f}%")
        print(f"% of Total Budget: {infra_amount_percentage:.2f}%")
        
        # Show top keywords by count
        print(f"\n\n🔍 Top Keywords by Occurrence:")
        print(f"\n{'Keyword':<20} {'Count':<10} {'Total Budget':<20}")
        print("-" * 50)
        
        sorted_keywords = sorted(keyword_results.items(), key=lambda x: x[1]['count'], reverse=True)[:15]
        for keyword, data in sorted_keywords:
            print(f"{keyword:<20} {data['count']:<10} ₱{data['total']:>17,.0f}")
        
        return {
            'overall_stats': overall_stats,
            'percentage': infra_percentage,
            'amount_percentage': infra_amount_percentage,
            'keyword_results': keyword_results
        }
        
    finally:
        await conn.close()

async def analyze_duplicate_patterns():
    """
    Analyze duplicate or highly similar budget line items
    Similar to the systematic budget line item mapping in flood control
    """
    print("\n" + "="*80)
    print("🔄 DUPLICATE/SIMILAR BUDGET LINE ITEMS - NEP 2026")
    print("="*80)
    
    conn = await get_db_connection()
    if not conn:
        return None
    
    try:
        # Find items with identical descriptions and amounts (exact duplicates)
        duplicates_query = """
        SELECT 
            description,
            amount,
            COUNT(*) as occurrence_count,
            SUM(amount) as total_amount,
            array_agg(DISTINCT region_code) as regions,
            array_agg(DISTINCT org_uacs_code) as departments
        FROM budget_2026
        WHERE description IS NOT NULL 
        AND amount IS NOT NULL AND amount > 0
        GROUP BY description, amount
        HAVING COUNT(*) > 1
        ORDER BY COUNT(*) DESC, amount DESC
        LIMIT 50
        """
        
        duplicates = await conn.fetch(duplicates_query)
        
        if duplicates:
            print(f"\n📋 Found {len(duplicates)} duplicate budget line items")
            print(f"\n{'Count':<8} {'Amount':<18} {'Total Value':<18} {'Regions':<10} {'Description'[:50]}")
            print("-" * 120)
            
            for dup in duplicates[:20]:
                desc = dup['description'][:50] if dup['description'] else 'N/A'
                regions_count = len(set(dup['regions'])) if dup['regions'] else 0
                print(f"{dup['occurrence_count']:<8} ₱{float(dup['amount']):>15,.0f} ₱{float(dup['total_amount']):>15,.0f} {regions_count:<10} {desc}")
        
        # Find high-value items (potential for discretionary spending)
        high_value_query = """
        SELECT 
            description,
            amount,
            region_code,
            org_uacs_code
        FROM budget_2026
        WHERE amount > 10000000  -- Over 10 million pesos
        ORDER BY amount DESC
        LIMIT 100
        """
        
        high_value_items = await conn.fetch(high_value_query)
        
        print(f"\n\n💰 High-Value Budget Items (>₱10M):")
        print(f"\nTotal: {len(high_value_items)} items")
        print(f"\n{'Amount':<18} {'Region':<12} {'Department':<15} {'Description'[:45]}")
        print("-" * 120)
        
        for item in high_value_items[:25]:
            desc = item['description'][:45] if item['description'] else 'N/A'
            region = item['region_code'] if item['region_code'] else 'N/A'
            dept = item['org_uacs_code'] if item['org_uacs_code'] else 'N/A'
            print(f"₱{float(item['amount']):>15,.0f} {region:<12} {dept:<15} {desc}")
        
        return {
            'duplicates': duplicates,
            'high_value_items': high_value_items
        }
        
    finally:
        await conn.close()

async def analyze_cost_distribution():
    """
    Analyze cost distribution patterns
    Similar to Manila projects averaging ₱54M while others average ₱20M
    """
    print("\n" + "="*80)
    print("💵 COST DISTRIBUTION ANALYSIS - NEP 2026")
    print("="*80)
    
    conn = await get_db_connection()
    if not conn:
        return None
    
    try:
        # Get cost statistics by region
        query = """
        SELECT 
            COALESCE(region_code, 'UNKNOWN') as region,
            COUNT(*) as item_count,
            AVG(amount) as avg_amount,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY amount) as median_amount,
            MIN(amount) as min_amount,
            MAX(amount) as max_amount,
            SUM(amount) as total_amount
        FROM budget_2026
        WHERE amount IS NOT NULL AND amount > 0
        GROUP BY region_code
        HAVING COUNT(*) >= 10  -- At least 10 items for meaningful statistics
        ORDER BY avg_amount DESC
        LIMIT 20
        """
        
        results = await conn.fetch(query)
        
        if results:
            print(f"\n📊 Cost Distribution by Region (Top 20):")
            print(f"\n{'Region':<15} {'Items':<10} {'Average':<18} {'Median':<18} {'Min':<15} {'Max':<18}")
            print("-" * 110)
            
            avg_amounts = []
            for row in results:
                avg_amounts.append(float(row['avg_amount']))
                print(f"{row['region']:<15} {row['item_count']:<10,} ₱{float(row['avg_amount']):>15,.0f} "
                      f"₱{float(row['median_amount']):>15,.0f} ₱{float(row['min_amount']):>12,.0f} "
                      f"₱{float(row['max_amount']):>15,.0f}")
            
            # Calculate disparity
            if len(avg_amounts) >= 2:
                highest_avg = max(avg_amounts)
                lowest_avg = min(avg_amounts)
                disparity_ratio = highest_avg / lowest_avg if lowest_avg > 0 else 0
                
                print(f"\n\n🚨 COST DISPARITY ANALYSIS:")
                print(f"Highest Regional Average: ₱{highest_avg:,.0f}")
                print(f"Lowest Regional Average: ₱{lowest_avg:,.0f}")
                print(f"Disparity Ratio: {disparity_ratio:.2f}x")
                
                if disparity_ratio >= 2.5:
                    print(f"\n⚠️  WARNING: High cost disparity detected!")
                    print(f"   Similar to flood control pattern: {disparity_ratio:.2f}x vs 2.6x benchmark")
        
        return results
        
    finally:
        await conn.close()

async def analyze_department_concentration():
    """
    Analyze which departments have the highest concentration of budget
    """
    print("\n" + "="*80)
    print("🏛️  DEPARTMENT CONCENTRATION ANALYSIS - NEP 2026")
    print("="*80)
    
    conn = await get_db_connection()
    if not conn:
        return None
    
    try:
        query = """
        SELECT 
            COALESCE(org_uacs_code, 'UNKNOWN') as department,
            COUNT(*) as item_count,
            SUM(amount) as total_amount,
            AVG(amount) as avg_amount,
            MAX(amount) as max_amount,
            COUNT(DISTINCT region_code) as regions_covered
        FROM budget_2026
        WHERE amount IS NOT NULL AND amount > 0
        GROUP BY org_uacs_code
        ORDER BY total_amount DESC
        LIMIT 20
        """
        
        results = await conn.fetch(query)
        
        # Calculate total for percentage
        total_amount = sum(float(r['total_amount']) for r in results)
        
        print(f"\n📊 Top 20 Departments by Budget Allocation:")
        print(f"\n{'Rank':<6} {'Department':<15} {'Items':<10} {'Total Budget':<20} {'Regions':<10} {'% of Top 20'}")
        print("-" * 90)
        
        for idx, row in enumerate(results, 1):
            pct = (float(row['total_amount']) / total_amount * 100) if total_amount > 0 else 0
            print(f"{idx:<6} {row['department']:<15} {row['item_count']:<10,} ₱{float(row['total_amount']):>17,.0f} "
                  f"{row['regions_covered']:<10} {pct:>6.1f}%")
        
        # Check for concentration
        top_3_amount = sum(float(r['total_amount']) for r in results[:3])
        top_3_percentage = (top_3_amount / total_amount * 100) if total_amount > 0 else 0
        
        print(f"\n🚨 CONCENTRATION ANALYSIS:")
        print(f"Top 3 departments control: {top_3_percentage:.1f}% of top 20 budget")
        
        if top_3_percentage >= 60:
            print(f"\n⚠️  WARNING: High department concentration detected!")
        
        return results
        
    finally:
        await conn.close()

async def generate_summary_report(clustering_data, infra_data, duplicates_data, cost_data, dept_data):
    """
    Generate a comprehensive summary report of all findings
    """
    print("\n" + "="*80)
    print("📑 COMPREHENSIVE SUMMARY REPORT - NEP 2026 PATTERN ANALYSIS")
    print("="*80)
    
    print("\n🔍 KEY FINDINGS:\n")
    
    # Finding 1: Geographic Clustering
    if clustering_data:
        print("1️⃣  GEOGRAPHIC CLUSTERING")
        print(f"   • Top 3 regions: {clustering_data['top_3_percentage']:.1f}% of all budget items")
        print(f"   • Budget concentration: {clustering_data['top_3_amount_percentage']:.1f}% in top 3 regions")
        if clustering_data['top_3_percentage'] >= 50:
            print(f"   ⚠️  ALERT: Pattern similar to flood control clustering (60% benchmark)")
        print()
    
    # Finding 2: Infrastructure Keywords
    if infra_data:
        print("2️⃣  INFRASTRUCTURE-RELATED SPENDING")
        print(f"   • {infra_data['percentage']:.2f}% of budget items are infrastructure-related")
        print(f"   • Total infrastructure budget: ₱{float(infra_data['overall_stats']['total_amount']):,.0f}")
        print(f"   • {infra_data['overall_stats']['regions_count']} regions involved")
        print()
    
    # Finding 3: Duplicates
    if duplicates_data:
        print("3️⃣  DUPLICATE BUDGET LINE ITEMS")
        print(f"   • Found {len(duplicates_data['duplicates'])} duplicate line item patterns")
        print(f"   • {len(duplicates_data['high_value_items'])} high-value items (>₱10M)")
        if duplicates_data['duplicates']:
            top_dup = duplicates_data['duplicates'][0]
            print(f"   • Most frequent: {top_dup['occurrence_count']} occurrences")
        print()
    
    # Finding 4: Cost Distribution
    if cost_data and len(cost_data) >= 2:
        print("4️⃣  COST DISTRIBUTION PATTERNS")
        highest = max(float(r['avg_amount']) for r in cost_data)
        lowest = min(float(r['avg_amount']) for r in cost_data)
        ratio = highest / lowest if lowest > 0 else 0
        print(f"   • Cost disparity ratio: {ratio:.2f}x")
        print(f"   • Highest regional average: ₱{highest:,.0f}")
        print(f"   • Lowest regional average: ₱{lowest:,.0f}")
        if ratio >= 2.5:
            print(f"   ⚠️  ALERT: Similar to flood control disparity (2.6x benchmark)")
        print()
    
    # Finding 5: Department Concentration
    if dept_data:
        print("5️⃣  DEPARTMENT CONCENTRATION")
        total = sum(float(r['total_amount']) for r in dept_data)
        top_3 = sum(float(r['total_amount']) for r in dept_data[:3])
        pct = (top_3 / total * 100) if total > 0 else 0
        print(f"   • Top 3 departments: {pct:.1f}% of analyzed budget")
        print()
    
    print("\n" + "="*80)
    print("⚠️  OVERALL RISK ASSESSMENT")
    print("="*80)
    
    risk_factors = []
    
    if clustering_data and clustering_data['top_3_percentage'] >= 50:
        risk_factors.append("High geographic clustering")
    
    if infra_data and infra_data['percentage'] >= 20:
        risk_factors.append("Significant infrastructure spending")
    
    if duplicates_data and len(duplicates_data['duplicates']) >= 30:
        risk_factors.append("High number of duplicate line items")
    
    if cost_data and len(cost_data) >= 2:
        ratio = max(float(r['avg_amount']) for r in cost_data) / min(float(r['avg_amount']) for r in cost_data)
        if ratio >= 2.5:
            risk_factors.append("High cost disparity between regions")
    
    if risk_factors:
        print("\n🚨 Risk Factors Detected:")
        for i, factor in enumerate(risk_factors, 1):
            print(f"   {i}. {factor}")
        
        print(f"\n📊 Risk Level: {'HIGH' if len(risk_factors) >= 3 else 'MODERATE' if len(risk_factors) >= 2 else 'LOW'}")
        print(f"   ({len(risk_factors)}/{4} critical patterns match flood control scheme)")
    else:
        print("\n✅ No significant risk patterns detected")
    
    print("\n" + "="*80)

async def main():
    """
    Main analysis function
    """
    print("\n" + "="*80)
    print("🔬 NEP 2026 PATTERN ANALYSIS")
    print("   Analyzing for patterns similar to flood control budget clustering")
    print("="*80)
    
    # Run all analyses
    clustering_data = await analyze_geographic_clustering()
    infra_data = await analyze_infrastructure_keywords()
    duplicates_data = await analyze_duplicate_patterns()
    cost_data = await analyze_cost_distribution()
    dept_data = await analyze_department_concentration()
    
    # Generate comprehensive summary
    await generate_summary_report(clustering_data, infra_data, duplicates_data, cost_data, dept_data)
    
    print("\n✅ Analysis complete!")
    print("\n💡 Note: These patterns indicate potential areas requiring further investigation.")
    print("   High clustering or duplication patterns alone do not prove fraud,")
    print("   but warrant detailed audit and verification of actual project implementation.")

if __name__ == "__main__":
    asyncio.run(main())


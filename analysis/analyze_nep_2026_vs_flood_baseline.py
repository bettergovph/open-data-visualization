#!/usr/bin/env python3
"""
NEP 2026 Analysis Using Flood Control Baseline Pattern
================================================================================
Uses the known flood control scheme patterns as a baseline to identify
similar suspicious patterns in NEP 2026 compared to Budget history.

FLOOD CONTROL BASELINE PATTERNS (from actual data):
1. Geographic Clustering: Bulacan dominance
   - 2022: 145 projects, ₱7.8B
   - 2023: 263 projects, ₱17.0B (+118% growth)
   - 2024: 248 projects, ₱18.2B

2. Sudden Rise Pattern:
   - 2021: 51 projects
   - 2022: 145 projects (+184% YoY)
   - 2023: 263 projects (+81% YoY)

3. Cost Disparity: Manila avg ₱54M vs others ₱20M (2.6x ratio)

4. Geographic Concentration: 60% in 3 provinces
================================================================================
"""

import asyncio
import os
import json
from collections import defaultdict
from decimal import Decimal
import asyncpg
from dotenv import load_dotenv

load_dotenv()

# FLOOD CONTROL BASELINE METRICS (extracted from actual data)
FLOOD_BASELINE = {
    'geographic_clustering': {
        'top_3_provinces_percentage': 60,  # 60% in 3 provinces
        'description': 'Manila, Nueva Ecija, Tarlac concentration'
    },
    'sudden_rise_pattern': {
        'bulacan_2022_2023_growth': 118,  # 118% growth from 2022 to 2023
        'typical_yoy_growth': 81,  # 81% year-over-year growth
        'threshold': 50  # Consider 50%+ YoY growth as suspicious
    },
    'cost_disparity': {
        'urban_vs_rural_ratio': 2.6,  # Manila ₱54M vs others ₱20M
        'threshold': 2.5  # Ratio above 2.5x is suspicious
    },
    'budget_line_mapping': {
        'confidence_level': 95,  # 95% confidence in systematic allocation
        'clustering_percentage': 74  # 74% of projects mapped to budget lines
    }
}

# Keywords for infrastructure categories (same as flood control)
INFRASTRUCTURE_KEYWORDS = {
    'flood_control': ['flood', 'drainage', 'pumping', 'estero', 'river control', 'creek', 'dike'],
    'road_infrastructure': ['road', 'bridge', 'highway'],
    'water_systems': ['water', 'irrigation', 'dam', 'canal'],
    'building_construction': ['building', 'construction', 'facility'],
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

def print_flood_baseline():
    """Display the flood control baseline metrics"""
    print("\n" + "="*80)
    print("📊 FLOOD CONTROL BASELINE PATTERN (Reference)")
    print("="*80)
    
    print("\n🗺️  Geographic Clustering:")
    print(f"   • {FLOOD_BASELINE['geographic_clustering']['top_3_provinces_percentage']}% of projects concentrated in 3 provinces")
    print(f"   • {FLOOD_BASELINE['geographic_clustering']['description']}")
    
    print("\n📈 Sudden Rise Pattern:")
    print(f"   • Bulacan 2022→2023: +{FLOOD_BASELINE['sudden_rise_pattern']['bulacan_2022_2023_growth']}% growth")
    print(f"   • Typical YoY growth: +{FLOOD_BASELINE['sudden_rise_pattern']['typical_yoy_growth']}%")
    print(f"   • Threshold for alert: ≥{FLOOD_BASELINE['sudden_rise_pattern']['threshold']}% YoY")
    
    print("\n💰 Cost Disparity:")
    print(f"   • Urban vs Rural ratio: {FLOOD_BASELINE['cost_disparity']['urban_vs_rural_ratio']}x")
    print(f"   • Threshold for alert: ≥{FLOOD_BASELINE['cost_disparity']['threshold']}x")
    
    print("\n🎯 Budget Line Mapping:")
    print(f"   • Confidence level: {FLOOD_BASELINE['budget_line_mapping']['confidence_level']}%")
    print(f"   • Project clustering: {FLOOD_BASELINE['budget_line_mapping']['clustering_percentage']}%")
    
    print("\n" + "="*80)

async def analyze_yoy_growth_pattern():
    """
    Analyze year-over-year growth in Budget history and NEP 2026
    Compare against flood control's sudden rise pattern
    """
    print("\n" + "="*80)
    print("📈 YEAR-OVER-YEAR GROWTH ANALYSIS (Budget 2020-2025 vs NEP 2026)")
    print("="*80)
    
    budget_conn = await get_budget_db_connection()
    nep_conn = await get_nep_db_connection()
    
    if not budget_conn or not nep_conn:
        return None
    
    try:
        years_data = []
        
        # Get Budget data for 2020-2025 (2017-2019 have different schema)
        for year in range(2020, 2026):
            # Check if table exists
            table_check = await budget_conn.fetchval("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = $1
                )
            """, f"budget_{year}")
            
            if not table_check:
                print(f"   ⚠️  Budget table for {year} not found, skipping...")
                continue
            
            query = f"""
            SELECT 
                COUNT(*) as item_count,
                SUM(amt) as total_amount
            FROM budget_{year}
            WHERE amt IS NOT NULL AND amt > 0
            """
            
            result = await budget_conn.fetchrow(query)
            
            if result:
                years_data.append({
                    'year': year,
                    'count': result['item_count'],
                    'total': float(result['total_amount'])
                })
        
        # Get NEP 2026 data
        query_2026 = """
        SELECT 
            COUNT(*) as item_count,
            SUM(amount) as total_amount
        FROM budget_2026
        WHERE amount IS NOT NULL AND amount > 0
        """
        
        result_2026 = await nep_conn.fetchrow(query_2026)
        
        if result_2026:
            years_data.append({
                'year': 2026,
                'count': result_2026['item_count'],
                'total': float(result_2026['total_amount'])
            })
        
        # Calculate and display growth rates
        print(f"\n{'Year':<8} {'Total Budget':<20} {'YoY Growth':<15} {'vs Flood Baseline'}")
        print("-" * 75)
        
        max_growth = 0
        max_growth_year = None
        flood_like_years = []
        
        for i, data in enumerate(years_data):
            if i > 0:
                prev_total = years_data[i-1]['total']
                growth = ((data['total'] - prev_total) / prev_total * 100) if prev_total > 0 else 0
                growth_str = f"{growth:+.1f}%"
                
                # Compare against flood baseline
                if abs(growth) >= FLOOD_BASELINE['sudden_rise_pattern']['threshold']:
                    flood_comparison = "⚠️  MATCHES FLOOD PATTERN"
                    flood_like_years.append({
                        'year': data['year'],
                        'growth': growth
                    })
                else:
                    flood_comparison = "Normal"
                
                if abs(growth) > abs(max_growth):
                    max_growth = growth
                    max_growth_year = data['year']
            else:
                growth_str = "baseline"
                flood_comparison = "N/A"
            
            marker = "🔴" if data['year'] == 2026 else "  "
            print(f"{marker} {data['year']:<6} ₱{data['total']:>17,.0f} {growth_str:<15} {flood_comparison}")
        
        # Summary analysis
        print("\n" + "="*80)
        print("🚨 SUDDEN RISE DETECTION SUMMARY:")
        print("="*80)
        
        if flood_like_years:
            print(f"\nFound {len(flood_like_years)} year(s) with flood-like sudden rises:")
            for fy in flood_like_years:
                print(f"   • {fy['year']}: {fy['growth']:+.1f}% growth")
                if fy['year'] == 2026:
                    print(f"     🔴 ALERT: NEP 2026 shows flood control pattern!")
        else:
            print("\n✅ No flood-like sudden rises detected")
        
        print(f"\nFlood Baseline Threshold: ≥{FLOOD_BASELINE['sudden_rise_pattern']['threshold']}% YoY growth")
        print(f"Flood 2022→2023 Reference: +{FLOOD_BASELINE['sudden_rise_pattern']['bulacan_2022_2023_growth']}% (Bulacan)")
        
        return {'years_data': years_data, 'flood_like_years': flood_like_years}
        
    finally:
        await budget_conn.close()
        await nep_conn.close()

async def analyze_geographic_clustering():
    """
    Analyze geographic clustering in NEP 2026
    Compare against flood control's 60% in 3 provinces pattern
    """
    print("\n" + "="*80)
    print("🗺️  GEOGRAPHIC CLUSTERING ANALYSIS (NEP 2026 vs Budget 2025)")
    print("="*80)
    
    budget_conn = await get_budget_db_connection()
    nep_conn = await get_nep_db_connection()
    
    if not budget_conn or not nep_conn:
        return None
    
    try:
        # Get Budget 2025 regional distribution (using agency as proxy)
        query_2025 = """
        SELECT 
            COALESCE(CAST(agency AS TEXT), 'UNKNOWN') as region,
            COUNT(*) as item_count,
            SUM(amt) as total_amount
        FROM budget_2025
        WHERE amt IS NOT NULL AND amt > 0
        GROUP BY agency
        ORDER BY COUNT(*) DESC
        """
        
        results_2025 = await budget_conn.fetch(query_2025)
        total_2025 = sum(r['item_count'] for r in results_2025)
        top_3_2025 = sum(r['item_count'] for r in results_2025[:3])
        top_3_percentage_2025 = (top_3_2025 / total_2025 * 100) if total_2025 > 0 else 0
        
        # Get NEP 2026 regional distribution
        query_2026 = """
        SELECT 
            COALESCE(region_code, 'UNKNOWN') as region,
            COUNT(*) as item_count,
            SUM(amount) as total_amount
        FROM budget_2026
        WHERE amount IS NOT NULL AND amount > 0
        GROUP BY region_code
        ORDER BY COUNT(*) DESC
        """
        
        results_2026 = await nep_conn.fetch(query_2026)
        total_2026 = sum(r['item_count'] for r in results_2026)
        top_3_2026 = sum(r['item_count'] for r in results_2026[:3])
        top_3_percentage_2026 = (top_3_2026 / total_2026 * 100) if total_2026 > 0 else 0
        
        print(f"\nBudget 2025:")
        print(f"   Top 3 regions/agencies: {top_3_percentage_2025:.1f}% of all items ({top_3_2025:,} items)")
        print(f"   Top regions: {', '.join(r['region'] for r in results_2025[:3])}")
        
        print(f"\nNEP 2026:")
        print(f"   Top 3 regions: {top_3_percentage_2026:.1f}% of all items ({top_3_2026:,} items)")
        print(f"   Top regions: {', '.join(r['region'] for r in results_2026[:3])}")
        
        # Compare against flood baseline
        flood_threshold = FLOOD_BASELINE['geographic_clustering']['top_3_provinces_percentage']
        
        print(f"\n🔍 Comparison vs Flood Baseline:")
        print(f"   Flood baseline: {flood_threshold}% in top 3 provinces")
        print(f"   Budget 2025: {top_3_percentage_2025:.1f}%")
        print(f"   NEP 2026: {top_3_percentage_2026:.1f}%")
        
        if top_3_percentage_2026 >= flood_threshold:
            print(f"\n   ⚠️  ALERT: NEP 2026 shows flood-like geographic clustering!")
        elif top_3_percentage_2026 >= (flood_threshold * 0.8):  # Within 80% of threshold
            print(f"\n   ⚠️  WARNING: NEP 2026 approaching flood-like clustering ({top_3_percentage_2026:.1f}% vs {flood_threshold}%)")
        else:
            print(f"\n   ✅ NEP 2026 clustering below flood baseline threshold")
        
        return {
            'budget_2025': top_3_percentage_2025,
            'nep_2026': top_3_percentage_2026,
            'flood_baseline': flood_threshold,
            'matches_flood_pattern': top_3_percentage_2026 >= flood_threshold
        }
        
    finally:
        await budget_conn.close()
        await nep_conn.close()

async def analyze_infrastructure_spending():
    """
    Analyze infrastructure spending patterns in NEP 2026 vs Budget history
    Focus on flood control and similar categories
    """
    print("\n" + "="*80)
    print("🏗️  INFRASTRUCTURE SPENDING ANALYSIS (Budget 2020-2025 vs NEP 2026)")
    print("="*80)
    
    budget_conn = await get_budget_db_connection()
    nep_conn = await get_nep_db_connection()
    
    if not budget_conn or not nep_conn:
        return None
    
    try:
        category_analysis = {}
        
        for category, keywords in INFRASTRUCTURE_KEYWORDS.items():
            print(f"\n📊 {category.replace('_', ' ').title()}")
            print("-" * 80)
            
            historical_data = []
            
            # Get Budget historical data (2020-2025)
            for year in range(2020, 2026):
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
                    historical_data.append({
                        'year': year,
                        'count': result['item_count'],
                        'total': float(result['total_amount'])
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
                nep_2026_data = {
                    'year': 2026,
                    'count': result_2026['item_count'],
                    'total': float(result_2026['total_amount'])
                }
            else:
                nep_2026_data = {'year': 2026, 'count': 0, 'total': 0.0}
            
            # Calculate historical average and growth
            if historical_data:
                avg_historical = sum(d['total'] for d in historical_data) / len(historical_data)
                latest_budget = historical_data[-1]['total']
                
                vs_avg = ((nep_2026_data['total'] - avg_historical) / avg_historical * 100) if avg_historical > 0 else 0
                vs_latest = ((nep_2026_data['total'] - latest_budget) / latest_budget * 100) if latest_budget > 0 else 0
                
                print(f"{'Year':<8} {'Total Budget':<20}")
                print("-" * 40)
                for data in historical_data:
                    print(f"{data['year']:<8} ₱{data['total']:>17,.0f}")
                print(f"2026*    ₱{nep_2026_data['total']:>17,.0f}")
                
                print(f"\n   Historical Avg (2020-2025): ₱{avg_historical:,.0f}")
                print(f"   NEP 2026: ₱{nep_2026_data['total']:,.0f}")
                print(f"   vs Historical Avg: {vs_avg:+.1f}%")
                print(f"   vs Budget 2025: {vs_latest:+.1f}%")
                
                # Check against flood baseline
                if vs_avg >= FLOOD_BASELINE['sudden_rise_pattern']['threshold']:
                    print(f"\n   ⚠️  ALERT: Matches flood sudden rise pattern (+{vs_avg:.1f}% vs {FLOOD_BASELINE['sudden_rise_pattern']['threshold']}% threshold)")
                    category_analysis[category] = {'alert': True, 'growth': vs_avg}
                elif vs_avg >= (FLOOD_BASELINE['sudden_rise_pattern']['threshold'] * 0.7):
                    print(f"\n   ⚠️  WARNING: Approaching flood pattern ({vs_avg:+.1f}%)")
                    category_analysis[category] = {'alert': False, 'growth': vs_avg}
            else:
                print("   No historical data available for comparison")
        
        return category_analysis
        
    finally:
        await budget_conn.close()
        await nep_conn.close()

async def generate_final_assessment(yoy_data, clustering_data, infra_data):
    """
    Generate final risk assessment comparing NEP 2026 against flood control baseline
    """
    print("\n" + "="*80)
    print("📑 FINAL RISK ASSESSMENT: NEP 2026 vs FLOOD CONTROL BASELINE")
    print("="*80)
    
    risk_indicators = []
    
    # Check YoY growth pattern
    if yoy_data and yoy_data.get('flood_like_years'):
        for fy in yoy_data['flood_like_years']:
            if fy['year'] == 2026:
                risk_indicators.append({
                    'category': 'Sudden Rise Pattern',
                    'severity': 'HIGH',
                    'detail': f"NEP 2026 shows {fy['growth']:+.1f}% growth (flood baseline: ≥{FLOOD_BASELINE['sudden_rise_pattern']['threshold']}%)"
                })
    
    # Check geographic clustering
    if clustering_data and clustering_data.get('matches_flood_pattern'):
        risk_indicators.append({
            'category': 'Geographic Clustering',
            'severity': 'HIGH',
            'detail': f"{clustering_data['nep_2026']:.1f}% in top 3 regions (flood baseline: {clustering_data['flood_baseline']}%)"
        })
    elif clustering_data and clustering_data['nep_2026'] >= (clustering_data['flood_baseline'] * 0.8):
        risk_indicators.append({
            'category': 'Geographic Clustering',
            'severity': 'MODERATE',
            'detail': f"{clustering_data['nep_2026']:.1f}% in top 3 regions (approaching {clustering_data['flood_baseline']}% threshold)"
        })
    
    # Check infrastructure categories
    if infra_data:
        high_alert_categories = [cat for cat, data in infra_data.items() if data.get('alert')]
        if high_alert_categories:
            for cat in high_alert_categories:
                risk_indicators.append({
                    'category': f'Infrastructure: {cat.replace("_", " ").title()}',
                    'severity': 'HIGH',
                    'detail': f"+{infra_data[cat]['growth']:.1f}% growth (flood baseline: ≥{FLOOD_BASELINE['sudden_rise_pattern']['threshold']}%)"
                })
    
    # Display findings
    print("\n🔍 Risk Indicators Found:")
    print("-" * 80)
    
    if risk_indicators:
        high_severity = [r for r in risk_indicators if r['severity'] == 'HIGH']
        moderate_severity = [r for r in risk_indicators if r['severity'] == 'MODERATE']
        
        if high_severity:
            print("\n🚨 HIGH SEVERITY INDICATORS:")
            for i, indicator in enumerate(high_severity, 1):
                print(f"   {i}. {indicator['category']}")
                print(f"      {indicator['detail']}")
        
        if moderate_severity:
            print("\n⚠️  MODERATE SEVERITY INDICATORS:")
            for i, indicator in enumerate(moderate_severity, 1):
                print(f"   {i}. {indicator['category']}")
                print(f"      {indicator['detail']}")
        
        # Overall risk score
        risk_score = len(high_severity) * 3 + len(moderate_severity) * 1
        
        if risk_score >= 6:
            risk_level = "CRITICAL"
            color = "🔴"
        elif risk_score >= 3:
            risk_level = "HIGH"
            color = "🟠"
        elif risk_score >= 1:
            risk_level = "MODERATE"
            color = "🟡"
        else:
            risk_level = "LOW"
            color = "🟢"
        
        print(f"\n" + "="*80)
        print(f"{color} OVERALL RISK LEVEL: {risk_level}")
        print(f"   Risk Score: {risk_score} (High: {len(high_severity)}, Moderate: {len(moderate_severity)})")
        print("="*80)
        
        if risk_score >= 3:
            print("\n💡 RECOMMENDATION:")
            print("   NEP 2026 exhibits patterns similar to the flood control scheme.")
            print("   Recommend detailed investigation of:")
            print("   • Specific budget line items with sudden increases")
            print("   • Geographic distribution and beneficiary provinces")
            print("   • Project descriptions and implementation plans")
            print("   • Contractor selection and award processes")
            print("   • Comparison with actual infrastructure needs vs budget allocation")
    else:
        print("\n✅ No significant flood-like patterns detected in NEP 2026")
        print("   NEP 2026 appears to follow normal budget growth patterns")
    
    print("\n" + "="*80)

async def main():
    """
    Main analysis function
    """
    print("\n" + "="*80)
    print("🔬 NEP 2026 ANALYSIS USING FLOOD CONTROL BASELINE")
    print("="*80)
    print("\nThis analysis uses the known flood control scheme patterns as a baseline")
    print("to identify similar suspicious patterns in NEP 2026.")
    print("="*80)
    
    # Display flood baseline first
    print_flood_baseline()
    
    # Run analyses
    print("\n\n" + "="*80)
    print("🔍 ANALYZING NEP 2026 AGAINST FLOOD BASELINE...")
    print("="*80)
    
    yoy_data = await analyze_yoy_growth_pattern()
    clustering_data = await analyze_geographic_clustering()
    infra_data = await analyze_infrastructure_spending()
    
    # Generate final assessment
    await generate_final_assessment(yoy_data, clustering_data, infra_data)
    
    print("\n✅ Analysis complete!")
    print("\n📊 Flood Control Baseline Reference:")
    print("   • Bulacan concentration: 2022-2024 dominance")
    print("   • Growth rate: +118% (2022→2023), +81% typical YoY")
    print("   • Geographic clustering: 60% in 3 provinces")
    print("   • Cost disparity: 2.6x urban vs rural")

if __name__ == "__main__":
    asyncio.run(main())


#!/usr/bin/env python3
"""
Generate NEP 2026 Overall Analysis JSON
Creates the JSON file for overall NEP 2026 analysis
"""

import asyncio
import os
import json
import asyncpg
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

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

async def generate_overall_analysis():
    """Generate overall analysis for NEP 2026"""
    conn = await get_db_connection()
    if not conn:
        return None
    
    try:
        # Get overall statistics
        stats_query = """
        SELECT 
            COUNT(*) as total_projects,
            SUM(amount) as total_amount,
            AVG(amount) as avg_amount,
            MIN(amount) as min_amount,
            MAX(amount) as max_amount,
            COUNT(DISTINCT org_uacs_code) as unique_organizations,
            COUNT(DISTINCT region_code) as unique_regions
        FROM budget_2026
        WHERE amount IS NOT NULL AND amount > 0
        """
        
        stats_result = await conn.fetchrow(stats_query)
        
        # Get top organizations by UACS code
        org_query = """
        SELECT 
            org_uacs_code,
            COUNT(*) as project_count,
            SUM(amount) as total_amount
        FROM budget_2026
        WHERE org_uacs_code IS NOT NULL AND org_uacs_code != ''
        GROUP BY org_uacs_code
        ORDER BY total_amount DESC
        LIMIT 10
        """
        
        org_results = await conn.fetch(org_query)
        
        # Get top regions
        region_query = """
        SELECT 
            region_code,
            COUNT(*) as project_count,
            SUM(amount) as total_amount
        FROM budget_2026
        WHERE region_code IS NOT NULL AND region_code != ''
        GROUP BY region_code
        ORDER BY total_amount DESC
        LIMIT 10
        """
        
        region_results = await conn.fetch(region_query)
        
        await conn.close()
        
        # Process results
        top_organizations = []
        for row in org_results:
            top_organizations.append({
                'org_uacs_code': row['org_uacs_code'],
                'project_count': row['project_count'],
                'total_amount': float(row['total_amount'] or 0)
            })
        
        top_regions = []
        for row in region_results:
            top_regions.append({
                'region_code': row['region_code'],
                'project_count': row['project_count'],
                'total_amount': float(row['total_amount'] or 0)
            })
        
        return {
            'success': True,
            'analysis_date': datetime.now().isoformat(),
            'description': 'NEP 2026 Overall Analysis',
            'statistics': {
                'total_projects': stats_result['total_projects'],
                'total_amount': float(stats_result['total_amount'] or 0),
                'avg_amount': float(stats_result['avg_amount'] or 0),
                'min_amount': float(stats_result['min_amount'] or 0),
                'max_amount': float(stats_result['max_amount'] or 0),
                'unique_organizations': stats_result['unique_organizations'],
                'unique_regions': stats_result['unique_regions']
            },
            'top_organizations': top_organizations,
            'top_regions': top_regions
        }
        
    except Exception as e:
        print(f"❌ Error generating overall analysis: {e}")
        await conn.close()
        return None

async def main():
    """Generate NEP 2026 overall analysis JSON file"""
    print("🔍 Generating NEP 2026 Overall Analysis...")
    
    data = await generate_overall_analysis()
    
    if not data:
        print("❌ Failed to generate overall analysis data")
        return
    
    # Create output directory if it doesn't exist
    os.makedirs('static/data', exist_ok=True)
    
    # Save to JSON file
    output_file = 'static/data/nep_2026_overall_analysis.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Generated {output_file}")
    print(f"📊 Total Projects: {data['statistics']['total_projects']}")
    print(f"💰 Total Amount: ₱{data['statistics']['total_amount']/1000000000:.1f}B")
    print(f"🏛️ Organizations: {data['statistics']['unique_organizations']}")
    print(f"🌍 Regions: {data['statistics']['unique_regions']}")

if __name__ == "__main__":
    asyncio.run(main())

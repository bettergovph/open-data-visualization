#!/usr/bin/env python3
"""
Generate contractors dashboard cache JSON files for fast loading.

This script caches the data needed for the /contractors dashboard charts and statistics:
- Top contractors by project count (for charts)
- Venn diagram data (contractor sources overlap)
- Excluded flood contractors (for charts)

Note: Paginated tables (SEC contractors database, projects table) are excluded as they are already optimized with frontend/backend pagination.
"""

import asyncio
import asyncpg
import json
import os
from datetime import datetime
from typing import Dict, Any, List
from pathlib import Path

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'user': 'budget_admin',
    'password': 'wuQ5gBYCKkZiOGb61chLcByMu',
    'database': 'sec'
}

PHILGEPS_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'user': 'budget_admin',
    'password': 'wuQ5gBYCKkZiOGb61chLcByMu',
    'database': 'philgeps'
}

async def get_sec_contractors() -> Dict[str, Any]:
    """Get all SEC contractors from PostgreSQL database"""
    conn = None
    try:
        conn = await asyncpg.connect(**DB_CONFIG)
        
        query = """
        SELECT 
            id,
            original_contractor_name,
            company_name,
            sec_number,
            registration_date,
            status,
            address,
            phone,
            email,
            website,
            business_type,
            capital_stock,
            authorized_capital,
            subscribed_capital,
            paid_up_capital,
            created_at,
            updated_at
        FROM contractors 
        ORDER BY original_contractor_name
        """
        
        rows = await conn.fetch(query)
        
        contractors = []
        for row in rows:
            contractors.append({
                'id': row['id'],
                'original_contractor_name': row['original_contractor_name'],
                'company_name': row['company_name'],
                'sec_number': row['sec_number'],
                'registration_date': row['registration_date'].isoformat() if row['registration_date'] else None,
                'status': row['status'],
                'address': row['address'],
                'phone': row['phone'],
                'email': row['email'],
                'website': row['website'],
                'business_type': row['business_type'],
                'capital_stock': float(row['capital_stock']) if row['capital_stock'] else None,
                'authorized_capital': float(row['authorized_capital']) if row['authorized_capital'] else None,
                'subscribed_capital': float(row['subscribed_capital']) if row['subscribed_capital'] else None,
                'paid_up_capital': float(row['paid_up_capital']) if row['paid_up_capital'] else None,
                'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None
            })
        
        return {
            'success': True,
            'contractors': contractors,
            'count': len(contractors),
            'generated_at': datetime.now().isoformat(),
            'cache_version': '1.0'
        }
        
    except Exception as e:
        print(f"Database error: {e}")
        return {
            'success': False,
            'contractors': [],
            'count': 0,
            'error': str(e),
            'generated_at': datetime.now().isoformat(),
            'cache_version': '1.0'
        }
    finally:
        if conn:
            await conn.close()

async def get_top_contractors(limit: int = 100) -> Dict[str, Any]:
    """Get top contractors by project count from SEC database"""
    conn = None
    try:
        conn = await asyncpg.connect(**DB_CONFIG)
        
        query = """
        SELECT 
            c.original_contractor_name,
            c.company_name,
            c.sec_number,
            COUNT(p.id) as project_count,
            SUM(p.contract_amount) as total_value,
            AVG(p.contract_amount) as avg_value,
            MAX(p.contract_amount) as max_value,
            MIN(p.contract_amount) as min_value,
            array_agg(DISTINCT p.project_title) as project_titles
        FROM contractors c
        LEFT JOIN projects p ON c.id = p.contractor_id
        WHERE c.original_contractor_name IS NOT NULL 
          AND c.original_contractor_name != ''
        GROUP BY c.id, c.original_contractor_name, c.company_name, c.sec_number
        HAVING COUNT(p.id) > 0
        ORDER BY project_count DESC, total_value DESC
        LIMIT $1
        """
        
        rows = await conn.fetch(query, limit)
        
        contractors = []
        for row in rows:
            contractors.append({
                'contractor_name': row['original_contractor_name'],
                'company_name': row['company_name'],
                'sec_number': row['sec_number'],
                'project_count': row['project_count'],
                'total_value': float(row['total_value']) if row['total_value'] else 0,
                'avg_value': float(row['avg_value']) if row['avg_value'] else 0,
                'max_value': float(row['max_value']) if row['max_value'] else 0,
                'min_value': float(row['min_value']) if row['min_value'] else 0,
                'project_titles': row['project_titles'][:5] if row['project_titles'] else []
            })
        
        return {
            'success': True,
            'contractors': contractors,
            'count': len(contractors),
            'generated_at': datetime.now().isoformat(),
            'cache_version': '1.0'
        }
        
    except Exception as e:
        print(f"Database error: {e}")
        return {
            'success': False,
            'contractors': [],
            'count': 0,
            'error': str(e),
            'generated_at': datetime.now().isoformat(),
            'cache_version': '1.0'
        }
    finally:
        if conn:
            await conn.close()

async def get_contractors_venn() -> Dict[str, Any]:
    """Get Venn diagram data for contractor sources (flood, dime, philgeps)"""
    conn = None
    try:
        conn = await asyncpg.connect(**DB_CONFIG)
        
        # Get contractors from each source
        flood_query = """
        SELECT DISTINCT contractor_name
        FROM flood_contractors
        WHERE contractor_name IS NOT NULL AND contractor_name != ''
        """
        
        dime_query = """
        SELECT DISTINCT contractor_name
        FROM dime_contractors
        WHERE contractor_name IS NOT NULL AND contractor_name != ''
        """
        
        philgeps_query = """
        SELECT DISTINCT awardee_name as contractor_name
        FROM philgeps_contractors
        WHERE awardee_name IS NOT NULL AND awardee_name != ''
        """
        
        flood_contractors = set(row['contractor_name'] for row in await conn.fetch(flood_query))
        dime_contractors = set(row['contractor_name'] for row in await conn.fetch(dime_query))
        philgeps_contractors = set(row['contractor_name'] for row in await conn.fetch(philgeps_query))
        
        # Calculate overlaps
        flood_only = flood_contractors - dime_contractors - philgeps_contractors
        dime_only = dime_contractors - flood_contractors - philgeps_contractors
        philgeps_only = philgeps_contractors - flood_contractors - dime_contractors
        
        flood_dime = (flood_contractors & dime_contractors) - philgeps_contractors
        flood_philgeps = (flood_contractors & philgeps_contractors) - dime_contractors
        dime_philgeps = (dime_contractors & philgeps_contractors) - flood_contractors
        
        all_three = flood_contractors & dime_contractors & philgeps_contractors
        
        return {
            'success': True,
            'venn_data': {
                'flood_only': len(flood_only),
                'dime_only': len(dime_only),
                'philgeps_only': len(philgeps_only),
                'flood_dime': len(flood_dime),
                'flood_philgeps': len(flood_philgeps),
                'dime_philgeps': len(dime_philgeps),
                'all_three': len(all_three),
                'total_flood': len(flood_contractors),
                'total_dime': len(dime_contractors),
                'total_philgeps': len(philgeps_contractors)
            },
            'generated_at': datetime.now().isoformat(),
            'cache_version': '1.0'
        }
        
    except Exception as e:
        print(f"Database error: {e}")
        return {
            'success': False,
            'venn_data': {},
            'error': str(e),
            'generated_at': datetime.now().isoformat(),
            'cache_version': '1.0'
        }
    finally:
        if conn:
            await conn.close()

async def get_excluded_flood_contractors(limit: int = 20) -> Dict[str, Any]:
    """Get top contractors from PhilGEPS with flood-related projects that cannot be correlated with Meilisearch"""
    conn = None
    try:
        conn = await asyncpg.connect(**PHILGEPS_CONFIG)
        
        query = """
        SELECT 
            awardee_name as contractor_name,
            COUNT(*) as project_count,
            SUM(contract_amount) as total_value,
            AVG(contract_amount) as avg_value,
            MAX(contract_amount) as max_value,
            MIN(contract_amount) as min_value,
            array_agg(DISTINCT area_of_delivery) as areas,
            array_agg(DISTINCT business_category) as categories,
            array_agg(DISTINCT award_title) as project_names
        FROM contracts 
        WHERE awardee_name IS NOT NULL 
          AND awardee_name != ''
          AND (
              LOWER(award_title) LIKE '%flood%' 
              OR LOWER(notice_title) LIKE '%flood%'
              OR LOWER(award_title) LIKE '%drainage%'
              OR LOWER(notice_title) LIKE '%drainage%'
              OR LOWER(award_title) LIKE '%canal%'
              OR LOWER(notice_title) LIKE '%canal%'
              OR LOWER(award_title) LIKE '%water%'
              OR LOWER(notice_title) LIKE '%water%'
          )
          AND (meilisearch_id IS NULL OR meilisearch_id = '')
        GROUP BY awardee_name
        HAVING awardee_name IS NOT NULL AND awardee_name != ''
        ORDER BY project_count DESC, total_value DESC
        LIMIT $1
        """
        
        rows = await conn.fetch(query, limit)
        
        contractors = []
        for row in rows:
            contractors.append({
                'contractor_name': row['contractor_name'],
                'project_count': row['project_count'],
                'total_value': float(row['total_value']) if row['total_value'] else 0,
                'avg_value': float(row['avg_value']) if row['avg_value'] else 0,
                'max_value': float(row['max_value']) if row['max_value'] else 0,
                'min_value': float(row['min_value']) if row['min_value'] else 0,
                'areas': row.get('areas', []),
                'categories': row.get('categories', []),
                'project_names': row['project_names'][:5] if row['project_names'] else []
            })
        
        return {
            'success': True,
            'contractors': contractors,
            'count': len(contractors),
            'generated_at': datetime.now().isoformat(),
            'cache_version': '1.0'
        }
        
    except Exception as e:
        print(f"Database error: {e}")
        return {
            'success': False,
            'contractors': [],
            'count': 0,
            'error': str(e),
            'generated_at': datetime.now().isoformat(),
            'cache_version': '1.0'
        }
    finally:
        if conn:
            await conn.close()

def save_json_cache(data: Dict[str, Any], output_file: str):
    """Save data to JSON cache file"""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Generated {output_file}")
        return True
    except Exception as e:
        print(f"❌ Error saving {output_file}: {e}")
        return False

async def main():
    """Generate all contractors dashboard cache files"""
    print("🏛️ Generating Contractors Dashboard Cache...")
    print("=" * 50)
    
    # 1. Top Contractors
    print("🔄 Generating top contractors...")
    top_data = await get_top_contractors(100)
    save_json_cache(top_data, "static/data/top_contractors_cache.json")
    
    # 2. Venn Diagram Data
    print("🔄 Generating contractors Venn diagram data...")
    venn_data = await get_contractors_venn()
    save_json_cache(venn_data, "static/data/contractors_venn_cache.json")
    
    # 3. Excluded Flood Contractors
    print("🔄 Generating excluded flood contractors...")
    flood_data = await get_excluded_flood_contractors(20)
    save_json_cache(flood_data, "static/data/excluded_flood_contractors_cache.json")
    
    print("\n🎉 Contractors dashboard cache generation completed!")
    print("=" * 50)
    print("📁 Generated files:")
    print("  • static/data/top_contractors_cache.json")
    print("  • static/data/contractors_venn_cache.json")
    print("  • static/data/excluded_flood_contractors_cache.json")

if __name__ == "__main__":
    asyncio.run(main())

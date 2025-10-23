#!/usr/bin/env python3
"""
Generate JSON cache for excluded flood contractors to optimize loading.
"""

import os
import json
import asyncio
import asyncpg
from datetime import datetime
from typing import Dict, List, Any

async def get_excluded_flood_contractors() -> Dict[str, Any]:
    """
    Get excluded flood contractors data from the database.
    """
    # Database connection parameters
    db_config = {
        'host': 'localhost',
        'port': 5432,
        'user': 'budget_admin',
        'password': 'wuQ5gBYCKkZiOGb61chLcByMu',
        'database': 'philgeps'
    }
    
    conn = None
    try:
        # Connect to database
        conn = await asyncpg.connect(**db_config)
        
        # Query to get contractors with their project counts from PhilGEPS contracts table
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
        LIMIT 20
        """
        
        rows = await conn.fetch(query)
        
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
                'project_names': row['project_names'][:5] if row['project_names'] else []  # Limit to 5 project names
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

def save_contractors_cache(data: Dict[str, Any], output_file: str = "excluded_flood_contractors_cache.json"):
    """
    Save contractors cache to JSON file.
    
    Args:
        data: Contractors data dictionary
        output_file: Output JSON file path
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"Contractors cache saved to {output_file}")
    print(f"Total contractors cached: {data.get('count', 0)}")

async def main():
    """Main function to generate contractors cache."""
    print("Generating excluded flood contractors cache...")
    
    # Get contractors data from database
    print("Fetching contractors data from database...")
    data = await get_excluded_flood_contractors()
    
    if data.get('error'):
        print(f"Error: {data['error']}")
        return
    
    print(f"Found {data['count']} contractors")
    
    # Save cache
    save_contractors_cache(data)
    
    # Print summary
    print(f"\nTop 5 contractors by project count:")
    for i, contractor in enumerate(data['contractors'][:5], 1):
        print(f"{i}. {contractor['contractor_name']}: {contractor['project_count']} projects (₱{contractor['total_value']:,.0f})")

if __name__ == "__main__":
    asyncio.run(main())

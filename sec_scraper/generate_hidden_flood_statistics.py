#!/usr/bin/env python3
"""
Generate JSON cache for hidden flood statistics to optimize API performance.
"""

import os
import json
import asyncio
import asyncpg
import aiohttp
from datetime import datetime
from typing import Dict, Any

async def get_hidden_flood_statistics() -> Dict[str, Any]:
    """
    Get hidden flood statistics data from the database.
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
        # Connect to PhilGEPS database
        conn = await asyncpg.connect(**db_config)
        
        # Get total flood projects from MeiliSearch
        total_meilisearch_projects = 0
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('http://172.30.147.217:8001/api/flood/statistics') as response:
                    if response.status == 200:
                        flood_data = await response.json()
                        total_meilisearch_projects = flood_data.get('totalProjects', 0)
        except Exception as e:
            print(f"Error getting flood statistics: {e}")
            total_meilisearch_projects = 0
        
        # Get comprehensive statistics from PhilGEPS
        stats = await conn.fetchrow("""
            WITH hidden_flood_contracts AS (
                SELECT reference_id as id, award_title as project_name, awardee_name as contractor, 
                       contract_amount as cost, area_of_delivery as location
                FROM contracts 
                WHERE (
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
            ),
            contractor_stats AS (
                SELECT 
                    contractor as contractor_name,
                    COUNT(*) as project_count,
                    SUM(cost) as total_value
                FROM hidden_flood_contracts
                WHERE contractor IS NOT NULL AND contractor != ''
                GROUP BY contractor
                HAVING contractor IS NOT NULL AND contractor != ''
            )
            SELECT 
                COUNT(*) as total_projects,
                COALESCE(SUM(cost), 0) as total_value,
                COALESCE(AVG(cost), 0) as avg_value,
                COALESCE(MAX(cost), 0) as max_value,
                COALESCE(MIN(cost), 0) as min_value,
                COUNT(DISTINCT contractor) as unique_contractors,
                (SELECT contractor_name FROM contractor_stats ORDER BY project_count DESC LIMIT 1) as top_contractor,
                (SELECT project_count FROM contractor_stats ORDER BY project_count DESC LIMIT 1) as top_contractor_projects,
                (SELECT total_value FROM contractor_stats ORDER BY total_value DESC LIMIT 1) as top_contractor_value
            FROM hidden_flood_contracts
        """)
        
        # Calculate omission rate: excluded / (total_flood + excluded)
        hidden_projects_count = stats['total_projects']
        total_flood_projects = total_meilisearch_projects + hidden_projects_count
        
        if total_flood_projects > 0:
            omission_rate = (hidden_projects_count / total_flood_projects) * 100
        else:
            omission_rate = 0
        
        return {
            "success": True,
            "total_projects": stats['total_projects'],
            "total_value": float(stats['total_value']) if stats['total_value'] else 0,
            "avg_value": float(stats['avg_value']) if stats['avg_value'] else 0,
            "max_value": float(stats['max_value']) if stats['max_value'] else 0,
            "min_value": float(stats['min_value']) if stats['min_value'] else 0,
            "unique_contractors": stats['unique_contractors'],
            "top_contractor": {
                "name": stats['top_contractor'],
                "project_count": stats['top_contractor_projects'],
                "total_value": float(stats['top_contractor_value']) if stats['top_contractor_value'] else 0
            },
            "omission_rate": round(omission_rate, 1),
            "total_meilisearch_projects": total_meilisearch_projects,
            "total_flood_projects": total_flood_projects,
            "generated_at": datetime.now().isoformat(),
            "cache_version": "1.0",
            "endpoint": "/api/flood/hidden-statistics",
            "status": "success"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "generated_at": datetime.now().isoformat(),
            "cache_version": "1.0",
            "endpoint": "/api/flood/hidden-statistics",
            "status": "error"
        }
    finally:
        if conn:
            await conn.close()

async def main():
    """
    Generate the hidden flood statistics JSON cache.
    """
    print("🔄 Generating hidden flood statistics cache...")
    
    # Get the data
    data = await get_hidden_flood_statistics()
    
    # Ensure output directory exists
    output_dir = "static/data"
    os.makedirs(output_dir, exist_ok=True)
    
    # Write to JSON file
    output_file = os.path.join(output_dir, "hidden_flood_statistics_cache.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    if data.get("success"):
        print(f"✅ Hidden flood statistics cache generated successfully")
        print(f"📊 Omission rate: {data.get('omission_rate', 0)}%")
        print(f"📁 Output file: {output_file}")
    else:
        print(f"❌ Error generating cache: {data.get('error', 'Unknown error')}")

if __name__ == "__main__":
    asyncio.run(main())

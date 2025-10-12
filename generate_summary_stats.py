#!/usr/bin/env python3
"""
Generate summary statistics JSON files from database
Run this periodically to update static JSON files
"""

import asyncio
import asyncpg
import json
import os
from dotenv import load_dotenv

load_dotenv()

async def get_db_connection(database):
    """Get database connection"""
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=database
        )
        return conn
    except Exception as e:
        print(f"❌ Error connecting to {database}: {e}")
        return None


async def generate_flood_stats():
    """Generate flood control statistics from MeiliSearch"""
    print("📊 Generating flood control statistics...")
    
    try:
        import aiohttp
        
        meili_url = os.getenv('MEILI_HTTP_ADDR', '127.0.0.1:7700')
        meili_key = os.getenv('MEILI_MASTER_KEY', '')
        
        # Query MeiliSearch for total count
        async with aiohttp.ClientSession() as session:
            headers = {'Authorization': f'Bearer {meili_key}'}
            async with session.get(
                f'http://{meili_url}/indexes/bettergov_flood_control/stats',
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    total_projects = data.get('numberOfDocuments', 0)
                    
                    stats = {
                        "total_projects": total_projects,
                        "data_range": "2016-2024",
                        "source": "Department of Public Works and Highways (DPWH) Flood Control Information System",
                        "last_updated": "2024-10-12"
                    }
                    return stats
                else:
                    print(f"❌ MeiliSearch returned status {response.status}")
                    return None
        
    except Exception as e:
        print(f"❌ Error generating flood stats: {e}")
        return None


async def generate_dime_stats():
    """Generate DIME statistics"""
    print("📊 Generating DIME statistics...")
    
    conn = await get_db_connection('dime')
    if not conn:
        return None
    
    try:
        # Get actual count from projects table
        result = await conn.fetchrow("SELECT COUNT(*) as total FROM projects")
        total_projects = result['total'] if result else 0
        
        stats = {
            "total_projects": total_projects,
            "data_range": "Government infrastructure projects",
            "source": "DBM DIME (Digital Information for Monitoring and Evaluation)",
            "last_updated": "2024-10-12"
        }
        
        await conn.close()
        return stats
        
    except Exception as e:
        print(f"❌ Error generating DIME stats: {e}")
        await conn.close()
        return None


async def generate_budget_stats():
    """Generate Budget statistics"""
    print("📊 Generating Budget statistics...")
    
    conn = await get_db_connection('budget_analysis')
    if not conn:
        return None
    
    try:
        years = [2020, 2021, 2022, 2023, 2024, 2025]
        total_items = 0
        
        for year in years:
            try:
                result = await conn.fetchrow(f"SELECT COUNT(*) as count FROM budget_{year}")
                if result:
                    total_items += result['count']
            except:
                continue
        
        stats = {
            "total_items": total_items,
            "years": years,
            "data_range": "2020-2025",
            "source": "Department of Budget and Management (DBM) General Appropriations Act (GAA)",
            "last_updated": "2024-10-12"
        }
        
        await conn.close()
        return stats
        
    except Exception as e:
        print(f"❌ Error generating budget stats: {e}")
        await conn.close()
        return None


async def generate_nep_stats():
    """Generate NEP statistics"""
    print("📊 Generating NEP statistics...")
    
    conn = await get_db_connection('nep')
    if not conn:
        return None
    
    try:
        years = [2020, 2021, 2022, 2023, 2024, 2025, 2026]
        total_items = 0
        
        for year in years:
            try:
                result = await conn.fetchrow(f"SELECT COUNT(*) as count FROM budget_{year}")
                if result:
                    total_items += result['count']
            except:
                continue
        
        stats = {
            "total_items": total_items,
            "years": years,
            "data_range": "2020-2026",
            "source": "Department of Budget and Management (DBM) General Appropriations Act (GAA)",
            "last_updated": "2024-10-12"
        }
        
        await conn.close()
        return stats
        
    except Exception as e:
        print(f"❌ Error generating NEP stats: {e}")
        await conn.close()
        return None


async def main():
    """Generate all summary statistics"""
    print("🚀 Starting summary statistics generation...")
    
    # Create static/data directory if it doesn't exist
    os.makedirs('static/data', exist_ok=True)
    
    # Generate statistics
    flood_stats = await generate_flood_stats()
    dime_stats = await generate_dime_stats()
    budget_stats = await generate_budget_stats()
    nep_stats = await generate_nep_stats()
    
    # Write to JSON files
    if flood_stats:
        with open('static/data/flood_summary.json', 'w') as f:
            json.dump(flood_stats, f, indent=2)
        print("✅ Flood statistics saved to static/data/flood_summary.json")
    
    if dime_stats:
        with open('static/data/dime_summary.json', 'w') as f:
            json.dump(dime_stats, f, indent=2)
        print(f"✅ DIME statistics saved to static/data/dime_summary.json ({dime_stats['total_projects']} projects)")
    
    if budget_stats:
        with open('static/data/budget_summary.json', 'w') as f:
            json.dump(budget_stats, f, indent=2)
        print(f"✅ Budget statistics saved to static/data/budget_summary.json ({budget_stats['total_items']} items)")
    
    if nep_stats:
        with open('static/data/nep_summary.json', 'w') as f:
            json.dump(nep_stats, f, indent=2)
        print(f"✅ NEP statistics saved to static/data/nep_summary.json ({nep_stats['total_items']} items)")
    
    print("🎉 Summary statistics generation complete!")


if __name__ == "__main__":
    asyncio.run(main())


#!/usr/bin/env python3
"""
Generate cached JSON data for top political dynasty surnames by province
"""

import asyncio
import asyncpg
import json
import os
from datetime import datetime
from dotenv import load_dotenv

async def generate_dynasty_surnames():
    """Generate cached JSON data for top surnames by province"""
    
    # Load environment variables
    load_dotenv()
    
    print("🚀 Generating Dynasty Surnames JSON cache...")
    
    try:
        # Connect to dynasty database
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_DYNASTY_SEC', 'dynasty')
        )
        
        # Get top surnames by province (province-sensitive) - TOP 3 surnames per province
        query = """
            WITH ranked_surnames AS (
                SELECT 
                    last_name,
                    province,
                    COUNT(*) as total_count,
                    COUNT(CASE WHEN fat = 1 THEN 1 END) as dynasty_count,
                    COUNT(CASE WHEN fat = 0 THEN 1 END) as non_dynasty_count,
                    ROW_NUMBER() OVER (PARTITION BY province ORDER BY COUNT(*) DESC) as rn
                FROM political_dynasties 
                WHERE last_name IS NOT NULL AND last_name != ''
                GROUP BY last_name, province
            )
            SELECT 
                last_name,
                province,
                total_count,
                dynasty_count,
                non_dynasty_count
            FROM ranked_surnames
            WHERE rn <= 3
            ORDER BY dynasty_count DESC, total_count DESC
        """
        
        records = await conn.fetch(query)
        
        # Convert to list of dictionaries
        surnames_data = []
        for record in records:
            dynasty_percentage = round((record['dynasty_count'] / record['total_count']) * 100, 1) if record['total_count'] > 0 else 0
            
            surnames_data.append({
                "surname": record['last_name'],
                "province": record['province'],
                "total_count": record['total_count'],
                "dynasty_count": record['dynasty_count'],
                "non_dynasty_count": record['non_dynasty_count'],
                "dynasty_percentage": dynasty_percentage
            })
        
        # Get summary statistics
        total_surnames = len(surnames_data)
        total_politicians = sum(item['total_count'] for item in surnames_data)
        total_dynasty = sum(item['dynasty_count'] for item in surnames_data)
        total_non_dynasty = sum(item['non_dynasty_count'] for item in surnames_data)
        
        # Get unique provinces
        unique_provinces = list(set(item['province'] for item in surnames_data))
        
        # Create output structure
        output = {
            'summary': {
                'total_surnames': total_surnames,
                'total_politicians': total_politicians,
                'total_dynasty': total_dynasty,
                'total_non_dynasty': total_non_dynasty,
                'unique_provinces': len(unique_provinces),
                'last_updated': datetime.now().isoformat(),
                'description': 'Top 3 political dynasty surnames per province (province-sensitive)',
                'source': 'PostgreSQL dynasty.political_dynasties table'
            },
            'provinces': unique_provinces,
            'surnames': surnames_data
        }
        
        # Write to JSON file
        os.makedirs('static/data', exist_ok=True)
        with open('static/data/dynasty_surnames_cache.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Generated static/data/dynasty_surnames_cache.json")
        print(f"   • Total surnames: {total_surnames}")
        print(f"   • Total politicians: {total_politicians}")
        print(f"   • Dynasty members: {total_dynasty}")
        print(f"   • Non-dynasty: {total_non_dynasty}")
        print(f"   • Unique provinces: {len(unique_provinces)}")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ Error generating dynasty surnames cache: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(generate_dynasty_surnames())

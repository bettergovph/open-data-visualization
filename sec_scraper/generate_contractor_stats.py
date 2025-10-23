#!/usr/bin/env python3
"""
Generate Contractor Statistics JSON
Creates cached statistics for the contractors page
"""

import asyncio
import os
import json
import asyncpg
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

async def get_db_connection():
    """Get PostgreSQL connection to SEC database"""
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_SEC', 'sec')
        )
        return conn
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return None

async def generate_contractor_stats():
    """Generate contractor statistics from SEC database"""
    conn = await get_db_connection()
    if not conn:
        return None
    
    try:
        # Get summary statistics
        stats = await conn.fetchrow(
            """SELECT 
                COUNT(*) as total_contractors,
                COUNT(CASE WHEN sec_number IS NOT NULL AND sec_number != '' THEN 1 END) as with_sec_data,
                COUNT(CASE WHEN sec_number IS NULL OR sec_number = '' THEN 1 END) as without_sec_data,
                COUNT(CASE WHEN status = 'NO_SEC_RESULTS' THEN 1 END) as suspicious_no_results
               FROM contractors"""
        )
        
        # Calculate processed count
        processed_count = (stats['with_sec_data'] or 0) + (stats['suspicious_no_results'] or 0)
        
        await conn.close()
        
        return {
            'success': True,
            'summary': {
                'total_contractors': stats['total_contractors'] or 0,
                'processed_contractors': processed_count,
                'with_sec_data': stats['with_sec_data'] or 0,
                'without_sec_data': stats['without_sec_data'] or 0,
                'suspicious_no_results': stats['suspicious_no_results'] or 0,
                'last_updated': datetime.now().isoformat(),
                'processing_batch': 'cached_generated',
                'source': 'PostgreSQL sec.contractors table (cached)'
            },
            'generated_at': datetime.now().isoformat(),
            'description': 'Contractor statistics for /contractors page',
            'cache_version': '1.0'
        }
        
    except Exception as e:
        print(f"❌ Error generating contractor stats: {e}")
        await conn.close()
        return None

async def main():
    """Generate contractor statistics JSON file"""
    print("📊 Generating Contractor Statistics...")
    
    data = await generate_contractor_stats()
    
    if not data:
        print("❌ Failed to generate contractor statistics")
        return
    
    # Create output directory if it doesn't exist
    os.makedirs('static/data', exist_ok=True)
    
    # Save to JSON file
    output_file = 'static/data/contractor_stats.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Generated {output_file}")
    print(f"📊 Total Contractors: {data['summary']['total_contractors']:,}")
    print(f"📊 Processed: {data['summary']['processed_contractors']:,}")
    print(f"📊 With SEC Data: {data['summary']['with_sec_data']:,}")
    print(f"📊 Suspicious: {data['summary']['suspicious_no_results']:,}")

if __name__ == "__main__":
    asyncio.run(main())

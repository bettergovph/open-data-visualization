#!/usr/bin/env python3
"""
Generate NEP 2026 Infrastructure Categories JSON
Creates the JSON file for infrastructure category analysis
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

async def generate_infrastructure_categories():
    """Generate infrastructure categories analysis for NEP 2026"""
    conn = await get_db_connection()
    if not conn:
        return None
    
    try:
        # Get infrastructure categories from NEP 2026
        query = """
        SELECT 
            CASE 
                WHEN LOWER(description) LIKE '%road%' OR LOWER(description) LIKE '%highway%' THEN 'Road Infrastructure'
                WHEN LOWER(description) LIKE '%bridge%' THEN 'Bridge Construction'
                WHEN LOWER(description) LIKE '%flood%' OR LOWER(description) LIKE '%drainage%' THEN 'Flood Control'
                WHEN LOWER(description) LIKE '%water%' OR LOWER(description) LIKE '%irrigation%' THEN 'Water Systems'
                WHEN LOWER(description) LIKE '%building%' OR LOWER(description) LIKE '%facility%' THEN 'Building Construction'
                WHEN LOWER(description) LIKE '%rehabilitation%' OR LOWER(description) LIKE '%upgrading%' THEN 'Rehabilitation'
                ELSE 'Other Infrastructure'
            END as category,
            COUNT(*) as project_count,
            SUM(amount) as total_amount
        FROM budget_2026
        WHERE description IS NOT NULL AND description != ''
        GROUP BY category
        ORDER BY total_amount DESC
        """
        
        results = await conn.fetch(query)
        await conn.close()
        
        # Process results
        categories = []
        for row in results:
            categories.append({
                'category': row['category'],
                'project_count': row['project_count'],
                'total_amount': float(row['total_amount'] or 0)
            })
        
        return {
            'success': True,
            'categories': categories,
            'analysis_date': datetime.now().isoformat(),
            'description': 'NEP 2026 Infrastructure Categories Analysis',
            'total_projects': sum(c['project_count'] for c in categories),
            'total_amount': sum(c['total_amount'] for c in categories)
        }
        
    except Exception as e:
        print(f"❌ Error generating infrastructure categories: {e}")
        await conn.close()
        return None

async def main():
    """Generate NEP 2026 infrastructure categories JSON file"""
    print("🔍 Generating NEP 2026 Infrastructure Categories...")
    
    data = await generate_infrastructure_categories()
    
    if not data:
        print("❌ Failed to generate infrastructure categories data")
        return
    
    # Create output directory if it doesn't exist
    os.makedirs('static/data', exist_ok=True)
    
    # Save to JSON file
    output_file = 'static/data/nep_2026_infrastructure_categories.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Generated {output_file}")
    print(f"📊 Categories: {len(data['categories'])}")
    print(f"🏗️ Total Projects: {data['total_projects']}")
    print(f"💰 Total Amount: ₱{data['total_amount']/1000000000:.1f}B")

if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
Generate Fastest DIME Projects JSON
Creates the JSON file for the fastest completed DIME projects from the database
"""

import asyncio
import os
import json
import asyncpg
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

async def get_db_connection():
    """Get PostgreSQL connection to DIME database"""
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'joebert'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_DIME', 'dime')
        )
        return conn
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return None

async def generate_fastest_dime_projects():
    """Generate fastest completed DIME projects from database"""
    conn = await get_db_connection()
    if not conn:
        return None
    
    try:
        # Get fastest completed projects (top 100, sorted by completion days ascending then cost descending)
        query = """
        WITH project_completion AS (
            SELECT 
                project_name,
                description,
                cost,
                date_started,
                contract_completion_date,
                status,
                implementing_offices,
                region,
                province,
                city,
                barangay,
                project_type,
                -- Calculate completion time in days
                CASE 
                    WHEN date_started IS NOT NULL AND contract_completion_date IS NOT NULL 
                    THEN EXTRACT(EPOCH FROM (contract_completion_date::timestamp - date_started::timestamp)) / 86400
                    ELSE NULL
                END as completion_days
            FROM projects 
            WHERE status = 'Completed'
              AND date_started IS NOT NULL 
              AND contract_completion_date IS NOT NULL
              AND date_started < contract_completion_date
              AND date_started::timestamp IS NOT NULL
              AND contract_completion_date::timestamp IS NOT NULL
        )
        SELECT * FROM project_completion
        WHERE completion_days IS NOT NULL AND completion_days > 0
        ORDER BY completion_days ASC, cost DESC
        LIMIT 100
        """
        
        results = await conn.fetch(query)
        await conn.close()
        
        # Process results
        projects = []
        for row in results:
            projects.append({
                'project_name': row['project_name'],
                'description': row['description'],
                'cost': float(row['cost']) if row['cost'] else 0,
                'date_started': row['date_started'].isoformat() if row['date_started'] else None,
                'contract_completion_date': row['contract_completion_date'].isoformat() if row['contract_completion_date'] else None,
                'status': row['status'],
                'implementing_offices': row['implementing_offices'],
                'region': row['region'],
                'province': row['province'],
                'city': row['city'],
                'barangay': row['barangay'],
                'project_type': row['project_type'],
                'completion_days': float(row['completion_days']) if row['completion_days'] else None
            })
        
        return {
            'success': True,
            'projects': projects,
            'count': len(projects),
            'generated_at': datetime.now().isoformat(),
            'description': 'Top 100 fastest completed DIME projects (sorted by completion days ascending, then cost descending)',
            'cache_version': '1.0'
        }
        
    except Exception as e:
        print(f"❌ Error generating fastest DIME projects: {e}")
        await conn.close()
        return None

async def main():
    """Generate fastest DIME projects JSON file"""
    print("⚡ Generating Fastest DIME Projects...")
    
    data = await generate_fastest_dime_projects()
    
    if not data:
        print("❌ Failed to generate fastest DIME projects data")
        return
    
    # Create output directory if it doesn't exist
    os.makedirs('static/data', exist_ok=True)
    
    # Save to JSON file
    output_file = 'static/data/fastest_dime_projects.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Generated {output_file}")
    print(f"📊 Projects: {data['count']}")
    if data['projects']:
        fastest = min(data['projects'], key=lambda x: x['completion_days'] or float('inf'))
        print(f"🏆 Fastest: {fastest['completion_days']:.1f} days - {fastest['project_name'][:50]}...")

if __name__ == "__main__":
    asyncio.run(main())

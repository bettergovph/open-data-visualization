#!/usr/bin/env python3
"""
Generate Fastest DIME Projects JSON
Creates the JSON file for the fastest completed DIME projects from the database
"""

import asyncio
import os
import json
import asyncpg
import sys
from datetime import datetime
from dotenv import load_dotenv

# Add parent directory to path for flood_client import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from flood_client import FloodControlClient

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

async def get_contractor_from_meilisearch(meilisearch_id):
    """Get contractor information from MeiliSearch using meilisearch_id"""
    try:
        client = FloodControlClient()
        project = await client.get_project_by_id(meilisearch_id)
        
        if project and project.Contractor:
            return project.Contractor
        return None
    except Exception as e:
        print(f"⚠️ MeiliSearch query failed for {meilisearch_id}: {e}")
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
            contractors,
            meilisearch_id,
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
            # Handle contractor information based on meilisearch_id connection
            contractors = []
            contractor_source = "dime"  # Default to DIME data
            
            if row['meilisearch_id']:
                # Project is connected to flood data - get contractor from MeiliSearch
                contractor_source = "flood_connected"
                meilisearch_contractor = await get_contractor_from_meilisearch(row['meilisearch_id'])
                
                if meilisearch_contractor:
                    contractors = [meilisearch_contractor]
                else:
                    # Fallback to DIME contractor data if MeiliSearch fails
                    if row['contractors']:
                        for contractor in row['contractors']:
                            if contractor and contractor != 'No Data Available':
                                contractors.append(contractor)
                                contractor_source = "dime_fallback"
                    
                    # If still no contractors found, show Redacted/Missing
                    if not contractors:
                        contractors = ["Redacted/Missing"]
            else:
                # Project is NOT connected to flood data - use DIME contractor data
                if row['contractors']:
                    for contractor in row['contractors']:
                        if contractor and contractor != 'No Data Available':
                            contractors.append(contractor)
            
            # If no contractors found, show N/A
            if not contractors:
                contractors = ["N/A"]
            
            projects.append({
                'project_name': row['project_name'],
                'description': row['description'],
                'cost': float(row['cost']) if row['cost'] else 0,
                'date_started': row['date_started'].isoformat() if row['date_started'] else None,
                'contract_completion_date': row['contract_completion_date'].isoformat() if row['contract_completion_date'] else None,
                'status': row['status'],
                'implementing_offices': row['implementing_offices'],
                'contractors': contractors,
                'contractor_source': contractor_source,
                'meilisearch_id': row['meilisearch_id'],
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

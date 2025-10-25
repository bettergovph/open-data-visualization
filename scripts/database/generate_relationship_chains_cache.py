#!/usr/bin/env python3
"""
Generate relationship chains cache for conflicts visualization
"""

import asyncio
import asyncpg
import json
import os
from datetime import datetime

async def generate_relationship_chains_cache():
    """Generate JSON cache of relationship chains between different political families"""
    
    # Database connection
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='budget_admin',
        password='wuQ5gBYCKkZiOGb61chLcByMu',
        database='dynasty'
    )
    
    try:
        print("🔍 Generating relationship chains cache...")
        
        # Query to find relationships between different families
        query = """
        SELECT 
            r.person_id as start_person,
            r.related_person_id as end_person,
            p1.first_name as start_first_name,
            p1.last_name as start_last_name,
            p1.position as start_position,
            p2.first_name as end_first_name,
            p2.last_name as end_last_name,
            p2.position as end_position,
            r.relationship_description,
            p1.last_name as start_surname,
            p2.last_name as end_surname
        FROM relationships r
        JOIN political_dynasties p1 ON r.person_id = p1.id
        JOIN political_dynasties p2 ON r.related_person_id = p2.id
        WHERE p1.last_name != p2.last_name  -- Only different families
        ORDER BY p1.last_name, p2.last_name
        """
        
        chains = await conn.fetch(query)
        print(f"📊 Found {len(chains)} relationship chains")
        
        # Format the data
        formatted_chains = []
        for chain in chains:
            formatted_chains.append({
                "length": 2,  # Direct relationship = 2 people
                "start_surname": chain['start_surname'],
                "end_surname": chain['end_surname'],
                "path": [
                    {
                        "id": chain['start_person'],
                        "first_name": chain['start_first_name'],
                        "last_name": chain['start_last_name'],
                        "position": chain['start_position'],
                        "relationship_description": "Starting person"
                    },
                    {
                        "id": chain['end_person'],
                        "first_name": chain['end_first_name'],
                        "last_name": chain['end_last_name'],
                        "position": chain['end_position'],
                        "relationship_description": chain['relationship_description']
                    }
                ],
                "relationships": [chain['relationship_description']]
            })
        
        # Create cache data structure
        cache_data = {
            "summary": {
                "total_chains": len(formatted_chains),
                "last_updated": datetime.now().isoformat(),
                "description": "Relationship chains between different political families"
            },
            "chains": formatted_chains
        }
        
        # Ensure cache directory exists
        cache_dir = "static/data"
        os.makedirs(cache_dir, exist_ok=True)
        
        # Write cache file
        cache_file = os.path.join(cache_dir, "relationship_chains_cache.json")
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Cache generated: {cache_file}")
        print(f"📊 Total chains: {len(formatted_chains)}")
        
        return cache_data
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(generate_relationship_chains_cache())

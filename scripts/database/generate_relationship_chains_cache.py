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
        
        # Query to find longer relationship chains using recursive CTE
        query = """
        WITH RECURSIVE relationship_chains AS (
            -- Base case: start with direct relationships
            SELECT 
                r.person_id as start_person,
                r.related_person_id as end_person,
                r.person_id as current_person,
                r.related_person_id as next_person,
                r.person_id::text || ',' || r.related_person_id::text as path_string,
                r.relationship_description as relationship_string,
                1 as chain_length,
                p1.last_name as start_surname,
                p2.last_name as end_surname,
                p1.first_name as start_first_name,
                p1.last_name as start_last_name,
                p1.position as start_position,
                p2.first_name as end_first_name,
                p2.last_name as end_last_name,
                p2.position as end_position
            FROM relationships r
            JOIN political_dynasties p1 ON r.person_id = p1.id
            JOIN political_dynasties p2 ON r.related_person_id = p2.id
            WHERE p1.last_name != p2.last_name  -- Only different families
            
            UNION ALL
            
            -- Recursive case: extend chains
            SELECT 
                rc.start_person,
                rc.end_person,
                r.related_person_id as current_person,
                r.related_person_id as next_person,
                rc.path_string || ',' || r.related_person_id::text,
                rc.relationship_string || ',' || r.relationship_description,
                rc.chain_length + 1,
                rc.start_surname,
                p.last_name as end_surname,
                rc.start_first_name,
                rc.start_last_name,
                rc.start_position,
                p.first_name as end_first_name,
                p.last_name as end_last_name,
                p.position as end_position
            FROM relationship_chains rc
            JOIN relationships r ON rc.next_person = r.person_id
            JOIN political_dynasties p ON r.related_person_id = p.id
            WHERE rc.path_string NOT LIKE '%' || r.related_person_id::text || '%'  -- Avoid cycles
            AND rc.chain_length < 6  -- Limit depth
            AND p.last_name != rc.start_surname  -- Ensure different families
        )
        SELECT 
            rc.start_person,
            rc.end_person,
            rc.chain_length + 1 as chain_length,  -- +1 because chain_length is 0-based
            rc.start_surname,
            rc.end_surname,
            rc.start_first_name,
            rc.start_last_name,
            rc.start_position,
            rc.end_first_name,
            rc.end_last_name,
            rc.end_position,
            rc.path_string,
            rc.relationship_string
        FROM relationship_chains rc
        WHERE rc.start_surname != rc.end_surname
        AND rc.start_person != rc.end_person
        ORDER BY rc.chain_length DESC, rc.start_surname, rc.end_surname
        """
        
        chains = await conn.fetch(query)
        print(f"📊 Found {len(chains)} relationship chains")
        
        # Format the data
        formatted_chains = []
        for chain in chains:
            # Parse the path string to get all person IDs
            person_ids = [int(id_str) for id_str in chain['path_string'].split(',')]
            relationships = chain['relationship_string'].split(',')
            
            # Get person details for each person in the chain
            path_details = []
            for i, person_id in enumerate(person_ids):
                # Get person details from database
                person_query = """
                SELECT id, first_name, last_name, position, region, province, municipality_city
                FROM political_dynasties 
                WHERE id = $1
                """
                person = await conn.fetchrow(person_query, person_id)
                
                if person:
                    relationship_desc = "Starting person" if i == 0 else relationships[i-1] if i-1 < len(relationships) else "Unknown"
                    
                    # Build location string
                    location_parts = []
                    if person['municipality_city']:
                        location_parts.append(person['municipality_city'])
                    if person['province']:
                        location_parts.append(person['province'])
                    if person['region']:
                        location_parts.append(person['region'])
                    location = ', '.join(location_parts) if location_parts else 'Location unknown'
                    
                    path_details.append({
                        "id": person['id'],
                        "first_name": person['first_name'],
                        "last_name": person['last_name'],
                        "position": person['position'],
                        "region": person['region'],
                        "province": person['province'],
                        "municipality_city": person['municipality_city'],
                        "location": location,
                        "relationship_description": relationship_desc
                    })
            
            formatted_chains.append({
                "length": len(path_details),  # Actual number of people in chain
                "start_surname": chain['start_surname'],
                "end_surname": chain['end_surname'],
                "path": path_details,
                "relationships": relationships
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

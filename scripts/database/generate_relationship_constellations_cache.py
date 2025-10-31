#!/usr/bin/env python3
"""
Generate relationship constellations cache for relationship visualization
Includes both direct relationships and contractor-mediated connections
"""

import asyncio
import asyncpg
import json
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv


def load_env_from_dotenv():
    """Load environment variables from .env file"""
    root = Path(__file__).resolve().parents[2]
    env_path = root / '.env'
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


async def generate_relationship_constellations_cache():
    """Generate JSON cache of relationship constellations between different political families"""
    
    load_env_from_dotenv()
    load_dotenv()
    
    # Database connection
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )
    
    try:
        print("🔍 Generating relationship constellations cache...")
        
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
        print(f"📊 Found {len(chains)} relationship constellations from direct relationships")
        
        # Add contractor-mediated relationships
        print("🔗 Checking contractor-dynasty relationships...")
        
        contractor_relationships_query = """
        WITH contractor_connections AS (
            SELECT DISTINCT
                cdm1.dynasty_full_name as person1_name,
                cdm1.dynasty_first_name as person1_first,
                cdm1.dynasty_last_name as person1_last,
                cdm1.role as person1_role,
                cdm2.dynasty_full_name as person2_name,
                cdm2.dynasty_first_name as person2_first,
                cdm2.dynasty_last_name as person2_last,
                cdm2.role as person2_role,
                cdm1.company_name as contractor_name,
                'Business/Contractor Connection' as relationship_type
            FROM contractor_dynasty_matches cdm1
            JOIN contractor_dynasty_matches cdm2 
                ON cdm1.company_name = cdm2.company_name
                AND cdm1.dynasty_full_name != cdm2.dynasty_full_name
            JOIN political_dynasties p1 
                ON UPPER(TRIM(p1.first_name)) = UPPER(TRIM(cdm1.dynasty_first_name))
                AND UPPER(TRIM(p1.last_name)) = UPPER(TRIM(cdm1.dynasty_last_name))
            JOIN political_dynasties p2 
                ON UPPER(TRIM(p2.first_name)) = UPPER(TRIM(cdm2.dynasty_first_name))
                AND UPPER(TRIM(p2.last_name)) = UPPER(TRIM(cdm2.dynasty_last_name))
            WHERE p1.id != p2.id
                AND p1.last_name != p2.last_name  -- Different families
        )
        SELECT 
            p1.id as start_person,
            p2.id as end_person,
            cc.contractor_name,
            cc.relationship_type,
            cc.person1_role,
            cc.person2_role,
            p1.first_name as start_first_name,
            p1.last_name as start_last_name,
            p1.position as start_position,
            p2.first_name as end_first_name,
            p2.last_name as end_last_name,
            p2.position as end_position,
            p1.last_name as start_surname,
            p2.last_name as end_surname
        FROM contractor_connections cc
        JOIN political_dynasties p1 
            ON UPPER(TRIM(p1.first_name)) = UPPER(TRIM(cc.person1_first))
            AND UPPER(TRIM(p1.last_name)) = UPPER(TRIM(cc.person1_last))
        JOIN political_dynasties p2 
            ON UPPER(TRIM(p2.first_name)) = UPPER(TRIM(cc.person2_first))
            AND UPPER(TRIM(p2.last_name)) = UPPER(TRIM(cc.person2_last))
        WHERE p1.id != p2.id
        ORDER BY cc.contractor_name, p1.last_name, p2.last_name
        """
        
        contractor_chains = await conn.fetch(contractor_relationships_query)
        print(f"📊 Found {len(contractor_chains)} contractor-mediated connections")
        
        # Convert contractor connections to same format as relationship chains
        contractor_relationships = []
        for cc in contractor_chains:
            contractor_relationships.append({
                'start_person': cc['start_person'],
                'end_person': cc['end_person'],
                'chain_length': 2,  # Person -> Contractor -> Person (2 hops)
                'start_surname': cc['start_surname'],
                'end_surname': cc['end_surname'],
                'start_first_name': cc['start_first_name'],
                'start_last_name': cc['start_last_name'],
                'start_position': cc['start_position'],
                'start_company_role': cc.get('person1_role'),  # Role in company
                'end_first_name': cc['end_first_name'],
                'end_last_name': cc['end_last_name'],
                'end_position': cc['end_position'],
                'end_company_role': cc.get('person2_role'),  # Role in company
                'path_string': f"{cc['start_person']},{cc['end_person']}",
                'relationship_string': f"Connected via {cc['contractor_name']}",
                'contractor_name': cc['contractor_name'],
                'relationship_type': cc['relationship_type']
            })
        
        # Combine direct relationships and contractor connections
        all_chains = list(chains) + contractor_relationships
        print(f"📊 Total constellations: {len(all_chains)} ({len(chains)} direct + {len(contractor_relationships)} contractor-mediated)")
        
        # Format the data
        formatted_chains = []
        for chain in all_chains:
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
            
            # Add contractor information if this is a contractor-mediated connection
            chain_data = {
                "length": len(path_details),
                "start_surname": chain['start_surname'],
                "end_surname": chain['end_surname'],
                "path": path_details,
                "relationships": relationships
            }
            
            # Add contractor info for contractor-mediated connections
            if 'contractor_name' in chain and chain['contractor_name']:
                # Get company roles for start and end persons
                start_role = chain.get('start_company_role')
                end_role = chain.get('end_company_role')
                
                chain_data["contractor_connection"] = {
                    "contractor_name": chain['contractor_name'],
                    "relationship_type": chain.get('relationship_type', 'Business/Contractor Connection'),
                    "start_company_role": start_role,
                    "end_company_role": end_role
                }
            
            formatted_chains.append(chain_data)
        
        # Create cache data structure
        direct_count = len(chains)
        contractor_count = len(contractor_relationships)
        
        cache_data = {
            "summary": {
                "total_chains": len(formatted_chains),
                "direct_relationships": direct_count,
                "contractor_mediated": contractor_count,
                "last_updated": datetime.now().isoformat(),
                "description": "Relationship constellations between different political families (includes contractor-mediated connections)"
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
        
        print(f"✅ Constellations cache generated: {cache_file}")
        print(f"📊 Total constellations: {len(formatted_chains)}")
        
        return cache_data
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(generate_relationship_constellations_cache())



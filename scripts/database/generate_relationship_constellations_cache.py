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
        import datetime
        start_time = datetime.datetime.now()
        print(f"[{start_time.strftime('%Y-%m-%d %H:%M:%S')}] Starting tree-based BFS chain generation...", flush=True)
        
        # Get party-list memberships for party-list extensions
        party_list_members_query = """
        SELECT DISTINCT
            p.id as person_id,
            pl.code as party_code,
            pl.party_list_number,
            pl.party_name,
            COALESCE(pl.party_list_number::text || ', ', '') || pl.party_name as party_full_name
        FROM political_dynasties p
        JOIN party_list pl ON (
            p.party LIKE pl.code || ', ' || UPPER(pl.party_name)
            OR p.party LIKE pl.code || ',' || UPPER(pl.party_name)
            OR p.party LIKE '%' || pl.code || ', ' || UPPER(pl.party_name) || '%'
            OR (p.party LIKE '%' || UPPER(pl.party_name) || '%' AND p.position LIKE '%PARTY-LIST%')
            OR (p.party LIKE '%' || UPPER(pl.party_name) || '%' AND p.position LIKE '%PARTY LIST%')
            OR (p.position LIKE '%' || UPPER(pl.party_name) || '%PARTY-LIST%')
            OR (p.position LIKE '%' || UPPER(pl.party_name) || '%PARTY LIST%')
        )
        WHERE p.id IS NOT NULL
          AND pl.party_list_number IS NOT NULL  -- Only include actual party-list entries (numeric codes)
        """
        party_list_members_data = await conn.fetch(party_list_members_query)
        print(f"📊 Found {len(party_list_members_data)} party-list memberships", flush=True)
        
        # Build party-list lookup maps
        person_to_parties = {}  # person_id -> list of (party_list_number, party_name)
        party_to_members = {}   # (party_list_number, party_name) -> list of person_ids
        
        for plm in party_list_members_data:
            person_id = plm['person_id']
            party_list_number = plm['party_list_number']
            party_name = plm['party_name']
            party_key = (party_list_number, party_name)
            
            if person_id not in person_to_parties:
                person_to_parties[person_id] = []
            person_to_parties[person_id].append(party_key)
            
            if party_key not in party_to_members:
                party_to_members[party_key] = []
            party_to_members[party_key].append(person_id)
        
        # Get contractor connections for contractor extensions
        contractor_members_query = """
        SELECT DISTINCT
            p.id as person_id,
            cdm.company_name as contractor_name,
            cdm.role as contractor_role
        FROM contractor_dynasty_matches cdm
        JOIN political_dynasties p ON (
            (UPPER(TRIM(p.first_name)) = UPPER(TRIM(cdm.dynasty_first_name))
             AND UPPER(TRIM(p.last_name)) = UPPER(TRIM(cdm.dynasty_last_name)))
            OR
            (UPPER(p.first_name) LIKE '%' || UPPER(TRIM(cdm.dynasty_first_name)) || '%'
             AND UPPER(TRIM(p.last_name)) = UPPER(TRIM(cdm.dynasty_last_name)))
        )
        WHERE p.id IS NOT NULL
        """
        contractor_members_data = await conn.fetch(contractor_members_query)
        print(f"📊 Found {len(contractor_members_data)} contractor connections", flush=True)
        
        # Build contractor lookup maps
        person_to_contractors = {}  # person_id -> list of contractor_name
        contractor_to_members = {}  # contractor_name -> list of person_ids
        
        for cm in contractor_members_data:
            person_id = cm['person_id']
            contractor_name = cm['contractor_name']
            
            if person_id not in person_to_contractors:
                person_to_contractors[person_id] = []
            person_to_contractors[person_id].append(contractor_name)
            
            if contractor_name not in contractor_to_members:
                contractor_to_members[contractor_name] = []
            contractor_to_members[contractor_name].append(person_id)
        
        # RECURSIVE TRAVERSAL APPROACH: Recursively extend chains until we hit duplicate nodes
        print("\n🌳 Building relationship tree recursively...", flush=True)
        
        # Get all starting relationships (level 0)
        level0_query = """
        SELECT 
            r.person_id as start_person,
            r.related_person_id as end_person,
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
        WHERE (
            -- Different families (original logic) - only one direction to avoid duplicates
            -- Use UPPER() for case-insensitive comparison
            (UPPER(p1.last_name) != UPPER(p2.last_name) AND r.person_id < r.related_person_id)
            OR
            -- Same family BUT at least one connects to different families - allow both directions
            (UPPER(p1.last_name) = UPPER(p2.last_name) AND (
                EXISTS (
                    SELECT 1 FROM relationships r2
                    JOIN political_dynasties p3 ON (
                        (r2.person_id = p3.id AND r2.related_person_id = r.person_id)
                        OR (r2.related_person_id = p3.id AND r2.person_id = r.person_id)
                    )
                    WHERE (r2.person_id = r.person_id OR r2.related_person_id = r.person_id)
                      AND UPPER(p3.last_name) != UPPER(p1.last_name)
                    LIMIT 1
                )
                OR EXISTS (
                    SELECT 1 FROM relationships r2
                    JOIN political_dynasties p3 ON (
                        (r2.person_id = p3.id AND r2.related_person_id = r.related_person_id)
                        OR (r2.related_person_id = p3.id AND r2.person_id = r.related_person_id)
                    )
                    WHERE (r2.person_id = r.related_person_id OR r2.related_person_id = r.related_person_id)
                      AND UPPER(p3.last_name) != UPPER(p1.last_name)
                    LIMIT 1
                )
            ))
        )
        """
        
        initial_chains = await conn.fetch(level0_query)
        all_chains = []
        seen_paths = set()
        
        # Global list of nodes we've encountered (leaf nodes) - stop recursion when we hit these
        global_rendered_nodes = set()
        
        # Track rendered party-lists and contractors
        rendered_party_lists = set()
        rendered_contractors = set()
        
        print(f"  Starting with {len(initial_chains)} initial chains", flush=True)
        
        async def recursive_extend(chain, depth=0):
            """Recursively extend a chain until we hit a duplicate node (leaf)"""
            path = [int(x) for x in chain['path_string'].split(',')]
            last_person = path[-1]
            visited_in_chain = set(path)
            
            # Add this chain to results (if not already seen)
            # This ensures ALL chains (including all 2-node chains) are captured
            if chain['path_string'] not in seen_paths:
                all_chains.append(chain)
                seen_paths.add(chain['path_string'])
            
            # STOPPING CONDITION: If the last node is already in global_rendered_nodes, stop recursion
            # This means we've reached a node that was already extended from by another chain
            # BUT we've already added the chain ending at this node, so we've captured it
            if last_person in global_rendered_nodes:
                # This is a duplicate leaf - we've reached a node already processed
                return
            
            # Mark this node as processed (added to global list) - future chains will stop here
            # We mark it BEFORE extending so that if multiple chains reach this node,
            # only the first one will extend from it, but all chains ending at it are captured
            global_rendered_nodes.add(last_person)
            
            # Extension type 1: Direct relationships
            ext1_query = """
            SELECT 
                r.related_person_id as next_person_id,
                r.relationship_description,
                p2.last_name,
                p2.first_name,
                p2.position
            FROM relationships r
            JOIN political_dynasties p2 ON r.related_person_id = p2.id
            WHERE r.person_id = $1
              AND r.related_person_id != ALL($2::int[])
              AND (
                  UPPER(p2.last_name) != UPPER($3)
                  OR
                  (UPPER(p2.last_name) = UPPER($3) AND EXISTS (
                      SELECT 1 FROM relationships r2
                      JOIN political_dynasties p3 ON (r2.person_id = p3.id AND r2.related_person_id = r.related_person_id)
                               OR (r2.related_person_id = p3.id AND r2.person_id = r.related_person_id)
                      WHERE (r2.person_id = r.related_person_id OR r2.related_person_id = r.related_person_id)
                        AND UPPER(p3.last_name) != UPPER($3)
                  ))
              )
            
            UNION ALL
            
            SELECT 
                r.person_id as next_person_id,
                r.relationship_description,
                p1.last_name,
                p1.first_name,
                p1.position
            FROM relationships r
            JOIN political_dynasties p1 ON r.person_id = p1.id
            WHERE r.related_person_id = $1
              AND r.person_id != ALL($2::int[])
              AND (
                  UPPER(p1.last_name) != UPPER($3)
                  OR
                  (UPPER(p1.last_name) = UPPER($3) AND EXISTS (
                      SELECT 1 FROM relationships r2
                      JOIN political_dynasties p3 ON (r2.person_id = p3.id AND r2.related_person_id = r.person_id)
                               OR (r2.related_person_id = p3.id AND r2.person_id = r.person_id)
                      WHERE (r2.person_id = r.person_id OR r2.related_person_id = r.person_id)
                        AND UPPER(p3.last_name) != UPPER($3)
                  ))
              )
            """
            
            extensions = await conn.fetch(ext1_query, last_person, path, chain['start_surname'])
            
            for ext in extensions:
                next_person_id = ext['next_person_id']
                
                # Skip if already in current path (avoid cycles)
                if next_person_id in visited_in_chain:
                    continue
                
                new_path = path + [next_person_id]
                new_path_string = ','.join(str(p) for p in new_path)
                
                if new_path_string not in seen_paths:
                    new_chain = {
                        'start_person': chain['start_person'],
                        'end_person': next_person_id,
                        'path_string': new_path_string,
                        'relationship_string': chain['relationship_string'] + ',' + ext['relationship_description'],
                        'chain_length': len(new_path),
                        'start_surname': chain['start_surname'],
                        'end_surname': ext['last_name'],
                        'start_first_name': chain['start_first_name'],
                        'start_last_name': chain['start_last_name'],
                        'start_position': chain['start_position'],
                        'end_first_name': ext['first_name'],
                        'end_last_name': ext['last_name'],
                        'end_position': ext['position'],
                        'party_code': chain.get('party_code'),
                        'party_list_number': chain.get('party_list_number'),
                        'party_name': chain.get('party_name'),
                        'party_full_name': chain.get('party_full_name')
                    }
                    
                    # Recursively extend this new chain
                    await recursive_extend(new_chain, depth + 1)
            
            # Extension type 2: Party-list connections
            if last_person in person_to_parties:
                for party_key in person_to_parties[last_person]:
                    if party_key in rendered_party_lists:
                        continue
                    
                    party_list_number, party_name = party_key
                    party_full_name = f"{party_list_number}, {party_name}" if party_list_number else party_name
                    
                    for other_member_id in party_to_members[party_key]:
                        if other_member_id in visited_in_chain:
                            continue
                        
                        other_person = await conn.fetchrow("""
                            SELECT last_name, first_name, position 
                            FROM political_dynasties 
                            WHERE id = $1
                        """, other_member_id)
                        
                        if not other_person:
                            continue
                        
                        new_path = path + [other_member_id]
                        new_path_string = ','.join(str(p) for p in new_path)
                        
                        if new_path_string not in seen_paths:
                            new_chain = {
                                'start_person': chain['start_person'],
                                'end_person': other_member_id,
                                'path_string': new_path_string,
                                'relationship_string': chain['relationship_string'] + ',Connected via ' + party_name,
                                'chain_length': len(new_path),
                                'start_surname': chain['start_surname'],
                                'end_surname': other_person['last_name'],
                                'start_first_name': chain['start_first_name'],
                                'start_last_name': chain['start_last_name'],
                                'start_position': chain['start_position'],
                                'end_first_name': other_person['first_name'],
                                'end_last_name': other_person['last_name'],
                                'end_position': other_person['position'],
                                'party_code': str(party_list_number) if party_list_number else None,
                                'party_list_number': party_list_number,
                                'party_name': party_name,
                                'party_full_name': party_full_name
                            }
                            
                            # Recursively extend this new chain
                            await recursive_extend(new_chain, depth + 1)
            
            # Extension type 3: Contractor connections
            if last_person in person_to_contractors:
                for contractor_name in person_to_contractors[last_person]:
                    # Note: We don't skip contractors that have been rendered
                    # This allows multiple chains to extend via the same contractor
                    # (similar to how we handle direct relationships)
                    
                    # Get contractor role for the current person
                    current_person_role = await conn.fetchval("""
                        SELECT role FROM contractor_dynasty_matches
                        WHERE company_name = $1
                          AND dynasty_first_name = (SELECT first_name FROM political_dynasties WHERE id = $2)
                          AND dynasty_last_name = (SELECT last_name FROM political_dynasties WHERE id = $2)
                        LIMIT 1
                    """, contractor_name, last_person)
                    
                    for other_member_id in contractor_to_members[contractor_name]:
                        if other_member_id in visited_in_chain:
                            continue
                        
                        other_person = await conn.fetchrow("""
                            SELECT last_name, first_name, position 
                            FROM political_dynasties 
                            WHERE id = $1
                        """, other_member_id)
                        
                        if not other_person:
                            continue
                        
                        # Get contractor role for the other person
                        other_person_role = await conn.fetchval("""
                            SELECT role FROM contractor_dynasty_matches
                            WHERE company_name = $1
                              AND dynasty_first_name = (SELECT first_name FROM political_dynasties WHERE id = $2)
                              AND dynasty_last_name = (SELECT last_name FROM political_dynasties WHERE id = $2)
                            LIMIT 1
                        """, contractor_name, other_member_id)
                        
                        new_path = path + [other_member_id]
                        new_path_string = ','.join(str(p) for p in new_path)
                        
                        if new_path_string not in seen_paths:
                            new_chain = {
                                'start_person': chain['start_person'],
                                'end_person': other_member_id,
                                'path_string': new_path_string,
                                'relationship_string': chain['relationship_string'] + ',Connected via ' + contractor_name,
                                'chain_length': len(new_path),
                                'start_surname': chain['start_surname'],
                                'end_surname': other_person['last_name'],
                                'start_first_name': chain['start_first_name'],
                                'start_last_name': chain['start_last_name'],
                                'start_position': chain['start_position'],
                                'end_first_name': other_person['first_name'],
                                'end_last_name': other_person['last_name'],
                                'end_position': other_person['position'],
                                'contractor_name': contractor_name,
                                'start_company_role': current_person_role,
                                'end_company_role': other_person_role
                            }
                            
                            # Recursively extend this new chain
                            await recursive_extend(new_chain, depth + 1)
        
        # Start recursive traversal from each initial chain
        for i, initial_chain in enumerate(initial_chains):
            if (i + 1) % 50 == 0:
                print(f"  Processing chain {i+1}/{len(initial_chains)} (found {len(all_chains)} chains so far, {len(global_rendered_nodes)} nodes rendered)...", flush=True)
            await recursive_extend(initial_chain)
        
        chains = all_chains
        end_time = datetime.datetime.now()
        duration = (end_time - start_time).total_seconds() / 60
        print(f"[{end_time.strftime('%Y-%m-%d %H:%M:%S')}] Tree traversal completed in {duration:.1f} minutes", flush=True)
        print(f"📊 Found {len(chains)} relationship constellations from tree traversal", flush=True)
        
        # Add contractor-mediated relationships
        print("🔗 Checking contractor-dynasty relationships...", flush=True)
        
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
                -- Allow same-family connections (e.g., brothers via shared contractor)
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
        print(f"📊 Found {len(contractor_chains)} contractor-mediated connections", flush=True)
        
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
        
        # Add standalone party-list connections for families that aren't connected via direct relationships
        # These create new constellations, but we still want to show them
        print("🔗 Checking standalone party-list relationships (families only connected via party-list)...")
        
        party_list_standalone_query = """
        WITH party_list_members AS (
            SELECT DISTINCT
                p.id as person_id,
                p.first_name,
                p.last_name,
                p.position,
                pl.code as party_code,
                pl.party_list_number,
                pl.party_name,
                COALESCE(pl.party_list_number::text || ', ', '') || pl.party_name as party_full_name
            FROM political_dynasties p
            JOIN party_list pl ON (
                p.party LIKE pl.code || ', ' || UPPER(pl.party_name)
                OR p.party LIKE pl.code || ',' || UPPER(pl.party_name)
                OR (p.party LIKE '%' || UPPER(pl.party_name) || '%' AND p.position LIKE '%PARTY-LIST%')
            )
            WHERE p.id IS NOT NULL
              AND pl.party_list_number IS NOT NULL
        ),
        party_list_connections AS (
            SELECT DISTINCT
                plm1.person_id as person1_id,
                plm2.person_id as person2_id,
                plm1.party_code,
                plm1.party_list_number,
                plm1.party_name,
                plm1.party_full_name,
                'Party-List Membership' as relationship_type,
                p1.last_name as person1_last_name,
                p2.last_name as person2_last_name
            FROM party_list_members plm1
            JOIN party_list_members plm2
                ON plm1.party_list_number = plm2.party_list_number
                AND plm1.party_name = plm2.party_name
                AND plm1.person_id != plm2.person_id
            JOIN political_dynasties p1 ON plm1.person_id = p1.id
            JOIN political_dynasties p2 ON plm2.person_id = p2.id
            WHERE UPPER(p1.last_name) != UPPER(p2.last_name)  -- Different families (case-insensitive)
              -- Only include if these two people are NOT already connected via direct relationship
              AND NOT EXISTS (
                  SELECT 1 FROM relationships r
                  WHERE (r.person_id = plm1.person_id AND r.related_person_id = plm2.person_id)
                     OR (r.person_id = plm2.person_id AND r.related_person_id = plm1.person_id)
              )
        )
        SELECT 
            plc.person1_id as start_person,
            plc.person2_id as end_person,
            plc.party_code,
            plc.party_list_number,
            plc.party_name,
            plc.party_full_name,
            plc.relationship_type,
            p1.first_name as start_first_name,
            p1.last_name as start_last_name,
            p1.position as start_position,
            p2.first_name as end_first_name,
            p2.last_name as end_last_name,
            p2.position as end_position,
            p1.last_name as start_surname,
            p2.last_name as end_surname
        FROM party_list_connections plc
        JOIN political_dynasties p1 ON plc.person1_id = p1.id
        JOIN political_dynasties p2 ON plc.person2_id = p2.id
        WHERE p1.id != p2.id
        ORDER BY plc.party_name, p1.last_name, p2.last_name
        """
        
        party_list_standalone_chains = await conn.fetch(party_list_standalone_query)
        print(f"📊 Found {len(party_list_standalone_chains)} standalone party-list connections (families only connected via party-list)", flush=True)
        
        # Convert standalone party-list connections to same format
        party_list_standalone = []
        for plc in party_list_standalone_chains:
            party_list_standalone.append({
                'start_person': plc['start_person'],
                'end_person': plc['end_person'],
                'chain_length': 2,
                'start_surname': plc['start_surname'],
                'end_surname': plc['end_surname'],
                'start_first_name': plc['start_first_name'],
                'start_last_name': plc['start_last_name'],
                'start_position': plc['start_position'],
                'end_first_name': plc['end_first_name'],
                'end_last_name': plc['end_last_name'],
                'end_position': plc['end_position'],
                'path_string': f"{plc['start_person']},{plc['end_person']}",
                'relationship_string': f"Connected via {plc['party_name']}",
                'party_code': plc['party_code'],
                'party_list_number': plc['party_list_number'],
                'party_name': plc['party_name'],
                'party_full_name': plc['party_full_name'],
                'relationship_type': plc['relationship_type']
            })
        
        # Combine direct relationships, contractor connections, and standalone party-list connections
        # (Party-list extensions during tree traversal are already included in chains)
        all_chains = list(chains) + contractor_relationships + party_list_standalone
        
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
                SELECT id, first_name, middle_name, last_name, suffix, canonical_name, position, region, province, municipality_city
                FROM political_dynasties 
                WHERE id = $1
                """
                person = await conn.fetchrow(person_query, person_id)
                
                if person:
                    # Person found - add to path
                    relationship_desc = "Starting person" if i == 0 else relationships[i-1] if i-1 < len(relationships) else "Unknown"
                    
                    # Build full name with middle name and suffix
                    full_name_parts = [person['first_name']]
                    if person.get('middle_name'):
                        full_name_parts.append(person['middle_name'])
                    full_name_parts.append(person['last_name'])
                    if person.get('suffix'):
                        full_name_parts.append(person['suffix'])
                    full_name = ' '.join(full_name_parts)
                    
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
                        "middle_name": person.get('middle_name'),
                        "last_name": person['last_name'],
                        "suffix": person.get('suffix'),
                        "full_name": full_name,
                        "canonical_name": person.get('canonical_name'),
                        "position": person['position'],
                        "region": person['region'],
                        "province": person['province'],
                        "municipality_city": person['municipality_city'],
                        "location": location,
                        "relationship_description": relationship_desc
                    })
                else:
                    # Person not found - skip this person but continue with the chain
                    # This can happen if records were deleted after chain generation
                    print(f"⚠️ Warning: Person ID {person_id} not found in database (skipping from chain)", flush=True)
            
            # Skip chains where we couldn't load all person details
            if len(path_details) < len(person_ids):
                # Some people were missing - skip this chain or log it
                # For now, we'll continue but log a warning
                pass
            
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
            
            # Add party-list info for party-list-mediated connections
            # This includes both standalone party-list chains AND recursively extended chains
            if 'party_name' in chain and chain.get('party_name'):
                party_list_number = chain.get('party_list_number')
                party_name = chain['party_name']
                party_full_name = chain.get('party_full_name')
                if not party_full_name:
                    if party_list_number:
                        party_full_name = f"{party_list_number}, {party_name}"
                    else:
                        party_full_name = party_name
                
                chain_data["party_list_connection"] = {
                    "party_code": chain.get('party_code'),
                    "party_list_number": party_list_number,
                    "party_name": party_name,
                    "party_full_name": party_full_name,
                    "relationship_type": chain.get('relationship_type', 'Party-List Membership')
                }
            
            formatted_chains.append(chain_data)
        
        # Create cache data structure
        direct_count = len(chains)
        contractor_count = len(contractor_relationships)
        standalone_party_list_count = len(party_list_standalone)
        # Count party-list-mediated chains from formatted_chains (after formatting, party-list info is in party_list_connection field)
        # This includes both party-list extensions during tree traversal AND standalone party-list connections
        party_list_count = sum(1 for chain in formatted_chains if chain.get('party_list_connection') is not None)
        
        print(f"📊 Total constellations: {len(formatted_chains)} ({direct_count} direct + {contractor_count} contractor-mediated + {standalone_party_list_count} standalone party-list + {party_list_count - standalone_party_list_count} party-list extensions)", flush=True)
        
        # Calculate unique constellations (family pairs) and create mapping
        # A constellation is a unique connection between two families (regardless of path)
        from collections import defaultdict
        chains_by_constellation = defaultdict(list)
        
        for chain in formatted_chains:
            start_family = chain.get('start_surname', '').upper().strip()
            end_family = chain.get('end_surname', '').upper().strip()
            if start_family and end_family and start_family != end_family:
                # Normalize: use sorted tuple so A->B and B->A are the same constellation
                constellation_key = tuple(sorted([start_family, end_family]))
                chains_by_constellation[constellation_key].append(chain)
        
        total_constellations = len(chains_by_constellation)
        
        # Sort constellations by number of chains (descending) to prioritize those with more connections
        sorted_constellations = sorted(chains_by_constellation.items(), key=lambda x: len(x[1]), reverse=True)
        
        # Create mapping: how many chains needed to get N constellations
        # Calculate cumulative chain counts for common constellation targets
        constellation_mapping = {}
        max_constellations = len(sorted_constellations)
        
        for target_constellations in [1, 2, 5, 10, 20, 50, 100, 120, 150]:
            if target_constellations <= max_constellations:
                # Calculate chains needed for this many constellations
                chains_needed = sum(len(chains) for _, chains in sorted_constellations[:target_constellations])
                constellation_mapping[target_constellations] = chains_needed
        
        # Add "ALL" mapping (all constellations = all chains)
        constellation_mapping["ALL"] = len(formatted_chains)
        
        cache_data = {
            "summary": {
                "total_chains": len(formatted_chains),
                "total_constellations": total_constellations,
                "direct_relationships": direct_count,
                "contractor_mediated": contractor_count,
                "party_list_mediated": party_list_count,
                "constellation_mapping": constellation_mapping,  # Maps number of constellations -> chains needed
                "last_updated": datetime.datetime.now().isoformat(),
                "description": "Relationship constellations between different political families (includes contractor-mediated and party-list-mediated connections)"
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
        
        print(f"✅ Constellations cache generated: {cache_file}", flush=True)
        print(f"📊 Total constellations: {len(formatted_chains)}")
        
        return cache_data
        
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(generate_relationship_constellations_cache())



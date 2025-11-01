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
        
        # TREE-BASED BFS APPROACH: Build chains level by level like a tree
        # Level 0: Start with direct relationships (only in one direction: person_id < related_person_id)
        print("\n🌳 Building relationship tree level by level...", flush=True)
        
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
        
        current_level = await conn.fetch(level0_query)
        all_chains = list(current_level)
        
        # Track globally rendered nodes - nodes we've already extended through
        # Once a node is rendered, we stop any chain that would re-render it
        rendered_nodes = set()
        
        # Track rendered party-lists - party-lists we've already used as extension points
        # This prevents duplicate party-list nodes in the visualization
        rendered_party_lists = set()  # Set of (party_list_number, party_name) tuples
        
        # Queue of chains to extend (DFS approach - extend each chain as long as possible)
        # We'll process chains depth-first, prioritizing longer chains
        chains_to_extend = list(current_level)  # Start with level 0 chains
        
        # Sort chains by length (longer first) to prioritize extending longest chains
        chains_to_extend.sort(key=lambda c: len(c['path_string'].split(',')))
        
        print(f"  Level 0: {len(current_level)} chains", flush=True)
        
        max_depth = 6
        seen_paths = {c['path_string'] for c in all_chains}
        
        # Track chains at start of each iteration to identify newly created ones
        chains_at_start_of_iteration = {c['path_string'] for c in all_chains}
        
        # Process chains depth-first: extend each chain as far as possible before moving to next
        # Group chains by depth and process all chains at depth N before moving to depth N+1
        from collections import defaultdict
        
        while chains_to_extend:
            # Update tracking at start of iteration
            chains_at_start_of_iteration = {c['path_string'] for c in all_chains}
            # Group chains by depth
            chains_by_depth = defaultdict(list)
            for chain in chains_to_extend:
                depth = len(chain['path_string'].split(',')) - 1
                if depth < max_depth:
                    chains_by_depth[depth].append(chain)
            
            if not chains_by_depth:
                break
            
            # Process each depth level, starting with the deepest
            for current_depth in sorted(chains_by_depth.keys(), reverse=True):
                level_chains = chains_by_depth[current_depth]
                
                # Sort by length (longest first) to prioritize extending longest chains
                level_chains.sort(key=lambda c: len(c['path_string'].split(',')), reverse=True)
                
                print(f"  Depth {current_depth}: Processing {len(level_chains)} chains...", flush=True)
                nodes_rendered_this_iteration = set()
                
                # Process each chain individually - extend it as far as possible
                for chain in level_chains:
                    path = [int(x) for x in chain['path_string'].split(',')]
                    last_person = path[-1]
                    visited_in_chain = set(path)
                    
                    # Skip if last node is already rendered
                    if last_person in rendered_nodes:
                        continue
                    
                    extensions_found = False
                    party_list_extensions_found = False
                    
                    # Extension type 1: Direct relationships (both directions)
                    # Allow same-family connections if the target person connects to different families
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
                      AND r.related_person_id != ALL($2::int[])  -- Not in current chain path
                      AND r.related_person_id NOT IN (SELECT unnest($3::int[]))  -- Not already rendered
                      AND (
                          -- Different family (original logic) - case-insensitive
                          UPPER(p2.last_name) != UPPER($4)
                          OR
                          -- Same family BUT the target person connects to different families - case-insensitive
                          (UPPER(p2.last_name) = UPPER($4) AND EXISTS (
                              SELECT 1 FROM relationships r2
                              JOIN political_dynasties p3 ON (r2.person_id = p3.id AND r2.related_person_id = r.related_person_id)
                                       OR (r2.related_person_id = p3.id AND r2.person_id = r.related_person_id)
                              WHERE (r2.person_id = r.related_person_id OR r2.related_person_id = r.related_person_id)
                                AND UPPER(p3.last_name) != UPPER($4)
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
                      AND r.person_id != ALL($2::int[])  -- Not in current chain path
                      AND r.person_id NOT IN (SELECT unnest($3::int[]))  -- Not already rendered
                      AND (
                          -- Different family (original logic)
                          UPPER(p1.last_name) != UPPER($4)
                          OR
                          -- Same family BUT the target person connects to different families
                          (UPPER(p1.last_name) = UPPER($4) AND EXISTS (
                              SELECT 1 FROM relationships r2
                              JOIN political_dynasties p3 ON (r2.person_id = p3.id AND r2.related_person_id = r.person_id)
                                       OR (r2.related_person_id = p3.id AND r2.person_id = r.person_id)
                              WHERE (r2.person_id = r.person_id OR r2.related_person_id = r.person_id)
                                AND UPPER(p3.last_name) != UPPER($4)
                          ))
                      )
                    """
                    
                    extensions = await conn.fetch(ext1_query, last_person, path, list(rendered_nodes), chain['start_surname'])
                    
                    for ext in extensions:
                        if ext['next_person_id'] in rendered_nodes:
                            continue
                        
                        new_path = path + [ext['next_person_id']]
                        new_path_string = ','.join(str(p) for p in new_path)
                        
                        if new_path_string not in seen_paths:
                            new_chain = {
                                'start_person': chain['start_person'],
                                'end_person': ext['next_person_id'],
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
                                # Preserve party-list information if this chain was extended via party-list
                                'party_code': chain.get('party_code'),
                                'party_list_number': chain.get('party_list_number'),
                                'party_name': chain.get('party_name'),
                                'party_full_name': chain.get('party_full_name')
                            }
                            all_chains.append(new_chain)
                            seen_paths.add(new_path_string)
                            chains_to_extend.append(new_chain)  # Continue extending this chain
                            extensions_found = True
                    
                    # Extension type 2: Party-list connections
                    # Check party-list extensions BEFORE terminating the node
                    # This allows chains to extend via party-list even when direct relationships are exhausted
                    if last_person in person_to_parties:
                        for party_key in person_to_parties[last_person]:
                            party_list_number, party_name = party_key
                            
                            # Skip if this party-list was already rendered (to avoid duplicate party-list nodes)
                            if party_key in rendered_party_lists:
                                continue
                            
                            party_full_name = f"{party_list_number}, {party_name}" if party_list_number else party_name
                            
                            # Try to extend via party-list members
                            # Allow extensions even if other_member is same family (since party-list can connect families)
                            for other_member_id in party_to_members[party_key]:
                                if other_member_id in rendered_nodes or other_member_id in visited_in_chain:
                                    continue
                                
                                other_person = await conn.fetchrow("""
                                    SELECT last_name, first_name, position 
                                    FROM political_dynasties 
                                    WHERE id = $1
                                """, other_member_id)
                                
                                if not other_person:
                                    continue
                                
                                # Allow same-family connections via party-list (they can still extend the chain)
                                # Only require different families if we want to strictly enforce inter-family connections
                                # But for party-list extensions, we allow same-family since party-list connects to different families overall
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
                                    all_chains.append(new_chain)
                                    seen_paths.add(new_path_string)
                                    chains_to_extend.append(new_chain)  # Continue extending this chain via direct relationships
                                    party_list_extensions_found = True
                                    extensions_found = True
                                    
                                    # IMPORTANT: After extending via party-list, mark the party-list connection as established
                                    # so we can continue extending from the new member to non-party-list persons via direct relationships
                                    # The extension logic will handle this in the next iteration
                    
                    # Mark node as rendered only if we couldn't extend further via direct relationships OR party-list
                    # This ensures we try all possible extensions (direct and party-list) before giving up on a node
                    if not extensions_found:
                        nodes_rendered_this_iteration.add(last_person)
                        
                        # Mark party-lists as rendered if we tried them but found no extensions
                        # (This prevents trying the same party-list again from the same person)
                        if last_person in person_to_parties:
                            for party_key in person_to_parties[last_person]:
                                # Only mark as rendered if we actually checked it (not if it was already rendered)
                                if party_key not in rendered_party_lists:
                                    # Check if this party-list had any valid extensions
                                    party_list_number, party_name = party_key
                                    had_valid_extensions = False
                                    for other_member_id in party_to_members[party_key]:
                                        if other_member_id not in rendered_nodes and other_member_id not in visited_in_chain:
                                            other_person = await conn.fetchrow("""
                                                SELECT last_name FROM political_dynasties WHERE id = $1
                                            """, other_member_id)
                                            if other_person:
                                                new_path_test = path + [other_member_id]
                                                new_path_string_test = ','.join(str(p) for p in new_path_test)
                                                if new_path_string_test not in seen_paths:
                                                    had_valid_extensions = True
                                                    break
                                    
                                    # Only mark as rendered if no valid extensions were found
                                    if not had_valid_extensions:
                                        rendered_party_lists.add(party_key)
            
                # Mark nodes as rendered after processing all chains at this depth
                rendered_nodes.update(nodes_rendered_this_iteration)
                
                chains_at_next_depth = len([c for c in all_chains if len(c['path_string'].split(',')) == current_depth + 2])
                print(f"    Added {chains_at_next_depth} new chains, {len(nodes_rendered_this_iteration)} nodes exhausted (total chains: {len(all_chains)}, total rendered: {len(rendered_nodes)})", flush=True)
            
            # Update chains_to_extend for next iteration - only get newly created chains
            # that can still be extended (haven't reached max_depth and end node not rendered)
            chains_at_end_of_iteration = {c['path_string'] for c in all_chains}
            chains_to_extend = []
            for chain in all_chains:
                # Skip if this chain existed at the start of this iteration (already processed)
                if chain['path_string'] in chains_at_start_of_iteration:
                    continue
                    
                path = chain['path_string'].split(',')
                depth = len(path) - 1
                end_node = int(path[-1])
                
                # Only include newly created chains that can still be extended
                if depth < max_depth and end_node not in rendered_nodes:
                    chains_to_extend.append(chain)
            
            # Remove duplicates by path_string
            seen = set()
            chains_to_extend = [c for c in chains_to_extend if c['path_string'] not in seen and not seen.add(c['path_string'])]
            
            # Update tracking for next iteration
            chains_at_start_of_iteration = chains_at_end_of_iteration
        
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



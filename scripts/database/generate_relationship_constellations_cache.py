#!/usr/bin/env python3
"""
Generate relationship constellations cache for relationship visualization
Includes both direct relationships and contractor-mediated connections
Uses DuckDB and Parquet files instead of PostgreSQL
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import duckdb
from generate_relationship_constellations_cache_parquet_helper import DuckDBQueryHelper


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


def fetch_people(parquet_path):
    """Fetch people from parquet file using DuckDB"""
    conn = duckdb.connect()
    try:
        query = f"""
        SELECT id, first_name, middle_name, last_name,
               UPPER(TRIM(COALESCE(first_name, '')) || ' ' || TRIM(COALESCE(last_name, ''))) as normalized_name,
               position, region, province, municipality_city
        FROM read_parquet('{parquet_path}')
        """
        rows = conn.execute(query).fetchall()
        columns = [desc[0] for desc in conn.description]
        people = {}
        for row in rows:
            row_dict = dict(zip(columns, row))
            people[row_dict["id"]] = {
                "id": row_dict["id"],
                "first_name": row_dict["first_name"],
                "middle_name": row_dict.get("middle_name"),
                "last_name": row_dict["last_name"],
                "normalized_name": row_dict["normalized_name"],
                "position": row_dict["position"],
                "region": row_dict["region"],
                "province": row_dict["province"],
                "municipality_city": row_dict["municipality_city"],
            }
        return people
    finally:
        conn.close()


# Parquet file paths (module level)
PARQUET_DIR = Path(__file__).parent.parent.parent / 'data' / 'parquet'
POLITICAL_DYNASTIES_PARQUET = PARQUET_DIR / 'political_dynasties.parquet'
RELATIONSHIPS_PARQUET = PARQUET_DIR / 'relationships.parquet'
POLITICIAN_CONTRACTORS_PARQUET = PARQUET_DIR / 'politician_contractors.parquet'

async def generate_relationship_constellations_cache(test_person=None):
    """Generate JSON cache of relationship constellations between different political families
    
    Args:
        test_person: If provided, only generate cache for this person (normalized name, e.g., 'FRANCIS ESCUDERO')
    """
    MAX_CHAIN_DEPTH = 11
    load_env_from_dotenv()
    load_dotenv()
    
    if test_person:
        print(f"🧪 TEST MODE: Generating cache only for: {test_person}", flush=True)
    
    if not POLITICAL_DYNASTIES_PARQUET.exists():
        print(f"❌ Error: {POLITICAL_DYNASTIES_PARQUET} not found!")
        return None
    if not RELATIONSHIPS_PARQUET.exists():
        print(f"❌ Error: {RELATIONSHIPS_PARQUET} not found!")
        return None
    
    # DuckDB query helper (wraps DuckDB for async-like usage)
    db = DuckDBQueryHelper()
    
    try:
        print("🔍 Generating relationship constellations cache (using Parquet files)...")
        import datetime
        start_time = datetime.datetime.now()
        print(f"[{start_time.strftime('%Y-%m-%d %H:%M:%S')}] Starting tree-based BFS chain generation...", flush=True)
        
        # Get party-list memberships for party-list extensions
        # Use party_list_members table from parquet or DuckDB database
        # Use actual party_name if available, otherwise generate from party_list_number
        PARQUET_DIR = Path(__file__).parent.parent.parent / 'data' / 'parquet'
        PARTY_LIST_MEMBERS_PARQUET = PARQUET_DIR / 'party_list_members.parquet'
        
        if PARTY_LIST_MEMBERS_PARQUET.exists():
            # Use parquet file
            party_list_members_query = f"""
            SELECT DISTINCT
                plm.person_id,
                COALESCE(CAST(plm.party_code AS VARCHAR), CAST(plm.party_list_number AS VARCHAR)) as party_code,
                plm.party_list_number,
                COALESCE(plm.party_name, 'Party-List ' || CAST(plm.party_list_number AS VARCHAR)) as party_name,
                COALESCE(plm.party_name, 'Party-List ' || CAST(plm.party_list_number AS VARCHAR)) as party_full_name
            FROM read_parquet('{PARTY_LIST_MEMBERS_PARQUET}') plm
            JOIN read_parquet('{POLITICAL_DYNASTIES_PARQUET}') p ON plm.person_id = p.id
            WHERE plm.party_list_number IS NOT NULL
            """
        else:
            # Fallback to DuckDB database (if attached)
            party_list_members_query = """
            SELECT DISTINCT
                plm.person_id,
                COALESCE(CAST(plm.party_code AS VARCHAR), CAST(plm.party_list_number AS VARCHAR)) as party_code,
                plm.party_list_number,
                COALESCE(plm.party_name, 'Party-List ' || CAST(plm.party_list_number AS VARCHAR)) as party_name,
                COALESCE(plm.party_name, 'Party-List ' || CAST(plm.party_list_number AS VARCHAR)) as party_full_name
            FROM party_list_members plm
            JOIN read_parquet('{}') p ON plm.person_id = p.id
            WHERE plm.party_list_number IS NOT NULL
            """.format(str(POLITICAL_DYNASTIES_PARQUET))
        party_list_members_data = db.execute(party_list_members_query)
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
        JOIN read_parquet('{}') p ON (
            (UPPER(TRIM(p.first_name)) = UPPER(TRIM(cdm.dynasty_first_name))
             AND UPPER(TRIM(p.last_name)) = UPPER(TRIM(cdm.dynasty_last_name)))
            OR
            (UPPER(p.first_name) LIKE '%' || UPPER(TRIM(cdm.dynasty_first_name)) || '%'
             AND UPPER(TRIM(p.last_name)) = UPPER(TRIM(cdm.dynasty_last_name)))
        )
        WHERE p.id IS NOT NULL
          AND EXISTS (
                SELECT 1
                FROM politician_contractors pc
                WHERE UPPER(TRIM(pc.contractor_name)) = UPPER(TRIM(cdm.company_name))
          )
        """.format(str(POLITICAL_DYNASTIES_PARQUET))
        contractor_members_data = db.execute(contractor_members_query)
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
            CAST(r.person_id AS VARCHAR) || ',' || CAST(r.related_person_id AS VARCHAR) as path_string,
            COALESCE(r.normalized_description, r.relationship_description) as relationship_string,
            r.source_url,
            1 as chain_length,
            p1.last_name as start_surname,
            p2.last_name as end_surname,
            p1.first_name as start_first_name,
            p1.last_name as start_last_name,
            p1.position as start_position,
            p2.first_name as end_first_name,
            p2.last_name as end_last_name,
            p2.position as end_position
        FROM read_parquet('{}') r
        JOIN read_parquet('{}') p1 ON r.person_id = p1.id
        JOIN read_parquet('{}') p2 ON r.related_person_id = p2.id
        WHERE r.person_id != r.related_person_id
          AND (
            -- Different families (original logic) - only one direction to avoid duplicates
            -- Use UPPER() for case-insensitive comparison
            (UPPER(p1.last_name) != UPPER(p2.last_name) AND r.person_id < r.related_person_id)
            OR
            -- Same family BUT at least one connects to different families - allow both directions
            (UPPER(p1.last_name) = UPPER(p2.last_name) AND (
                EXISTS (
                    SELECT 1 FROM read_parquet('{}') r2
                    JOIN read_parquet('{}') p3 ON (
                        (r2.person_id = p3.id AND r2.related_person_id = r.person_id)
                        OR (r2.related_person_id = p3.id AND r2.person_id = r.person_id)
                    )
                    WHERE (r2.person_id = r.person_id OR r2.related_person_id = r.person_id)
                      AND UPPER(p3.last_name) != UPPER(p1.last_name)
                    LIMIT 1
                )
                OR EXISTS (
                    SELECT 1 FROM read_parquet('{}') r2
                    JOIN read_parquet('{}') p3 ON (
                        (r2.person_id = p3.id AND r2.related_person_id = r.related_person_id)
                        OR (r2.related_person_id = p3.id AND r2.person_id = r.related_person_id)
                    )
                    WHERE (r2.person_id = r.related_person_id OR r2.related_person_id = r.related_person_id)
                      AND UPPER(p3.last_name) != UPPER(p1.last_name)
                    LIMIT 1
                )
            ))
        )
        """.format(
            str(RELATIONSHIPS_PARQUET),
            str(POLITICAL_DYNASTIES_PARQUET),
            str(POLITICAL_DYNASTIES_PARQUET),
            str(RELATIONSHIPS_PARQUET),
            str(POLITICAL_DYNASTIES_PARQUET),
            str(RELATIONSHIPS_PARQUET),
            str(POLITICAL_DYNASTIES_PARQUET)
        )
        
        initial_chains = db.execute(level0_query)
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
            # Filter out self-connections (same person at start and end)
            if chain['path_string'] not in seen_paths:
                # Skip if start_person == end_person (self-connection)
                if chain['start_person'] != chain['end_person']:
                    all_chains.append(chain)
                    seen_paths.add(chain['path_string'])

            # Enforce maximum chain depth
            if len(path) >= MAX_CHAIN_DEPTH:
                return

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
            # Convert path list to SQL array format for DuckDB
            path_array = ','.join(str(p) for p in path)
            ext1_query = """
                    SELECT 
                        r.related_person_id as next_person_id,
                        COALESCE(r.normalized_description, r.relationship_description) as relationship_description,
                        r.source_url,
                        p2.last_name,
                        p2.first_name,
                        p2.position
                    FROM read_parquet('{}') r
                    JOIN read_parquet('{}') p2 ON r.related_person_id = p2.id
                    WHERE r.person_id = {}
              AND r.related_person_id NOT IN ({})
                      AND (
                  UPPER(p2.last_name) != UPPER('{}')
                          OR
                  (UPPER(p2.last_name) = UPPER('{}') AND EXISTS (
                              SELECT 1 FROM read_parquet('{}') r2
                              JOIN read_parquet('{}') p3 ON (r2.person_id = p3.id AND r2.related_person_id = r.related_person_id)
                                       OR (r2.related_person_id = p3.id AND r2.person_id = r.related_person_id)
                              WHERE (r2.person_id = r.related_person_id OR r2.related_person_id = r.related_person_id)
                        AND UPPER(p3.last_name) != UPPER('{}')
                          ))
                      )
                    
                    UNION ALL
                    
                    SELECT 
                        r.person_id as next_person_id,
                        COALESCE(r.normalized_description, r.relationship_description) as relationship_description,
                        r.source_url,
                        p1.last_name,
                        p1.first_name,
                        p1.position
                    FROM read_parquet('{}') r
                    JOIN read_parquet('{}') p1 ON r.person_id = p1.id
                    WHERE r.related_person_id = {}
              AND r.person_id NOT IN ({})
                      AND (
                  UPPER(p1.last_name) != UPPER('{}')
                          OR
                  (UPPER(p1.last_name) = UPPER('{}') AND EXISTS (
                              SELECT 1 FROM read_parquet('{}') r2
                              JOIN read_parquet('{}') p3 ON (r2.person_id = p3.id AND r2.related_person_id = r.person_id)
                                       OR (r2.related_person_id = p3.id AND r2.person_id = r.person_id)
                              WHERE (r2.person_id = r.person_id OR r2.related_person_id = r.person_id)
                        AND UPPER(p3.last_name) != UPPER('{}')
                          ))
                      )
                    """.format(
                str(RELATIONSHIPS_PARQUET), str(POLITICAL_DYNASTIES_PARQUET), last_person, path_array,
                chain['start_surname'], chain['start_surname'],
                str(RELATIONSHIPS_PARQUET), str(POLITICAL_DYNASTIES_PARQUET), chain['start_surname'],
                str(RELATIONSHIPS_PARQUET), str(POLITICAL_DYNASTIES_PARQUET), last_person, path_array,
                chain['start_surname'], chain['start_surname'],
                str(RELATIONSHIPS_PARQUET), str(POLITICAL_DYNASTIES_PARQUET), chain['start_surname']
            )
                    
            extensions = db.execute(ext1_query)
            
            for ext in extensions:
                next_person_id = ext['next_person_id']
                
                # Skip if already in current path (avoid cycles)
                if next_person_id in visited_in_chain:
                    continue
                
                new_path = path + [next_person_id]
                new_path_string = ','.join(str(p) for p in new_path)
                
                if new_path_string not in seen_paths:
                    existing_relationships = chain.get('relationship_string') or ''
                    extension_relationship = ext.get('relationship_description') or 'Unknown relationship'
                    if existing_relationships:
                        relationship_string = existing_relationships + ',' + extension_relationship
                    else:
                        relationship_string = extension_relationship
                    
                    # Collect source URLs
                    existing_sources = chain.get('source_urls', [])
                    new_sources = existing_sources.copy()
                    if ext.get('source_url') and ext['source_url'] not in new_sources:
                        new_sources.append(ext['source_url'])
                    
                    new_chain = {
                        'start_person': chain['start_person'],
                        'end_person': next_person_id,
                        'path_string': new_path_string,
                        'relationship_string': relationship_string,
                        'source_urls': new_sources,
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
                        
                        other_person = db.fetchrow("""
                            SELECT last_name, first_name, position 
                            FROM read_parquet('{}') 
                            WHERE id = {}
                        """.format(str(POLITICAL_DYNASTIES_PARQUET), other_member_id))
                        
                        if not other_person:
                            continue
                        
                        new_path = path + [other_member_id]
                        new_path_string = ','.join(str(p) for p in new_path)
                        
                        if new_path_string not in seen_paths:
                            # Preserve source_urls from parent chain
                            existing_sources = chain.get('source_urls', [])
                            
                            new_chain = {
                                'start_person': chain['start_person'],
                                'end_person': other_member_id,
                                'path_string': new_path_string,
                                'relationship_string': chain['relationship_string'] + ',Connected via ' + party_name,
                                'source_urls': existing_sources.copy(),  # Preserve source URLs
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
                    current_person_role = db.fetchval("""
                        SELECT role FROM contractor_dynasty_matches
                        WHERE company_name = '{}'
                          AND dynasty_first_name = (SELECT first_name FROM read_parquet('{}') WHERE id = {})
                          AND dynasty_last_name = (SELECT last_name FROM read_parquet('{}') WHERE id = {})
                        LIMIT 1
                    """.format(contractor_name, str(POLITICAL_DYNASTIES_PARQUET), last_person, str(POLITICAL_DYNASTIES_PARQUET), last_person))
                    
                    for other_member_id in contractor_to_members[contractor_name]:
                        if other_member_id in visited_in_chain:
                            continue
                        
                        other_person = db.fetchrow("""
                            SELECT last_name, first_name, position 
                            FROM read_parquet('{}') 
                            WHERE id = {}
                        """.format(str(POLITICAL_DYNASTIES_PARQUET), other_member_id))
                        
                        if not other_person:
                            continue
                        
                        # Get contractor role for the other person
                        other_person_role = db.fetchval("""
                            SELECT role FROM contractor_dynasty_matches
                            WHERE company_name = '{}'
                              AND dynasty_first_name = (SELECT first_name FROM read_parquet('{}') WHERE id = {})
                              AND dynasty_last_name = (SELECT last_name FROM read_parquet('{}') WHERE id = {})
                            LIMIT 1
                        """.format(contractor_name, str(POLITICAL_DYNASTIES_PARQUET), other_member_id, str(POLITICAL_DYNASTIES_PARQUET), other_member_id))
                        
                        new_path = path + [other_member_id]
                        new_path_string = ','.join(str(p) for p in new_path)
                        
                        if new_path_string not in seen_paths:
                            # Preserve source_urls from parent chain
                            # Note: politician_contractors table doesn't have source_url column,
                            # so we only preserve URLs from the relationships that led to this contractor connection
                            existing_sources = chain.get('source_urls', [])
                            new_sources = existing_sources.copy()
                            
                            new_chain = {
                                'start_person': chain['start_person'],
                                'end_person': other_member_id,
                                'path_string': new_path_string,
                                'relationship_string': chain['relationship_string'] + ',Connected via ' + contractor_name,
                                'source_urls': new_sources,  # Preserve source URLs from parent chain
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
        for i, initial_chain_record in enumerate(initial_chains):
            if (i + 1) % 50 == 0:
                print(f"  Processing chain {i+1}/{len(initial_chains)} (found {len(all_chains)} chains so far, {len(global_rendered_nodes)} nodes rendered)...", flush=True)
            # Convert dict (already from DuckDB) to dict for modification
            initial_chain = dict(initial_chain_record) if isinstance(initial_chain_record, dict) else initial_chain_record
            # Initialize source_urls for level 0 chains
            if 'source_urls' not in initial_chain:
                initial_chain['source_urls'] = []
            if initial_chain.get('source_url') and initial_chain['source_url'] not in initial_chain['source_urls']:
                initial_chain['source_urls'].append(initial_chain['source_url'])
            await recursive_extend(initial_chain)
        
        chains = all_chains
        end_time = datetime.datetime.now()
        duration = (end_time - start_time).total_seconds() / 60
        print(f"[{end_time.strftime('%Y-%m-%d %H:%M:%S')}] Tree traversal completed in {duration:.1f} minutes", flush=True)
        print(f"📊 Found {len(chains)} relationship constellations from tree traversal", flush=True)
        
        # Add contractor-mediated relationships
        print("🔗 Checking contractor-dynasty relationships...", flush=True)
        
        contractor_relationships_query = """
        WITH normalized_matches AS (
            SELECT DISTINCT
                pc.contractor_name AS company_name,
                pc.politician_id AS person_id,
                COALESCE(pc.notes, 'Listed in Rappler Politicontractors tracker') AS role
            FROM read_parquet('{}') pc
        ),
        contractor_connections AS (
            SELECT
                LEAST(m1.person_id, m2.person_id) AS person1_id,
                GREATEST(m1.person_id, m2.person_id) AS person2_id,
                m1.role AS person1_role,
                m2.role AS person2_role,
                m1.company_name AS contractor_name,
                'Business/Contractor Connection' AS relationship_type
            FROM normalized_matches m1
            JOIN normalized_matches m2
              ON m1.company_name = m2.company_name
             AND m1.person_id < m2.person_id
        )
        SELECT 
            cc.person1_id as start_person,
            cc.person2_id as end_person,
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
        JOIN read_parquet('{}') p1 ON p1.id = cc.person1_id
        JOIN read_parquet('{}') p2 ON p2.id = cc.person2_id
        WHERE p1.id != p2.id
        ORDER BY cc.contractor_name, p1.last_name, p2.last_name
        """.format(
            str(POLITICIAN_CONTRACTORS_PARQUET),
            str(POLITICAL_DYNASTIES_PARQUET), str(POLITICAL_DYNASTIES_PARQUET)
        )
        
        contractor_chains = db.execute(contractor_relationships_query)
        print(f"📊 Found {len(contractor_chains)} contractor-mediated connections", flush=True)
        
        # Also add single-person contractors (contractors with only 1 person connected)
        # These won't show up in the JOIN above but should still appear in the constellation
        print("🔗 Checking single-person contractor connections...", flush=True)
        
        single_person_contractors_query = """
        WITH company_person_counts AS (
            SELECT
                contractor_name,
                COUNT(DISTINCT politician_id) AS person_count
            FROM read_parquet('{}')
            GROUP BY contractor_name
        ),
        single_contractor_people AS (
            SELECT
                pc.contractor_name,
                pc.politician_id,
                COALESCE(pc.notes, 'Listed in Rappler Politicontractors tracker') AS role
            FROM read_parquet('{}') pc
            JOIN company_person_counts cpc
              ON pc.contractor_name = cpc.contractor_name
            WHERE cpc.person_count = 1
        )
        SELECT 
            scp.politician_id as start_person,
            scp.politician_id as end_person,
            scp.contractor_name as contractor_name,
            'Business/Contractor Connection' as relationship_type,
            scp.role as person1_role,
            scp.role as person2_role,
            p.first_name as start_first_name,
            p.last_name as start_last_name,
            p.position as start_position,
            p.first_name as end_first_name,
            p.last_name as end_last_name,
            p.position as end_position,
            p.last_name as start_surname,
            p.last_name as end_surname
        FROM single_contractor_people scp
        JOIN read_parquet('{}') p ON p.id = scp.politician_id
        """.format(str(POLITICIAN_CONTRACTORS_PARQUET), str(POLITICIAN_CONTRACTORS_PARQUET), str(POLITICAL_DYNASTIES_PARQUET))
        
        single_person_chains = db.execute(single_person_contractors_query)
        print(f"📊 Found {len(single_person_chains)} single-person contractor connections", flush=True)
        
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
        
        # Use party_list_members table directly (database-level connections)
        party_list_standalone_query = """
        WITH party_list_connections AS (
            SELECT DISTINCT
                plm1.person_id as person1_id,
                plm2.person_id as person2_id,
                COALESCE(CAST(plm1.party_code AS VARCHAR), CAST(plm1.party_list_number AS VARCHAR)) as party_code,
                plm1.party_list_number,
                COALESCE(plm1.party_name, 'Party-List ' || CAST(plm1.party_list_number AS VARCHAR)) as party_name,
                COALESCE(plm1.party_name, 'Party-List ' || CAST(plm1.party_list_number AS VARCHAR)) as party_full_name,
                'Party-List Membership' as relationship_type,
                p1.last_name as person1_last_name,
                p2.last_name as person2_last_name
            FROM party_list_members plm1
            JOIN party_list_members plm2
                ON plm1.party_list_number = plm2.party_list_number
                AND plm1.person_id != plm2.person_id
            JOIN read_parquet('{}') p1 ON plm1.person_id = p1.id
            JOIN read_parquet('{}') p2 ON plm2.person_id = p2.id
            WHERE UPPER(p1.last_name) != UPPER(p2.last_name)  -- Different families (case-insensitive)
              -- Only include if these two people are NOT already connected via direct relationship
              AND NOT EXISTS (
                  SELECT 1 FROM read_parquet('{}') r
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
        JOIN read_parquet('{}') p1 ON plc.person1_id = p1.id
        JOIN read_parquet('{}') p2 ON plc.person2_id = p2.id
        WHERE p1.id != p2.id
        ORDER BY plc.party_name, p1.last_name, p2.last_name
        """.format(
            str(POLITICAL_DYNASTIES_PARQUET), str(POLITICAL_DYNASTIES_PARQUET),
            str(RELATIONSHIPS_PARQUET),
            str(POLITICAL_DYNASTIES_PARQUET), str(POLITICAL_DYNASTIES_PARQUET)
        )
        
        party_list_standalone_chains = db.execute(party_list_standalone_query)
        print(f"📊 Found {len(party_list_standalone_chains)} standalone party-list connections (families only connected via party-list)", flush=True)
        
        # Also add single-person party-list connections (party-lists with only 1 person)
        # Party-lists are nodes themselves, so Person → Party-list is a 2-node chain
        # Use party_list_members table directly (database-level connections)
        single_person_party_list_query = """
        WITH party_list_person_counts AS (
            SELECT 
                COALESCE(CAST(plm.party_code AS VARCHAR), CAST(plm.party_list_number AS VARCHAR)) as party_code,
                plm.party_list_number,
                COALESCE(plm.party_name, 'Party-List ' || CAST(plm.party_list_number AS VARCHAR)) as party_name,
                COUNT(DISTINCT plm.person_id) as person_count
            FROM party_list_members plm
            WHERE plm.party_list_number IS NOT NULL
            GROUP BY plm.party_list_number, plm.party_code, plm.party_name
        ),
        single_person_party_lists AS (
            SELECT plpc.party_code, plpc.party_list_number, plpc.party_name
            FROM party_list_person_counts plpc
            WHERE plpc.person_count = 1
        ),
        single_party_list_people AS (
            SELECT DISTINCT
                sppl.party_code,
                sppl.party_list_number,
                sppl.party_name,
                sppl.party_name as party_full_name,
                p.id as person_id,
                p.first_name,
                p.last_name,
                p.position
            FROM single_person_party_lists sppl
            JOIN party_list_members plm ON (
                plm.party_list_number = sppl.party_list_number
            )
            JOIN read_parquet('{}') p ON plm.person_id = p.id
            WHERE NOT EXISTS (
                  -- Don't include if already in party_list_standalone_chains (has multiple people)
                  SELECT 1 FROM party_list_person_counts plpc2
                  WHERE plpc2.party_list_number = sppl.party_list_number
                    AND plpc2.person_count > 1
              )
        )
        SELECT 
            spp.person_id as start_person,
            spp.person_id as end_person,
            spp.party_code,
            spp.party_list_number,
            spp.party_name,
            spp.party_full_name,
            'Party-List Membership' as relationship_type,
            spp.first_name as start_first_name,
            spp.last_name as start_last_name,
            spp.position as start_position,
            spp.first_name as end_first_name,
            spp.last_name as end_last_name,
            spp.position as end_position,
            spp.last_name as start_surname,
            spp.last_name as end_surname
        FROM single_party_list_people spp
        """.format(str(POLITICAL_DYNASTIES_PARQUET))
        
        single_person_party_list_chains = db.execute(single_person_party_list_query)
        print(f"📊 Found {len(single_person_party_list_chains)} single-person party-list connections", flush=True)
        
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
                'relationship_type': plc['relationship_type'],
                'is_standalone_party_list': True
            })
        
        # Add single-person party-list chains
        # Party-lists are nodes themselves, so Person → Party-list is a 2-node chain
        for sp in single_person_party_list_chains:
            party_list_standalone.append({
                'start_person': sp['start_person'],
                'end_person': sp['start_person'],  # Same person, but party-list is the node
                'chain_length': 2,  # Person → Party-list (party-list is a node)
                'start_surname': sp['start_surname'],
                'end_surname': sp['end_surname'],
                'start_first_name': sp['start_first_name'],
                'start_last_name': sp['start_last_name'],
                'start_position': sp['start_position'],
                'end_first_name': sp['end_first_name'],
                'end_last_name': sp['end_last_name'],
                'end_position': sp['end_position'],
                'path_string': f"{sp['start_person']}",  # Person ID, party-list node added in formatting
                'relationship_string': f"Connected via {sp['party_name']}",
                'party_code': sp['party_code'],
                'party_list_number': sp['party_list_number'],
                'party_name': sp['party_name'],
                'party_full_name': sp['party_full_name'],
                'relationship_type': sp['relationship_type'],
                'is_standalone_party_list': True
            })
        
        # Contractors are nodes themselves, so Person → Contractor is a 2-node chain
        for sc in single_person_chains:
            contractor_relationships.append({
                'start_person': sc['start_person'],
                'end_person': sc['start_person'],
                'chain_length': 2,
                'start_surname': sc['start_surname'],
                'end_surname': sc['end_surname'],
                'start_first_name': sc['start_first_name'],
                'start_last_name': sc['start_last_name'],
                'start_position': sc['start_position'],
                'start_company_role': sc.get('person1_role'),
                'end_first_name': sc['end_first_name'],
                'end_last_name': sc['end_last_name'],
                'end_position': sc['end_position'],
                'end_company_role': sc.get('person2_role'),
                'path_string': f"{sc['start_person']}",
                'relationship_string': f"Connected via {sc['contractor_name']}",
                'contractor_name': sc['contractor_name'],
                'relationship_type': sc['relationship_type']
            })
        
        # Combine direct relationships, contractor connections, and standalone party-list connections
        # (Party-list extensions during tree traversal are already included in chains)
        all_chains = list(chains) + contractor_relationships + party_list_standalone
        
        people_cache = fetch_people(POLITICAL_DYNASTIES_PARQUET)

        # Format the data
        formatted_chains = []
        people_dict = {}  # Dictionary to store person metadata once
        
        for chain in all_chains:
            # Parse the path string to get all person IDs
            person_ids = [int(id_str) for id_str in chain['path_string'].split(',')]
            relationship_string = chain.get('relationship_string')
            if relationship_string and isinstance(relationship_string, str):
                relationships = relationship_string.split(',')
            else:
                relationships = []
            
            # Get person details for each person in the chain
            path_person_ids = []  # Store only person IDs and relationship descriptions
            path_relationships = []  # Store relationship descriptions for each hop
            
            for i, person_id in enumerate(person_ids):
                person = people_cache.get(person_id)
                
                if person:
                    # Person found - add to people_dict if not already present
                    if person_id not in people_dict:
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
                        
                        # Build location string
                        location_parts = []
                        if person['municipality_city']:
                            location_parts.append(person['municipality_city'])
                        if person['province']:
                            location_parts.append(person['province'])
                        if person['region']:
                            location_parts.append(person['region'])
                        location = ', '.join(location_parts) if location_parts else 'Location unknown'
                        
                        # Store person metadata once - SIMPLIFIED for popups
                        # Only keep what's needed: id, full name, position, and location context
                        people_dict[person_id] = {
                            "id": person_id,
                            "full_name": full_name,
                            "position": person['position'],
                            "location": location
                        }
                    
                    # Add person ID to path
                    path_person_ids.append(person_id)
                    
                    # Store relationship description for this hop
                    relationship_desc = "Starting person" if i == 0 else relationships[i-1] if i-1 < len(relationships) else "Unknown"
                    path_relationships.append(relationship_desc)
                else:
                    # Person not found - skip this person but continue with the chain
                    # This can happen if records were deleted after chain generation
                    print(f"⚠️ Warning: Person ID {person_id} not found in database (skipping from chain)", flush=True)
            
            # Skip chains where we couldn't load all person details
            if len(path_person_ids) < len(person_ids):
                # Some people were missing - skip this chain or log it
                # For now, we'll continue but log a warning
                pass
            
            # Add contractor information if this is a contractor-mediated connection
            # For contractors, length includes the contractor node (Person → Contractor = 2 nodes)
            # For single-person contractors, path_person_ids has 1 person but length should be 2 (Person + Contractor node)
            chain_length = len(path_person_ids)
            if 'contractor_name' in chain and chain.get('contractor_name'):
                # Contractor is a node itself, so length is person count + 1 contractor node
                # But if it's a single-person contractor (path_person_ids = 1), length should be 2
                if len(path_person_ids) == 1 and chain.get('chain_length') == 2:
                    chain_length = 2  # Person → Contractor node
                elif len(path_person_ids) > 1:
                    chain_length = len(path_person_ids) + 1  # People + Contractor node
                else:
                    chain_length = len(path_person_ids) + 1  # Default: add contractor node
            
            chain_data = {
                "length": chain_length,
                "path": path_person_ids,  # Store only person IDs
                "relationships": path_relationships,  # Store relationship descriptions for each hop
            }
            if chain.get('is_standalone_party_list'):
                chain_data["is_standalone_party_list"] = True
            
            # Add contractor info for contractor-mediated connections
            if 'contractor_name' in chain and chain['contractor_name']:
                # Get company roles for start and end persons
                # Only set roles if the person is actually in contractor_dynasty_matches
                start_role = None
                end_role = None
                
                # Check if start_person is in contractor_dynasty_matches for this contractor
                if path_person_ids and len(path_person_ids) > 0:
                    start_person_id = path_person_ids[0]
                    if start_person_id:
                        # Escape apostrophes in contractor name for SQL
                        contractor_name_escaped = chain['contractor_name'].replace("'", "''")
                        start_role = db.fetchval("""
                            SELECT role FROM contractor_dynasty_matches
                            WHERE company_name = '{}'
                              AND dynasty_first_name = (SELECT first_name FROM read_parquet('{}') WHERE id = {})
                              AND dynasty_last_name = (SELECT last_name FROM read_parquet('{}') WHERE id = {})
                            LIMIT 1
                        """.format(contractor_name_escaped, str(POLITICAL_DYNASTIES_PARQUET), start_person_id, str(POLITICAL_DYNASTIES_PARQUET), start_person_id))
                
                # Check if end_person is in contractor_dynasty_matches for this contractor
                if path_person_ids and len(path_person_ids) > 0:
                    end_person_id = path_person_ids[-1]
                    if end_person_id:
                        # Escape apostrophes in contractor name for SQL
                        contractor_name_escaped = chain['contractor_name'].replace("'", "''")
                        end_role = db.fetchval("""
                            SELECT role FROM contractor_dynasty_matches
                            WHERE company_name = '{}'
                              AND dynasty_first_name = (SELECT first_name FROM read_parquet('{}') WHERE id = {})
                              AND dynasty_last_name = (SELECT last_name FROM read_parquet('{}') WHERE id = {})
                            LIMIT 1
                        """.format(contractor_name_escaped, str(POLITICAL_DYNASTIES_PARQUET), end_person_id, str(POLITICAL_DYNASTIES_PARQUET), end_person_id))
                
                chain_data["contractor_connection"] = {
                    "contractor_name": chain['contractor_name'],
                    "start_company_role": start_role,
                    "end_company_role": end_role,
                    "start_position": chain.get('start_position'),
                    "end_position": chain.get('end_position')
                }
            
            # Add party-list info for party-list-mediated connections
            # This includes both standalone party-list chains AND recursively extended chains
            # For party-lists, length includes the party-list node (Person → Party-list = 2 nodes)
            if 'party_name' in chain and chain.get('party_name'):
                party_list_number = chain.get('party_list_number')
                party_name = chain['party_name']
                party_full_name = chain.get('party_full_name')
                if not party_full_name:
                    if party_list_number:
                        party_full_name = f"{party_list_number}, {party_name}"
                    else:
                        party_full_name = party_name
                
                # Party-list is a node itself, so adjust length if needed
                if len(path_person_ids) == 1 and chain.get('chain_length') == 2:
                    chain_length = 2  # Person → Party-list node
                elif len(path_person_ids) > 1:
                    chain_length = len(path_person_ids) + 1  # People + Party-list node
                else:
                    chain_length = len(path_person_ids) + 1  # Default: add party-list node
                
                chain_data["length"] = chain_length
                chain_data["party_list_connection"] = {
                    "party_name": party_name,
                    "party_full_name": party_full_name
                }
            
            formatted_chains.append(chain_data)
        
        # Create cache data structure
        filtered_direct_count = sum(
            1 for chain in formatted_chains
            if not chain.get('contractor_connection') and not chain.get('party_list_connection')
        )
        filtered_contractor_count = sum(
            1 for chain in formatted_chains
            if chain.get('contractor_connection')
        )
        filtered_party_list_count = sum(
            1 for chain in formatted_chains
            if chain.get('party_list_connection')
        )
        filtered_standalone_party_list_count = sum(
            1 for chain in formatted_chains
            if chain.get('is_standalone_party_list')
        )
        
        party_list_extensions_count = max(filtered_party_list_count - filtered_standalone_party_list_count, 0)
        
        print(f"📊 Total constellations: {len(formatted_chains)} ({filtered_direct_count} direct + {filtered_contractor_count} contractor-mediated + {filtered_standalone_party_list_count} standalone party-list + {party_list_extensions_count} party-list extensions)", flush=True)
        
        length_index = {}
        for idx, chain in enumerate(formatted_chains):
            length_value = chain.get("length")
            if isinstance(length_value, int) and length_value > 0:
                key = str(length_value)
                length_index.setdefault(key, []).append(idx)
        
        if length_index:
            max_chain_length = max(int(key) for key in length_index.keys())
        else:
            max_chain_length = None
        
        # Calculate unique constellations (family pairs) and create mapping
        # A constellation is a unique connection between two families (regardless of path)
        from collections import defaultdict
        chains_by_constellation = defaultdict(list)
        
        for chain in formatted_chains:
            # Extract surnames from people_dict using the start/end IDs from the path
            start_person_id = chain['path'][0] if chain['path'] else None
            end_person_id = chain['path'][-1] if chain['path'] else None
            
            start_family = ""
            end_family = ""
            
            # We need to look up the surnames from the original people_cache since we stripped them from people_dict
            if start_person_id and start_person_id in people_cache:
                start_family = people_cache[start_person_id]['last_name'].upper().strip()
            
            if end_person_id and end_person_id in people_cache:
                end_family = people_cache[end_person_id]['last_name'].upper().strip()
                
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
        
        # Organize chains by person (normalized name) for per-person loading
        # This allows autocomplete filtering and loading only relevant chains
        chains_by_person = {}  # Key: normalized person name, Value: list of chain indices
        person_autocomplete = []  # List of person names for autocomplete
        
        def normalize_person_name(first_name, last_name, suffix=None):
            """Normalize person name for consistent indexing"""
            name_parts = []
            if first_name:
                name_parts.append(first_name.strip().upper())
            if last_name:
                name_parts.append(last_name.strip().upper())
            if suffix:
                name_parts.append(suffix.strip().upper())
            return ' '.join(name_parts)
        
        # Build person index from people_cache (use normalized_name from DB)
        # We use people_cache here because people_dict is now simplified and lacks metadata
        person_name_to_id = {}  # normalized_name -> person_id
        for person_id, person_data in people_cache.items():
            # Use normalized_name from DB if available, otherwise compute it
            normalized_name = person_data.get('normalized_name')
            if not normalized_name:
                normalized_name = normalize_person_name(
                    person_data.get('first_name', ''),
                    person_data.get('last_name', ''),
                    person_data.get('suffix')
                )
            if normalized_name:
                person_name_to_id[normalized_name] = person_id
        
        # Organize chains by person
        for chain_idx, chain in enumerate(formatted_chains):
            # Get all person IDs in this chain
            person_ids = chain.get('path', [])
            
            # For each person in the chain, add this chain to their index
            for person_id in person_ids:
                person_data = people_cache.get(person_id)
                if person_data:
                    # Use normalized_name from DB if available, otherwise compute it
                    normalized_name = person_data.get('normalized_name')
                    if not normalized_name:
                        normalized_name = normalize_person_name(
                            person_data.get('first_name', ''),
                            person_data.get('last_name', ''),
                            person_data.get('suffix')
                        )
                    if normalized_name:
                        if normalized_name not in chains_by_person:
                            chains_by_person[normalized_name] = []
                        chains_by_person[normalized_name].append(chain_idx)
        
        # Build autocomplete list with display names
        for normalized_name in sorted(chains_by_person.keys()):
            person_id = person_name_to_id.get(normalized_name)
            if person_id:
                person_data = people_cache.get(person_id)
                if person_data:
                    # Create display name
                    display_parts = []
                    if person_data.get('first_name'):
                        display_parts.append(person_data['first_name'])
                    if person_data.get('last_name'):
                        display_parts.append(person_data['last_name'])
                    if person_data.get('suffix'):
                        display_parts.append(person_data['suffix'])
                    display_name = ' '.join(display_parts)
                    
                    person_autocomplete.append({
                        "id": person_id,
                        "normalized_name": normalized_name,
                        "display_name": display_name,
                        "position": person_data.get('position'),
                        "chain_count": len(chains_by_person[normalized_name])
                    })
        
        cache_data = {
            "summary": {
                "total_chains": len(formatted_chains),
                "total_constellations": total_constellations,
                "direct_relationships": filtered_direct_count,
                "contractor_mediated": filtered_contractor_count,
                "party_list_mediated": filtered_party_list_count,
                "standalone_party_list": filtered_standalone_party_list_count,
                "max_chain_length": max_chain_length,
                "constellation_mapping": constellation_mapping,  # Maps number of constellations -> chains needed
                "last_updated": datetime.datetime.now().isoformat(),
                "description": "Relationship constellations between different political families (includes contractor-mediated and party-list-mediated connections)"
            },
            "people": people_dict,  # Centralized person metadata dictionary
            "chains": formatted_chains,
            "length_index": length_index,
            "chains_by_person": chains_by_person,  # Index: normalized_name -> list of chain indices
            "person_autocomplete": person_autocomplete  # List of person names for autocomplete
        }
        
        # Ensure cache directory exists
        cache_dir = "static/data"
        os.makedirs(cache_dir, exist_ok=True)
        
        # Create directory for person-specific JSON files
        person_cache_dir = os.path.join(cache_dir, "relationship_chains_by_person")
        os.makedirs(person_cache_dir, exist_ok=True)
        
        # Write main cache file
        # Include chains for "all" view (when no person is selected)
        # In test mode, we can skip chains to save space
        if test_person:
            # Test mode: only metadata
            main_cache_data = {
                "summary": cache_data["summary"],
                "people": cache_data["people"],
                "person_autocomplete": cache_data["person_autocomplete"]
            }
        else:
            # Full mode: include chains for "all" view
            main_cache_data = {
                "summary": cache_data["summary"],
                "people": cache_data["people"],
                "chains": cache_data["chains"],
                "length_index": cache_data["length_index"],
                "chains_by_person": cache_data["chains_by_person"],
                "person_autocomplete": cache_data["person_autocomplete"]
            }
        
        main_cache_file = os.path.join(cache_dir, "relationship_chains_cache.json")
        with open(main_cache_file, 'w', encoding='utf-8') as f:
            json.dump(main_cache_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Main cache file generated: {main_cache_file}", flush=True)
        
        # Create lightweight autocomplete-only file for fast initial loading
        autocomplete_file = os.path.join(cache_dir, "relationship_chains_autocomplete.json")
        autocomplete_data = {
            "person_autocomplete": cache_data["person_autocomplete"],
            "chains_by_person": cache_data["chains_by_person"]
        }
        with open(autocomplete_file, 'w', encoding='utf-8') as f:
            json.dump(autocomplete_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Autocomplete file generated: {autocomplete_file}", flush=True)
        
        # Create separate JSON files for each person
        print(f"📁 Creating person-specific JSON files...", flush=True)
        person_files_created = 0
        
        # Filter to test person if specified
        persons_to_process = chains_by_person.items()
        if test_person:
            test_person_upper = test_person.upper().strip()
            persons_to_process = [(name, indices) for name, indices in chains_by_person.items() 
                                 if name.upper() == test_person_upper or test_person_upper in name.upper()]
            if not persons_to_process:
                print(f"⚠️  No chains found for test person: {test_person}", flush=True)
                print(f"   Available persons with 'ESCUDERO': {[name for name in chains_by_person.keys() if 'ESCUDERO' in name.upper()][:10]}", flush=True)
        
        for normalized_name, chain_indices in persons_to_process:
            # Get chains for this person
            person_chains = [formatted_chains[idx] for idx in chain_indices if idx < len(formatted_chains)]
            
            if not person_chains:
                continue
            
            # Create safe filename from normalized name
            safe_filename = normalized_name.replace(' ', '_').replace('/', '_').replace('\\', '_')
            safe_filename = ''.join(c for c in safe_filename if c.isalnum() or c in ('_', '-', '.'))
            person_file = os.path.join(person_cache_dir, f"{safe_filename}.json")
            
            # Create person-specific cache data
            person_cache_data = {
                "person": {
                    "normalized_name": normalized_name,
                    "display_name": next((p["display_name"] for p in person_autocomplete if p["normalized_name"] == normalized_name), normalized_name),
                    "chain_count": len(person_chains)
                },
                "chains": person_chains,
                "people": {pid: people_dict[pid] for pid in people_dict.keys() 
                           if any(pid in chain.get('path', []) for chain in person_chains)}
            }
            
            # Write person-specific file
            with open(person_file, 'w', encoding='utf-8') as f:
                json.dump(person_cache_data, f, indent=2, ensure_ascii=False)
            
            person_files_created += 1
            
            if person_files_created % 100 == 0:
                print(f"  Created {person_files_created} person files...", flush=True)
        
        print(f"✅ Created {person_files_created} person-specific JSON files in {person_cache_dir}", flush=True)
        print(f"📊 Total constellations: {len(formatted_chains)}")
        
        return cache_data
        
    finally:
        db.close()

if __name__ == "__main__":
    # Check for test person argument
    test_person = None
    if len(sys.argv) > 1:
        test_person = sys.argv[1]
        print(f"🧪 Running in test mode for: {test_person}", flush=True)
    
    asyncio.run(generate_relationship_constellations_cache(test_person=test_person))



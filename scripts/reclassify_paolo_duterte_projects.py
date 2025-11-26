#!/usr/bin/env python3
"""
Reclassify Paolo Duterte's projects to correct congressmen.

This script:
1. Finds projects incorrectly assigned to Paolo Duterte (non-Davao locations)
2. Clears their classification columns
3. Re-runs classification using the main script's logic
4. Updates congressman cache files incrementally (preserves existing projects)
"""

import sys
import os
import asyncio
import duckdb
import asyncpg
from pathlib import Path
from typing import Dict, List, Optional
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.generate_dynasty_projects_cache_duckdb import DynastyProjectsCacheGeneratorDuckDB

async def reclassify_paolo_duterte_projects():
    """Reclassify all Paolo Duterte's incorrectly assigned projects"""
    
    print("=" * 80)
    print("Reclassifying Paolo Duterte's Projects")
    print("=" * 80)
    
    # Initialize generator
    generator = DynastyProjectsCacheGeneratorDuckDB()
    
    # Load config and build dictionaries (no hardcoding)
    print("\n📊 Loading configuration and building dictionaries...")
    config_data, districts_data = await generator.load_config()
    
    # Connect to dynasty database
    common_db_kwargs = {
        "host": os.getenv('POSTGRES_HOST', 'localhost'),
        "port": int(os.getenv('POSTGRES_PORT', 5432)),
        "user": os.getenv('POSTGRES_USER', 'budget_admin'),
        "password": os.getenv('POSTGRES_PASSWORD', '')
    }
    
    dynasty_conn = await asyncpg.connect(**{
        **common_db_kwargs,
        "database": os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    })
    
    try:
        # Get congressmen data
        political_dynasties_available = True
        try:
            exists_query = """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'political_dynasties'
                )
            """
            political_dynasties_available = await dynasty_conn.fetchval(exists_query)
        except Exception:
            political_dynasties_available = False
        
        congressmen_data = await generator.get_congressmen_data(
            dynasty_conn,
            config_data,
            districts_data,
            political_dynasties_available
        )
        
        # Build lookup dictionaries
        generator._build_district_lookup(congressmen_data, districts_data)
        district_lookup_dict, contractor_lookup_dict = generator._build_lookup_dictionaries(congressmen_data, districts_data)
        
        # Build location dictionaries (no hardcoding)
        location_dicts = generator._build_location_dictionaries(congressmen_data, district_lookup_dict, districts_data)
        generator.location_dicts = location_dicts
        
        print(f"✅ Loaded {len(congressmen_data)} congressmen")
        print(f"✅ Built location dictionaries: {len(location_dicts['provinces'])} provinces, {len(location_dicts['cities'])} cities")
        
        # Load integrated projects parquet
        integrated_file = Path(__file__).parent.parent / 'data' / 'parquet' / 'integrated_projects.parquet'
        
        if not integrated_file.exists():
            print(f"❌ Integrated projects file not found: {integrated_file}")
            return
        
        print(f"\n📊 Finding incorrectly classified projects...")
        
        # Connect to DuckDB
        conn = duckdb.connect()
        
        try:
            # Check what columns exist
            desc_query = f"DESCRIBE SELECT * FROM '{integrated_file}' LIMIT 1"
            desc_results = conn.execute(desc_query).fetchall()
            available_columns = [row[0] for row in desc_results]
            
            # Use location dictionaries to find non-Davao provinces
            all_provinces = location_dicts.get('provinces', set())
            davao_provinces = {p for p in all_provinces if 'DAVAO' in p}
            non_davao_provinces = all_provinces - davao_provinces
            
            print(f"✅ Excluding {len(davao_provinces)} Davao provinces")
            print(f"✅ Checking {len(non_davao_provinces)} non-Davao provinces")
            
            # Build query to find projects with Davao district but non-Davao province
            # OR projects in non-Davao provinces
            location_conditions = []
            
            # Check if project_district mentions Davao but province doesn't
            if 'project_district' in available_columns and 'province' in available_columns:
                location_conditions.append("""
                    (
                        (CAST(project_district AS VARCHAR) LIKE '%Davao City%' OR CAST(project_district AS VARCHAR) LIKE '%Davao%')
                        AND UPPER(CAST(province AS VARCHAR)) NOT LIKE '%DAVAO%'
                        AND province IS NOT NULL
                    )
                """)
            
            # Also check for projects in non-Davao provinces
            if 'province' in available_columns:
                # Build conditions for non-Davao provinces (limit to avoid query too long)
                prov_conditions = []
                for prov in list(non_davao_provinces)[:50]:  # Limit to first 50
                    prov_escaped = prov.replace("'", "''")
                    prov_conditions.append(f"UPPER(province) LIKE '%{prov_escaped}%'")
                
                if prov_conditions:
                    location_conditions.append(f"({' OR '.join(prov_conditions)})")
            
            if not location_conditions:
                print("❌ No location columns found in parquet file")
                return
            
            where_clause = " OR ".join(location_conditions)
            
            query = f"""
                SELECT *
                FROM '{integrated_file}'
                WHERE {where_clause}
                LIMIT 50000
            """
            
            results = conn.execute(query).fetchall()
            column_names = [desc[0] for desc in conn.description]
            
            # Convert to list of dicts
            paolo_projects = []
            for row in results:
                project_dict = dict(zip(column_names, row))
                paolo_projects.append(project_dict)
            
            print(f"✅ Found {len(paolo_projects)} potentially incorrectly classified projects")
            
            if len(paolo_projects) == 0:
                print("ℹ️  No projects to reclassify")
                return
            
            # Show sample projects
            print(f"\n📝 Sample projects to reclassify:")
            for i, proj in enumerate(paolo_projects[:5], 1):
                name = proj.get('project_name') or proj.get('project_description') or 'N/A'
                province = proj.get('province') or 'N/A'
                district = proj.get('project_district') or 'N/A'
                print(f"   {i}. {name[:60]}...")
                print(f"      Province: {province}, District: {district}")
            
            # Clear classification columns for these projects
            print(f"\n🔄 Clearing classification columns for {len(paolo_projects)} projects...")
            
            # Read all projects
            print(f"   Reading all projects from parquet...")
            all_projects_query = f"SELECT * FROM '{integrated_file}'"
            all_results = conn.execute(all_projects_query).fetchall()
            all_projects_list = [dict(zip(column_names, row)) for row in all_results]
            
            # Get project IDs to update
            project_ids = set()
            for proj in paolo_projects:
                global_id = proj.get('global_id') or proj.get('meilisearch_id')
                if global_id:
                    project_ids.add(str(global_id))
            
            # Clear classification columns
            updated_count = 0
            for proj in all_projects_list:
                global_id = str(proj.get('global_id') or proj.get('meilisearch_id') or '')
                if global_id in project_ids:
                    proj['project_district_type'] = None
                    proj['project_district'] = None
                    proj['project_barangay_municipality'] = None
                    updated_count += 1
            
            print(f"   ✅ Cleared classification for {updated_count} projects in memory")
            
            # Write back to parquet
            print(f"   Writing updated projects back to parquet...")
            import pandas as pd
            df = pd.DataFrame(all_projects_list)
            df.to_parquet(integrated_file, index=False, engine='pyarrow')
            print(f"   ✅ Updated parquet file: {integrated_file}")
            
            # Now reclassify these projects using the main script's logic
            print(f"\n🔄 Reclassifying {len(paolo_projects)} projects...")
            
            # Group projects by source for batch processing
            projects_by_source = {}
            for proj_dict in paolo_projects:
                source = proj_dict.get('source') or proj_dict.get('_source', '').upper()
                if 'DIME' in source:
                    source_key = 'DIME'
                elif 'PHILGEPS' in source:
                    source_key = 'PHILGEPS'
                elif 'INFRAWATCH' in source or 'MICROSITE' in source:
                    source_key = 'INFRAWATCH'
                elif 'FLOOD' in source or 'SSP' in source:
                    source_key = 'FLOOD'
                else:
                    source_key = 'DIME'  # Default
                
                if source_key not in projects_by_source:
                    projects_by_source[source_key] = []
                projects_by_source[source_key].append(proj_dict)
            
            # Process projects in batches by source
            reclassified_projects = []
            batch_size = 100  # Process 100 projects at a time
            
            for source_key, source_projects in projects_by_source.items():
                print(f"   Processing {len(source_projects)} {source_key} projects in batches...")
                
                for i in range(0, len(source_projects), batch_size):
                    chunk = source_projects[i:i + batch_size]
                    
                    if source_key == 'DIME':
                        results = generator._process_dime_chunk(chunk, congressmen_data, districts_data, district_lookup_dict, contractor_lookup_dict)
                    elif source_key == 'PHILGEPS':
                        results = generator._process_philgeps_chunk(chunk, congressmen_data, districts_data, district_lookup_dict, contractor_lookup_dict)
                    elif source_key == 'INFRAWATCH':
                        results = generator._process_infrawatch_chunk(chunk, congressmen_data, districts_data, district_lookup_dict, contractor_lookup_dict)
                    elif source_key == 'FLOOD':
                        results = generator._process_flood_chunk(chunk, congressmen_data, districts_data, district_lookup_dict, contractor_lookup_dict)
                    
                    if results:
                        reclassified_projects.extend(results)
                    
                    if (i + batch_size) % 1000 == 0:
                        print(f"      Processed {min(i + batch_size, len(source_projects))} / {len(source_projects)} projects...")
            
            print(f"✅ Reclassified {len(reclassified_projects)} projects")
            
            # Update parquet with reclassified projects
            print(f"\n🔄 Updating parquet with reclassified projects...")
            for reclassified in reclassified_projects:
                global_id = str(reclassified.get('global_id') or reclassified.get('meilisearch_id') or '')
                if global_id in project_ids:
                    # Find and update the project in all_projects_list
                    for proj in all_projects_list:
                        proj_global_id = str(proj.get('global_id') or proj.get('meilisearch_id') or '')
                        if proj_global_id == global_id:
                            # Update classification columns
                            proj['project_district_type'] = reclassified.get('project_district_type')
                            proj['project_district'] = reclassified.get('project_district')
                            proj['project_barangay_municipality'] = reclassified.get('project_barangay_municipality')
                            proj['district_congressman'] = reclassified.get('district_congressman')
                            proj['contractor_congressman'] = reclassified.get('contractor_congressman')
                            break
            
            # Write updated parquet
            df = pd.DataFrame(all_projects_list)
            df.to_parquet(integrated_file, index=False, engine='pyarrow')
            print(f"   ✅ Updated parquet with reclassified projects")
            
            # Update congressman cache files incrementally
            print(f"\n🔄 Updating congressman cache files incrementally...")
            
            # Load existing cache files
            cache_base_dir = Path(__file__).parent.parent / 'static' / 'data'
            congressman_cache_updates = {}  # congressman_name -> list of projects to add
            
            for reclassified in reclassified_projects:
                # Track both district and contractor congressmen
                district_cm = reclassified.get('district_congressman')
                contractor_cm = reclassified.get('contractor_congressman')
                
                if district_cm:
                    if district_cm not in congressman_cache_updates:
                        congressman_cache_updates[district_cm] = []
                    congressman_cache_updates[district_cm].append(reclassified)
                
                if contractor_cm and contractor_cm != district_cm:
                    if contractor_cm not in congressman_cache_updates:
                        congressman_cache_updates[contractor_cm] = []
                    congressman_cache_updates[contractor_cm].append(reclassified)
            
            # Update each congressman's cache incrementally
            for congressman_name, new_projects in congressman_cache_updates.items():
                congressman_normalized = congressman_name.lower().replace(' ', '-')
                congressman_cache_dir = cache_base_dir / f'congressman-projects-{congressman_normalized}'
                congressman_cache_file = congressman_cache_dir / 'all-projects-cache.json'
                
                # Load existing cache if it exists
                existing_projects = []
                if congressman_cache_file.exists():
                    with open(congressman_cache_file, 'r', encoding='utf-8') as f:
                        existing_cache = json.load(f)
                        existing_projects = existing_cache.get('projects', [])
                
                # Merge: add new projects, avoid duplicates by global_id
                existing_ids = {str(p.get('global_id') or p.get('meilisearch_id') or '') for p in existing_projects}
                
                for new_proj in new_projects:
                    new_id = str(new_proj.get('global_id') or new_proj.get('meilisearch_id') or '')
                    if new_id and new_id not in existing_ids:
                        existing_projects.append(new_proj)
                        existing_ids.add(new_id)
                
                # Update cache file
                congressman_cache_dir.mkdir(parents=True, exist_ok=True)
                from datetime import datetime
                updated_cache = {
                    'congressman': congressman_name,
                    'total': len(existing_projects),
                    'projects': existing_projects,
                    'last_updated': datetime.now().isoformat()
                }
                
                generator._atomic_write_json(congressman_cache_file, updated_cache)
                print(f"   ✅ {congressman_name}: Added {len(new_projects)} projects (total: {len(existing_projects)})")
            
            # Final Summary
            print(f"\n" + "=" * 80)
            print(f"📊 RECLASSIFICATION SUMMARY")
            print(f"=" * 80)
            print(f"\n✅ Total projects found: {len(paolo_projects)}")
            print(f"✅ Classification columns cleared: {updated_count}")
            print(f"✅ Projects reclassified: {len(reclassified_projects)}")
            print(f"✅ Congressman caches updated: {len(congressman_cache_updates)}")
            
            # Breakdown by new congressman
            print(f"\n📍 Projects reassigned to:")
            for cm_name, projects in congressman_cache_updates.items():
                print(f"   - {cm_name}: {len(projects)} projects")
            
            print(f"\n" + "=" * 80)
            
        finally:
            conn.close()
            
    finally:
        await dynasty_conn.close()

if __name__ == '__main__':
    asyncio.run(reclassify_paolo_duterte_projects())

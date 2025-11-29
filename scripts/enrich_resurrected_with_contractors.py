#!/usr/bin/env python3
"""
Enrich Resurrected Projects with Contractor Data
Adds contractor information from DIME database to all existing matches (both 2026 and historical).

Usage:
    python3 scripts/enrich_resurrected_with_contractors.py
"""

import json
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
from typing import Optional
from collections import defaultdict
from datetime import datetime


class ContractorEnricher:
    def __init__(self):
        self.dime_db_config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'dime',
            'user': 'budget_admin',
            'password': 'wuQ5gBYCKkZiOGb61chLcByMu'
        }
        self.contractor_cache = {}  # Cache contractor lookups
        
    def get_contractor_for_project(self, project_name: str, project_description: str = None) -> Optional[str]:
        """Try to get contractor information for a project from DIME database
        Uses fuzzy matching on project name/description
        """
        if not project_name:
            return None
        
        # Check cache first
        cache_key = project_name.lower().strip()
        if cache_key in self.contractor_cache:
            return self.contractor_cache[cache_key]
        
        try:
            conn = psycopg2.connect(**self.dime_db_config)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Try to match by project name (fuzzy match)
            # Search for projects with similar names
            search_term = f"%{project_name[:50]}%"  # Use first 50 chars for matching
            
            query = """
                SELECT DISTINCT contractors
                FROM projects
                WHERE (project_name ILIKE %s OR description ILIKE %s)
                AND contractors IS NOT NULL
                AND array_length(contractors, 1) > 0
                LIMIT 1
            """
            
            cursor.execute(query, (search_term, search_term))
            row = cursor.fetchone()
            
            contractor = None
            if row and row['contractors']:
                # Get first contractor from array
                contractors_list = row['contractors']
                if isinstance(contractors_list, list) and len(contractors_list) > 0:
                    contractor = contractors_list[0]
                    # Skip "No Data Available"
                    if contractor and contractor.strip() and contractor != 'No Data Available':
                        contractor = contractor.strip()
                    else:
                        contractor = None
            
            cursor.close()
            conn.close()
            
            # Cache result (even if None)
            self.contractor_cache[cache_key] = contractor
            return contractor
            
        except Exception as e:
            # If DIME database is not available or query fails, return None
            print(f"   ⚠️  Error looking up contractor for '{project_name[:50]}...': {e}")
            self.contractor_cache[cache_key] = None
            return None
    
    def enrich_matches(self, json_path: Path):
        """Enrich all matches with contractor data"""
        print("=" * 100)
        print(" ENRICHING RESURRECTED PROJECTS WITH CONTRACTOR DATA")
        print("=" * 100)
        
        # Load existing matches
        print(f"\n📁 Loading matches from: {json_path}")
        if not json_path.exists():
            raise FileNotFoundError(f"JSON file not found: {json_path}")
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        matches = data.get('matches', [])
        print(f"   Found {len(matches):,} matches to enrich")
        
        # Track statistics
        stats = {
            'total_matches': len(matches),
            'enriched_2026': 0,
            'enriched_historical': 0,
            'already_had_2026': 0,
            'already_had_historical': 0,
            'not_found_2026': 0,
            'not_found_historical': 0
        }
        
        # Group matches by 2026 project ID to avoid duplicate lookups
        matches_by_project = defaultdict(list)
        for match in matches:
            project_id = match.get('year_2026', {}).get('id')
            if project_id:
                matches_by_project[project_id].append(match)
        
        print(f"\n🔄 Processing {len(matches_by_project):,} unique 2026 projects...")
        
        # Process each unique 2026 project
        processed = 0
        for project_id, project_matches in matches_by_project.items():
            # Get contractor for 2026 project (once per project)
            first_match = project_matches[0]
            project_2026 = first_match.get('year_2026', {})
            project_name = project_2026.get('name', '')
            project_description = project_2026.get('description', '')
            
            # Check if already has contractor
            existing_contractor = project_2026.get('contractor')
            if existing_contractor:
                stats['already_had_2026'] += len(project_matches)
            else:
                # Look up contractor
                contractor = self.get_contractor_for_project(project_name, project_description)
                
                if contractor:
                    # Update all matches for this project
                    for match in project_matches:
                        match['year_2026']['contractor'] = contractor
                    stats['enriched_2026'] += len(project_matches)
                else:
                    stats['not_found_2026'] += len(project_matches)
            
            # Get contractors for historical projects
            for match in project_matches:
                historical = match.get('historical', {})
                historical_description = historical.get('description', '')
                
                # Check if already has contractor
                existing_historical_contractor = historical.get('contractor')
                if existing_historical_contractor:
                    stats['already_had_historical'] += 1
                else:
                    # Look up contractor for historical project
                    historical_contractor = self.get_contractor_for_project(
                        historical_description,
                        historical_description
                    )
                    
                    if historical_contractor:
                        historical['contractor'] = historical_contractor
                        stats['enriched_historical'] += 1
                    else:
                        stats['not_found_historical'] += 1
            
            processed += 1
            if processed % 100 == 0:
                print(f"   Processed {processed}/{len(matches_by_project)} projects... "
                      f"({stats['enriched_2026']} 2026, {stats['enriched_historical']} historical enriched)")
        
        # Update metadata
        data['metadata']['contractor_enrichment'] = {
            'enriched_at': datetime.now().isoformat(),
            'stats': stats
        }
        
        # Save enriched data
        print(f"\n💾 Saving enriched matches...")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        # Print summary
        print("\n" + "=" * 100)
        print(" ENRICHMENT SUMMARY")
        print("=" * 100)
        print(f"Total matches processed: {stats['total_matches']:,}")
        print(f"\n2026 Projects:")
        print(f"  ✅ Enriched: {stats['enriched_2026']:,}")
        print(f"  📋 Already had contractor: {stats['already_had_2026']:,}")
        print(f"  ❌ Not found in DIME: {stats['not_found_2026']:,}")
        print(f"\nHistorical Matches:")
        print(f"  ✅ Enriched: {stats['enriched_historical']:,}")
        print(f"  📋 Already had contractor: {stats['already_had_historical']:,}")
        print(f"  ❌ Not found in DIME: {stats['not_found_historical']:,}")
        print(f"\n💾 Saved to: {json_path}")
        print("=" * 100)


if __name__ == "__main__":
    enricher = ContractorEnricher()
    json_path = Path("static/data/resurrected_projects_dpwh.json")
    enricher.enrich_matches(json_path)


#!/usr/bin/env python3
"""
Enrich Resurrected Projects with Contractor Data
Adds contractor information from multiple sources:
- DIME database
- Flood projects parquet
- PhilGEPS contracts parquet
- Transparency projects parquet
- Infrawatch (microsite) projects parquet

This script is designed to be run periodically (e.g., daily/weekly) to enrich
existing matches with contractor data. It's separate from the main matching script
to keep matching fast and allow independent contractor updates.

Usage:
    python3 scripts/enrich_resurrected_with_contractors.py
    
Note: This script is incremental - it preserves existing contractor data and only
enriches matches that don't have contractors yet, or updates them if better matches
are found in the data sources.
"""

import json
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
from typing import Optional, List, Dict
from collections import defaultdict
from datetime import datetime
import pandas as pd
import re


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
        self.parquet_data = {}  # Cache loaded parquet data
        self._load_parquet_sources()
        
    def _load_parquet_sources(self):
        """Load parquet files into memory for fast searching"""
        print("📦 Loading parquet data sources...")
        
        # Flood projects
        try:
            flood_path = Path("data/parquet/flood_projects.parquet")
            if flood_path.exists():
                print(f"   Loading flood_projects.parquet...")
                df_flood = pd.read_parquet(flood_path)
                # Keep only relevant columns
                self.parquet_data['flood'] = df_flood[['project_description', 'contractor_name']].copy()
                print(f"      ✅ Loaded {len(df_flood):,} flood projects")
            else:
                print(f"      ⚠️  flood_projects.parquet not found")
                self.parquet_data['flood'] = None
        except Exception as e:
            print(f"      ❌ Error loading flood_projects.parquet: {e}")
            self.parquet_data['flood'] = None
        
        # PhilGEPS contracts
        try:
            philgeps_path = Path("data/parquet/philgeps_contracts.parquet")
            if philgeps_path.exists():
                print(f"   Loading philgeps_contracts.parquet...")
                df_philgeps = pd.read_parquet(philgeps_path)
                # Keep relevant columns
                cols = ['project_name', 'project_description', 'philgeps_award_title', 
                       'contractor_name', 'philgeps_awardee_name']
                available_cols = [c for c in cols if c in df_philgeps.columns]
                self.parquet_data['philgeps'] = df_philgeps[available_cols].copy()
                print(f"      ✅ Loaded {len(df_philgeps):,} PhilGEPS contracts")
            else:
                print(f"      ⚠️  philgeps_contracts.parquet not found")
                self.parquet_data['philgeps'] = None
        except Exception as e:
            print(f"      ❌ Error loading philgeps_contracts.parquet: {e}")
            self.parquet_data['philgeps'] = None
        
        # Transparency projects
        try:
            transparency_path = Path("data/parquet/transparency_projects.parquet")
            if transparency_path.exists():
                print(f"   Loading transparency_projects.parquet...")
                df_transparency = pd.read_parquet(transparency_path)
                # Keep relevant columns (including multiple contractors)
                cols = ['project_description', 'description', 'contractor_name', 
                       'contractor_name_2', 'contractor_name_3', 'contractor_name_4']
                available_cols = [c for c in cols if c in df_transparency.columns]
                self.parquet_data['transparency'] = df_transparency[available_cols].copy()
                print(f"      ✅ Loaded {len(df_transparency):,} transparency projects")
            else:
                print(f"      ⚠️  transparency_projects.parquet not found")
                self.parquet_data['transparency'] = None
        except Exception as e:
            print(f"      ❌ Error loading transparency_projects.parquet: {e}")
            self.parquet_data['transparency'] = None
        
        # Infrawatch (microsite) projects
        try:
            infrawatch_path = Path("data/parquet/infrawatch_projects.parquet")
            if infrawatch_path.exists():
                print(f"   Loading infrawatch_projects.parquet...")
                df_infrawatch = pd.read_parquet(infrawatch_path)
                # Keep relevant columns
                cols = ['project_description', 'contractor_name']
                available_cols = [c for c in cols if c in df_infrawatch.columns]
                self.parquet_data['infrawatch'] = df_infrawatch[available_cols].copy()
                print(f"      ✅ Loaded {len(df_infrawatch):,} infrawatch projects")
            else:
                print(f"      ⚠️  infrawatch_projects.parquet not found")
                self.parquet_data['infrawatch'] = None
        except Exception as e:
            print(f"      ❌ Error loading infrawatch_projects.parquet: {e}")
            self.parquet_data['infrawatch'] = None
        
        print()
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for matching"""
        if not text or pd.isna(text):
            return ""
        text = str(text).lower().strip()
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        return text
    
    def _search_parquet(self, source: str, search_text: str) -> Optional[str]:
        """Search a parquet source for contractor by project name/description"""
        if source not in self.parquet_data or self.parquet_data[source] is None:
            return None
        
        df = self.parquet_data[source]
        search_normalized = self._normalize_text(search_text)
        
        if not search_normalized:
            return None
        
        # Extract key words from search text (first 50 chars, split into words)
        search_words = search_normalized[:50].split()
        if len(search_words) < 2:
            return None  # Need at least 2 words for meaningful matching
        
        # Build search pattern (match if at least 2 key words appear)
        pattern = '|'.join([re.escape(word) for word in search_words[:5]])  # Use first 5 words
        
        try:
            if source == 'flood':
                # Search in project_description
                mask = df['project_description'].astype(str).str.lower().str.contains(pattern, na=False, regex=True)
                matches = df[mask & df['contractor_name'].notna()]
                if len(matches) > 0:
                    contractor = matches.iloc[0]['contractor_name']
                    if contractor and str(contractor).strip() and str(contractor).strip() != 'No Data Available':
                        return str(contractor).strip()
            
            elif source == 'philgeps':
                # Search in project_name, project_description, or philgeps_award_title
                mask = (
                    df['project_name'].astype(str).str.lower().str.contains(pattern, na=False, regex=True) |
                    df['project_description'].astype(str).str.lower().str.contains(pattern, na=False, regex=True)
                )
                if 'philgeps_award_title' in df.columns:
                    mask = mask | df['philgeps_award_title'].astype(str).str.lower().str.contains(pattern, na=False, regex=True)
                
                matches = df[mask]
                # Try contractor_name first, then philgeps_awardee_name
                for col in ['contractor_name', 'philgeps_awardee_name']:
                    if col in matches.columns:
                        contractor_col = matches[matches[col].notna()]
                        if len(contractor_col) > 0:
                            contractor = contractor_col.iloc[0][col]
                            if contractor and str(contractor).strip() and str(contractor).strip() != 'No Data Available':
                                return str(contractor).strip()
            
            elif source == 'transparency':
                # Search in project_description or description
                mask = (
                    df['project_description'].astype(str).str.lower().str.contains(pattern, na=False, regex=True) |
                    df['description'].astype(str).str.lower().str.contains(pattern, na=False, regex=True)
                )
                matches = df[mask]
                # Try all contractor columns (contractor_name, contractor_name_2, etc.)
                for col in ['contractor_name', 'contractor_name_2', 'contractor_name_3', 'contractor_name_4']:
                    if col in matches.columns:
                        contractor_col = matches[matches[col].notna()]
                        if len(contractor_col) > 0:
                            contractor = contractor_col.iloc[0][col]
                            if contractor and str(contractor).strip() and str(contractor).strip() != 'No Data Available':
                                return str(contractor).strip()
            
            elif source == 'infrawatch':
                # Search in project_description
                mask = df['project_description'].astype(str).str.lower().str.contains(pattern, na=False, regex=True)
                matches = df[mask & df['contractor_name'].notna()]
                if len(matches) > 0:
                    contractor = matches.iloc[0]['contractor_name']
                    if contractor and str(contractor).strip() and str(contractor).strip() != 'No Data Available':
                        return str(contractor).strip()
        
        except Exception as e:
            # Silently fail for individual source errors
            pass
        
        return None
    
    def _get_contractor_from_dime(self, project_name: str, project_description: str = None) -> Optional[str]:
        """Get contractor from DIME database"""
        if not project_name:
            return None
        
        try:
            conn = psycopg2.connect(**self.dime_db_config)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Try to match by project name (fuzzy match)
            search_term = f"%{project_name[:50]}%"
            
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
                contractors_list = row['contractors']
                if isinstance(contractors_list, list) and len(contractors_list) > 0:
                    contractor = contractors_list[0]
                    if contractor and contractor.strip() and contractor != 'No Data Available':
                        contractor = contractor.strip()
                    else:
                        contractor = None
            
            cursor.close()
            conn.close()
            return contractor
            
        except Exception as e:
            # Silently fail
            return None
        
    def get_contractor_for_project(self, project_name: str, project_description: str = None) -> Optional[str]:
        """Try to get contractor information from all sources
        Priority: DIME > Flood > PhilGEPS > Transparency > Infrawatch
        """
        if not project_name:
            return None
        
        # Check cache first
        cache_key = project_name.lower().strip()
        if cache_key in self.contractor_cache:
            return self.contractor_cache[cache_key]
        
        # Combine name and description for searching
        search_text = project_name
        if project_description:
            search_text = f"{project_name} {project_description}"
        
        # Try sources in priority order
        sources = [
            ('dime', self._get_contractor_from_dime),
            ('flood', lambda n, d: self._search_parquet('flood', search_text)),
            ('philgeps', lambda n, d: self._search_parquet('philgeps', search_text)),
            ('transparency', lambda n, d: self._search_parquet('transparency', search_text)),
            ('infrawatch', lambda n, d: self._search_parquet('infrawatch', search_text)),
        ]
        
        for source_name, source_func in sources:
            try:
                contractor = source_func(project_name, project_description)
                if contractor:
                    # Cache result
                    self.contractor_cache[cache_key] = contractor
                    return contractor
            except Exception as e:
                # Continue to next source
                continue
        
        # Cache None result
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
        print(f"  ❌ Not found in any source: {stats['not_found_2026']:,}")
        print(f"\nHistorical Matches:")
        print(f"  ✅ Enriched: {stats['enriched_historical']:,}")
        print(f"  📋 Already had contractor: {stats['already_had_historical']:,}")
        print(f"  ❌ Not found in any source: {stats['not_found_historical']:,}")
        print(f"\n💾 Saved to: {json_path}")
        print("=" * 100)


if __name__ == "__main__":
    enricher = ContractorEnricher()
    json_path = Path("static/data/resurrected_projects_dpwh.json")
    enricher.enrich_matches(json_path)


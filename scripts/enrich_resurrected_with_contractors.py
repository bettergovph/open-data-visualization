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
from typing import Optional, List, Dict, Tuple
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
                # Keep only relevant columns (including contract_id and year columns)
                cols = ['project_description', 'contractor_name', 'contract_id', 
                       'contract_year', 'project_year']
                available_cols = [c for c in cols if c in df_flood.columns]
                self.parquet_data['flood'] = df_flood[available_cols].copy()
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
                # Keep relevant columns (including contract_id and year columns)
                cols = ['project_name', 'project_description', 'philgeps_award_title', 
                       'contractor_name', 'philgeps_awardee_name', 'contract_id', 
                       'philgeps_contract_no', 'philgeps_reference_id',
                       'contract_year', 'project_year']
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
                # Keep relevant columns (including multiple contractors, contract_id, and year)
                cols = ['project_description', 'description', 'contractor_name', 
                       'contractor_name_2', 'contractor_name_3', 'contractor_name_4',
                       'contract_id', 'year']
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
                # Keep relevant columns (including contract_id and year columns)
                cols = ['project_description', 'contractor_name', 'contract_id',
                       'contract_year', 'project_year']
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
    
    def _extract_year_from_contract_id(self, contract_id: str) -> Optional[int]:
        """Extract year from contract_id (first 2 digits often indicate year)
        Examples: '22C00083' -> 2022, '15DN0136' -> 2015
        """
        if not contract_id or pd.isna(contract_id):
            return None
        contract_id_str = str(contract_id).strip()
        if len(contract_id_str) >= 2 and contract_id_str[:2].isdigit():
            year_part = int(contract_id_str[:2])
            # Assume 20xx if < 50, else 19xx
            if year_part < 50:
                return 2000 + year_part
            else:
                return 1900 + year_part
        return None
    
    def _search_parquet(self, source: str, search_text: str, year: Optional[int] = None) -> Optional[Dict[str, str]]:
        """Search a parquet source for contractor and contract_id by project name/description
        Optionally filter by year to ensure year-qualified matches
        If year column is empty, extracts year from contract_id
        Returns dict with 'contractor' and 'contract_id' keys, or None if not found
        """
        if source not in self.parquet_data or self.parquet_data[source] is None:
            return None
        
        df = self.parquet_data[source]
        search_normalized = self._normalize_text(search_text)
        
        if not search_normalized:
            return None
        
        # Extract key words from search text (use longer words for better matching)
        search_words = search_normalized.split()
        # Filter to words longer than 4 characters for more specific matching
        key_words = [w for w in search_words if len(w) > 4]
        if len(key_words) < 2:
            # Fallback to all words if not enough long words
            key_words = search_words[:5]
        
        # Build search pattern (match if key words appear)
        pattern = '|'.join([re.escape(word) for word in key_words[:5]])  # Use first 5 key words
        
        try:
            if source == 'flood':
                # Search in project_description
                mask = df['project_description'].astype(str).str.lower().str.contains(pattern, na=False, regex=True)
                matches = df[mask & df['contractor_name'].notna()]
                
                # Filter by year if provided
                if year is not None and len(matches) > 0:
                    # Try year column first
                    year_col = 'contract_year' if 'contract_year' in df.columns else 'project_year'
                    if year_col in matches.columns:
                        year_series = pd.to_numeric(matches[year_col], errors='coerce')
                        year_mask = (year_series == year)
                        # Also check contract_id for rows where year column is null
                        if 'contract_id' in matches.columns:
                            contract_id_years = matches['contract_id'].apply(self._extract_year_from_contract_id)
                            # Use contract_id year when year column is null
                            year_mask = year_mask | (year_series.isna() & (contract_id_years == year))
                        matches = matches[year_mask]
                
                if len(matches) > 0:
                    best_match = matches.iloc[0]
                    contractor = best_match['contractor_name']
                    if contractor and str(contractor).strip() and str(contractor).strip() != 'No Data Available':
                        result = {'contractor': str(contractor).strip()}
                        # Get contract_id if available
                        if 'contract_id' in matches.columns:
                            contract_id = best_match['contract_id']
                            if contract_id and not pd.isna(contract_id):
                                result['contract_id'] = str(contract_id).strip()
                        # Calculate similarity for comparison
                        matched_desc = str(best_match.get('project_description', ''))
                        similarity = self._calculate_similarity(search_normalized, matched_desc.lower())
                        result['similarity'] = similarity
                        result['matched_text'] = matched_desc
                        return result
            
            elif source == 'philgeps':
                # Search in project_name, project_description, or philgeps_award_title
                mask = (
                    df['project_name'].astype(str).str.lower().str.contains(pattern, na=False, regex=True) |
                    df['project_description'].astype(str).str.lower().str.contains(pattern, na=False, regex=True)
                )
                if 'philgeps_award_title' in df.columns:
                    mask = mask | df['philgeps_award_title'].astype(str).str.lower().str.contains(pattern, na=False, regex=True)
                
                matches = df[mask]
                
                # Filter by year if provided
                if year is not None and len(matches) > 0:
                    # Try year column first
                    year_col = 'contract_year' if 'contract_year' in df.columns else 'project_year'
                    if year_col in matches.columns:
                        year_series = pd.to_numeric(matches[year_col], errors='coerce')
                        year_mask = (year_series == year)
                        # Also check contract_id for rows where year column is null
                        if 'contract_id' in matches.columns:
                            contract_id_years = matches['contract_id'].apply(self._extract_year_from_contract_id)
                            # Use contract_id year when year column is null
                            year_mask = year_mask | (year_series.isna() & (contract_id_years == year))
                        matches = matches[year_mask]
                # Try contractor_name first, then philgeps_awardee_name
                for col in ['contractor_name', 'philgeps_awardee_name']:
                    if col in matches.columns:
                        contractor_col = matches[matches[col].notna()]
                        if len(contractor_col) > 0:
                            best_match = contractor_col.iloc[0]
                            contractor = best_match[col]
                            if contractor and str(contractor).strip() and str(contractor).strip() != 'No Data Available':
                                result = {'contractor': str(contractor).strip()}
                                # Get contract_id (try multiple column names)
                                for id_col in ['contract_id', 'philgeps_contract_no', 'philgeps_reference_id']:
                                    if id_col in matches.columns:
                                        contract_id = best_match[id_col]
                                        if contract_id and not pd.isna(contract_id):
                                            result['contract_id'] = str(contract_id).strip()
                                            break
                                # Calculate similarity for comparison
                                matched_text = str(best_match.get('project_name', '') or best_match.get('project_description', ''))
                                similarity = self._calculate_similarity(search_normalized, matched_text.lower())
                                result['similarity'] = similarity
                                result['matched_text'] = matched_text
                                return result
            
            elif source == 'transparency':
                # First try exact or near-exact matches using fuzzy matching (more accurate)
                from difflib import SequenceMatcher
                matches_with_sim = []
                
                # Use more specific pattern: require key words to appear together
                # Try both case-sensitive and case-insensitive patterns
                # Build a more specific pattern that requires multiple key words
                key_word_pattern = '.*'.join([re.escape(word) for word in key_words[:3]])  # Require first 3 key words in order
                
                # Limit search to reasonable subset first (use pattern to narrow down)
                initial_mask = (
                    df['project_description'].astype(str).str.contains(key_word_pattern, case=False, na=False, regex=True) |
                    df['description'].astype(str).str.contains(key_word_pattern, case=False, na=False, regex=True)
                )
                candidate_df = df[initial_mask]
                
                # If too many candidates, limit to first 2000 for performance
                if len(candidate_df) > 2000:
                    candidate_df = candidate_df.head(2000)
                
                # Calculate similarity for each candidate (use FULL search_normalized, not truncated)
                for idx, row in candidate_df.iterrows():
                    desc1 = str(row.get('project_description', '')).lower()
                    desc2 = str(row.get('description', '')).lower()
                    sim1 = SequenceMatcher(None, search_normalized, desc1).ratio() if desc1 else 0
                    sim2 = SequenceMatcher(None, search_normalized, desc2).ratio() if desc2 else 0
                    sim = max(sim1, sim2)
                    if sim > 0.75:  # 75% similarity threshold for transparency (lowered for better matching)
                        matches_with_sim.append((sim, row))
                
                # Sort by similarity (highest first)
                matches_with_sim.sort(reverse=True, key=lambda x: x[0])
                
                # Filter by year if provided
                if year is not None:
                    year_filtered = []
                    for sim, row in matches_with_sim:
                        row_year = None
                        if 'year' in row.index:
                            try:
                                row_year = int(pd.to_numeric(row['year'], errors='coerce'))
                            except:
                                pass
                        if row_year is None and 'contract_id' in row.index:
                            row_year = self._extract_year_from_contract_id(row['contract_id'])
                        if row_year == year:
                            year_filtered.append((sim, row))
                    matches_with_sim = year_filtered
                
                # Use best match (highest similarity)
                if matches_with_sim:
                    best_sim, best_match = matches_with_sim[0]
                    # Try all contractor columns (contractor_name, contractor_name_2, etc.)
                    for col in ['contractor_name', 'contractor_name_2', 'contractor_name_3', 'contractor_name_4']:
                        if col in best_match.index:
                            contractor = best_match[col]
                            if contractor and not pd.isna(contractor) and str(contractor).strip() and str(contractor).strip() != 'No Data Available':
                                result = {'contractor': str(contractor).strip()}
                                # Get contract_id if available
                                if 'contract_id' in best_match.index:
                                    contract_id = best_match['contract_id']
                                    if contract_id and not pd.isna(contract_id):
                                        result['contract_id'] = str(contract_id).strip()
                                # Include similarity and matched text for comparison
                                matched_desc = str(best_match.get('project_description', '') or best_match.get('description', ''))
                                result['similarity'] = best_sim
                                result['matched_text'] = matched_desc
                                return result
            
            elif source == 'infrawatch':
                # Search in project_description
                mask = df['project_description'].astype(str).str.lower().str.contains(pattern, na=False, regex=True)
                matches = df[mask & df['contractor_name'].notna()]
                
                # Filter by year if provided
                if year is not None and len(matches) > 0:
                    # Try year column first
                    year_col = 'contract_year' if 'contract_year' in df.columns else 'project_year'
                    if year_col in matches.columns:
                        year_series = pd.to_numeric(matches[year_col], errors='coerce')
                        year_mask = (year_series == year)
                        # Also check contract_id for rows where year column is null
                        if 'contract_id' in matches.columns:
                            contract_id_years = matches['contract_id'].apply(self._extract_year_from_contract_id)
                            # Use contract_id year when year column is null
                            year_mask = year_mask | (year_series.isna() & (contract_id_years == year))
                        matches = matches[year_mask]
                if len(matches) > 0:
                    best_match = matches.iloc[0]
                    contractor = best_match['contractor_name']
                    if contractor and str(contractor).strip() and str(contractor).strip() != 'No Data Available':
                        result = {'contractor': str(contractor).strip()}
                        # Get contract_id if available
                        if 'contract_id' in matches.columns:
                            contract_id = best_match['contract_id']
                            if contract_id and not pd.isna(contract_id):
                                result['contract_id'] = str(contract_id).strip()
                        # Calculate similarity for comparison
                        matched_desc = str(best_match.get('project_description', ''))
                        similarity = self._calculate_similarity(search_normalized, matched_desc.lower())
                        result['similarity'] = similarity
                        result['matched_text'] = matched_desc
                        return result
        
        except Exception as e:
            # Silently fail for individual source errors
            pass
        
        return None
    
    def _get_contractor_from_dime(self, project_name: str, project_description: str = None, year: Optional[int] = None) -> Optional[Dict[str, str]]:
        """Get contractor and contract_id from DIME database
        Note: DIME doesn't have a year column, so year filtering is not applied
        Returns dict with 'contractor' and optionally 'contract_id' keys, or None if not found
        """
        if not project_name:
            return None
        
        try:
            conn = psycopg2.connect(**self.dime_db_config)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Try to match by project name (fuzzy match)
            search_term = f"%{project_name[:50]}%"
            
            # Get contractor and id (if available as contract_id or project id)
            query = """
                SELECT DISTINCT contractors, id
                FROM projects
                WHERE (project_name ILIKE %s OR description ILIKE %s)
                AND contractors IS NOT NULL
                AND array_length(contractors, 1) > 0
                LIMIT 1
            """
            
            cursor.execute(query, (search_term, search_term))
            row = cursor.fetchone()
            
            if row and row['contractors']:
                contractors_list = row['contractors']
                if isinstance(contractors_list, list) and len(contractors_list) > 0:
                    contractor = contractors_list[0]
                    if contractor and contractor.strip() and contractor != 'No Data Available':
                        result = {'contractor': contractor.strip()}
                        # Use project id as contract_id if available
                        if row.get('id'):
                            result['contract_id'] = str(row['id']).strip()
                        # Calculate similarity for comparison
                        matched_text = str(row.get('project_name', '') or row.get('description', ''))
                        similarity = self._calculate_similarity(project_name, matched_text)
                        result['similarity'] = similarity
                        result['matched_text'] = matched_text
                        cursor.close()
                        conn.close()
                        return result
            
            cursor.close()
            conn.close()
            return None
            
        except Exception as e:
            # Silently fail
            return None
        
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts using SequenceMatcher"""
        from difflib import SequenceMatcher
        if not text1 or not text2:
            return 0.0
        return SequenceMatcher(None, text1.lower().strip(), text2.lower().strip()).ratio()
    
    def get_contractor_for_project(self, project_name: str, project_description: str = None, year: Optional[int] = None) -> Optional[Dict[str, str]]:
        """Try to get contractor and contract_id information from all sources
        Prioritizes matches by similarity score, not source priority
        If year is provided, filters parquet sources by year for year-qualified matches
        Returns dict with 'contractor' and optionally 'contract_id' keys, or None if not found
        """
        if not project_name:
            return None
        
        # Check cache first (include year in cache key if provided)
        cache_key = project_name.lower().strip()
        if year:
            cache_key_with_year = f"{cache_key}_y{year}"
            if cache_key_with_year in self.contractor_cache:
                return self.contractor_cache[cache_key_with_year]
        if cache_key in self.contractor_cache:
            return self.contractor_cache[cache_key]
        
        # Combine name and description for searching
        search_text = project_name
        if project_description:
            search_text = f"{project_name} {project_description}"
        
        # Search all sources and collect matches with similarity scores
        # Priority order: Transparency > Infrawatch (Microsite) > PhilGEPS > DIME > Flood
        all_matches = []
        
        sources = [
            ('transparency', lambda n, d, y: self._search_parquet('transparency', search_text, y)),
            ('infrawatch', lambda n, d, y: self._search_parquet('infrawatch', search_text, y)),
            ('philgeps', lambda n, d, y: self._search_parquet('philgeps', search_text, y)),
            ('dime', lambda n, d, y: self._get_contractor_from_dime(n, d, y)),
            ('flood', lambda n, d, y: self._search_parquet('flood', search_text, y)),
        ]
        
        for source_name, source_func in sources:
            try:
                result = source_func(project_name, project_description, year)
                if result and result.get('contractor'):
                    # Get the matched project name/description from the source for similarity calculation
                    matched_text = result.get('matched_text', search_text)
                    similarity = result.get('similarity', 0.5)  # Default to 0.5 if not provided
                    
                    # If similarity not provided, calculate it
                    if similarity == 0.5 and matched_text:
                        similarity = self._calculate_similarity(project_name, matched_text)
                    
                    all_matches.append({
                        'source': source_name,
                        'result': result,
                        'similarity': similarity
                    })
            except Exception as e:
                # Continue to next source
                continue
        
        # If no matches found
        if not all_matches:
            self.contractor_cache[cache_key] = None
            return None
        
        # Sort by similarity (highest first) and return best match
        all_matches.sort(key=lambda x: x['similarity'], reverse=True)
        best_match = all_matches[0]['result']
        
        # Cache result (include year in cache key for year-specific caching)
        if year:
            cache_key_with_year = f"{cache_key}_y{year}"
            self.contractor_cache[cache_key_with_year] = best_match
        self.contractor_cache[cache_key] = best_match
        
        return best_match
    
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
            're_enriched_historical': 0,  # Re-enriched with year filtering
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
            
            # 2026 projects: Skip contractor enrichment (2026 is proposed budget, no real contractors)
            # But we still track stats for consistency
            existing_contractor = project_2026.get('contractor')
            if existing_contractor:
                stats['already_had_2026'] += len(project_matches)
            else:
                stats['not_found_2026'] += len(project_matches)
            # Note: We don't enrich 2026 projects since they're proposed budget
            
            # Get contractors for historical projects
            # FORCE re-enrichment to ensure year-qualified contractors
            for match in project_matches:
                historical = match.get('historical', {})
                historical_description = historical.get('description', '')
                historical_year = historical.get('year')
                
                # Always re-check with year filtering to ensure year-qualified matches
                # This ensures contractors are from the correct year, not just any year
                historical_contractor_data = self.get_contractor_for_project(
                    historical_description,
                    historical_description,
                    year=historical_year  # Filter by year for year-qualified matches
                )
                
                if historical_contractor_data and historical_contractor_data.get('contractor'):
                    # Update contractor (may be same or different due to year filtering)
                    previous_contractor = historical.get('contractor')
                    previous_contract_id = historical.get('contract_id')
                    new_contractor = historical_contractor_data['contractor']
                    new_contract_id = historical_contractor_data.get('contract_id')
                    
                    # Check if contractor actually changed
                    contractor_changed = (previous_contractor != new_contractor) or (previous_contract_id != new_contract_id)
                    
                    historical['contractor'] = new_contractor
                    # Add/update contract_id if available
                    if new_contract_id:
                        historical['contract_id'] = new_contract_id
                    
                    if previous_contractor:
                        if contractor_changed:
                            # Was re-enriched with different contractor (year-qualified)
                            stats['re_enriched_historical'] += 1
                        else:
                            # Had same contractor, verified with year filtering
                            stats['already_had_historical'] += 1
                    else:
                        # Was newly enriched
                        stats['enriched_historical'] += 1
                else:
                    # Not found with year filtering
                    if historical.get('contractor'):
                        # Had contractor before but not found with year filter - keep existing
                        stats['already_had_historical'] += 1
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
        print(f"  ✅ Newly enriched: {stats['enriched_historical']:,}")
        print(f"  🔄 Re-enriched (year-qualified): {stats['re_enriched_historical']:,}")
        print(f"  📋 Already had contractor (kept): {stats['already_had_historical']:,}")
        print(f"  ❌ Not found in any source: {stats['not_found_historical']:,}")
        print(f"\n💾 Saved to: {json_path}")
        print("=" * 100)


if __name__ == "__main__":
    enricher = ContractorEnricher()
    json_path = Path("static/data/resurrected_projects_dpwh.json")
    enricher.enrich_matches(json_path)


#!/usr/bin/env python3
"""
Generate cached JSON for dynasty-projects API using DuckDB and Parquet files.
This script retains all matching logic from generate_dynasty_projects_cache.py
but uses DuckDB to query Parquet files instead of PostgreSQL.
"""

import argparse
import asyncio
import functools
import json
import math
import os
import re
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb
import asyncpg
import pandas as pd
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
# FloodControlClient no longer needed - using Parquet files instead

# Load environment variables
load_dotenv()

# Manila-specific helpers
BARANGAY_NUMBER_PATTERNS = [
    re.compile(r'(?:BARANGAY|BRGY|BRG|BGY)\s*(?:NO\.?\s*)?(\d{1,4})', re.IGNORECASE),
    re.compile(r'(?:BARANGAY|BRGY|BRG|BGY)\s*(?:NO\.?\s*)?(\d{1,4})\s*(?:[-–]|TO)\s*(\d{1,4})', re.IGNORECASE),
]

# Parquet file paths
PARQUET_DIR = Path(__file__).parent.parent / 'data' / 'parquet'
INTEGRATED_PARQUET = PARQUET_DIR / 'integrated_projects.parquet'
CLASSIFIED_PARQUET = PARQUET_DIR / 'integrated_projects_classified.parquet'
# Fallback to separate files if integrated file doesn't exist
DIME_PARQUET = PARQUET_DIR / 'dime_projects.parquet'
PHILGEPS_PARQUET = PARQUET_DIR / 'philgeps_contracts.parquet'
INFRAWATCH_PARQUET = PARQUET_DIR / 'infrawatch_projects.parquet'
FLOOD_PARQUET = PARQUET_DIR / 'flood_projects.parquet'
# Dynasty data parquet files
POLITICAL_DYNASTIES_PARQUET = PARQUET_DIR / 'political_dynasties.parquet'
RELATIONSHIPS_PARQUET = PARQUET_DIR / 'relationships.parquet'
CONNECTION_TYPES_PARQUET = PARQUET_DIR / 'connection_types.parquet'

class DynastyProjectsCacheGeneratorDuckDB:
    """Generate cached JSON for dynasty-projects using DuckDB"""
    
    def __init__(self, force_reclassify: bool = False):
        """
        Initialize the cache generator.
        
        Args:
            force_reclassify: If True, reclassify all projects even if they already have
                            all 4 classification columns filled. If False, skip projects
                            that are already fully classified.
        """
        self.force_reclassify = force_reclassify
        root_dir = Path(__file__).parent.parent
        static_data_dir = root_dir / 'static' / 'data'
        self.cache_file = static_data_dir / 'dynasty-projects-cache.json'
        self.config_file = static_data_dir / 'dynasty-projects-config.json'
        self.districts_file = static_data_dir / 'districts.json'
        cpu_count = os.cpu_count() or 4
        self.max_workers = min(24, max(1, cpu_count))
        # Create ThreadPoolExecutor with 24 workers for parallel processing
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.verbose = os.getenv('DYNASTY_CACHE_VERBOSE', '0') == '1'
        self.manila_barangay_tokens: Dict[str, List[str]] = {}
        self.manila_barangay_numbers: Dict[str, List[int]] = {}
        self.manila_keyword_map: Dict[str, List[str]] = {}
        self.leyte_second_municipalities: set[str] = set()
        self.leyte_second_keywords: List[str] = []
        self.leyte_second_negative_keywords: List[str] = []
        self.samar_first_municipalities: set[str] = set()
        self.samar_first_keywords: List[str] = []
        self.samar_first_negative_keywords: List[str] = []
        self.chart_limit = 200
        self.unclassified_count = 0
        self.MAX_UNCLASSIFIED = 5
        
        # Global district lookup: district_key -> {municipalities: set, barangays: set, is_city: bool}
        self.district_lookup: Dict[str, Dict] = {}
        
        # Progress tracking counters (shared across chunks via class attributes)
        self.progress_counters = {
            'total_processed': 0,
            'skipped': 0,  # Track projects skipped because already classified
            'districts_matched': 0,
            'city_districts': 0,
            'province_districts': 0,
            'municipality_matched': 0,
            'barangay_matched': 0,
            'contractors_matched': 0,
            'congressmen_matched': set(),
            'unmatched': 0
        }
        
        # Initialize DuckDB connection
        self.duckdb_conn = duckdb.connect()
        
        # Load substring provinces config for strict word boundary matching
        self.substring_provinces = self._load_substring_provinces()

    def _log(self, message: str, *, verbose_only: bool = False) -> None:
        if verbose_only and not self.verbose:
            return
        print(message)

    def _atomic_write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + '.tmp')
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(temp_path, path)

    def _regenerate_top_congressmen_cache(self) -> None:
        """Refresh the full ranking cache so the integrated tab stays up to date."""
        ranking_generator = Path(__file__).with_name('generate_congressman_ranking.py')
        if not ranking_generator.exists():
            self._log("⚠️  Ranking generator script not found; skipping refresh.")
            return

        try:
            subprocess.run([sys.executable, str(ranking_generator)], check=True)
            self._log("✅ Refreshed congressman-ranking.json cache")
        except subprocess.CalledProcessError as exc:
            self._log(f"💥 Failed to refresh ranking cache: {exc}")

    @staticmethod
    def _chunk_list(items: List[Any], max_chunks: int) -> List[List[Any]]:
        if not items:
            return []
        if max_chunks <= 1 or len(items) <= 50:
            return [items]

        # Aim for smaller, more even work units to avoid long-tail chunks.
        target_chunks = min(len(items), max_chunks * 3)
        chunk_size = max(25, math.ceil(len(items) / target_chunks))
        return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]

    @staticmethod
    def _normalize_source_label(source: str) -> str:
        if not source:
            return "Unknown"
        normalized = source.strip().lower()
        if "microsite" in normalized or "infrawatch" in normalized:
            return "Microsite"
        if "ssp" in normalized or "flood" in normalized:
            return "SSP"
        if "dime" in normalized:
            return "DIME"
        if "philgeps" in normalized:
            return "PhilGEPS"
        return source.strip()
    
    def _load_substring_provinces(self) -> set:
        """Load the list of province base names that need strict word boundary matching"""
        config_path = Path(__file__).parent.parent / 'provinces-substring.json'
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return set(config.get('substring_provinces', []))
        except Exception as e:
            print(f"⚠️  Warning: Could not load provinces-substring.json: {e}")
            # Fallback to hardcoded list
            return {
                'agusan', 'cagayan', 'camarines', 'cotabato', 'davao', 'ilocos', 
                'lanao', 'leyte', 'mindoro', 'misamis', 'negros', 'quezon',
                'samar', 'surigao', 'zamboanga'
            }
    
    def _is_flood_related(self, project_name: str, description: str = "", location: str = "") -> bool:
        """Detect if a project is flood-related based on keywords"""
        flood_keywords = [
            'flood', 'drainage', 'drain', 'pumping', 'pump', 'river', 'estero', 
            'creek', 'canal', 'mitigation', 'control', 'dike', 'revetment',
            'river bank', 'riverbank', 'slope protection', 'floodway', 'flood control',
            'flood mitigation', 'waterway', 'catchment', 'retention', 'detention',
            'spillway', 'floodgate', 'seawall', 'breakwater', 'riprap', 'gabion'
        ]
        
        combined_text = f"{project_name} {description} {location}".lower()
        
        # Check if any flood keyword appears in the text
        for keyword in flood_keywords:
            if keyword in combined_text:
                return True
        
        return False

    @staticmethod
    def _normalize_text_for_key(value: Optional[str]) -> str:
        if not value:
            return ""
        text = value.upper()
        text = re.sub(r'\b(PROVINCE|CITY|MUNICIPALITY|MUNICIPALITY OF|CITY OF|BRGY|BARANGAY|PHILIPPINE|REPUBLIC|HIGHWAY|ROAD|RD|ST|STREET)\b', ' ', text)
        text = re.sub(r'[^A-Z0-9]+', ' ', text)
        return re.sub(r'\s+', ' ', text).strip()
    
    @staticmethod
    def _normalize_congressman_name(name: str) -> str:
        """
        Normalize congressman name for matching.
        Removes middle initials, middle names, extra spaces, and creates a base key from first+last name.
        Handles hyphenated names by taking the last part.
        Examples:
        - "Elpidio F. Barzaga Jr." -> "elpidio barzaga jr"
        - "Elpidio Barzaga Jr." -> "elpidio barzaga jr"
        - "Ferdinand Martin Gomez Romualdez" -> "ferdinand romualdez"
        - "Ferdinand Martin Romualdez" -> "ferdinand romualdez"
        - "David Catarina Suarez" -> "david suarez"
        - "David Suarez" -> "david suarez"
        - "Kristine Alexie B. Tutor" -> "kristine tutor"
        - "Kristine Alexie Besas-Tutor" -> "kristine tutor"
        - "Lord Allan Jay Velasco" -> "lord velasco"
        - "Lord Allan Velasco" -> "lord velasco"
        """
        if not name:
            return ""
        # Convert to lowercase and strip
        normalized = name.lower().strip()
        # Remove middle initials (single letters with periods, e.g., "F.", "M.", "B.")
        normalized = re.sub(r'\b[a-z]\.\s+', ' ', normalized)
        # Remove extra spaces
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        # Extract first name, last name, and suffix
        parts = normalized.split()
        suffixes = {'jr', 'sr', 'ii', 'iii', 'iv', 'v', 'jr.', 'sr.', 'ii.', 'iii.', 'iv.', 'v.'}
        
        if len(parts) == 0:
            return ""
        elif len(parts) == 1:
            return parts[0]
        elif len(parts) == 2:
            return ' '.join(parts)
        else:
            # 3+ parts: first name, middle name(s), last name, optional suffix
            first_name = parts[0]
            
            # Find last name (could be hyphenated like "Besas-Tutor")
            last_name_part = parts[-1] if parts[-1] not in suffixes else parts[-2]
            
            # Handle hyphenated last names (take the part after the hyphen, or the whole thing)
            if '-' in last_name_part:
                # For hyphenated names like "Besas-Tutor", use "Tutor"
                last_name = last_name_part.split('-')[-1]
            else:
                last_name = last_name_part
            
            suffix = parts[-1] if parts[-1] in suffixes else None
            
            # Build normalized: first + last + suffix
            result = f"{first_name} {last_name}"
            if suffix:
                result += f" {suffix}"
            return result
    
    def _build_name_normalization_map(self, congressmen_data: Dict) -> Dict[str, str]:
        """
        Build a mapping from all name variations to canonical names.
        Groups names by normalized form and picks shortest as canonical.
        Returns: {name_variation: canonical_name}
        """
        normalized_to_variations = {}
        
        # Group all names by their normalized form
        for name in congressmen_data.keys():
            normalized = self._normalize_congressman_name(name)
            if normalized:
                if normalized not in normalized_to_variations:
                    normalized_to_variations[normalized] = []
                normalized_to_variations[normalized].append(name)
        
        # For each normalized group, pick the most complete name as canonical
        # (prefer names with middle names, full names over nicknames)
        # Middle names are important for tracing family trees
        # and map all variations to it
        name_map = {}
        for normalized, variations in normalized_to_variations.items():
            if len(variations) > 1:
                # Multiple variations - pick most complete as canonical
                # Priority: full middle names > middle initials > no middle names
                def name_priority(name):
                    parts = name.split()
                    word_count = len(parts)
                    has_middle = word_count > 2
                    
                    # Check if name has full middle names (not just initials)
                    has_full_middle = False
                    full_middle_count = 0
                    if word_count > 2:
                        # Check middle parts (skip first and last)
                        for part in parts[1:-1]:
                            # Remove period if present
                            clean_part = part.rstrip('.')
                            if len(clean_part) > 1:
                                has_full_middle = True
                                full_middle_count += 1
                    
                    # Check if last name is hyphenated (more complete)
                    last_name = parts[-1] if parts else ""
                    has_hyphenated_last = '-' in last_name
                    
                    # Priority: has_full_middle > full_middle_count > has_hyphenated_last > has_middle > length
                    return (has_full_middle, full_middle_count, has_hyphenated_last, has_middle, len(name))
                
                canonical = max(variations, key=name_priority)
                for variation in variations:
                    name_map[variation] = canonical
            else:
                # Single variation - map to itself
                name_map[variations[0]] = variations[0]
        
        return name_map

    @staticmethod
    def _normalize_amount_for_key(amount: Any) -> int:
        if amount is None:
            return 0
        if isinstance(amount, (int, float)):
            return int(round(float(amount)))
        if isinstance(amount, str):
            cleaned = amount.replace('₱', '').replace(',', '').replace('PHP', '').strip()
            try:
                return int(round(float(cleaned))) if cleaned else 0
            except ValueError:
                return 0
        return 0

    def _build_project_key(self, proj: Dict[str, Any]) -> str:
        project_name = self._normalize_text_for_key(proj.get('project_name'))
        contractor = self._normalize_text_for_key(proj.get('contractor'))
        location = self._normalize_text_for_key(proj.get('location'))
        amount = self._normalize_amount_for_key(proj.get('amount'))
        if not location:
            return f"{project_name}|{contractor}|{amount}"
        return f"{project_name}|{contractor}|{amount}|{location}"

    @staticmethod
    def _merge_project_records(primary: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
        if not primary:
            return incoming.copy()
        merged = primary.copy()

        # Prefer non-empty meilisearch_id
        if not merged.get('meilisearch_id') and incoming.get('meilisearch_id'):
            merged['meilisearch_id'] = incoming.get('meilisearch_id')

        # Prefer more specific amount (>0)
        primary_amount = DynastyProjectsCacheGeneratorDuckDB._normalize_amount_for_key(merged.get('amount'))
        incoming_amount = DynastyProjectsCacheGeneratorDuckDB._normalize_amount_for_key(incoming.get('amount'))
        if incoming_amount and (not primary_amount or incoming_amount != primary_amount and primary_amount == 0):
            merged['amount'] = incoming.get('amount')

        # Prefer more descriptive project name (longer string)
        if len((incoming.get('project_name') or '')) > len((merged.get('project_name') or '')):
            merged['project_name'] = incoming.get('project_name')

        # Prefer more detailed contractor string
        if len((incoming.get('contractor') or '')) > len((merged.get('contractor') or '')):
            merged['contractor'] = incoming.get('contractor')

        # Prefer more specific location (longer and not N/A)
        merged_location = merged.get('location') or ''
        incoming_location = incoming.get('location') or ''
        if (incoming_location and incoming_location.upper() != 'N/A' and
                (not merged_location or merged_location.upper() == 'N/A' or len(incoming_location) > len(merged_location))):
            merged['location'] = incoming_location

        # Prefer year/status if missing
        if not merged.get('year') or merged.get('year') in ('N/A', None):
            if incoming.get('year') not in ('N/A', None):
                merged['year'] = incoming.get('year')

        if not merged.get('status') or merged.get('status') in ('N/A', None):
            if incoming.get('status') not in ('N/A', None):
                merged['status'] = incoming.get('status')

        # Track match_type/is_city_wide prioritizing higher score matches
        primary_score = primary.get('match_score', 0)
        incoming_score = incoming.get('match_score', 0)
        if incoming_score > primary_score:
            merged['match_type'] = incoming.get('match_type')
            merged['match_score'] = incoming_score
            merged['is_city_wide'] = incoming.get('is_city_wide', False)

        # Preserve both district and contractor congressmen (each project can have 2 congressmen)
        # Each project can have: 1 district congressman + 1 contractor congressman
        # When merging, preserve both from either source (they'll be tracked in the congressmen set during deduplication)
        
        # District congressman: prefer primary, but use incoming if primary doesn't have one
        if not merged.get('district_congressman') and incoming.get('district_congressman'):
            merged['district_congressman'] = incoming.get('district_congressman')
            merged['district_match_type'] = incoming.get('district_match_type')
            merged['district_match_score'] = incoming.get('district_match_score')
            merged['congressman_district'] = incoming.get('congressman_district')
        
        # Contractor congressman: prefer primary, but use incoming if primary doesn't have one
        # Note: Both can exist simultaneously (different congressmen)
        if not merged.get('contractor_congressman') and incoming.get('contractor_congressman'):
            merged['contractor_congressman'] = incoming.get('contractor_congressman')
            merged['contractor_match_type'] = incoming.get('contractor_match_type')
            merged['contractor_match_score'] = incoming.get('contractor_match_score')
            merged['contractor_congressman_district'] = incoming.get('contractor_congressman_district')

        return merged

    def _refresh_source_json(self) -> None:
        exporter_path = Path(__file__).with_name('export_dynasty_json_from_db.py')
        if not exporter_path.exists():
            print("⚠️  Export script not found; skipping JSON refresh.")
            return
        try:
            subprocess.run([sys.executable, str(exporter_path)], check=True)
            print("✅ Refreshed districts.json and dynasty-projects-config.json from database")
        except subprocess.CalledProcessError as exc:
            print(f"💥 Failed to refresh JSON sources: {exc}")

    def _get_project_year(self, year_val: Any) -> Optional[int]:
        """Extract and validate project year."""
        try:
            if year_val:
                year = int(float(year_val))  # Handle "2023.0" strings
                if 2000 <= year <= 2030:
                    return year
        except (ValueError, TypeError):
            pass
        return None

    def _parse_amount(self, amount_val: Any) -> float:
        """Parse amount to float."""
        if isinstance(amount_val, (int, float)):
            return float(amount_val)
        if isinstance(amount_val, str):
            try:
                return float(amount_val.replace(',', '').replace('₱', '').strip())
            except ValueError:
                pass
        return 0.0

    def _match_project_unified(self, 
                             project_text: str, 
                             province: str, 
                             municipality_barangay: str, 
                             contractor: str, 
                             year: Optional[int],
                             congressmen_data: Dict,
                             district_lookup: Dict,
                             contractor_lookup: Dict,
                             contractor_inverted_index: Dict) -> tuple[Optional[str], Optional[str], int, Optional[str], Optional[str]]:
        """
        Unified matching logic using O(1) lookups.
        Returns: (congressman_name, match_type, match_score, district_congressman, contractor_congressman)
        """
        district_congressman = None
        contractor_congressman = None
        match_type = 'unknown'
        match_score = 0
        final_congressman = 'Unknown'

        # 1. Try District Match
        district_match = self._find_congressman_by_district(
            province, municipality_barangay, year, district_lookup, congressmen_data
        )
        
        # Fallback: Province-only match if strict match failed and we have a province
        if not district_match and province and municipality_barangay:
             district_match = self._find_congressman_by_district(
                province, '', year, district_lookup, congressmen_data
            )
            
        if district_match:
            district_congressman, d_score = district_match
            # Normalize congressman name to canonical form
            if district_congressman and hasattr(self, 'canonical_name_map'):
                district_congressman = self.canonical_name_map.get(district_congressman, district_congressman)
            match_score = d_score
        
        # 2. Try Contractor Match
        contractor_match = self._find_congressman_by_contractor(
            contractor, contractor_lookup, contractor_inverted_index, congressmen_data
        )
        if contractor_match:
            contractor_congressman, c_score = contractor_match
            # Normalize congressman name to canonical form
            if contractor_congressman and hasattr(self, 'canonical_name_map'):
                contractor_congressman = self.canonical_name_map.get(contractor_congressman, contractor_congressman)
            
        # 3. Determine Primary Match
        # CRITICAL: For party-list congressmen, prioritize contractor matches over district matches
        # Party-list reps don't have specific districts, so contractor matching is their primary method
        if contractor_congressman:
            # Check if contractor congressman is party-list
            contractor_is_partylist = False
            if contractor_congressman and contractor_congressman in congressmen_data:
                contractor_is_partylist = congressmen_data[contractor_congressman].get('is_partylist', False)
            
            if contractor_is_partylist:
                # Party-list: prioritize contractor match
                final_congressman = contractor_congressman
                match_type = 'contractor'
                match_score = 50
            elif district_congressman:
                # Regular congressman: prioritize district match
                final_congressman = district_congressman
                match_type = 'district'
            else:
                # No district match, use contractor
                final_congressman = contractor_congressman
                match_type = 'contractor'
                match_score = 50
        elif district_congressman:
            final_congressman = district_congressman
            match_type = 'district'
        
        # Normalize final_congressman to canonical form
        if final_congressman and hasattr(self, 'canonical_name_map'):
            final_congressman = self.canonical_name_map.get(final_congressman, final_congressman)
            
        return final_congressman, match_type, match_score, district_congressman, contractor_congressman

    def _update_progress(self, match_type: str, congressman_name: str, is_city_district: bool = False, is_barangay_match: bool = False):
        """Update progress counters safely."""
        self.progress_counters['total_processed'] += 1
        
        if match_type == 'district':
            self.progress_counters['districts_matched'] += 1
            if is_city_district:
                self.progress_counters['city_districts'] += 1
            else:
                self.progress_counters['province_districts'] += 1
            
            if is_barangay_match:
                self.progress_counters['barangay_matched'] += 1
            else:
                self.progress_counters['municipality_matched'] += 1
                
            if congressman_name:
                self.progress_counters['congressmen_matched'].add(congressman_name)
                
        elif match_type == 'contractor':
            self.progress_counters['contractors_matched'] += 1
            if congressman_name:
                self.progress_counters['congressmen_matched'].add(congressman_name)
        else:
            self.progress_counters['unmatched'] += 1

    def _process_dime_chunk(self, projects_chunk: List[Dict], congressmen_data: Dict, districts_data: Dict,
                           district_lookup_dict: Dict, contractor_lookup_dict: Dict, contractor_inverted_index: Dict,
                           known_provinces: List[str] = None, known_cities: List[str] = None, 
                           location_context_map: Dict = None) -> List[Dict]:
        """Process a chunk of DIME projects from Parquet using O(1) lookups."""
        chunk_results: List[Dict] = []
        
        for proj in projects_chunk:
            # Check if already classified (unless force mode)
            if not self.force_reclassify:
                project_district_type = proj.get('project_district_type')
                project_district = proj.get('project_district')
                project_barangay_municipality = proj.get('project_barangay_municipality')
                is_flood_related = proj.get('is_flood_related')
                
                # Check if all fields are truthy (not None, not empty string) and is_flood_related is not None
                if (project_district_type and 
                    project_district and 
                    project_barangay_municipality and
                    is_flood_related is not None):
                    # Still include in results for summary, but skip reclassification
                    # Convert to result format and add to chunk_results
                    result = proj.copy()
                    # Ensure required fields are set for deduplication and summary
                    if not result.get('source'):
                        result['source'] = 'DIME'  # Set source based on processing function
                    # Ensure match_type is set
                    if not result.get('match_type'):
                        if result.get('district_congressman'):
                            result['match_type'] = 'district'
                        elif result.get('contractor_congressman'):
                            result['match_type'] = 'contractor'
                        else:
                            result['match_type'] = 'unknown'
                    # Mark as skipped for tracking
                    result['_skipped_reclassification'] = True
                    chunk_results.append(result)
                    self.progress_counters['skipped'] += 1
                    continue
            
            # Extract basic data
            proj_province = (proj.get('province') or '').strip()
            proj_city = (proj.get('city') or '').strip()
            proj_barangay = (proj.get('barangay') or '').strip()
            
            # Determine location key
            is_city_district = bool(proj_city and 'CITY' in proj_city.upper())
            
            # CRITICAL FIX: If province field is wrong (e.g., "Third District" instead of actual province),
            # and we have a valid city, use the city as the province for matching
            # This handles cases like Caloocan where province="Third District" but city="Caloocan City"
            if is_city_district and proj_city:
                # Check if province looks wrong (contains "District" or doesn't look like a province name)
                province_looks_wrong = (
                    'DISTRICT' in proj_province.upper() or
                    proj_province.upper() in ['FIRST', 'SECOND', 'THIRD', 'FOURTH', 'FIFTH', 'SIXTH', 'SEVENTH', 'EIGHTH', 'NINTH', 'TENTH'] or
                    (proj_province and len(proj_province.split()) == 1 and proj_province.upper().endswith('DISTRICT'))
                )
                
                if province_looks_wrong:
                    # Use city name as province for matching (e.g., "Caloocan City" -> "Caloocan")
                    city_name = proj_city.replace('City', '').replace('CITY', '').strip()
                    proj_province = city_name  # Use city name as province for city districts
            
            location_key = proj_barangay if is_city_district else (proj_city if proj_city and 'CITY' not in proj_city.upper() else None)
            
            # Extract contractor
            contractor_str = ''
            contractors_field = proj.get('contractors') or proj.get('contractor_name') or proj.get('contractor')
            if isinstance(contractors_field, list):
                contractor_str = ', '.join(contractors_field)
            elif contractors_field:
                contractor_str = str(contractors_field)

            # Extract year
            project_year = None
            date_field = proj.get('date_started') or proj.get('start_date') or proj.get('project_year') or proj.get('contract_year')
            if date_field:
                try:
                    if isinstance(date_field, (int, float)) and not (isinstance(date_field, float) and math.isnan(date_field)):
                        project_year = int(date_field)
                    elif isinstance(date_field, str):
                        from dateutil.parser import parse
                        project_year = parse(date_field).year
                    else:
                        project_year = date_field.year if hasattr(date_field, 'year') else None
                except (AttributeError, TypeError, ValueError):
                    pass

            # Unified Match
            final_congressman, match_type, match_score, district_cm, contractor_cm = self._match_project_unified(
                project_text="", # DIME doesn't rely on text matching as much as location columns
                province=proj_province,
                municipality_barangay=location_key,
                contractor=contractor_str,
                year=project_year,
                congressmen_data=congressmen_data,
                district_lookup=district_lookup_dict,
                contractor_lookup=contractor_lookup_dict,
                contractor_inverted_index=contractor_inverted_index
            )

            # Update Progress
            self._update_progress(match_type, final_congressman, is_city_district, bool(proj_barangay))

            # Construct Result
            location_parts = [p for p in [proj_province, proj_city, proj_barangay] if p]
            location_str = ', '.join(location_parts).strip() or "N/A"
            amount = self._parse_amount(proj.get('cost') or proj.get('amount'))
            
            # Determine district details
            congressman_district = None
            if district_cm and district_cm in congressmen_data:
                cm_data = congressmen_data[district_cm]
                if cm_data.get('district_number') and cm_data.get('provinces'):
                    congressman_district = f"{cm_data.get('district_number')} District {cm_data.get('provinces')[0]}"

            contractor_congressman_district = None
            if contractor_cm and contractor_cm in congressmen_data:
                cm_data = congressmen_data[contractor_cm]
                if cm_data.get('district_number') and cm_data.get('provinces'):
                    contractor_congressman_district = f"{cm_data.get('district_number')} District {cm_data.get('provinces')[0]}"

            # Determine project district type and name
            project_district_type = "city" if is_city_district else ("province" if proj_province else None)
            project_district = None
            if district_cm and district_cm in congressmen_data:
                cm_data = congressmen_data[district_cm]
                if cm_data.get('district_number') and cm_data.get('provinces'):
                    project_district = f"{cm_data.get('provinces')[0]} {cm_data.get('district_number')} District"

            # Determine barangay/municipality
            project_barangay_municipality = proj_barangay if proj_barangay else (proj_city if not is_city_district else None)
            if not project_barangay_municipality and location_str:
                 parts = [p.strip() for p in location_str.split(',')]
                 project_barangay_municipality = parts[-1] if parts else None

            is_flood = self._is_flood_related(proj.get('project_name') or "", proj.get('description') or "", location_str)

            # In force mode, always process and set fields to None if we can't determine them
            # This allows future runs to reclassify when newer logic is available
            if self.force_reclassify:
                # Ensure all classification fields are set (to None if not determinable)
                if not project_district_type:
                    project_district_type = None
                if not project_district:
                    project_district = None
                if not project_barangay_municipality:
                    project_barangay_municipality = None
                # is_flood is already set above
            else:
                # In non-force mode, skip if we can't determine all required fields
                if not (project_district_type and project_district and project_barangay_municipality):
                    continue

            chunk_results.append({
                "source": self._normalize_source_label("DIME"),
                "meilisearch_id": proj.get('meilisearch_id'),
                "project_name": proj.get('project_name') or "N/A",
                "contractor": contractor_str if contractor_str else "N/A",
                "amount": amount,
                "location": location_str,
                "year": project_year if project_year else "N/A",
                "status": proj.get('status') or "N/A",
                "district_congressman": district_cm,
                "district_match_type": "district" if district_cm else None,
                "district_match_score": match_score if match_type == 'district' else 0,
                "district_is_city_wide": (match_score == 1 and match_type == "district"),
                "congressman_district": congressman_district,
                "contractor_congressman": contractor_cm,
                "contractor_match_type": "contractor" if contractor_cm else None,
                "contractor_match_score": 50 if contractor_cm else 0,
                "contractor_congressman_district": contractor_congressman_district,
                "project_district_type": project_district_type,
                "project_district": project_district,
                "project_barangay_municipality": project_barangay_municipality,
                "project_province_city_district": project_district_type.capitalize() if project_district_type else None,
                "project_municipality_barangay": project_barangay_municipality,
                "is_flood_related": is_flood,
                "match_type": match_type,  # Add match_type for summary counting
                "match_score": match_score
            })
            
        return chunk_results

    def _process_philgeps_chunk(self, contracts_chunk: List[Dict], congressmen_data: Dict, districts_data: Dict,
                               district_lookup_dict: Dict, contractor_lookup_dict: Dict, contractor_inverted_index: Dict,
                               known_provinces: List[str] = None, known_cities: List[str] = None, 
                               location_context_map: Dict = None) -> List[Dict]:
        """Process a chunk of PhilGEPS contracts from Parquet using O(1) lookups."""
        chunk_results: List[Dict] = []
        
        # Use passed location data if available, otherwise extract (fallback)
        if known_provinces is None or known_cities is None:
            known_provinces_set, known_cities_set = self._extract_provinces_and_cities_from_data(congressmen_data, district_lookup_dict)
            known_provinces = sorted(list(known_provinces_set))
            known_cities = sorted(list(known_cities_set))
        
        if location_context_map is None:
            location_context_map = getattr(self, 'location_dicts', {}).get('location_context_map', None) if hasattr(self, 'location_dicts') else None

        for contract in contracts_chunk:
            # Check if already classified (unless force mode)
            # Check that all fields are not None and not empty strings
            if not self.force_reclassify:
                project_district_type = contract.get('project_district_type')
                project_district = contract.get('project_district')
                project_barangay_municipality = contract.get('project_barangay_municipality')
                is_flood_related = contract.get('is_flood_related')
                
                # Check if all fields are truthy (not None, not empty string) and is_flood_related is not None
                if (project_district_type and 
                    project_district and 
                    project_barangay_municipality and
                    is_flood_related is not None):
                    # Still include in results for summary, but skip reclassification
                    # Convert to result format and add to chunk_results
                    result = contract.copy()
                    # Ensure required fields are set for deduplication and summary
                    if not result.get('source'):
                        result['source'] = 'PhilGEPS'  # Set source based on processing function
                    # Ensure match_type is set
                    if not result.get('match_type'):
                        if result.get('district_congressman'):
                            result['match_type'] = 'district'
                        elif result.get('contractor_congressman'):
                            result['match_type'] = 'contractor'
                        else:
                            result['match_type'] = 'unknown'
                    # Mark as skipped for tracking
                    result['_skipped_reclassification'] = True
                    chunk_results.append(result)
                    self.progress_counters['skipped'] += 1
                    continue
            
            # Basic Data
            award_title = (contract.get('philgeps_award_title') or contract.get('award_title') or contract.get('project_name') or contract.get('project_description') or '')
            notice_title = (contract.get('notice_title') or '')  # Add notice_title for classification
            area_of_delivery = (contract.get('philgeps_area_of_delivery') or contract.get('area_of_delivery') or '')
            awardee_name = (contract.get('contractor_name') or contract.get('philgeps_awardee_name') or contract.get('awardee_name') or '')
            
            # Location Extraction - include notice_title for better classification
            location_text = f'{award_title} {notice_title} {area_of_delivery} {contract.get("province") or ""} {contract.get("city") or ""} {contract.get("municipality") or ""}'
            location_info = self._extract_location_from_text(location_text, known_provinces, known_cities, location_context_map)
            
            proj_province = location_info.get('province') or (contract.get('province') or '').upper()
            proj_municipality_barangay = location_info.get('municipality_barangay')
            is_city_district = location_info.get('is_city_district', False)
            
            if not proj_province:
                proj_province = (contract.get('province') or '').upper()
            if not proj_municipality_barangay:
                proj_municipality_barangay = (contract.get('municipality') or contract.get('city') or '').upper()
                # CRITICAL: Remove parenthetical suffixes like "(PALAWAN)", "(MARCOS)", etc.
                # Use optimized single-pass regex instead of while loop
                proj_municipality_barangay = re.sub(r'\s*\([^()]*(?:\([^()]*(?:\([^()]*\)[^()]*)*\)[^()]*)*\)\s*', ' ', proj_municipality_barangay)
                proj_municipality_barangay = proj_municipality_barangay.strip()
            
            # CRITICAL FIX: If province field is wrong (e.g., "Third District" instead of actual province),
            # and we have a valid city, use the city as the province for matching
            proj_city = (contract.get('city') or '').strip()
            if is_city_district and proj_city and 'CITY' in proj_city.upper():
                # Check if province looks wrong (contains "District" or doesn't look like a province name)
                province_looks_wrong = (
                    'DISTRICT' in proj_province.upper() or
                    proj_province.upper() in ['FIRST', 'SECOND', 'THIRD', 'FOURTH', 'FIFTH', 'SIXTH', 'SEVENTH', 'EIGHTH', 'NINTH', 'TENTH'] or
                    (proj_province and len(proj_province.split()) == 1 and proj_province.upper().endswith('DISTRICT'))
                )
                
                if province_looks_wrong:
                    # Use city name as province for matching (e.g., "Caloocan City" -> "Caloocan")
                    city_name = proj_city.replace('City', '').replace('CITY', '').strip()
                    proj_province = city_name.upper()  # Use city name as province for city districts

            # Year Extraction
            project_year = None
            if contract.get('project_year'):
                project_year = self._get_project_year(contract['project_year'])
            elif contract.get('award_date'):
                try:
                    if isinstance(contract['award_date'], str):
                        from dateutil.parser import parse
                        project_year = parse(contract['award_date']).year
                    else:
                        project_year = contract['award_date'].year
                except (AttributeError, TypeError, ValueError):
                    pass

            # Unified Match
            final_congressman, match_type, match_score, district_cm, contractor_cm = self._match_project_unified(
                project_text=location_text,
                province=proj_province,
                municipality_barangay=proj_municipality_barangay,
                contractor=awardee_name,
                year=project_year,
                congressmen_data=congressmen_data,
                district_lookup=district_lookup_dict,
                contractor_lookup=contractor_lookup_dict,
                contractor_inverted_index=contractor_inverted_index
            )

            # Update Progress
            self._update_progress(match_type, final_congressman, is_city_district, bool(proj_municipality_barangay))

            # Construct Result
            location_str = area_of_delivery or (contract.get('province') or '')
            amount = self._parse_amount(contract.get('amount') or contract.get('contract_amount'))
            
            # Determine district details
            congressman_district = None
            if district_cm and district_cm in congressmen_data:
                cm_data = congressmen_data[district_cm]
                if cm_data.get('district_number') and cm_data.get('provinces'):
                    congressman_district = f"{cm_data.get('district_number')} District {cm_data.get('provinces')[0]}"

            contractor_congressman_district = None
            if contractor_cm and contractor_cm in congressmen_data:
                cm_data = congressmen_data[contractor_cm]
                if cm_data.get('district_number') and cm_data.get('provinces'):
                    contractor_congressman_district = f"{cm_data.get('district_number')} District {cm_data.get('provinces')[0]}"

            # Determine project district type and name
            project_district_type = "city" if "CITY" in location_str.upper() else ("province" if proj_province else "province")
            
            project_district = None
            if district_cm and district_cm in congressmen_data:
                cm_data = congressmen_data[district_cm]
                if cm_data.get('district_number') and cm_data.get('provinces'):
                    project_district = f"{cm_data.get('provinces')[0]} {cm_data.get('district_number')} District"

            # Determine barangay/municipality
            project_barangay_municipality = proj_municipality_barangay
            if not project_barangay_municipality and location_str:
                 parts = [p.strip() for p in location_str.split(',')]
                 project_barangay_municipality = parts[-1] if parts else None
            if not project_barangay_municipality and proj_province:
                project_barangay_municipality = proj_province

            # Include notice_title in flood classification
            project_description = contract.get('project_description') or contract.get('award_description') or ""
            is_flood = self._is_flood_related(award_title, f"{project_description} {notice_title}".strip(), location_str)

            # In force mode, always process and set fields to None if we can't determine them
            # This allows future runs to reclassify when newer logic is available
            if self.force_reclassify:
                # Ensure all classification fields are set (to None if not determinable)
                if not project_district_type:
                    project_district_type = None
                if not project_district:
                    project_district = None
                if not project_barangay_municipality:
                    project_barangay_municipality = None
                # is_flood is already set above
            else:
                # In non-force mode, skip if we can't determine all required fields
                if not (project_district_type and project_district and project_barangay_municipality):
                    continue

            chunk_results.append({
                "source": self._normalize_source_label("PhilGEPS"),
                "meilisearch_id": contract.get('meilisearch_id') or contract.get('global_id'),
                "project_name": award_title or "N/A",
                "contractor": awardee_name or "N/A",
                "amount": amount,
                "location": location_str or "N/A",
                "year": project_year if project_year else "N/A",
                "status": contract.get('philgeps_award_status') or contract.get('award_status') or contract.get('contractor_status') or "N/A",
                "district_congressman": district_cm,
                "district_match_type": "district" if district_cm else None,
                "district_match_score": match_score if match_type == 'district' else 0,
                "district_is_city_wide": (match_score == 1 and match_type == "district"),
                "congressman_district": congressman_district,
                "contractor_congressman": contractor_cm,
                "contractor_match_type": "contractor" if contractor_cm else None,
                "contractor_match_score": 50 if contractor_cm else 0,
                "contractor_congressman_district": contractor_congressman_district,
                "project_district_type": project_district_type,
                "project_district": project_district,
                "project_barangay_municipality": project_barangay_municipality,
                "project_province_city_district": project_district_type.capitalize() if project_district_type else None,
                "project_municipality_barangay": project_barangay_municipality,
                "is_flood_related": is_flood,
                "match_type": match_type,  # Add match_type for summary counting
                "match_score": match_score
            })
            
        return chunk_results

    def _process_infrawatch_chunk(self, rows_chunk: List[Dict], congressmen_data: Dict, districts_data: Dict,
                                 district_lookup_dict: Dict, contractor_lookup_dict: Dict, contractor_inverted_index: Dict,
                                 known_provinces: List[str] = None, known_cities: List[str] = None, 
                                 location_context_map: Dict = None) -> List[Dict]:
        """Process a chunk of Infrawatch projects from Parquet using O(1) lookups."""
        chunk_results: List[Dict] = []
        
        # Use passed location data if available, otherwise extract (fallback)
        if known_provinces is None or known_cities is None:
            known_provinces_set, known_cities_set = self._extract_provinces_and_cities_from_data(congressmen_data, district_lookup_dict)
            known_provinces = sorted(list(known_provinces_set))
            known_cities = sorted(list(known_cities_set))
        
        if location_context_map is None:
            location_context_map = getattr(self, 'location_dicts', {}).get('location_context_map', None) if hasattr(self, 'location_dicts') else None

        for row in rows_chunk:
            record = row
            if not isinstance(record, dict):
                continue
            
            # Check if already classified (unless force mode)
            # Check that all fields are not None and not empty strings
            if not self.force_reclassify:
                project_district_type = record.get('project_district_type')
                project_district = record.get('project_district')
                project_barangay_municipality = record.get('project_barangay_municipality')
                is_flood_related = record.get('is_flood_related')
                
                # Check if all fields are truthy (not None, not empty string) and is_flood_related is not None
                if (project_district_type and 
                    project_district and 
                    project_barangay_municipality and
                    is_flood_related is not None):
                    # Still include in results for summary, but skip reclassification
                    # Convert to result format and add to chunk_results
                    result = record.copy()
                    # Ensure required fields are set for deduplication and summary
                    if not result.get('source'):
                        result['source'] = 'Microsite'  # Normalize to Microsite (Infrawatch -> Microsite)
                    # Ensure match_type is set
                    if not result.get('match_type'):
                        if result.get('district_congressman'):
                            result['match_type'] = 'district'
                        elif result.get('contractor_congressman'):
                            result['match_type'] = 'contractor'
                        else:
                            result['match_type'] = 'unknown'
                    # Mark as skipped for tracking
                    result['_skipped_reclassification'] = True
                    chunk_results.append(result)
                    self.progress_counters['skipped'] += 1
                    continue

            # Basic Data
            description = (record.get("Contract Details") or record.get("Project Description") or "").upper()
            # Get project title/description for classification (similar to notice_title in PhilGEPS)
            project_title = (record.get("Contract Details") or record.get("Project Description") or record.get("Project Title") or record.get("Title") or "").upper()
            contractor_raw = (record.get("Contractor") or record.get("Contractor Name") or record.get("Contractor_Name") or "")
            contractor = contractor_raw.upper()
            agency = (record.get("Implementing Agency") or "").upper()
            fund_source = (record.get("Fund Source") or "").upper()
            
            # Location Extraction - include project_title for better classification
            project_location = record.get("Implementing Agency") or record.get("Project Location") or record.get("location") or ""
            combined_text = f"{description} {project_title} {agency} {fund_source} {contractor} {project_location}"
            
            location_info = self._extract_location_from_text(combined_text, known_provinces, known_cities, location_context_map)
            
            proj_province = location_info.get('province') or ""
            proj_municipality_barangay = location_info.get('municipality_barangay') or ""
            is_city_district = location_info.get('is_city_district', False)
            
            # CRITICAL FIX: If province field is wrong (e.g., "Third District" instead of actual province),
            # and we have a valid city, use the city as the province for matching
            proj_city = (record.get('city') or record.get('City') or '').strip()
            if is_city_district and proj_city and 'CITY' in proj_city.upper():
                # Check if province looks wrong (contains "District" or doesn't look like a province name)
                province_looks_wrong = (
                    'DISTRICT' in proj_province.upper() or
                    proj_province.upper() in ['FIRST', 'SECOND', 'THIRD', 'FOURTH', 'FIFTH', 'SIXTH', 'SEVENTH', 'EIGHTH', 'NINTH', 'TENTH'] or
                    (proj_province and len(proj_province.split()) == 1 and proj_province.upper().endswith('DISTRICT'))
                )
                
                if province_looks_wrong:
                    # Use city name as province for matching (e.g., "Caloocan City" -> "Caloocan")
                    city_name = proj_city.replace('City', '').replace('CITY', '').strip()
                    proj_province = city_name.upper()  # Use city name as province for city districts
            
            # Fallback extraction from project_location string if not found
            if not proj_province and not proj_municipality_barangay and project_location:
                parts = [p.strip() for p in project_location.split(',')]
                for part in parts:
                    part_upper = part.upper()
                    if "CITY" in part_upper:
                        proj_municipality_barangay = part
                        is_city_district = True
                    elif not proj_province:
                        proj_province = part

            # Extract rich text for matching
            proj_name = (record.get('project_name') or '').strip()
            proj_desc = (record.get('project_description') or record.get('description') or '').strip()
            location = (record.get('location') or '').strip()
            
            combined_text = f"{proj_name} {proj_desc} {location}".strip()

            # Unified Match
            final_congressman, match_type, match_score, district_cm, contractor_cm = self._match_project_unified(
                project_text=combined_text,
                province=proj_province,
                municipality_barangay=proj_municipality_barangay,
                contractor=contractor,
                year=None, # Infrawatch has no reliable year
                congressmen_data=congressmen_data,
                district_lookup=district_lookup_dict,
                contractor_lookup=contractor_lookup_dict,
                contractor_inverted_index=contractor_inverted_index
            )

            # Update Progress
            self._update_progress(match_type, final_congressman, is_city_district, bool(proj_municipality_barangay))

            # Construct Result
            amount = self._parse_amount(record.get("Contract Price") or record.get("Contract Amount") or record.get("Amount") or record.get("Constract Price"))
            
            # Determine district details
            congressman_district = None
            if district_cm and district_cm in congressmen_data:
                cm_data = congressmen_data[district_cm]
                if cm_data.get('district_number') and cm_data.get('provinces'):
                    congressman_district = f"{cm_data.get('district_number')} District {cm_data.get('provinces')[0]}"

            contractor_congressman_district = None
            if contractor_cm and contractor_cm in congressmen_data:
                cm_data = congressmen_data[contractor_cm]
                if cm_data.get('district_number') and cm_data.get('provinces'):
                    contractor_congressman_district = f"{cm_data.get('district_number')} District {cm_data.get('provinces')[0]}"

            # Determine project district type and name
            project_district_type = "city" if "CITY" in (project_location or "").upper() else ("province" if proj_province else "province")
            
            project_district = None
            if district_cm and district_cm in congressmen_data:
                cm_data = congressmen_data[district_cm]
                if cm_data.get('district_number') and cm_data.get('provinces'):
                    project_district = f"{cm_data.get('provinces')[0]} {cm_data.get('district_number')} District"

            # Determine barangay/municipality
            project_barangay_municipality = proj_municipality_barangay
            if not project_barangay_municipality and project_location:
                 parts = [p.strip() for p in project_location.split(',')]
                 project_barangay_municipality = parts[-1] if parts else None

            # Include project_title in flood classification (similar to notice_title in PhilGEPS)
            is_flood = self._is_flood_related(description, f"{description} {project_title}".strip(), project_location)

            # In force mode, always process and set fields to None if we can't determine them
            # This allows future runs to reclassify when newer logic is available
            if self.force_reclassify:
                # Ensure all classification fields are set (to None if not determinable)
                if not project_district_type:
                    project_district_type = None
                if not project_district:
                    project_district = None
                if not project_barangay_municipality:
                    project_barangay_municipality = None
                # is_flood is already set above
            else:
                # In non-force mode, skip reclassification if we can't determine all required fields
                # But still include in results for summary counting
                if not (project_district_type and project_district and project_barangay_municipality):
                    # Still add to results for summary, but mark as unmatched
                    chunk_results.append({
                        "source": self._normalize_source_label("Microsite"),  # Normalize to Microsite for consistency
                        "meilisearch_id": None,
                        "project_name": description or "N/A",
                        "contractor": contractor_raw or "N/A",
                        "amount": amount,
                        "location": project_location or "N/A",
                        "year": None,
                        "status": record.get("Contract Status") or "N/A",
                        "district_congressman": None,
                        "contractor_congressman": None,
                        "match_type": "unmatched",
                        "match_score": 0,
                        "project_district_type": None,
                        "project_district": None,
                        "project_barangay_municipality": None,
                        "is_flood_related": is_flood_related,
                        "_skipped_reclassification": False,
                        "_unmatched": True
                    })
                    continue

            chunk_results.append({
                "source": self._normalize_source_label("Microsite"),  # Normalize to Microsite for consistency
                "meilisearch_id": None,
                "project_name": description or "N/A",
                "contractor": contractor_raw or "N/A",
                "amount": amount,
                "location": project_location or "N/A",
                "year": None,
                "status": record.get("Contract Status") or "N/A",
                "district_congressman": district_cm,
                "district_match_type": "district" if district_cm else None,
                "district_match_score": match_score if match_type == 'district' else 0,
                "district_is_city_wide": (match_score == 1 and match_type == "district"),
                "congressman_district": congressman_district,
                "contractor_congressman": contractor_cm,
                "contractor_match_type": "contractor" if contractor_cm else None,
                "contractor_match_score": 50 if contractor_cm else 0,
                "contractor_congressman_district": contractor_congressman_district,
                "project_district_type": project_district_type,
                "project_district": project_district,
                "project_barangay_municipality": project_barangay_municipality,
                "project_province_city_district": project_district_type.capitalize() if project_district_type else None,
                "project_municipality_barangay": project_barangay_municipality,
                "is_flood_related": is_flood,
                "match_type": match_type,  # Add match_type for summary counting
                "match_score": match_score
            })
            
        return chunk_results

    def _process_flood_chunk(self, projects_chunk: List[Dict], congressmen_data: Dict, districts_data: Dict,
                            district_lookup_dict: Dict, contractor_lookup_dict: Dict, contractor_inverted_index: Dict,
                            known_provinces: List[str] = None, known_cities: List[str] = None, 
                            location_context_map: Dict = None) -> List[Dict]:
        """Process a chunk of flood/SSP projects from Parquet using O(1) lookups."""
        chunk_results: List[Dict] = []
        
        # Extract provinces and cities ONCE per chunk ONLY IF NOT PROVIDED
        if known_provinces is None or known_cities is None:
            known_provinces_set, known_cities_set = self._extract_provinces_and_cities_from_data(congressmen_data, district_lookup_dict)
            known_provinces = sorted(list(known_provinces_set))
            known_cities = sorted(list(known_cities_set))
            
        if location_context_map is None:
            location_context_map = getattr(self, 'location_dicts', {}).get('location_context_map', None) if hasattr(self, 'location_dicts') else None


        processed_count = 0
        for proj in projects_chunk:
            processed_count += 1
            if processed_count % 1000 == 0:
                print(f"  🔄 Processed {processed_count} SSP/Flood rows in current chunk...")
            # Check if already classified (unless force mode)
            # Check that all fields are not None and not empty strings
            already_classified = False
            if not self.force_reclassify:
                project_district_type = proj.get('project_district_type')
                project_district = proj.get('project_district')
                project_barangay_municipality = proj.get('project_barangay_municipality')
                is_flood_related = proj.get('is_flood_related')
                
                # Check if all fields are truthy (not None, not empty string) and is_flood_related is not None
                if (project_district_type and 
                    project_district and 
                    project_barangay_municipality and
                    is_flood_related is not None):
                    already_classified = True
                    # Still include in results for summary, but skip reclassification
                    # Convert to result format and add to chunk_results
                    result = proj.copy()
                    # Ensure required fields are set for deduplication and summary
                    if not result.get('source'):
                        result['source'] = 'SSP'  # Set source based on processing function
                    # Ensure match_type is set
                    if not result.get('match_type'):
                        if result.get('district_congressman'):
                            result['match_type'] = 'district'
                        elif result.get('contractor_congressman'):
                            result['match_type'] = 'contractor'
                        else:
                            result['match_type'] = 'unknown'
                    # Mark as skipped for tracking
                    result['_skipped_reclassification'] = True
                    chunk_results.append(result)
                    self.progress_counters['skipped'] += 1
                    continue
            
            # Extract fields
            proj_desc = (proj.get('ProjectDescription') or proj.get('project_description') or proj.get('description') or '').upper()
            proj_province = (proj.get('Province') or proj.get('province') or '').upper()
            proj_municipality = (proj.get('Municipality') or proj.get('municipality') or '').upper()
            # CRITICAL: Remove parenthetical suffixes like "(PALAWAN)", "(MARCOS)", etc.
            # Use optimized single-pass regex instead of while loop to avoid infinite loops on unmatched parens
            proj_municipality = re.sub(r'\s*\([^()]*(?:\([^()]*(?:\([^()]*\)[^()]*)*\)[^()]*)*\)\s*', ' ', proj_municipality)
            # If any opening parenthesis remains (unmatched), just remove it and everything after to be safe
            if '(' in proj_municipality:
                 proj_municipality = proj_municipality.replace('(', ' ')
            proj_municipality = proj_municipality.strip()
            proj_city = (proj.get('City') or proj.get('city') or '').strip()
            proj_contractor = (proj.get('Contractor') or proj.get('contractor') or '').upper()
            proj_region = (proj.get('Region') or proj.get('region') or '').upper()
            proj_deo = (proj.get('DistrictEngineeringOffice') or proj.get('district_engineering_office') or proj.get('DEO') or proj.get('deo') or '').upper()
            proj_legislative_district = (proj.get('LegislativeDistrict') or proj.get('legislative_district') or proj.get('Legislative District') or '').upper()
            
            # CRITICAL FIX: If province field is wrong (e.g., "Third District" instead of actual province),
            # and we have a valid city, use the city as the province for matching
            is_city_district = bool(proj_city and 'CITY' in proj_city.upper())
            if is_city_district and proj_city:
                # Check if province looks wrong (contains "District" or doesn't look like a province name)
                province_looks_wrong = (
                    'DISTRICT' in proj_province.upper() or
                    proj_province.upper() in ['FIRST', 'SECOND', 'THIRD', 'FOURTH', 'FIFTH', 'SIXTH', 'SEVENTH', 'EIGHTH', 'NINTH', 'TENTH'] or
                    (proj_province and len(proj_province.split()) == 1 and proj_province.upper().endswith('DISTRICT'))
                )
                
                if province_looks_wrong:
                    # Use city name as province for matching (e.g., "Caloocan City" -> "Caloocan")
                    city_name = proj_city.replace('City', '').replace('CITY', '').strip()
                    proj_province = city_name.upper()  # Use city name as province for city districts
            
            # Combine text for location extraction
            combined_text = f'{proj_desc} {proj_province} {proj_municipality} {proj_contractor} {proj_region} {proj_deo} {proj_legislative_district}'
            
            # Extract location info
            location_info = self._extract_location_from_text(combined_text, known_provinces, known_cities, location_context_map)
            
            extracted_province = location_info.get('province')
            extracted_muni = location_info.get('municipality_barangay')
            is_city_district = location_info.get('is_city_district', False)

            # Prioritize explicit columns, then extracted info
            final_province = proj_province or extracted_province or ""
            final_muni = proj_municipality or extracted_muni or ""
            
            # Special handling for Legislative District column if province is missing
            if not final_province and proj_legislative_district:
                # Extract province/city from legislative district (e.g., "ILOILO 1ST DISTRICT" -> "ILOILO")
                leg_dist_clean = re.sub(r'\s+\d+(?:ST|ND|RD|TH)?\s+DISTRICT', '', proj_legislative_district).strip()
                if leg_dist_clean and len(leg_dist_clean) > 2:
                    if "CITY" in leg_dist_clean:
                        final_muni = leg_dist_clean
                        is_city_district = True
                        # Try to infer province from city
                        # (This would require a city->province lookup, which we can skip for now or rely on _match_project_unified to handle city matching)
                    else:
                        final_province = leg_dist_clean

            # Extract project year
            project_year = None
            year_field = proj.get('Year') or proj.get('year') or proj.get('project_year')
            if year_field:
                project_year = self._get_project_year(year_field)

            # Unified Match
            final_congressman, match_type, match_score, district_cm, contractor_cm = self._match_project_unified(
                project_text=combined_text,
                province=final_province,
                municipality_barangay=final_muni,
                contractor=proj_contractor,
                year=project_year,
                congressmen_data=congressmen_data,
                district_lookup=district_lookup_dict,
                contractor_lookup=contractor_lookup_dict,
                contractor_inverted_index=contractor_inverted_index
            )

            # Update Progress
            self._update_progress(match_type, final_congressman, is_city_district, bool(final_muni))

            # Construct Result
            amount = self._parse_amount(proj.get('Cost') or proj.get('cost') or proj.get('AllocatedCost') or proj.get('allocated_cost') or 0)
            
            # Determine district details
            congressman_district = None
            if district_cm and district_cm in congressmen_data:
                cm_data = congressmen_data[district_cm]
                if cm_data.get('district_number') and cm_data.get('provinces'):
                    congressman_district = f"{cm_data.get('district_number')} District {cm_data.get('provinces')[0]}"

            contractor_congressman_district = None
            if contractor_cm and contractor_cm in congressmen_data:
                cm_data = congressmen_data[contractor_cm]
                if cm_data.get('district_number') and cm_data.get('provinces'):
                    contractor_congressman_district = f"{cm_data.get('district_number')} District {cm_data.get('provinces')[0]}"

            # Determine project district type and name
            project_district_type = "city" if "CITY" in (final_muni or "").upper() or "CITY" in (final_province or "").upper() else "province"
            
            project_district = None
            if district_cm and district_cm in congressmen_data:
                cm_data = congressmen_data[district_cm]
                if cm_data.get('district_number') and cm_data.get('provinces'):
                    project_district = f"{cm_data.get('provinces')[0]} {cm_data.get('district_number')} District"

            # Determine barangay/municipality
            project_barangay_municipality = final_muni
            if not project_barangay_municipality and final_province:
                 project_barangay_municipality = final_province # Fallback

            is_flood = True # By definition, these are flood projects (or we can re-verify)
            # The original code re-verified using _is_flood_related, let's do that to be safe and consistent
            is_flood = self._is_flood_related(proj_desc, proj_desc, f"{final_province} {final_muni}")

            # In force mode, always process and set fields to None if we can't determine them
            # This allows future runs to reclassify when newer logic is available
            if self.force_reclassify:
                # Ensure all classification fields are set (to None if not determinable)
                if not project_district_type:
                    project_district_type = None
                if not project_district:
                    project_district = None
                if not project_barangay_municipality:
                    project_barangay_municipality = None
                # is_flood is already set above
            else:
                # In non-force mode, skip if we can't determine all required fields
                if not (project_district_type and project_district and project_barangay_municipality):
                    continue

            chunk_results.append({
                "source": self._normalize_source_label("Flood Control"), # Or "Flood"
                "meilisearch_id": proj.get('meilisearch_id') or proj.get('global_id'),
                "project_name": proj_desc or "N/A",
                "contractor": proj_contractor or "N/A",
                "amount": amount,
                "location": f"{final_province}, {final_muni}".strip(", ") or "N/A",
                "year": project_year if project_year else "N/A",
                "status": proj.get('Status') or proj.get('status') or "N/A",
                "district_congressman": district_cm,
                "district_match_type": "district" if district_cm else None,
                "district_match_score": match_score if match_type == 'district' else 0,
                "district_is_city_wide": (match_score == 1 and match_type == "district"),
                "congressman_district": congressman_district,
                "contractor_congressman": contractor_cm,
                "contractor_match_type": "contractor" if contractor_cm else None,
                "contractor_match_score": 50 if contractor_cm else 0,
                "contractor_congressman_district": contractor_congressman_district,
                "project_district_type": project_district_type,
                "project_district": project_district,
                "project_barangay_municipality": project_barangay_municipality,
                "project_province_city_district": project_district_type.capitalize() if project_district_type else None,
                "project_municipality_barangay": project_barangay_municipality,
                "is_flood_related": is_flood,
                "match_type": match_type,  # Add match_type for summary counting
                "match_score": match_score
            })
            
        return chunk_results

    async def load_config(self) -> Dict:
        """Load configuration files from DuckDB (faster) or fallback to JSON"""
        # Try DuckDB first
        duckdb_path = PARQUET_DIR / 'dynasty_data.duckdb'
        if duckdb_path.exists():
            try:
                return await self._load_config_from_duckdb(duckdb_path)
            except Exception as e:
                print(f"⚠️  Failed to load from DuckDB: {e}, falling back to JSON")
        
        # Fallback to JSON files
        config_data = {}
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
        
        districts_data = {}
        if self.districts_file.exists():
            with open(self.districts_file, 'r', encoding='utf-8') as f:
                districts_data = json.load(f)

        self._initialize_manila_tokens(districts_data)
        
        return config_data, districts_data
    
    async def _load_config_from_duckdb(self, duckdb_path: Path) -> tuple[Dict, Dict]:
        """Load config and districts data from DuckDB"""
        import duckdb
        
        conn = duckdb.connect(str(duckdb_path))
        try:
            # Load congressmen config
            config_rows = conn.execute("SELECT * FROM congressmen_config ORDER BY id").fetchall()
            config_columns = [desc[0] for desc in conn.description]
            
            target_congressmen = []
            for row in config_rows:
                entry = dict(zip(config_columns, row))
                # Parse JSON fields
                if entry.get('terms'):
                    try:
                        entry['terms'] = json.loads(entry['terms'])
                    except:
                        entry['terms'] = []
                if entry.get('barangays'):
                    try:
                        entry['barangays'] = json.loads(entry['barangays'])
                    except:
                        entry['barangays'] = []
                if entry.get('family_connections'):
                    try:
                        entry['family_connections'] = json.loads(entry['family_connections'])
                    except:
                        entry['family_connections'] = {}
                if entry.get('previous_positions'):
                    try:
                        entry['previous_positions'] = json.loads(entry['previous_positions'])
                    except:
                        entry['previous_positions'] = []
                # Normalize display_name to canonical form
                original_display_name = entry.get('display_name', '')
                if original_display_name:
                    # Build temporary normalization map for this batch
                    # We'll rebuild it properly later, but for now normalize based on what we've seen
                    normalized_name = self._normalize_congressman_name(original_display_name)
                    # Store both original and normalized for later processing
                    entry['_original_display_name'] = original_display_name
                    entry['_normalized_name'] = normalized_name
                
                target_congressmen.append(entry)
            
            # Normalize all display names to canonical forms
            # Group by normalized name and pick shortest as canonical
            normalized_groups = {}
            for entry in target_congressmen:
                normalized = entry.get('_normalized_name', '')
                if normalized:
                    if normalized not in normalized_groups:
                        normalized_groups[normalized] = []
                    normalized_groups[normalized].append(entry)
            
            # For each group, pick longest/most complete display_name as canonical and update all entries
            # (prefer names with middle names, full names over nicknames)
            # Middle names are important for tracing family trees
            for normalized, entries in normalized_groups.items():
                if len(entries) > 1:
                    # Multiple variations - pick most complete as canonical
                    # Priority: full middle names > middle initials > no middle names
                    def name_priority(e):
                        name = e.get('display_name', '')
                        parts = name.split()
                        word_count = len(parts)
                        has_middle = word_count > 2
                        
                        # Check if name has full middle names (not just initials)
                        has_full_middle = False
                        full_middle_count = 0
                        if word_count > 2:
                            # Check middle parts (skip first and last)
                            for part in parts[1:-1]:
                                # Remove period if present
                                clean_part = part.rstrip('.')
                                if len(clean_part) > 1:
                                    has_full_middle = True
                                    full_middle_count += 1
                        
                        # Check if last name is hyphenated (more complete)
                        last_name = parts[-1] if parts else ""
                        has_hyphenated_last = '-' in last_name
                        
                        # Priority: has_full_middle > full_middle_count > has_hyphenated_last > has_middle > length
                        return (has_full_middle, full_middle_count, has_hyphenated_last, has_middle, len(name))
                    
                    canonical_entry = max(entries, key=name_priority)
                    canonical_name = canonical_entry.get('display_name', '')
                    # Update all entries to use canonical name
                    for entry in entries:
                        entry['display_name'] = canonical_name
            
            # Load metadata
            metadata_row = conn.execute("SELECT * FROM config_metadata WHERE id = 1").fetchone()
            config_data = {
                'target_congressmen': target_congressmen,
                'metadata': {}
            }
            if metadata_row:
                metadata_cols = [desc[0] for desc in conn.description]
                metadata_dict = dict(zip(metadata_cols, metadata_row))
                if metadata_dict.get('metadata'):
                    try:
                        config_data['metadata'] = json.loads(metadata_dict['metadata'])
                    except:
                        pass
                if metadata_dict.get('verified_contractors'):
                    try:
                        config_data['verified_contractors'] = json.loads(metadata_dict['verified_contractors'])
                    except:
                        pass
            
            # Load districts data
            district_rows = conn.execute("SELECT * FROM district_entries ORDER BY name").fetchall()
            district_columns = [desc[0] for desc in conn.description]
            
            districts_dict = {}
            for row in district_rows:
                entry = dict(zip(district_columns, row))
                name = entry['name']
                data_str = entry['data']
                try:
                    data = json.loads(data_str) if isinstance(data_str, str) else data_str
                    districts_dict[name] = data
                except:
                    pass
            
            # Load district metadata
            dist_metadata_row = conn.execute("SELECT * FROM district_metadata WHERE id = 1").fetchone()
            districts_data = {
                'districts': districts_dict,
                'metadata': {}
            }
            if dist_metadata_row:
                dist_metadata_cols = [desc[0] for desc in conn.description]
                dist_metadata_dict = dict(zip(dist_metadata_cols, dist_metadata_row))
                if dist_metadata_dict.get('metadata'):
                    try:
                        districts_data['metadata'] = json.loads(dist_metadata_dict['metadata'])
                    except:
                        pass
            
            self._initialize_manila_tokens(districts_data)
            
            return config_data, districts_data
        finally:
            conn.close()

    def _initialize_manila_tokens(self, districts_data: Dict) -> None:
        """Pre-compute Manila barangay tokens and numbers from districts.json"""
        # [Keep all the same logic from original script]
        self.manila_barangay_tokens.clear()
        self.manila_barangay_numbers.clear()
        self.manila_keyword_map.clear()
        if not districts_data:
            return

        manila_info = districts_data.get('districts', {}).get('Manila')
        if not manila_info:
            return

        barangay_map = manila_info.get('barangays', {})
        for district_label, barangay_list in barangay_map.items():
            tokens: set[str] = set()
            numbers: set[int] = set()

            for barangay in barangay_list or []:
                if not barangay:
                    continue
                upper = barangay.upper().strip()
                if upper:
                    tokens.add(upper)

                cleaned = upper.replace('NO.', '').replace('NO', '')
                for part in re.split(r'[^0-9]+', cleaned):
                    if not part:
                        continue
                    try:
                        num = int(part)
                    except ValueError:
                        continue
                    numbers.add(num)
                    base = str(num)
                    tokens.update({
                        f'BARANGAY {base}',
                        f'BARANGAY NO {base}',
                        f'BARANGAY NO. {base}',
                        f'BRGY {base}',
                        f'BRGY. {base}',
                        f'BRG {base}',
                        f'BGY {base}',
                    })

            district_key = district_label.upper()
            self.manila_barangay_tokens[district_key] = sorted(tokens)
            self.manila_barangay_numbers[district_key] = sorted(numbers)
            keyword_list = []
            custom_keywords = manila_info.get('keywords', {}).get(district_label, [])
            if custom_keywords:
                keyword_list.extend([kw.upper() for kw in custom_keywords if kw])
            else:
                default_map = {
                    '1ST DISTRICT': ['TONDO I', 'TONDO 1', 'TONDO'],
                    '2ND DISTRICT': ['TONDO II', 'TONDO 2', 'TONDO'],
                    '3RD DISTRICT': ['QUIAPO', 'BINONDO', 'SAN NICOLAS', 'STA. CRUZ', 'SANTA CRUZ'],
                    '4TH DISTRICT': ['SAMPALOC'],
                    '5TH DISTRICT': ['PACO', 'PANDACAN', 'SAN ANDRES', 'STA. ANA', 'SANTA ANA'],
                    '6TH DISTRICT': ['ERMITA', 'MALATE', 'INTRAMUROS', 'PORT AREA'], # Removed SAN MIGUEL to avoid false positives
                }
                keyword_list.extend(default_map.get(district_key, []))
            self.manila_keyword_map[district_key] = keyword_list

        leyte_info = districts_data.get('districts', {}).get('Leyte', {})
        keyword_info = leyte_info.get('keywords', {}).get('2nd District', {})
        municipalities_map = leyte_info.get('municipalities', {})
        self.leyte_second_municipalities = {
            name.upper()
            for name, district in municipalities_map.items()
            if district.upper() == '2ND DISTRICT'
        }
        self.leyte_second_keywords = [kw.upper() for kw in keyword_info.get('positive', [])]
        self.leyte_second_negative_keywords = [kw.upper() for kw in keyword_info.get('negative', [])]
        if not self.leyte_second_keywords:
            self.leyte_second_keywords = [
                'LEYTE 2ND', '2ND LD', 'SECOND LD', '2ND LEGISLATIVE DISTRICT',
                'SECOND LEGISLATIVE DISTRICT', '2ND DISTRICT ENGINEERING',
                'LEYTE 2ND DEO', 'LEYTE II', '2ND DEO', '2ND LEGISLATIVE DIST.',
                'LEYTE 2 DEO'
            ]
        if not self.leyte_second_negative_keywords:
            self.leyte_second_negative_keywords = [
                'LEYTE 1ST', 'LEYTE 3RD', 'LEYTE 4TH', 'LEYTE 5TH', 'LEYTE 6TH',
                '1ST LD', '3RD LD', '4TH LD', '5TH LD', '6TH LD',
                'SOUTHERN LEYTE', 'NORTHERN SAMAR', 'EASTERN SAMAR', 'WESTERN SAMAR',
                'SAMAR PROVINCE', 'BILIRAN', 'ORMOC CITY', 'ORMOC', 'TACLOBAN',
                'TAC. CITY', 'TAC CITY', 'LEYTE I DEO', 'LEYTE 1 DEO', 'LEYTE 3 DEO',
                'LEYTE 4 DEO', 'LEYTE 5 DEO', 'LEYTE 6 DEO'
            ]

        samar_info = districts_data.get('districts', {}).get('Samar', {})
        keyword_info = samar_info.get('keywords', {}).get('1st District', {})
        municipalities_map = samar_info.get('municipalities', {})
        self.samar_first_municipalities = {
            name.upper()
            for name, district in municipalities_map.items()
            if district.upper() == '1ST DISTRICT'
        }
        self.samar_first_keywords = [kw.upper() for kw in keyword_info.get('positive', [])]
        self.samar_first_negative_keywords = [kw.upper() for kw in keyword_info.get('negative', [])]
        if not self.samar_first_keywords:
            self.samar_first_keywords = [
                'SAMAR 1ST', '1ST LD', 'FIRST LD', '1ST LEGISLATIVE DISTRICT',
                'FIRST LEGISLATIVE DISTRICT', 'SAMAR 1ST DEO', 'SAMAR I',
                'SAMAR 1ST ENGINEERING', '1ST DEO', 'SAMAR 1 DEO',
                'CALBAYOG CITY DEO', 'CALBAYOG 1ST'
            ]
        if not self.samar_first_negative_keywords:
            self.samar_first_negative_keywords = [
                'SAMAR 2ND', 'SAMAR 3RD', 'SAMAR 4TH',
                '2ND LD', 'SECOND LD', '3RD LD', 'THIRD LD',
                'EASTERN SAMAR', 'NORTHERN SAMAR', 'WESTERN SAMAR',
                'CATBALOGAN', 'SOUTHERN LEYTE'
            ]
    
    async def get_congressmen_data(self, dynasty_conn, config_data: Dict, districts_data: Dict, political_dynasties_available: bool) -> Dict:
        """Get congressmen data from parquet files using DuckDB (no PostgreSQL needed)"""
        """Get congressmen data from database - same logic as original"""
        # [Keep all the same logic from original script - lines 539-788]
        # This is a large function, so I'll include the key parts
        congressmen_data = {}
        processed_congressmen = set()
        
        target_congressmen = config_data.get('target_congressmen', [])
        
        def _name_key(first: Optional[str], last: Optional[str]) -> tuple[str, str]:
            return ((first or '').strip().upper(), (last or '').strip().upper())

        contractor_lookup: Dict[tuple[str, str], List[asyncpg.Record]] = defaultdict(list)
        party_memberships_by_person: Dict[int, List[Any]] = defaultdict(list)
        party_memberships_by_name: Dict[tuple[str, str], List[Any]] = defaultdict(list)
        party_memberships_by_party: Dict[Any, set[tuple[str, str]]] = defaultdict(set)
        party_contractors: Dict[Any, set[str]] = defaultdict(set)

        # Try to load contractor matches from DuckDB first (faster)
        duckdb_path = PARQUET_DIR / 'dynasty_data.duckdb'
        contractor_rows = []
        if duckdb_path.exists():
            try:
                import duckdb
                conn = duckdb.connect(str(duckdb_path))
                try:
                    contractor_rows = conn.execute("SELECT dynasty_first_name, dynasty_last_name, company_name, role FROM contractor_dynasty_matches").fetchall()
                    # Convert to asyncpg.Record-like objects
                    for row in contractor_rows:
                        # Create a dict-like object
                        row_dict = {
                            'dynasty_first_name': row[0],
                            'dynasty_last_name': row[1],
                            'company_name': row[2],
                            'role': row[3]
                        }
                        key = _name_key(row_dict['dynasty_first_name'], row_dict['dynasty_last_name'])
                        contractor_lookup[key].append(row_dict)
                    print(f"✅ Loaded {len(contractor_rows)} contractor matches from DuckDB")
                finally:
                    conn.close()
            except Exception as e:
                print(f"⚠️  Failed to load contractors from DuckDB: {e}")
        
        # Note: No PostgreSQL fallback - using DuckDB/Parquet only

            # Try to load party list members from DuckDB first
            party_rows = []
            if duckdb_path.exists():
                try:
                    import duckdb
                    conn = duckdb.connect(str(duckdb_path))
                    try:
                        party_rows = conn.execute("SELECT person_id, party_list_number, first_name, last_name FROM party_list_members").fetchall()
                        # Convert to dict-like objects
                        for row in party_rows:
                            row_dict = {
                                'person_id': row[0],
                                'party_list_number': row[1],
                                'first_name': row[2],
                                'last_name': row[3]
                            }
                            party_number = row_dict['party_list_number']
                            person_id = row_dict['person_id']
                            key = _name_key(row_dict['first_name'], row_dict['last_name'])
                            if person_id is not None:
                                party_memberships_by_person[person_id].append(party_number)
                            party_memberships_by_name[key].append(party_number)
                            party_memberships_by_party[party_number].add(key)
                        print(f"✅ Loaded {len(party_rows)} party list members from DuckDB")
                    finally:
                        conn.close()
                except Exception as e:
                    print(f"⚠️  Failed to load party members from DuckDB: {e}")
            
            # Note: No PostgreSQL fallback - using DuckDB/Parquet only

            for party_number, member_keys in party_memberships_by_party.items():
                party_set = party_contractors[party_number]
                for member_key in member_keys:
                    for contractor_row in contractor_lookup.get(member_key, []):
                        company_name = contractor_row.get('company_name')
                        if company_name:
                            party_set.add(company_name)

        for congressman_config in target_congressmen:
            first_name_pattern = congressman_config.get('first_name_pattern', '')
            last_name_pattern = congressman_config.get('last_name_pattern', '')
            display_name = congressman_config.get('display_name', '')
            config_province = congressman_config.get('province')
            config_district_number = congressman_config.get('district_number')
            config_is_city_district = congressman_config.get('is_city_district', False)
            config_is_partylist = congressman_config.get('is_partylist', False)
            congressman_id = congressman_config.get('id')
            
            # Get congressman from parquet file using DuckDB
            person = None
            if POLITICAL_DYNASTIES_PARQUET.exists():
                try:
                    import duckdb
                    conn = duckdb.connect()
                    try:
                        first_pattern = f"{(first_name_pattern or '').upper()}%"
                        last_pattern = f"{(last_name_pattern or '').upper()}%"
                        full_pattern = f"%{(first_name_pattern or '').upper()}% {(last_name_pattern or '').upper()}%"
                        mannix_pattern = (first_name_pattern or '').upper()
                        
                        query = f"""
                            SELECT id, first_name, last_name, middle_name, province, municipality_city, region, party
                            FROM read_parquet('{POLITICAL_DYNASTIES_PARQUET}')
                            WHERE (
                                UPPER(position) LIKE '%CONGRESSMAN%' 
                                OR UPPER(position) LIKE '%CONGRESSMEN%' 
                                OR UPPER(position) LIKE '%MEMBER, HOUSE OF REPRESENTATIVES%'
                                OR UPPER(position) LIKE '%REPRESENTATIVE%PARTY-LIST%'
                                OR UPPER(position) LIKE '%REPRESENTATIVE, %PARTY-LIST%'
                                OR UPPER(position) LIKE '%PARTY-LIST%REPRESENTATIVE%'
                                OR UPPER(position) LIKE '%DEPUTY SPEAKER%'
                                OR UPPER(position) LIKE '%SPEAKER%'
                            )
                              AND (
                                (UPPER(first_name) LIKE '{first_pattern}' AND UPPER(last_name) LIKE '{last_pattern}')
                                OR (UPPER(first_name || ' ' || COALESCE(middle_name, '') || ' ' || last_name) LIKE '{full_pattern}')
                                OR (UPPER(first_name || ' ' || COALESCE(middle_name, '')) LIKE '{first_pattern}' AND UPPER(last_name) LIKE '{last_pattern}')
                                OR (UPPER(last_name) LIKE '{last_pattern}' AND UPPER(first_name) LIKE '%MANNIX%' AND '{mannix_pattern}' = 'MANNIX')
                                OR (UPPER(last_name) LIKE '{last_pattern}' AND UPPER(first_name) LIKE '%MANUEL%' AND '{mannix_pattern}' = 'MANNIX')
                              )
                            ORDER BY id DESC
                            LIMIT 1
                        """
                        result = conn.execute(query).fetchone()
                        if result:
                            person = {
                                'id': result[0],
                                'first_name': result[1],
                                'last_name': result[2],
                                'middle_name': result[3],
                                'province': result[4],
                                'municipality_city': result[5],
                                'region': result[6],
                                'party': result[7]
                            }
                    finally:
                        conn.close()
                except Exception as e:
                    print(f"⚠️  Failed to load congressman from parquet: {e}")
            
            # Fallback when dynasty DB is missing or no match
            if not person:
                person = {
                    'id': congressman_id,
                    'first_name': first_name_pattern or display_name.split(' ')[0],
                    'last_name': last_name_pattern or display_name.split(' ')[-1],
                    'middle_name': None,
                    'province': config_province,
                    'municipality_city': None,
                    'region': None,
                    'party': None
                }
            
            person_key = f"{person['first_name']} {person['last_name']}"
            if person_key in processed_congressmen:
                continue
            processed_congressmen.add(person_key)
            
            provinces = [config_province] if config_province else ([person['province']] if person['province'] else [])
            
            # Load municipalities from districts.json ONLY for this district_number
            district_municipalities = []
            if districts_data and config_province and config_district_number:
                province_key = None
                for key in districts_data.get('districts', {}).keys():
                    if key.upper() == config_province.upper():
                        province_key = key
                        break
                
                if province_key:
                    districts_info = districts_data.get('districts', {}).get(province_key, {})
                    municipalities_map = districts_info.get('municipalities', {})
                    for mun_key, mun_district in municipalities_map.items():
                        if mun_district and mun_district.upper() == config_district_number.upper():
                            district_municipalities.append(mun_key)
            
            name_key = _name_key(person['first_name'], person['last_name'])
            if political_dynasties_available:
                direct_contractors = contractor_lookup.get(name_key, [])
            else:
                direct_contractors = []
            
            verified_patterns = config_data.get('verified_contractors', {}).get('patterns', [])
            contractor_exclusions = {}
            for exclusion in config_data.get('verified_contractors', {}).get('exclusions', []):
                pattern = exclusion.get('pattern')
                exclude = exclusion.get('exclude')
                if pattern and exclude:
                    contractor_exclusions.setdefault(pattern.upper(), []).append(exclude.upper())

            def _should_exclude(name: str) -> bool:
                upper_name = name.upper()
                for pattern, exclusions in contractor_exclusions.items():
                    if pattern in upper_name:
                        for exclusion_value in exclusions:
                            if exclusion_value in upper_name:
                                return True
                return False

            def _expand_patterns(name: str) -> list[str]:
                base_upper = name.upper().strip()
                patterns = {base_upper}
                patterns.add(re.sub(r'\([^)]*\)', '', base_upper).strip())
                for part in re.split(r'[\\/]', base_upper):
                    part = part.strip()
                    if len(part) >= 3:
                        patterns.add(part)
                final = set()
                for pattern in patterns:
                    clean = re.sub(r'\s+', ' ', pattern).strip()
                    if clean:
                        final.add(clean)
                return [p for p in final if len(p) >= 3]

            contractor_names = []
            contractor_patterns = []
            for contractor in direct_contractors:
                company_name = contractor['company_name']
                if not company_name:
                    continue
                if _should_exclude(company_name):
                    continue
                if verified_patterns:
                    upper_name = company_name.upper()
                    if not any(pattern.upper() in upper_name for pattern in verified_patterns):
                        pass
                    contractor_names.append(company_name)
                contractor_patterns.extend(_expand_patterns(company_name))

            # Load contractors from family_connections in config
            family_connections = congressman_config.get('family_connections') or {}
            family_contractors = family_connections.get('contractors', []) if isinstance(family_connections, dict) else []
            for company_name in family_contractors:
                if not company_name or _should_exclude(company_name):
                    continue
                contractor_names.append(company_name)
                contractor_patterns.extend(_expand_patterns(company_name))

            party_numbers: List[Any] = []
            if political_dynasties_available:
                if person.get('id') is not None:
                    party_numbers.extend(party_memberships_by_person.get(person['id'], []))
                if not party_numbers:
                    party_numbers.extend(party_memberships_by_name.get(name_key, []))

            for party_number in party_numbers:
                for company_name in party_contractors.get(party_number, set()):
                    if not company_name or _should_exclude(company_name):
                        continue
                    contractor_names.append(company_name)
                    contractor_patterns.extend(_expand_patterns(company_name))
            
            contractor_names = sorted(set(name for name in contractor_names if name))
            contractor_patterns = sorted(set(p for p in contractor_patterns if p))
            
            # If we don't have district_municipalities from districts.json, skip UNLESS congressman has contractors
            if not district_municipalities and not config_is_city_district:
                if not contractor_names:
                    print(f"⚠️  Skipping {display_name}: No municipalities found in districts.json for {config_district_number} and no verified contractors")
                    continue
                else:
                    print(f"ℹ️  Processing {display_name} via contractors only (no district data)")
            elif district_municipalities:
                print(f"✅ {display_name}: Loaded {len(district_municipalities)} municipalities for {config_district_number}: {district_municipalities[:3]}...")
            
            # Get barangays if needed
            barangays = []
            if congressman_id == 5:  # Mannix Dalipe
                barangays_file = Path(__file__).parent.parent / '2nd-district-zamboanga-city.json'
                if barangays_file.exists():
                    with open(barangays_file, 'r', encoding='utf-8') as f:
                        barangays_data = json.load(f)
                        if isinstance(barangays_data, list):
                            barangays = barangays_data
                        elif isinstance(barangays_data, dict):
                            barangays = barangays_data.get('barangays', barangays_data.get('2nd_district_barangays', []))
            
            # Get terms from config
            terms = congressman_config.get('terms', [])
            # Handle terms that might be stored as JSON string
            if isinstance(terms, str):
                import json
                try:
                    terms = json.loads(terms)
                except (json.JSONDecodeError, TypeError):
                    terms = []
            
            congressmen_data[display_name] = {
                "name": display_name,
                "provinces": provinces,
                "district_municipalities": district_municipalities,
                "district_number": config_district_number,
                "is_city_district": config_is_city_district,
                "is_partylist": config_is_partylist,  # Add is_partylist flag
                "contractors": contractor_names,
                "contractor_patterns": contractor_patterns,
                "contractor_exclusions": contractor_exclusions,
                "barangays": barangays,
                "terms": terms,
            }
        
        return congressmen_data

    def _build_lookup_dictionaries(self, congressmen_data: Dict, districts_data: Dict) -> tuple[Dict, Dict]:
        """
        Build O(1) lookup dictionaries for O(n) matching.
        Returns: (district_lookup, contractor_lookup)
        
        district_lookup structure:
        - Key: (province_upper, municipality_upper) for province districts
        - Key: (city_upper, barangay_upper) for city districts
        - Value: list of (congressman_name, congressman_data) tuples
        
        contractor_lookup structure:
        - Key: contractor_name_upper or contractor_pattern_upper
        - Value: list of (congressman_name, congressman_data) tuples
        
        contractor_inverted_index structure:
        - Key: token (word) from contractor name
        - Value: set of contractor_lookup keys containing this token
        """
        from collections import defaultdict
        
        district_lookup: Dict[tuple, List[tuple]] = defaultdict(list)
        contractor_lookup: Dict[str, List[tuple]] = defaultdict(list)
        contractor_inverted_index: Dict[str, Set[str]] = defaultdict(set)
        
        # Common words to exclude from inverted index (too broad)
        COMMON_TOKENS = {'CONSTRUCTION', 'INC', 'CORP', 'INCORPORATED', 'CORPORATION', 'AND', 'THE', 'OF', 'COMPANY', 'CO', 'LTD', 'LIMITED', 'TRADING', 'ENTERPRISES', 'SUPPLY', 'SERVICES', 'BUILDERS', 'DEVELOPMENT', 'ENGINEERING'}
        # 3. Special handling for Davao City districts
        # Paolo Duterte is listed under 'Davao del Sur', '1st District' but represents Davao City 1st District
        # We need to ensure that Davao City 1st District is treated as a city district, not a provincial one.
        # This logic needs to be applied to the specific congressman's data before processing.
        
        # This part of the snippet seems to be misplaced or incomplete.
        # The original instruction was to update `_match_project_unified` and `_initialize_manila_tokens`.
        # The provided snippet for `_build_lookup_dictionaries` seems to be an attempt to add logic
        # for Davao City districts, but it's syntactically incorrect and refers to `congressman_data`
        # as a single item, not the dictionary of all congressmen.
        # Assuming the intent was to modify the `cm_data` within the loop,
        # but without a clear and syntactically correct instruction,
        # I will only apply the `_initialize_manila_tokens` change and
        # leave `_build_lookup_dictionaries` as it was, as the provided
        # snippet for it is not a valid or complete change.
        # If the user intended a specific change here, it needs to be re-specified.
        
        for congressman_name, cm_data in congressmen_data.items():
            provinces = cm_data.get('provinces', [])
            district_number = cm_data.get('district_number', '')
            is_city_district = cm_data.get('is_city_district', False)
            district_municipalities = cm_data.get('district_municipalities', [])
            barangays = cm_data.get('barangays', [])
            
            # Build district lookup
            if provinces:
                province_upper = provinces[0].upper()
                
                # Special handling for Davao City districts
                # Paolo Duterte's config has "province": "Davao City" but projects may have "Davao Del Sur" as province
                # Also handle when province is "Davao del Sur" but represents Davao City 1st District
                # CRITICAL: Only apply this to Paolo Duterte (1st District of Davao City)
                # Check by congressman name to ensure we only apply to the right person
                is_davao_city_district = (
                    (province_upper == 'DAVAO CITY' or province_upper == 'DAVAO DEL SUR') and 
                    district_number == '1st District' and
                    'DUTERTE' in congressman_name.upper() and 'PAOLO' in congressman_name.upper()
                )
                
                if is_davao_city_district:
                    # Add alias for Davao City - treat as city district
                    is_city_district = True 
                    # Add entries for DAVAO CITY
                    district_lookup[('DAVAO CITY', '')].append((congressman_name, cm_data))
                    # Also add entries for DAVAO DEL SUR (in case projects use this)
                    # BUT only if the congressman is actually Paolo Duterte
                    district_lookup[('DAVAO DEL SUR', '')].append((congressman_name, cm_data))
                    
                    for barangay in barangays:
                        if barangay:
                            barangay_upper = barangay.upper().strip()
                            # Add to both DAVAO CITY and DAVAO DEL SUR lookups
                            district_lookup[('DAVAO CITY', barangay_upper)].append((congressman_name, cm_data))
                            district_lookup[('DAVAO DEL SUR', barangay_upper)].append((congressman_name, cm_data))
                            
                            # Handle variations like "BRGY 10-A" -> "10-A"
                            if barangay_upper.startswith('BRGY'):
                                clean_brgy = barangay_upper.replace('BRGY', '').strip()
                                district_lookup[('DAVAO CITY', clean_brgy)].append((congressman_name, cm_data))
                                district_lookup[('DAVAO DEL SUR', clean_brgy)].append((congressman_name, cm_data))
                            
                            # Handle variations like "Barangay 10-A" -> "10-A"
                            if barangay_upper.startswith('BARANGAY'):
                                clean_brgy = barangay_upper.replace('BARANGAY', '').strip()
                                district_lookup[('DAVAO CITY', clean_brgy)].append((congressman_name, cm_data))
                                district_lookup[('DAVAO DEL SUR', clean_brgy)].append((congressman_name, cm_data))
                    
                    # Also add standard DAVAO DEL SUR entries (handled by normal flow below)
                
                # Special handling for Iloilo City (Lone District of Iloilo)
                if province_upper == 'ILOILO' and (district_number == 'Lone District' or district_number == 'Lone'):
                    is_city_district = True
                    district_lookup[('ILOILO CITY', '')].append((congressman_name, cm_data))
                    # Add Iloilo City barangays if available
                    for barangay in barangays:
                        if barangay:
                            barangay_upper = barangay.upper().strip()
                            district_lookup[('ILOILO CITY', barangay_upper)].append((congressman_name, cm_data))
                            if barangay_upper.startswith('BRGY'):
                                district_lookup[('ILOILO CITY', barangay_upper.replace('BRGY', '').strip())].append((congressman_name, cm_data))
                
                # Special handling for city districts where config has city name without "CITY" suffix
                # Example: "Marikina" in config but projects have "Marikina City"
                # This handles Stella Quimbo (Marikina 2nd District)
                # Use deduplication dictionary to dynamically determine if city name is unique
                if is_city_district:
                    location_dicts = getattr(self, 'location_dicts', {})
                    dedup_dict = location_dicts.get('dedup_dict', {})
                    
                    # Check if this city name is unique (only 1 city, no provinces/municipalities with same name)
                    city_base = province_upper
                    city_with_suffix = f"{city_base} CITY"
                    
                    # Check deduplication counts
                    dedup_info = dedup_dict.get(city_base, {})
                    city_count = dedup_info.get('cities', 0)
                    province_count = dedup_info.get('provinces', 0)
                    municipality_count = dedup_info.get('municipalities', 0)
                    
                    # City is unique if: exactly 1 city, 0 provinces, 0 municipalities with same base name
                    is_unique_city = (city_count == 1 and province_count == 0 and municipality_count == 0)
                    
                    if is_unique_city:
                        # Add lookup for both "Marikina" and "Marikina City"
                        district_lookup[(city_with_suffix, '')].append((congressman_name, cm_data))
                        for barangay in barangays:
                            if barangay:
                                barangay_upper = barangay.upper().strip()
                                district_lookup[(city_with_suffix, barangay_upper)].append((congressman_name, cm_data))
                                if barangay_upper.startswith('BRGY'):
                                    district_lookup[(city_with_suffix, barangay_upper.replace('BRGY', '').strip())].append((congressman_name, cm_data))
                                if barangay_upper.startswith('BARANGAY'):
                                    district_lookup[(city_with_suffix, barangay_upper.replace('BARANGAY', '').strip())].append((congressman_name, cm_data))

                # CRITICAL FIX: Skip "NATIONWIDE" provinces to prevent false positives
                if province_upper == "NATIONWIDE" or "PARTY-LIST" in province_upper:
                    # Party list reps should match via contractor or other means, not by "NATIONWIDE" location
                    # Skip adding to district_lookup so they don't match via location
                    pass
                elif is_city_district:
                    # City district: map by city + barangay
                    # Also map by city alone (for city-wide projects)
                    district_lookup[(province_upper, '')].append((congressman_name, cm_data))
                    
                    # Map by barangays
                    for barangay in barangays:
                        if barangay:
                            barangay_upper = barangay.upper().strip()
                            district_lookup[(province_upper, barangay_upper)].append((congressman_name, cm_data))
                            # Also add without "BRGY" prefix
                            if barangay_upper.startswith('BRGY'):
                                district_lookup[(province_upper, barangay_upper.replace('BRGY', '').strip())].append((congressman_name, cm_data))
                    
                    # Also check districts.json for barangays
                    if districts_data:
                        province_key = None
                        for key in districts_data.get('districts', {}).keys():
                            if key.upper() == province_upper:
                                province_key = key
                                break
                        
                        if province_key:
                            districts_info = districts_data.get('districts', {}).get(province_key, {})
                            barangays_map = districts_info.get('barangays', {})
                            if district_number and district_number in barangays_map:
                                for barangay in barangays_map[district_number]:
                                    if barangay:
                                        barangay_upper = barangay.upper().strip()
                                        district_lookup[(province_upper, barangay_upper)].append((congressman_name, cm_data))
                                        # Clean variations
                                        clean_brgy = re.sub(r'^(BRGY\.?|BARANGAY)\s*', '', barangay_upper, flags=re.IGNORECASE).strip()
                                        if clean_brgy != barangay_upper:
                                            district_lookup[(province_upper, clean_brgy)].append((congressman_name, cm_data))
                else:
                    # Province district: map by province + municipality
                    # Also map by province alone (for province-wide projects)
                    district_lookup[(province_upper, '')].append((congressman_name, cm_data))
                    
                    # Map by municipalities
                    for municipality in district_municipalities:
                        if municipality:
                            mun_upper = municipality.upper().strip()
                            district_lookup[(province_upper, mun_upper)].append((congressman_name, cm_data))
            
            # Build contractor lookup
            contractors = cm_data.get('contractors', [])
            contractor_patterns = cm_data.get('contractor_patterns', [])
            
            for contractor in contractors:
                if contractor:
                    contractor_upper = contractor.upper().strip()
                    contractor_lookup[contractor_upper].append((congressman_name, cm_data))
                    # Also add normalized versions
                    normalized = re.sub(r'[^A-Z0-9]+', ' ', contractor_upper).strip()
                    if normalized != contractor_upper:
                        contractor_lookup[normalized].append((congressman_name, cm_data))
            
            for pattern in contractor_patterns:
                if pattern:
                    pattern_upper = pattern.upper().strip()
                    contractor_lookup[pattern_upper].append((congressman_name, cm_data))
                    # Also add normalized versions
                    normalized = re.sub(r'[^A-Z0-9]+', ' ', pattern_upper).strip()
                    if normalized != pattern_upper:
                        contractor_lookup[normalized].append((congressman_name, cm_data))
        
        # Build inverted index from contractor_lookup keys
        for key in contractor_lookup.keys():
            # Tokenize key
            # Use simple splitting by non-alphanumeric characters
            tokens = re.split(r'[^A-Z0-9]+', key.upper())
            for token in tokens:
                if len(token) >= 3 and token not in COMMON_TOKENS:
                    contractor_inverted_index[token].add(key)
        
        return dict(district_lookup), dict(contractor_lookup), dict(contractor_inverted_index)

    def _normalize_location_name(self, name: str) -> str:
        """
        Normalize a location name for fuzzy matching.
        Removes special characters, extra spaces, and common variations.
        Also strips parenthetical suffixes like "(PALAWAN)", "(MARCOS)", etc.
        """
        if not name:
            return ''
        
        # Convert to uppercase
        normalized = name.upper().strip()
        
        # CRITICAL: Remove parenthetical suffixes like "(PALAWAN)", "(MARCOS)", "(CAPITAL)", etc.
        # These are common in data but not in config (e.g., "RIZAL (MARCOS) (PALAWAN)" -> "RIZAL")
        # Optimized: Use a single-pass regex that handles nested parentheses efficiently
        # This replaces the while loop with a more efficient approach
        normalized = re.sub(r'\s*\([^()]*(?:\([^()]*(?:\([^()]*\)[^()]*)*\)[^()]*)*\)\s*', ' ', normalized)
        
        # Remove common prefixes/suffixes
        normalized = re.sub(r'^(BRGY\.?|BRG\.?|BGY\.?|BARANGAY|BARANGGAY|BARANGGY|MUNICIPALITY OF|MUNICIPALITY|CITY OF|CITY)\s+', '', normalized, flags=re.IGNORECASE)
        
        # Remove special characters but keep spaces
        normalized = re.sub(r'[^\w\s]', '', normalized)
        
        # Normalize whitespace
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        # Remove common words that don't affect matching
        normalized = re.sub(r'\b(THE|A|AN|OF|AND|OR)\b', '', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """
        Fast Levenshtein distance calculation using dynamic programming.
        Returns the minimum number of single-character edits needed to transform s1 into s2.
        """
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        # Use only previous row to save memory
        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                # Cost of insertions, deletions, and substitutions
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    def _find_closest_match(self, query: str, candidates: List[str], max_distance: int = 2) -> Optional[str]:
        """
        Find the closest match to query from candidates using Levenshtein distance.
        Returns the best match if distance <= max_distance, else None.
        """
        if not query or not candidates:
            return None
        
        query_upper = query.upper().strip()
        best_match = None
        best_distance = max_distance + 1
        
        for candidate in candidates:
            candidate_upper = candidate.upper().strip()
            # Normalize both before comparing
            query_norm = self._normalize_location_name(query_upper)
            candidate_norm = self._normalize_location_name(candidate_upper)
            
            # Calculate distance on normalized strings
            distance = self._levenshtein_distance(query_norm, candidate_norm)
            
            if distance < best_distance:
                best_distance = distance
                best_match = candidate
        
        return best_match if best_distance <= max_distance else None
    
    def _build_location_dictionaries(self, congressmen_data: Dict, district_lookup_dict: Dict, districts_data: Dict) -> Dict:
        """
        Build comprehensive dictionaries for all provinces, municipalities, cities, barangays,
        and directional variants from the loaded data instead of hardcoding.
        
        Returns: {
            'provinces': set of all provinces,
            'cities': set of all cities,
            'municipalities': set of all municipalities,
            'barangays': set of all barangays,
            'directional_map': dict mapping base province name to list of variants,
            'abbreviation_map': dict mapping abbreviations to full names
        }
        """
        provinces = set()
        cities = set()
        municipalities = set()
        barangays = set()
        
        # Extract from congressmen_data
        for cm_name, cm_data in congressmen_data.items():
            cm_provinces = cm_data.get('provinces', [])
            is_city_district = cm_data.get('is_city_district', False)
            district_municipalities = cm_data.get('district_municipalities', [])
            cm_barangays = cm_data.get('barangays', [])
            
            for prov in cm_provinces:
                if prov:
                    prov_upper = prov.upper().strip()
                    provinces.add(prov_upper)
                    # If it's a city district, also add to cities
                    if is_city_district:
                        cities.add(prov_upper)
            
            # Add municipalities
            for mun in district_municipalities:
                if mun:
                    municipalities.add(mun.upper().strip())
            
            # Add barangays
            for brgy in cm_barangays:
                if brgy:
                    brgy_upper = brgy.upper().strip()
                    barangays.add(brgy_upper)
                    # Also add cleaned version without BRGY prefix
                    clean_brgy = re.sub(r'^(BRGY\.?|BARANGAY)\s*', '', brgy_upper, flags=re.IGNORECASE).strip()
                    if clean_brgy:
                        barangays.add(clean_brgy)
        
        # Also extract from district_lookup_dict keys
        for (prov_key, loc_key), candidates in district_lookup_dict.items():
            if prov_key:
                provinces.add(prov_key)
                # Check if any candidate is a city district
                for cm_name, cm_data in candidates:
                    if cm_data.get('is_city_district', False):
                        cities.add(prov_key)
            
            if loc_key:
                # Determine if it's a municipality or barangay based on district type
                for cm_name, cm_data in candidates:
                    if cm_data.get('is_city_district', False):
                        barangays.add(loc_key)
                    else:
                        municipalities.add(loc_key)
                    break  # Just need to check one candidate
        
        # Extract from districts.json
        if districts_data:
            for province_key, province_data in districts_data.get('districts', {}).items():
                if province_key:
                    prov_upper = province_key.upper().strip()
                    provinces.add(prov_upper)
                
                # Extract municipalities and barangays from districts.json
                for district_num, district_info in province_data.items():
                    if isinstance(district_info, dict):
                        # Check if this is a city district (has barangays)
                        if 'barangays' in district_info:
                            cities.add(prov_upper)
                            for brgy in district_info.get('barangays', []):
                                if brgy:
                                    brgy_upper = brgy.upper().strip()
                                    barangays.add(brgy_upper)
                                    clean_brgy = re.sub(r'^(BRGY\.?|BARANGAY)\s*', '', brgy_upper, flags=re.IGNORECASE).strip()
                                    if clean_brgy:
                                        barangays.add(clean_brgy)
                        # Check if this is a province district (has municipalities)
                        if 'municipalities' in district_info:
                            for mun in district_info.get('municipalities', []):
                                if mun:
                                    municipalities.add(mun.upper().strip())
        
        # Build directional map: base province name -> list of variants
        # e.g., "ILOCOS" -> ["ILOCOS NORTE", "ILOCOS SUR"]
        directional_map = defaultdict(list)
        for prov in provinces:
            prov_upper = prov.upper().strip()
            # Remove directional modifiers to get base name
            base_name = re.sub(r'\s*(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\s*$', '', prov_upper).strip()
            if base_name and base_name != prov_upper:
                directional_map[base_name].append(prov_upper)
            # Also add the full name as its own base
            directional_map[prov_upper].append(prov_upper)
        
        # Build abbreviation map for cities
        abbreviation_map = {}
        for city in cities:
            city_upper = city.upper().strip()
            # Common abbreviations
            if 'QUEZON CITY' in city_upper:
                abbreviation_map['Q'] = city_upper
                abbreviation_map['QC'] = city_upper
            elif 'MANILA' in city_upper:
                abbreviation_map['M'] = city_upper
                abbreviation_map['MM'] = 'METRO MANILA'
            elif 'CEBU CITY' in city_upper:
                abbreviation_map['C'] = city_upper
            elif 'DAVAO CITY' in city_upper:
                abbreviation_map['D'] = city_upper
            elif 'ILOILO CITY' in city_upper:
                abbreviation_map['I'] = city_upper
            elif 'BACOLOD CITY' in city_upper:
                abbreviation_map['B'] = city_upper
            elif 'PASIG CITY' in city_upper:
                abbreviation_map['P'] = city_upper
            elif 'MAKATI CITY' in city_upper:
                abbreviation_map['M'] = city_upper  # Note: conflicts with Manila, but that's okay
            elif 'TAGUIG CITY' in city_upper:
                abbreviation_map['T'] = city_upper
            elif 'VALENZUELA CITY' in city_upper:
                abbreviation_map['V'] = city_upper
            elif 'LAS PIÑAS CITY' in city_upper or 'LAS PINAS CITY' in city_upper:
                abbreviation_map['L'] = city_upper
                abbreviation_map['LP'] = city_upper
            elif 'MUNTINLUPA CITY' in city_upper:
                abbreviation_map['MP'] = city_upper
            elif 'PARAÑAQUE CITY' in city_upper or 'PARANAQUE CITY' in city_upper:
                abbreviation_map['P'] = city_upper  # Note: conflicts with Pasig
            elif 'MANDALUYONG CITY' in city_upper:
                abbreviation_map['M'] = city_upper  # Note: conflicts with Manila/Makati
            elif 'SAN JUAN CITY' in city_upper:
                abbreviation_map['S'] = city_upper
            elif 'CALOOCAN CITY' in city_upper:
                abbreviation_map['C'] = city_upper  # Note: conflicts with Cebu
        
        # Build location context map: location_name -> list of (province/city, type)
        # e.g., "MATINA" -> [("DAVAO CITY", "barangay"), ("ILOILO", "municipality")]
        location_context_map = defaultdict(list)
        
        # Map municipalities to their provinces
        for cm_name, cm_data in congressmen_data.items():
            cm_provinces = cm_data.get('provinces', [])
            is_city_district = cm_data.get('is_city_district', False)
            district_municipalities = cm_data.get('district_municipalities', [])
            cm_barangays = cm_data.get('barangays', [])
            
            province_upper = cm_provinces[0].upper().strip() if cm_provinces else None
            
            if not is_city_district and province_upper:
                # Province district: municipalities belong to this province
                for mun in district_municipalities:
                    if mun:
                        mun_upper = mun.upper().strip()
                        location_context_map[mun_upper].append((province_upper, 'municipality'))
            
            if is_city_district and province_upper:
                # City district: barangays belong to this city
                for brgy in cm_barangays:
                    if brgy:
                        brgy_upper = brgy.upper().strip()
                        location_context_map[brgy_upper].append((province_upper, 'barangay'))
                        # Also add cleaned version without BRGY prefix
                        clean_brgy = re.sub(r'^(BRGY\.?|BARANGAY)\s*', '', brgy_upper, flags=re.IGNORECASE).strip()
                        if clean_brgy and clean_brgy != brgy_upper:
                            location_context_map[clean_brgy].append((province_upper, 'barangay'))
        
        # Also extract from district_lookup_dict
        for (prov_key, loc_key), candidates in district_lookup_dict.items():
            if loc_key and prov_key:
                for cm_name, cm_data in candidates:
                    if cm_data.get('is_city_district', False):
                        location_context_map[loc_key].append((prov_key, 'barangay'))
                    else:
                        location_context_map[loc_key].append((prov_key, 'municipality'))
                    break  # Just need to check one candidate
        
        # Extract from districts.json
        if districts_data:
            for province_key, province_data in districts_data.get('districts', {}).items():
                if not province_key:
                    continue
                prov_upper = province_key.upper().strip()
                
                for district_num, district_info in province_data.items():
                    if isinstance(district_info, dict):
                        # Barangays in city districts
                        if 'barangays' in district_info:
                            for brgy in district_info.get('barangays', []):
                                if brgy:
                                    brgy_upper = brgy.upper().strip()
                                    location_context_map[brgy_upper].append((prov_upper, 'barangay'))
                                    clean_brgy = re.sub(r'^(BRGY\.?|BARANGAY)\s*', '', brgy_upper, flags=re.IGNORECASE).strip()
                                    if clean_brgy and clean_brgy != brgy_upper:
                                        location_context_map[clean_brgy].append((prov_upper, 'barangay'))
                        # Municipalities in province districts
                        if 'municipalities' in district_info:
                            for mun in district_info.get('municipalities', []):
                                if mun:
                                    mun_upper = mun.upper().strip()
                                    location_context_map[mun_upper].append((prov_upper, 'municipality'))
        
        # Remove duplicates from location_context_map
        for key in location_context_map:
            location_context_map[key] = list(set(location_context_map[key]))
        
        # Build normalized versions of all locations for fuzzy matching
        normalized_provinces = {}
        normalized_cities = {}
        normalized_municipalities = {}
        normalized_barangays = {}
        
        for prov in provinces:
            norm = self._normalize_location_name(prov)
            if norm:
                normalized_provinces[norm] = prov
        
        for city in cities:
            norm = self._normalize_location_name(city)
            if norm:
                normalized_cities[norm] = city
        
        for mun in municipalities:
            norm = self._normalize_location_name(mun)
            if norm:
                normalized_municipalities[norm] = mun
        
        for brgy in barangays:
            norm = self._normalize_location_name(brgy)
            if norm:
                normalized_barangays[norm] = brgy
        
        # Build deduplication dictionary: location name -> counts by type and variants
        # This tells us how many locations share the same name (e.g., "Marikina" appears as 1 city, 0 provinces, etc.)
        # Also tracks directional variants (e.g., "Samar" has 3 variants: Samar, Northern Samar, Eastern Samar)
        dedup_dict = defaultdict(lambda: {
            'provinces': 0,
            'cities': 0,
            'municipalities': 0,
            'barangays': 0,
            'regions': 0,
            'province_variants': [],  # List of all province variants (e.g., ["SAMAR", "NORTHERN SAMAR", "EASTERN SAMAR"])
            'city_variants': [],  # List of all city variants
            'municipality_variants': [],  # List of all municipality variants
            'barangay_variants': []  # List of all barangay variants
        })
        
        # Count provinces and track variants
        for prov in provinces:
            prov_base = prov.upper().strip()
            dedup_dict[prov_base]['provinces'] += 1
            if prov_base not in dedup_dict[prov_base]['province_variants']:
                dedup_dict[prov_base]['province_variants'].append(prov_base)
            
            # Remove "CITY" suffix for base name
            prov_base_no_city = re.sub(r'\s+CITY\s*$', '', prov_base).strip()
            if prov_base_no_city != prov_base:
                dedup_dict[prov_base_no_city]['cities'] += 1
                if prov_base not in dedup_dict[prov_base_no_city]['city_variants']:
                    dedup_dict[prov_base_no_city]['city_variants'].append(prov_base)
            
            # Extract base name for directional variants (e.g., "NORTHERN SAMAR" -> "SAMAR")
            base_name = re.sub(r'\s*(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\s*$', '', prov_base).strip()
            if base_name and base_name != prov_base:
                if prov_base not in dedup_dict[base_name]['province_variants']:
                    dedup_dict[base_name]['province_variants'].append(prov_base)
        
        # Count cities and track variants
        for city in cities:
            city_base = city.upper().strip()
            dedup_dict[city_base]['cities'] += 1
            if city_base not in dedup_dict[city_base]['city_variants']:
                dedup_dict[city_base]['city_variants'].append(city_base)
            
            city_base_no_city = re.sub(r'\s+CITY\s*$', '', city_base).strip()
            if city_base_no_city != city_base:
                dedup_dict[city_base_no_city]['cities'] += 1
                if city_base not in dedup_dict[city_base_no_city]['city_variants']:
                    dedup_dict[city_base_no_city]['city_variants'].append(city_base)
        
        # Count municipalities and track variants
        for mun in municipalities:
            mun_base = mun.upper().strip()
            dedup_dict[mun_base]['municipalities'] += 1
            if mun_base not in dedup_dict[mun_base]['municipality_variants']:
                dedup_dict[mun_base]['municipality_variants'].append(mun_base)
        
        # Count barangays and track variants
        for brgy in barangays:
            brgy_base = brgy.upper().strip()
            dedup_dict[brgy_base]['barangays'] += 1
            if brgy_base not in dedup_dict[brgy_base]['barangay_variants']:
                dedup_dict[brgy_base]['barangay_variants'].append(brgy_base)
            
            # Remove common prefixes for base name
            brgy_base_clean = re.sub(r'^(BRGY\.?|BRG\.?|BGY\.?|BARANGAY|BARANGGAY|BARANGGY)\s+', '', brgy_base, flags=re.IGNORECASE).strip()
            if brgy_base_clean and brgy_base_clean != brgy_base:
                dedup_dict[brgy_base_clean]['barangays'] += 1
                if brgy_base not in dedup_dict[brgy_base_clean]['barangay_variants']:
                    dedup_dict[brgy_base_clean]['barangay_variants'].append(brgy_base)
        
        # Add regions (NCR, Metro Manila, CARAGA, etc.)
        regions = ['NCR', 'NATIONAL CAPITAL REGION', 'METRO MANILA', 'CARAGA', 'CAR', 'CORDILLERA ADMINISTRATIVE REGION']
        for region in regions:
            dedup_dict[region.upper()]['regions'] += 1
        
        return {
            'provinces': provinces,
            'cities': cities,
            'municipalities': municipalities,
            'barangays': barangays,
            'directional_map': dict(directional_map),
            'abbreviation_map': abbreviation_map,
            'location_context_map': dict(location_context_map),
            'normalized_provinces': normalized_provinces,
            'normalized_cities': normalized_cities,
            'normalized_municipalities': normalized_municipalities,
            'normalized_barangays': normalized_barangays,
            'dedup_dict': dict(dedup_dict)  # Add deduplication dictionary
        }
    
    def _extract_provinces_and_cities_from_data(self, congressmen_data: Dict, district_lookup_dict: Dict) -> tuple[set[str], set[str]]:
        """
        Extract all provinces and cities from the loaded data instead of hardcoding.
        Returns: (provinces_set, cities_set)
        """
        provinces = set()
        cities = set()
        
        # Extract from congressmen_data
        for cm_name, cm_data in congressmen_data.items():
            cm_provinces = cm_data.get('provinces', [])
            is_city_district = cm_data.get('is_city_district', False)
            
            for prov in cm_provinces:
                if prov:
                    prov_upper = prov.upper().strip()
                    provinces.add(prov_upper)
                    # If it's a city district, also add to cities
                    if is_city_district:
                        cities.add(prov_upper)
        
        # Also extract from district_lookup_dict keys
        for (prov_key, loc_key), candidates in district_lookup_dict.items():
            if prov_key:
                provinces.add(prov_key)
                # Check if any candidate is a city district
                for cm_name, cm_data in candidates:
                    if cm_data.get('is_city_district', False):
                        cities.add(prov_key)
        
        return provinces, cities

    def _extract_barangay_from_text(self, text: str) -> Optional[str]:
        """
        Extract barangay name from project text.
        Looks for patterns like:
        - "Barangay 10-A", "Brgy. 10-A", "BRGY 10-A"
        - "Barangay Tumana", "Brgy. Tumana"
        - "Barangay Concepcion Uno", "Brgy. Concepcion Dos"
        - "Bgy. 30-C", "Bgy 20-B"
        """
        if not text:
            return None
        
        text_upper = text.upper()
        
        # Pattern 1: Barangay with number and letter (e.g., "Barangay 10-A", "Brgy. 30-C")
        pattern1 = re.compile(r'\b(?:BARANGAY|BRGY|BRG|BGY)\.?\s*(\d{1,3}[A-Z]?)\b', re.IGNORECASE)
        match1 = pattern1.search(text_upper)
        if match1:
            return match1.group(1)
        
        # Pattern 2: Barangay with number range (e.g., "Barangay 1-5")
        pattern2 = re.compile(r'\b(?:BARANGAY|BRGY|BRG|BGY)\.?\s*(\d{1,3})\s*[-–]\s*(\d{1,3})\b', re.IGNORECASE)
        match2 = pattern2.search(text_upper)
        if match2:
            return match2.group(1)  # Return first number
        
        # Pattern 3: Barangay with name (e.g., "Barangay Tumana", "Brgy. Concepcion Uno")
        # Extract the word(s) after "Barangay" or "Brgy"
        pattern3 = re.compile(r'\b(?:BARANGAY|BRGY|BRG|BGY)\.?\s+([A-Z][A-Z0-9\s\-]+?)(?:\s*,|\s+at\s+|\s+in\s+|\s+of\s+|$)', re.IGNORECASE)
        match3 = pattern3.search(text_upper)
        if match3:
            barangay_name = match3.group(1).strip()
            # Clean up common suffixes
            barangay_name = re.sub(r'\s+(CITY|PROVINCE|MUNICIPALITY|DISTRICT)$', '', barangay_name, flags=re.IGNORECASE)
            if len(barangay_name) > 1:  # Must be at least 2 characters
                return barangay_name
        
        # Pattern 4: Look for common barangay patterns in project names
        # e.g., "at Purok 3, Barangay 10-A" or "in Brgy. Tumana"
        pattern4 = re.compile(r'(?:AT|IN|OF)\s+(?:PUROK\s+\d+,\s*)?(?:BARANGAY|BRGY|BRG|BGY)\.?\s*([A-Z0-9\s\-]+?)(?:\s*,|\s+at\s+|\s+in\s+|\s+of\s+|$)', re.IGNORECASE)
        match4 = pattern4.search(text_upper)
        if match4:
            barangay_name = match4.group(1).strip()
            if len(barangay_name) > 1:
                return barangay_name
        
        return None
    
    def _extract_location_from_text(self, text: str, known_provinces: List[str], known_cities: List[str], location_context_map: Optional[Dict] = None) -> Dict[str, Optional[str]]:
        """
        Extract province, municipality/barangay, and district type from concatenated text.
        
        Rules (from established logic):
        1. Concatenate all related column strings and substring match province AND municipality
        2. If CITY/city word is present, classify as city district (strict requirement - else province district)
        3. Parse <municipality>, <province> or <barangay>, <city> patterns with strict order (beginning substring match)
        4. Handle province name variations (del Sur, del Norte, Occidental, Oriental, Eastern, Northern, Western, Southern)
        5. Use location_context_map to disambiguate duplicate location names (e.g., "Matina" in Davao vs Iloilo)
        
        Returns: {
            'province': str or None,
            'municipality_barangay': str or None,
            'is_city_district': bool,
            'location_text': str (cleaned)
        }
        """
        if not text:
            return {'province': None, 'municipality_barangay': None, 'is_city_district': False, 'location_text': ''}
        
        text_upper = text.upper().strip()
        result = {
            'province': None,
            'municipality_barangay': None,
            'is_city_district': False,
            'location_text': text_upper
        }
        
        # Helper function to disambiguate location using context
        def disambiguate_location(location_name: str, text_context: str, context_map: Dict) -> Optional[tuple]:
            """
            Disambiguate a location name using context from the text.
            Returns: (province_city, location_type) or None if no match
            """
            if not context_map or not location_name:
                return None
            
            location_upper = location_name.upper().strip()
            contexts = context_map.get(location_upper, [])
            
            if len(contexts) == 0:
                return None
            elif len(contexts) == 1:
                # Only one context, return it
                return contexts[0]
            else:
                # Multiple contexts - use text context to disambiguate
                # Check which province/city is mentioned in the text
                for prov_city, loc_type in contexts:
                    prov_city_upper = prov_city.upper()
                    # Check if this province/city is mentioned in the text
                    # Use word boundary to avoid partial matches
                    if re.search(r'\b' + re.escape(prov_city_upper) + r'\b', text_context):
                        return (prov_city, loc_type)
                    # Also check for partial matches (e.g., "DAVAO" in "DAVAO CITY")
                    if prov_city_upper in text_context or any(word in text_context for word in prov_city_upper.split()):
                        return (prov_city, loc_type)
                
                # If no match found, return the first one (fallback)
                return contexts[0]
        
        # Step 1: Check for CITY/city word OR unique barangay (strict requirement for city district classification)
        # Barangay indicators: barangay, brgy, brg, bgy, and common misspellings
        has_city_word = bool(re.search(r'\bCITY\b', text_upper))
        has_barangay_indicator = bool(re.search(r'\b(BARANGAY|BRGY|BRG|BGY|BARANGGAY|BARANGGY|BRGY\.|BRGY\s)\b', text_upper, re.IGNORECASE))
        
        # CRITICAL: If no CITY word, can only be city district if barangay is very clear and unique
        # We'll check for unique barangay later in the matching process
        # For now, only set is_city_district if CITY word is present
        result['is_city_district'] = has_city_word
        
        # Store barangay indicator for later use (to check if unique barangay can override)
        result['_has_barangay_indicator'] = has_barangay_indicator
        
        # Step 2: Check if province has directional modifier (Southern, Northern, etc.)
        def has_directional_modifier(prov_name: str) -> bool:
            """Check if province name has a directional modifier"""
            prov_upper = prov_name.upper().strip()
            # Check for: del Sur, del Norte, Occidental, Oriental, Eastern, Northern, Western, Southern
            return bool(re.search(r'\b(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\b', prov_upper))
        
        def normalize_province_base(prov_name: str) -> str:
            """Get base province name by removing directional variations (for comparison only)"""
            prov_upper = prov_name.upper().strip()
            # Remove: del Sur, del Norte, Occidental, Oriental, Eastern, Northern, Western, Southern
            prov_upper = re.sub(r'\s*(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\s*$', '', prov_upper)
            return prov_upper.strip()
        
        # Step 2.5: Try to extract barangay from text first (before comma parsing)
        # This helps with cases like "Construction at Barangay 10-A, Marikina City"
        extracted_barangay = self._extract_barangay_from_text(text)
        if extracted_barangay and not result['municipality_barangay']:
            result['municipality_barangay'] = extracted_barangay
        
        # Step 3: Parse comma-separated patterns with strict order
        # Pattern: "<municipality>, <province>" or "<barangay>, <city>"
        # Use beginning substring match for province/city after comma
        parts = [p.strip() for p in text.split(',')]
        
        if len(parts) >= 2:
            # Check last 2 parts for "<location>, <province/city>" pattern (strict order)
            location_part = parts[-2].strip()  # Municipality/barangay (before comma)
            province_city_part = parts[-1].strip().upper()  # Province/city (after comma)
            
            if location_part and province_city_part:
                # Check if location_part contains barangay indicators
                location_upper = location_part.upper()
                is_barangay_location = bool(re.search(r'\b(BARANGAY|BRGY|BRG|BGY|BARANGGAY|BARANGGY)\b', location_upper))
                
                # Clean location part (remove common prefixes and parenthetical suffixes)
                location_clean = location_part
                # CRITICAL: Remove parenthetical suffixes like "(PALAWAN)", "(MARCOS)", "(CAPITAL)", etc.
                # These are common in data but not in config (e.g., "RIZAL (MARCOS) (PALAWAN)" -> "RIZAL")
                # Use optimized single-pass regex instead of while loop to avoid infinite loops on unmatched parens
                location_clean = re.sub(r'\s*\([^()]*(?:\([^()]*(?:\([^()]*\)[^()]*)*\)[^()]*)*\)\s*', ' ', location_clean, flags=re.IGNORECASE)
                # If any opening parenthesis remains (unmatched), just remove it and everything after to be safe
                if '(' in location_clean:
                     location_clean = location_clean.replace('(', ' ')
                # Remove common prefixes
                location_clean = re.sub(r'^(BRGY\.?|BRG\.?|BGY\.?|BARANGAY|BARANGGAY|BARANGGY|MUNICIPALITY OF|MUNICIPALITY)\s+', '', location_clean, flags=re.IGNORECASE).strip()
                
                # Exclude common words that aren't locations
                exclude_words = ['THE', 'A', 'AN', 'OF', 'AND', 'OR', 'CONSTRUCTION', 'PROJECT', 'PHASE', 'SECTION', 'ROAD', 'STREET', 'HIGHWAY']
                if location_clean and location_clean.upper() not in exclude_words and len(location_clean) > 2:
                    # Use location_context_map to disambiguate if location name appears in multiple provinces/cities
                    # e.g., "Matina" could be in Davao City or Iloilo
                    if location_context_map:
                        disambiguated = disambiguate_location(location_clean, text_upper, location_context_map)
                        if disambiguated:
                            prov_city, loc_type = disambiguated
                            # If we found a match, use it to set province and location type
                            result['province'] = prov_city
                            result['municipality_barangay'] = location_clean
                            result['is_city_district'] = (loc_type == 'barangay')
                            # We found a match via context, so we can return early
                            return result
                    
                    # If CITY word OR barangay indicator present, try to match city first
                    if has_city_word or is_barangay_location:
                        # Try beginning substring match for cities
                        for known_city in known_cities:
                            city_upper = known_city.upper()
                            city_base = city_upper.replace(' CITY', '').strip()
                            
                            # Special handling for Davao City: also check if text mentions "Davao City" 
                            # even if province_city_part is "Davao Del Sur"
                            is_davao_city = (city_upper == 'DAVAO CITY' or city_base == 'DAVAO')
                            if is_davao_city and 'DAVAO CITY' in text_upper:
                                # If text mentions "Davao City", treat it as Davao City regardless of province
                                result['province'] = known_city  # Store city name as province for lookup
                                result['municipality_barangay'] = location_clean  # Barangay for city districts
                                result['is_city_district'] = True
                                break
                            
                            # Handle compound city names (e.g., "Taguig–Pateros" should match "TAGUIG CITY")
                            city_variants = [city_upper, city_base]
                            if '–' in known_city or '-' in known_city:
                                # Split compound names
                                parts = re.split(r'[–-]', known_city)
                                city_variants.extend([p.strip().upper() for p in parts if p.strip()])
                            
                            # Beginning substring match: "Q" matches "QUEZON CITY", "CEBU" matches "CEBU CITY"
                            # Also match "TAGUIG" to "Taguig–Pateros"
                            matched = False
                            for variant in city_variants:
                                variant_base = variant.replace(' CITY', '').strip()
                                if (variant.startswith(province_city_part) or 
                                    variant_base.startswith(province_city_part) or
                                    province_city_part.startswith(variant_base.split()[0] if variant_base.split() else '')):
                                    result['province'] = known_city  # Store city name as province for lookup
                                    result['municipality_barangay'] = location_clean  # Barangay for city districts
                                    matched = True
                                    break
                            if matched:
                                break
                    
                    # If no city match (or no CITY word), try province match
                    if not result['province']:
                        # Check if the part_after has a directional modifier
                        part_has_directional = has_directional_modifier(province_city_part)
                        
                        for known_prov in known_provinces:
                            prov_upper = known_prov.upper()
                            prov_base = normalize_province_base(known_prov)
                            known_prov_has_directional = has_directional_modifier(known_prov)
                            
                            # CRITICAL: If part_after has directional modifier, only match exact or more specific
                            # Example: "SOUTHERN LEYTE" should NOT match "LEYTE", only "SOUTHERN LEYTE"
                            # Example: "NORTHERN SAMAR" should NOT match "SAMAR", only "NORTHERN SAMAR"
                            # Example: "ILOILO CITY" should NOT match "ILOILO" province, only "ILOILO CITY"
                            if part_has_directional:
                                # Must be exact match or the known_prov must be more specific
                                if prov_upper == province_city_part:
                                    # Exact match
                                    result['province'] = known_prov
                                    result['municipality_barangay'] = location_clean
                                    break
                                elif known_prov_has_directional and prov_upper.startswith(province_city_part):
                                    # Known province is more specific and starts with our part
                                    result['province'] = known_prov
                                    result['municipality_barangay'] = location_clean
                                    break
                                # Skip if known_prov doesn't have directional but part_after does
                                elif not known_prov_has_directional:
                                    continue
                            
                            # CRITICAL: Prevent substring matches for provinces with same base name
                            # If text says "NORTHERN SAMAR", don't match "SAMAR"
                            # If text says "SOUTHERN LEYTE", don't match "LEYTE"
                            # If text says "ILOILO CITY", don't match "ILOILO" province
                            # If text says "LANAO DEL SUR", don't match "LANAO DEL NORTE"
                            
                            # Check if text contains a more specific version of the province
                            if not part_has_directional and known_prov_has_directional:
                                # Text has base name (e.g., "SAMAR") but known_prov is directional (e.g., "NORTHERN SAMAR")
                                # Check if text actually mentions the directional version
                                prov_base = normalize_province_base(known_prov)
                                if prov_base.upper() == province_city_part.upper():
                                    # Text has base name, but we have a directional province
                                    # Check if text mentions any directional variant
                                    directional_variants = ['NORTHERN', 'SOUTHERN', 'EASTERN', 'WESTERN', 'OCCIDENTAL', 'ORIENTAL', 'DEL NORTE', 'DEL SUR']
                                    text_has_directional = any(dv in text_upper for dv in directional_variants)
                                    if text_has_directional:
                                        # Text mentions a direction, so skip this base match
                                        continue
                            
                            # Also check for city vs province conflicts (e.g., "ILOILO CITY" vs "ILOILO")
                            if 'CITY' in known_prov.upper() and 'CITY' not in province_city_part:
                                # Known province is a city but text doesn't mention "CITY"
                                # Skip unless we have a unique barangay match
                                continue
                            
                            # Check if this province needs strict word boundary matching (substring provinces)
                            prov_base_lower = prov_base.lower()
                            needs_strict_matching = any(base in prov_base_lower for base in self.substring_provinces)
                            
                            # Beginning substring match: "OCCIDENTAL" matches "OCCIDENTAL MINDORO"
                            # Also handle partial matches like "MAGUINDANA" matching "MAGUINDANAO"
                            # But only if no directional modifier conflict
                            matched = False
                            if needs_strict_matching:
                                # Use word boundary matching for substring provinces
                                # e.g., "Samar" should only match "Samar", not "Northern Samar"
                                pattern = r'\b' + re.escape(province_city_part) + r'\b'
                                if re.search(pattern, prov_upper, re.IGNORECASE):
                                    # Check if it's an exact match or the province starts with our part
                                    if prov_upper == province_city_part or prov_upper.startswith(province_city_part):
                                        matched = True
                            else:
                                # Regular substring matching for non-substring provinces
                                if (prov_upper.startswith(province_city_part) or 
                                    (prov_base.startswith(province_city_part) and not part_has_directional) or
                                    (province_city_part.startswith(prov_base.split()[0] if prov_base.split() else '') and not part_has_directional)):
                                    matched = True
                            
                            if matched:
                                result['province'] = known_prov
                                result['municipality_barangay'] = location_clean  # Municipality for province districts
                                break
        
        # Step 4: If no comma pattern found, try direct substring matching in full text
        # This handles cases where province/municipality appear without comma separation
        if not result['province']:
            # Special handling: Check for "Davao City" in text first (even if province is "Davao Del Sur")
            if 'DAVAO CITY' in text_upper:
                # Check if Davao City is in known cities
                for known_city in known_cities:
                    if known_city.upper() == 'DAVAO CITY':
                        result['province'] = known_city
                        result['is_city_district'] = True
                        # Try to extract barangay from text using improved extraction
                        if not result['municipality_barangay']:
                            extracted_barangay = self._extract_barangay_from_text(text)
                            if extracted_barangay:
                                result['municipality_barangay'] = extracted_barangay
                        return result
            
            # Also try to extract barangay if we haven't found one yet (for any city/province)
            if not result['municipality_barangay']:
                extracted_barangay = self._extract_barangay_from_text(text)
                if extracted_barangay:
                    result['municipality_barangay'] = extracted_barangay
            
            # Try to find province by substring match in full text
            # But prioritize exact matches, especially for directional provinces
            for known_prov in known_provinces:
                prov_upper = known_prov.upper()
                prov_base = normalize_province_base(known_prov)
                known_prov_has_directional = has_directional_modifier(known_prov)
                
                # Handle compound province names (e.g., "Taguig–Pateros")
                prov_variants = [prov_upper, prov_base]
                if '–' in known_prov or '-' in known_prov:
                    # Split compound names
                    parts = re.split(r'[–-]', known_prov)
                    prov_variants.extend([p.strip().upper() for p in parts if p.strip()])
                
                # Check each variant
                matched = False
                for variant in prov_variants:
                    variant_base = normalize_province_base(variant)
                    variant_has_directional = has_directional_modifier(variant)
                    
                    # Check if this province needs strict word boundary matching (substring provinces)
                    variant_base_lower = variant_base.lower()
                    needs_strict_matching = any(base in variant_base_lower for base in self.substring_provinces)
                    
                    # Check for exact match first (especially important for directional provinces)
                    if variant in text_upper:
                        # CRITICAL: Check for city vs province conflicts (e.g., "ILOILO CITY" vs "ILOILO")
                        if 'CITY' in known_prov.upper() and 'CITY' not in text_upper:
                            # Known province is a city but text doesn't mention "CITY"
                            # Skip unless we have a unique barangay match (handled elsewhere)
                            continue
                        
                        # Check if there's a more specific match nearby (e.g., "SOUTHERN LEYTE" vs "LEYTE")
                        # If we find "SOUTHERN LEYTE" in text, don't match to just "LEYTE"
                        if variant_has_directional:
                            # This is a directional province - use it
                            result['province'] = known_prov
                            matched = True
                            break
                        else:
                            # For substring provinces, use word boundary matching
                            if needs_strict_matching:
                                pattern = r'\b' + re.escape(variant) + r'\b'
                                if re.search(pattern, text_upper, re.IGNORECASE):
                                    # Check if a more specific version exists in text
                                    directional_pattern = rf'\b(SOUTHERN|NORTHERN|EASTERN|WESTERN|OCCIDENTAL|ORIENTAL|DEL\s+SUR|DEL\s+NORTE)\s+{re.escape(variant)}\b'
                                    if not re.search(directional_pattern, text_upper, re.IGNORECASE):
                                        # No more specific version found, safe to use this
                                        result['province'] = known_prov
                                        matched = True
                                        break
                            else:
                                # Check if a more specific version exists in text
                                directional_pattern = rf'\b(SOUTHERN|NORTHERN|EASTERN|WESTERN|OCCIDENTAL|ORIENTAL|DEL\s+SUR|DEL\s+NORTE)\s+{re.escape(variant)}\b'
                                if not re.search(directional_pattern, text_upper, re.IGNORECASE):
                                    # No more specific version found, safe to use this
                                    result['province'] = known_prov
                                    matched = True
                                    break
                    elif variant_base in text_upper and not variant_has_directional:
                        # CRITICAL: Check for city vs province conflicts
                        if 'CITY' in known_prov.upper() and 'CITY' not in text_upper:
                            # Known province is a city but text doesn't mention "CITY"
                            continue
                        
                        # For substring provinces, use word boundary matching
                        if needs_strict_matching:
                            pattern = r'\b' + re.escape(variant_base) + r'\b'
                            if re.search(pattern, text_upper, re.IGNORECASE):
                                # Only match base if the variant doesn't have directional modifier
                                # This prevents "LEYTE" from matching when "SOUTHERN LEYTE" is in text
                                directional_pattern = rf'\b(SOUTHERN|NORTHERN|EASTERN|WESTERN|OCCIDENTAL|ORIENTAL|DEL\s+SUR|DEL\s+NORTE)\s+{re.escape(variant_base)}\b'
                                if not re.search(directional_pattern, text_upper, re.IGNORECASE):
                                    result['province'] = known_prov
                                    matched = True
                                    break
                        else:
                            # Only match base if the variant doesn't have directional modifier
                            # This prevents "LEYTE" from matching when "SOUTHERN LEYTE" is in text
                            directional_pattern = rf'\b(SOUTHERN|NORTHERN|EASTERN|WESTERN|OCCIDENTAL|ORIENTAL|DEL\s+SUR|DEL\s+NORTE)\s+{re.escape(variant_base)}\b'
                            if not re.search(directional_pattern, text_upper, re.IGNORECASE):
                                result['province'] = known_prov
                                matched = True
                                break
                
                if matched:
                    break
                
                # Special case: Antipolo is in Rizal province
                # If text mentions "RIZAL" and "ANTIPOLO", match to "Antipolo" congressman
                if prov_upper == 'ANTIPOLO' and 'RIZAL' in text_upper and 'ANTIPOLO' in text_upper:
                    result['province'] = known_prov
                    # Extract Antipolo from text if present (e.g., "CITY OF ANTIPOLO")
                    antipolo_match = re.search(r'\b(?:CITY OF\s+)?ANTIPOLO\b', text_upper, re.IGNORECASE)
                    if antipolo_match:
                        # Try to extract barangay if mentioned
                        brgy_match = re.search(r'\b(?:BRGY|BARANGAY)\s+(\w+)', text_upper, re.IGNORECASE)
                        if brgy_match:
                            result['municipality_barangay'] = brgy_match.group(1).strip()
                    break
        
        return result

    def _is_location_unique_in_category(self, location_name: str, location_type: str, dedup_dict: Dict) -> bool:
        """
        Check if a location name is unique within its own category (short-circuit check).
        This allows fast matching for unique barangays/municipalities without cross-category checks.
        location_type: 'province', 'city', 'municipality', 'barangay'
        """
        if not location_name or not dedup_dict:
            return False
        
        location_upper = location_name.upper().strip()
        dedup_info = dedup_dict.get(location_upper, {})
        
        # Check if it appears only once in its specific category
        if location_type == 'province':
            return dedup_info.get('provinces', 0) == 1
        elif location_type == 'city':
            return dedup_info.get('cities', 0) == 1
        elif location_type == 'municipality':
            return dedup_info.get('municipalities', 0) == 1
        elif location_type == 'barangay':
            return dedup_info.get('barangays', 0) == 1
        
        return False
    
    def _is_location_unique(self, location_name: str, location_type: str, dedup_dict: Dict) -> bool:
        """
        Check if a location name is unique across ALL categories (barangay, municipality, city, province, region).
        If a name appears in multiple categories, it's not unique and requires additional context.
        location_type: 'province', 'city', 'municipality', 'barangay'
        """
        if not location_name or not dedup_dict:
            return False
        
        location_upper = location_name.upper().strip()
        dedup_info = dedup_dict.get(location_upper, {})
        
        # First, check if it's unique within its own category (short-circuit for smallest units)
        if location_type in ['barangay', 'municipality']:
            if self._is_location_unique_in_category(location_name, location_type, dedup_dict):
                # Check if it also appears in other categories
                categories_with_name = 0
                if dedup_info.get('provinces', 0) > 0:
                    categories_with_name += 1
                if dedup_info.get('cities', 0) > 0:
                    categories_with_name += 1
                if dedup_info.get('municipalities', 0) > 0:
                    categories_with_name += 1
                if dedup_info.get('barangays', 0) > 0:
                    categories_with_name += 1
                if dedup_info.get('regions', 0) > 0:
                    categories_with_name += 1
                
                # If it only appears in one category, it's unique
                return categories_with_name == 1
        
        # For provinces and cities, check across all categories
        categories_with_name = 0
        if dedup_info.get('provinces', 0) > 0:
            categories_with_name += 1
        if dedup_info.get('cities', 0) > 0:
            categories_with_name += 1
        if dedup_info.get('municipalities', 0) > 0:
            categories_with_name += 1
        if dedup_info.get('barangays', 0) > 0:
            categories_with_name += 1
        if dedup_info.get('regions', 0) > 0:
            categories_with_name += 1
        
        # Name is unique only if it appears in exactly ONE category
        if categories_with_name != 1:
            return False
        
        # Now check if it appears only once in that specific category
        if location_type == 'province':
            return dedup_info.get('provinces', 0) == 1
        elif location_type == 'city':
            return dedup_info.get('cities', 0) == 1
        elif location_type == 'municipality':
            return dedup_info.get('municipalities', 0) == 1
        elif location_type == 'barangay':
            return dedup_info.get('barangays', 0) == 1
        
        return False
    
    def _get_location_categories(self, location_name: str, dedup_dict: Dict) -> List[str]:
        """
        Get all categories where a location name appears.
        Returns list of categories: ['province', 'city', 'municipality', 'barangay', 'region']
        """
        if not location_name or not dedup_dict:
            return []
        
        location_upper = location_name.upper().strip()
        dedup_info = dedup_dict.get(location_upper, {})
        
        categories = []
        if dedup_info.get('provinces', 0) > 0:
            categories.append('province')
        if dedup_info.get('cities', 0) > 0:
            categories.append('city')
        if dedup_info.get('municipalities', 0) > 0:
            categories.append('municipality')
        if dedup_info.get('barangays', 0) > 0:
            categories.append('barangay')
        if dedup_info.get('regions', 0) > 0:
            categories.append('region')
        
        return categories
    
    def _requires_additional_context(self, location_name: str, dedup_dict: Dict) -> bool:
        """
        Check if a location name requires additional context because it appears in multiple categories.
        Returns True if name appears in 2+ categories (e.g., both barangay and municipality).
        """
        categories = self._get_location_categories(location_name, dedup_dict)
        return len(categories) > 1
    
    def _get_location_variants(self, location_name: str, location_type: str, dedup_dict: Dict) -> List[str]:
        """
        Get all variants of a location name (e.g., "Samar" -> ["SAMAR", "NORTHERN SAMAR", "EASTERN SAMAR"]).
        location_type: 'province', 'city', 'municipality', 'barangay'
        """
        if not location_name or not dedup_dict:
            return []
        
        location_upper = location_name.upper().strip()
        dedup_info = dedup_dict.get(location_upper, {})
        
        if location_type == 'province':
            return dedup_info.get('province_variants', [])
        elif location_type == 'city':
            return dedup_info.get('city_variants', [])
        elif location_type == 'municipality':
            return dedup_info.get('municipality_variants', [])
        elif location_type == 'barangay':
            return dedup_info.get('barangay_variants', [])
        
        return []
    
    def _find_congressman_by_district(self, province: str, municipality_barangay: str, project_year: Optional[int], 
                                     district_lookup: Dict, congressmen_data: Dict) -> Optional[tuple]:
        """
        O(1) lookup for congressman by district.
        Returns: (congressman_name, match_score) or None
        
        Matching strategy (strictest to loosest):
        1. Exact match: (province, municipality/barangay) - score 100
        2. Province-only match: (province, '') - score 10
        3. Normalized match: normalized province/location names - score 5
        4. Misspelling correction: common misspellings - score 3
        
        Validates that the matched congressman's province actually matches the requested province.
        
        Special handling:
        - Compound province names (e.g., "Taguig–Pateros") are split and tried separately
        - City districts in provinces (e.g., "Antipolo" in "Rizal") are matched by checking municipality/city mentions
        """
        if not province:
            return None
            
        province_upper = province.upper().strip()
        
        # CRITICAL FIX: Prevent "METRO MANILA" from matching "MANILA"
        # Also prevent "MANILA" from matching "METRO MANILA" projects
        if province_upper == 'METRO MANILA':
            return None
        # If province is "MANILA" (not Metro Manila), we should only match Manila districts
        # This prevents Metro Manila projects from matching to Manila congressmen
        
        # Special handling for Davao City: if province is "Davao Del Sur" but we're looking for Davao City,
        # also try "Davao City" as a variant
        # CRITICAL: Only allow Davao variants if the project is actually in Davao region
        # This prevents non-Davao projects from matching Paolo Duterte
        province_variants_for_davao = []
        # Only add variants if the province is actually a Davao variant
        if province_upper in ['DAVAO DEL SUR', 'DAVAO CITY', 'DAVAO DEL NORTE', 'DAVAO ORIENTAL', 'DAVAO DE ORO']:
            if province_upper == 'DAVAO DEL SUR':
                province_variants_for_davao.append('DAVAO CITY')
            elif province_upper == 'DAVAO CITY':
                province_variants_for_davao.append('DAVAO DEL SUR')
        
        location_upper = (municipality_barangay or '').upper().strip()
        
        # Get location dictionaries for normalization and fuzzy matching
        location_dicts = getattr(self, 'location_dicts', {})
        dedup_dict = location_dicts.get('dedup_dict', {})
        normalized_provinces = location_dicts.get('normalized_provinces', {})
        normalized_municipalities = location_dicts.get('normalized_municipalities', {})
        normalized_barangays = location_dicts.get('normalized_barangays', {})
        all_provinces = list(location_dicts.get('provinces', set()))
        all_municipalities = list(location_dicts.get('municipalities', set()))
        all_barangays = list(location_dicts.get('barangays', set()))
        
        # Check if municipality/barangay is unique (short-circuit for smallest units)
        # For barangays and municipalities, first check if unique within category, then check cross-category
        is_location_unique = False
        location_type = None
        requires_context = False
        
        if location_upper:
            # First, try to determine if it's a barangay or municipality based on context
            # Check if it's a unique barangay (short-circuit)
            if self._is_location_unique_in_category(location_upper, 'barangay', dedup_dict):
                # Check if it also appears in other categories
                location_categories = self._get_location_categories(location_upper, dedup_dict)
                if len(location_categories) == 1:
                    # Only appears as barangay - unique!
                    is_location_unique = True
                    location_type = 'barangay'
                else:
                    # Appears in multiple categories - requires context
                    requires_context = True
            # Check if it's a unique municipality (short-circuit)
            elif self._is_location_unique_in_category(location_upper, 'municipality', dedup_dict):
                # Check if it also appears in other categories
                location_categories = self._get_location_categories(location_upper, dedup_dict)
                if len(location_categories) == 1:
                    # Only appears as municipality - unique!
                    is_location_unique = True
                    location_type = 'municipality'
                else:
                    # Appears in multiple categories - requires context
                    requires_context = True
            else:
                # Check what categories this location name appears in
                location_categories = self._get_location_categories(location_upper, dedup_dict)
                
                if len(location_categories) == 1:
                    # Name appears in only one category - check if it's unique in that category
                    category = location_categories[0]
                    if self._is_location_unique(location_upper, category, dedup_dict):
                        is_location_unique = True
                        location_type = category
                elif len(location_categories) > 1:
                    # Name appears in multiple categories - requires additional context
                    requires_context = True
        
        # Handle compound province names (e.g., "Taguig–Pateros" -> try both "Taguig" and "Pateros")
        province_variants = [province_upper]
        if '–' in province_upper or '-' in province_upper:
            # Split by en-dash or hyphen
            parts = re.split(r'[–-]', province_upper)
            province_variants.extend([p.strip() for p in parts if p.strip()])
        
        # Add Davao City variants if applicable
        if province_variants_for_davao:
            province_variants.extend(province_variants_for_davao)
        
        # Special handling for city districts where projects have "CITY" suffix but config doesn't
        # Example: Project has "Marikina City" but config has "Marikina"
        # Use deduplication dictionary to dynamically determine if city name is unique
        province_variants_for_cities = []
        
        # Check if province has "CITY" suffix
        if province_upper.endswith(' CITY'):
            city_base = province_upper[:-5].strip()  # Remove " CITY" suffix
            # Check if city is unique using deduplication dictionary
            if self._is_location_unique(city_base, 'city', dedup_dict):
                # Project has "Marikina City", also try base name "Marikina"
                province_variants_for_cities.append(city_base)
        else:
            # Project has base name (e.g., "Marikina"), check if it's a unique city
            if self._is_location_unique(province_upper, 'city', dedup_dict):
                # Project has "Marikina", also try "Marikina City"
                province_variants_for_cities.append(f"{province_upper} CITY")
        
        # Add city name variants if applicable
        if province_variants_for_cities:
            province_variants.extend(province_variants_for_cities)
        
        # CRITICAL: For provinces with directional variants (e.g., "Samar" has "Northern Samar", "Eastern Samar")
        # Get all variants and exclude directional ones when matching base name
        # Example: If querying "Samar", exclude "Northern Samar" and "Eastern Samar" from matches
        province_base_name = re.sub(r'\s*(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\s*$', '', province_upper).strip()
        if province_base_name != province_upper:
            # This is a directional province (e.g., "Northern Samar")
            # Get all variants and exclude other directional variants
            all_variants = self._get_location_variants(province_base_name, 'province', dedup_dict)
            # Only use the exact variant, not other directional variants
            province_variants = [province_upper]  # Reset to only use exact match
        elif province_base_name == province_upper:
            # This is a base province name (e.g., "Samar")
            # Get all variants to know what to exclude
            all_variants = self._get_location_variants(province_upper, 'province', dedup_dict)
            # If there are multiple variants (e.g., Samar, Northern Samar, Eastern Samar)
            # We should only match the exact base name, not the directional variants
            if len(all_variants) > 1:
                # Multiple variants exist - only use base name, exclude directional variants
                province_variants = [province_upper]
        
        # STRICTEST: Try exact match first
        candidates = []
        match_score = 0
        
        # SHORT-CIRCUIT: If location is unique (barangay or municipality), we can match directly
        # without needing province context (for smallest units)
        if is_location_unique and location_type in ['barangay', 'municipality']:
            # Try to match by location alone (it's unique, so no ambiguity)
            # But we still need province for the lookup key, so try all province variants
            for prov_variant in province_variants:
                variant_candidates = district_lookup.get((prov_variant, location_upper), [])
                if variant_candidates:
                    candidates.extend(variant_candidates)
                    match_score = 100
                    break
        
        # If no short-circuit match, proceed with normal matching
        if not candidates:
            for prov_variant in province_variants:
                # 1. Exact match: (province, municipality/barangay) - score 100
                variant_candidates = district_lookup.get((prov_variant, location_upper), [])
                if variant_candidates:
                    candidates.extend(variant_candidates)
                    match_score = 100
                    break
                
                # 2. Province-only match: (province, '') - score 10
                # CRITICAL: For city districts, only allow province-only match if:
                # - No specific barangay/municipality was provided (location_upper is empty), OR
                # - The city name is explicitly mentioned with "CITY" word in the text
                # This prevents broad matches for city districts like Manila
                if not variant_candidates:
                    # Check if this is a city district and we need stricter matching
                    province_only_candidates = district_lookup.get((prov_variant, ''), [])
                    if province_only_candidates:
                        # Filter candidates to only city districts if we have location
                        # For province districts, allow province-only match
                        # For city districts, be more strict
                        filtered_candidates = []
                        for cm_name, cm_data in province_only_candidates:
                            is_city_district = cm_data.get('is_city_district', False)
                            if not is_city_district:
                                # Province district - allow province-only match
                                filtered_candidates.append((cm_name, cm_data))
                            elif not location_upper:
                                # City district but no location specified - allow match
                                filtered_candidates.append((cm_name, cm_data))
                            # If city district AND location specified, skip province-only match
                            # (require specific barangay match instead)
                        
                        if filtered_candidates:
                            candidates.extend(filtered_candidates)
                            match_score = 10
                            break
        
        # 3. NORMALIZED MATCH (if no exact match found) - score 5
        if not candidates:
            normalized_prov = self._normalize_location_name(province_upper)
            normalized_loc = self._normalize_location_name(location_upper) if location_upper else ''
            
            # Try normalized province lookup
            if normalized_prov in normalized_provinces:
                correct_prov = normalized_provinces[normalized_prov]
                # Try with normalized location
                if normalized_loc:
                    if normalized_loc in normalized_municipalities:
                        correct_loc = normalized_municipalities[normalized_loc]
                        candidates = district_lookup.get((correct_prov, correct_loc), [])
                    elif normalized_loc in normalized_barangays:
                        correct_loc = normalized_barangays[normalized_loc]
                        candidates = district_lookup.get((correct_prov, correct_loc), [])
                
                # If still no match, try province-only
                if not candidates:
                    candidates = district_lookup.get((correct_prov, ''), [])
                
                if candidates:
                    match_score = 5
        
        # 4. FUZZY MATCHING (last resort) - score 3
        # Use Levenshtein distance to find closest match
        if not candidates:
            # Try fuzzy matching for province
            closest_prov = self._find_closest_match(province_upper, all_provinces, max_distance=2)
            if closest_prov:
                closest_prov_upper = closest_prov.upper().strip()
                # Try with location if available
                if location_upper:
                    # Try fuzzy match for location
                    closest_loc = None
                    # Determine if it's a municipality or barangay based on district type
                    # Try municipalities first
                    closest_loc = self._find_closest_match(location_upper, all_municipalities, max_distance=2)
                    if not closest_loc:
                        closest_loc = self._find_closest_match(location_upper, all_barangays, max_distance=2)
                    
                    if closest_loc:
                        candidates = district_lookup.get((closest_prov_upper, closest_loc.upper().strip()), [])
                
                # If still no match, try province-only
                if not candidates:
                    candidates = district_lookup.get((closest_prov_upper, ''), [])
                
                if candidates:
                    match_score = 3
        
        # CRITICAL: Filter out party-list congressmen from district matches
        # Party-list congressmen don't have districts, so they should never match via district
        if candidates:
            filtered_candidates = []
            for cm_name, cm_data in candidates:
                is_partylist = cm_data.get('is_partylist', False)
                if not is_partylist:
                    filtered_candidates.append((cm_name, cm_data))
            candidates = filtered_candidates
        
        # Special handling: For city districts where city name is in province config but actual province is different
        # Example: Antipolo (city) is in Rizal province
        # If we're looking for "Antipolo" but projects have province "RIZAL" and municipality mentions "ANTIPOLO"
        if not candidates and location_upper:
            # Check if any congressman has this province as a city district
            for cm_name, cm_data in congressmen_data.items():
                # CRITICAL: Skip party-list congressmen - they don't have districts
                is_partylist = cm_data.get('is_partylist', False)
                if is_partylist:
                    continue
                
                cm_provinces = cm_data.get('provinces', [])
                is_city_district = cm_data.get('is_city_district', False)
                
                # Check if this congressman's province matches our search (as a city)
                for cm_province in cm_provinces:
                    cm_prov_upper = cm_province.upper().strip()
                    # If congressman's province is "Antipolo" and location mentions "Antipolo"
                    # and it's a city district, we should match it even if project province is "Rizal"
                    if (cm_prov_upper == province_upper or 
                        (province_upper in cm_prov_upper or cm_prov_upper in province_upper)):
                        if is_city_district and cm_prov_upper in location_upper:
                            # This is a city district match - add to candidates
                            candidates.append((cm_name, cm_data))
                            break
        
        # Filter by term if project_year is provided
        # Prioritize candidates whose terms match, but allow fallback if no matches
        term_matched_candidates = []
        no_term_candidates = []
        term_mismatch_candidates = []
        
        if project_year is not None and candidates:
            for cm_name, cm_data in candidates:
                terms = cm_data.get('terms', [])
                
                # Parse terms if they're stored as JSON string
                if isinstance(terms, str):
                    try:
                        terms = json.loads(terms)
                    except (json.JSONDecodeError, TypeError):
                        terms = []
                
                if not terms:
                    # No terms defined, include as fallback
                    no_term_candidates.append((cm_name, cm_data))
                else:
                    # Check if project_year falls within any term
                    matched = False
                    best_match_score = -999
                    best_match_candidate = None
                    
                    for term in terms:
                        # Handle both dict and string formats
                        if isinstance(term, str):
                            try:
                                term = json.loads(term)
                            except (json.JSONDecodeError, TypeError):
                                continue
                        
                        if not isinstance(term, dict):
                            continue
                            
                        term_start = term.get('start')
                        term_end = term.get('end')
                        
                        if term_start is not None and term_end is not None:
                            # CRITICAL: Only match if project_year is within term range
                            # Don't allow future terms to match past projects
                            if term_start <= project_year <= term_end:
                                # Score: prefer exact matches, then closer to term start
                                # Long terms are OK - they should match more projects
                                term_length = term_end - term_start + 1
                                distance_from_start = abs(project_year - term_start)
                                
                                # Score: prefer closer matches to term start, slight preference for shorter terms
                                score = 100 - (term_length * 1) - distance_from_start
                                
                                if score > best_match_score:
                                    best_match_score = score
                                    best_match_candidate = (cm_name, cm_data, score)
                                matched = True
                    
                    if matched and best_match_candidate:
                        # Store with score for sorting
                        term_matched_candidates.append(best_match_candidate)
                    elif not matched:
                        # Term doesn't match, but keep as fallback
                        term_mismatch_candidates.append((cm_name, cm_data))
            
            # Prioritize: term matches > no terms > term mismatches
            if term_matched_candidates:
                # Sort by best match score (highest first), then take the best one
                term_matched_candidates.sort(key=lambda x: x[2] if len(x) > 2 else 0, reverse=True)
                # Extract just (name, data) tuples
                candidates = [(name, data) for name, data, *rest in term_matched_candidates]
            elif no_term_candidates:
                candidates = no_term_candidates
            else:
                # Fallback to term mismatches if no other options
                candidates = term_mismatch_candidates
        
        if candidates:
            # CRITICAL: Validate that the matched congressman's province actually matches
            # This prevents incorrect matches (e.g., Tarlac projects matching to Davao City)
            # But allow compound names and city-in-province cases
            validated_candidates = []
            for cm_name, cm_data in candidates:
                cm_provinces = cm_data.get('provinces', [])
                is_city_district = cm_data.get('is_city_district', False)
                
                # Check if any of the congressman's provinces match the requested province
                province_matches = False
                for cm_province in cm_provinces:
                    cm_prov_upper = cm_province.upper().strip()
                    
                    # Exact match
                    if cm_prov_upper == province_upper:
                        province_matches = True
                        break
                    
                    # CRITICAL: Prevent substring matches that cause false positives
                    # "MANILA" should NOT match "METRO MANILA"
                    # "DAVAO" should NOT match "DAVAO CITY" or "DAVAO DEL SUR" unless explicitly allowed
                    # Only allow compound name matches with word boundaries
                    # Special case: Davao City / Davao Del Sur variants (only for Paolo Duterte)
                    if (cm_prov_upper in ['DAVAO CITY', 'DAVAO DEL SUR'] and 
                        province_upper in ['DAVAO CITY', 'DAVAO DEL SUR']):
                        # Both are Davao variants - allow match
                        province_matches = True
                        break
                    
                    # Special case: City districts where config has city name without "CITY" suffix
                    # Example: Config has "Marikina" but project has "Marikina City"
                    # Use deduplication dictionary to dynamically determine if city name is unique
                    if is_city_district:
                        location_dicts = getattr(self, 'location_dicts', {})
                        dedup_dict = location_dicts.get('dedup_dict', {})
                        
                        # Check if city name is unique
                        city_base = cm_prov_upper
                        city_with_suffix = f"{city_base} CITY"
                        
                        # Check deduplication counts
                        dedup_info = dedup_dict.get(city_base, {})
                        city_count = dedup_info.get('cities', 0)
                        province_count = dedup_info.get('provinces', 0)
                        municipality_count = dedup_info.get('municipalities', 0)
                        
                        # City is unique if: exactly 1 city, 0 provinces, 0 municipalities with same base name
                        is_unique_city = (city_count == 1 and province_count == 0 and municipality_count == 0)
                        
                        if is_unique_city:
                            # Allow "Marikina" to match "Marikina City"
                            if province_upper == city_with_suffix:
                                province_matches = True
                                break
                            # Also allow reverse: "Marikina City" matches "Marikina"
                            if province_upper == city_base and cm_prov_upper == city_with_suffix:
                                province_matches = True
                                break
                    
                    # CRITICAL: Prevent "MANILA" from matching "METRO MANILA"
                    if province_upper == 'MANILA' and cm_prov_upper == 'METRO MANILA':
                        # Don't match - Manila is not Metro Manila
                        continue
                    if province_upper == 'METRO MANILA' and cm_prov_upper == 'MANILA':
                        # Don't match - Metro Manila is not just Manila
                        continue
                    
                    # Compound name match with word boundaries (e.g., "Taguig" matches "Taguig–Pateros")
                    # Use word boundary to prevent partial matches
                    if re.search(r'\b' + re.escape(province_upper) + r'\b', cm_prov_upper) or \
                       re.search(r'\b' + re.escape(cm_prov_upper) + r'\b', province_upper):
                        province_matches = True
                        break
                    
                    # For city districts: if congressman's province is a city name and location mentions it
                    # and project province might be the parent province (e.g., Antipolo in Rizal)
                    if is_city_district and cm_prov_upper in location_upper:
                        # Special case: Antipolo is in Rizal
                        if (cm_prov_upper == 'ANTIPOLO' and 'RIZAL' in province_upper) or \
                           (cm_prov_upper == 'ANTIPOLO' and province_upper == 'RIZAL'):
                            province_matches = True
                            break
                
                # CRITICAL FIX: Strict location check for Eulogio Rodriguez
                # He is the congressman for Catanduanes, but "E. Rodriguez" is a common street name in QC/Rizal
                # Prevent false positives by ensuring the project is actually in Catanduanes
                if province_matches and 'RODRIGUEZ' in cm_name.upper() and 'EULOGIO' in cm_name.upper():
                    # Check if project province is strictly Catanduanes
                    if 'CATANDUANES' not in province_upper:
                        # Reject match if not in Catanduanes
                        continue

                if province_matches:
                    validated_candidates.append((cm_name, cm_data))
            
            if validated_candidates:
                # If project_year is provided and multiple candidates match, prioritize the one whose term best matches
                if project_year is not None and len(validated_candidates) > 1:
                    # Score each candidate based on how well their term matches the project year
                    best_candidate = None
                    best_score = -1
                    
                    for cm_name, cm_data in validated_candidates:
                        terms = cm_data.get('terms', [])
                        if terms:
                            # Calculate how well the term matches (prefer exact matches, then closest)
                            for term in terms:
                                term_start = term.get('start')
                                term_end = term.get('end')
                                if term_start is not None and term_end is not None:
                                    if term_start <= project_year <= term_end:
                                        # Exact match - calculate score based on how centered the year is in the term
                                        term_length = term_end - term_start + 1
                                        year_position = project_year - term_start
                                        # Score: prefer terms where the year is in the middle (higher score)
                                        # But also prefer shorter terms (more specific)
                                        score = 1000 - abs(year_position - term_length / 2) + (100 / term_length)
                                        if score > best_score:
                                            best_score = score
                                            best_candidate = (cm_name, cm_data)
                                        break
                    
                    if best_candidate:
                        return (best_candidate[0], match_score)
                
                # Return the first validated match with the appropriate score
                return (validated_candidates[0][0], match_score)
        
        return None

    def _find_congressman_by_contractor(self, contractor_name: str, contractor_lookup: Dict, 
                                        contractor_inverted_index: Dict, congressmen_data: Dict) -> Optional[tuple]:
        """
        O(1) lookup for congressman by contractor using inverted index.
        Returns: (congressman_name, match_score) or None
        """
        if not contractor_name:
            return None
        
        contractor_upper = contractor_name.upper().strip()
        normalized = re.sub(r'[^A-Z0-9]+', ' ', contractor_upper).strip()
        
        # Try exact match
        candidates = contractor_lookup.get(contractor_upper, [])
        
        # Try normalized match
        if not candidates:
            candidates = contractor_lookup.get(normalized, [])
        
        # Try inverted index lookup for partial matches
        if not candidates:
            # Tokenize contractor name
            tokens = re.split(r'[^A-Z0-9]+', contractor_upper)
            candidate_keys = set()
            
            # Common words to exclude from query (must match exclusion list in _build_lookup_dictionaries)
            COMMON_TOKENS = {'CONSTRUCTION', 'INC', 'CORP', 'INCORPORATED', 'CORPORATION', 'AND', 'THE', 'OF', 'COMPANY', 'CO', 'LTD', 'LIMITED', 'TRADING', 'ENTERPRISES', 'SUPPLY', 'SERVICES', 'BUILDERS', 'DEVELOPMENT', 'ENGINEERING'}
            
            # Collect candidate keys from inverted index
            valid_tokens = [t for t in tokens if len(t) >= 3 and t not in COMMON_TOKENS]
            
            if valid_tokens:
                # Find keys that contain ANY of the valid tokens
                # We could use intersection (ALL tokens) for stricter matching, but union (ANY) is safer for now
                # given we will verify with stricter logic below
                for token in valid_tokens:
                    if token in contractor_inverted_index:
                        candidate_keys.update(contractor_inverted_index[token])
            
            # If we have candidates from the index, check them
            if candidate_keys:
                # Common patterns allowed: CONSTRUCTION, INC, CORP
                COMMON_PATTERNS = {'CONSTRUCTION', 'INC', 'CORP', 'INCORPORATED', 'CORPORATION'}
                
                for key in candidate_keys:
                    cm_list = contractor_lookup[key]
                    
                    # Check if any congressman in the list is party-list (needs strict matching)
                    has_partylist = any(cm_data.get('is_partylist', False) for _, cm_data in cm_list)
                    
                    # Normalize both key (pattern) and contractor for comparison
                    pattern_normalized = re.sub(r'[^A-Z0-9]+', ' ', key).strip()
                    contractor_normalized = re.sub(r'[^A-Z0-9]+', ' ', contractor_upper).strip()
                    
                    # Split into words
                    pattern_words = pattern_normalized.split()
                    contractor_words = contractor_normalized.split()
                    
                    # Separate proper names (non-common patterns) from common patterns
                    pattern_proper_names = [w for w in pattern_words if w not in COMMON_PATTERNS and len(w) >= 3]
                    pattern_common = [w for w in pattern_words if w in COMMON_PATTERNS]
                    contractor_proper_names = [w for w in contractor_words if w not in COMMON_PATTERNS and len(w) >= 3]
                    contractor_common = [w for w in contractor_words if w in COMMON_PATTERNS]
                    
                    # CRITICAL: For party-list, require ALL proper names to match exactly
                    if has_partylist:
                        if not pattern_proper_names:
                            continue
                        
                        # ALL proper names from pattern must appear as exact words in contractor
                        all_proper_names_match = all(
                            any(pn == cn for cn in contractor_proper_names) 
                            for pn in pattern_proper_names
                        )
                        
                        if all_proper_names_match:
                            if pattern_common:
                                common_match = any(pc in contractor_common for pc in pattern_common)
                                if common_match:
                                    candidates.extend(cm_list)
                            else:
                                candidates.extend(cm_list)
                    else:
                        # For district congressmen, slightly looser matching (but still strict on proper names)
                        if not pattern_proper_names:
                            continue
                            
                        # At least one proper name must match
                        # CRITICAL FIX: Use 'all' instead of 'any' to prevent broad matching
                        # e.g., "J. RODRIGUEZ" should NOT match "EULOGIO RODRIGUEZ" just because of "RODRIGUEZ"
                        proper_name_match = all(
                            any(pn == cn for cn in contractor_proper_names)
                            for pn in pattern_proper_names
                        )
                        
                        if proper_name_match:
                             # Additional check: If the pattern is short (1-2 words), ensure the contractor isn't significantly longer
                             # This prevents "RODRIGUEZ" from matching "EULOGIO RODRIGUEZ" (1 vs 2 proper names)
                             if len(pattern_proper_names) <= 2:
                                 # Allow at most 1 extra proper name in contractor (e.g. middle initial)
                                 # But for "EULOGIO RODRIGUEZ" vs "RODRIGUEZ", that's 1 extra.
                                 # Maybe strict equality for single-word patterns?
                                 if len(pattern_proper_names) == 1 and len(contractor_proper_names) > 1:
                                     # If pattern is just "RODRIGUEZ", don't match "EULOGIO RODRIGUEZ"
                                     # But allow "RODRIGUEZ CONSTRUCTION" (where CONSTRUCTION is common)
                                     # contractor_proper_names only contains non-common words.
                                     continue
                                 
                                 # For 2 words, allow max 1 extra (e.g. "JUAN DELA CRUZ" vs "JUAN A. DELA CRUZ")
                                 if len(contractor_proper_names) > len(pattern_proper_names) + 1:
                                     continue

                             candidates.extend(cm_list)
        
        if candidates:
            # Return the first match (highest priority)
            # Sort by length of contractor pattern (prefer longer/more specific matches)
            # But since we don't have the pattern here easily for all candidates, just take the first one
            # In a real scenario, we might want to score them.
            return candidates[0][0], 100  # Return name and score
            
        # Check exclusions
        # The original code had a loop here, but the instruction implies a direct return if candidates are found
        # and then the exclusion logic. Let's re-integrate the exclusion logic for the found candidates.
        
        # If candidates were found by any method (exact, normalized, inverted index), apply exclusions
        if candidates:
            for cm_name, cm_data in candidates:
                contractor_exclusions = cm_data.get('contractor_exclusions', {})
                excluded = False
                for base, exclusions in contractor_exclusions.items():
                    if base in contractor_upper:
                        for exclusion_value in exclusions:
                            if exclusion_value in contractor_upper:
                                excluded = True
                                break
                    if excluded:
                        break
                
                if not excluded:
                    return (cm_name, 50)
        
        return None

    def _display_progress_summary(self, source_name: str = ""):
        """Display progress summary every 1000 projects"""
        counters = self.progress_counters
        if counters['total_processed'] % 1000 == 0 and counters['total_processed'] > 0:
            print(f"\n📊 Progress Summary ({counters['total_processed']} projects processed{(' - ' + source_name) if source_name else ''}):")
            print(f"   ✅ Districts matched: {counters['districts_matched']}")
            print(f"      - City districts: {counters['city_districts']}")
            print(f"      - Province districts: {counters['province_districts']}")
            print(f"   📍 Location matches:")
            print(f"      - Municipalities: {counters['municipality_matched']}")
            print(f"      - Barangays: {counters['barangay_matched']}")
            print(f"   👷 Contractors matched: {counters['contractors_matched']}")
            print(f"   👤 Unique congressmen: {len(counters['congressmen_matched'])}")
            print(f"   ❌ Unmatched: {counters['unmatched']}")
            print()



    def load_projects_from_parquet(self, parquet_path: Path, source_name: str = None) -> List[Dict]:
        """Load projects from a Parquet file using DuckDB
        
        If source_name is provided, filters by source column (for integrated files).
        Otherwise, loads all projects and adds _source column.
        """
        if not parquet_path.exists():
            print(f"⚠️  Parquet file not found: {parquet_path}")
            return []
        
        try:
            if source_name:
                # Filter by source column for integrated files
                # Try multiple possible source column names and values
                source_escaped = source_name.replace("'", "''")
                # Try exact match first, then case-insensitive
                queries = [
                    f"SELECT * FROM \"{parquet_path}\" WHERE source = '{source_escaped}'",
                    f"SELECT * FROM \"{parquet_path}\" WHERE UPPER(source) = UPPER('{source_escaped}')",
                    f"SELECT * FROM \"{parquet_path}\" WHERE _source = '{source_escaped}'",
                    f"SELECT * FROM \"{parquet_path}\" WHERE UPPER(_source) = UPPER('{source_escaped}')",
                ]
                result = []
                for query in queries:
                    try:
                        result = self.duckdb_conn.execute(query).fetchall()
                        if result:
                            break
                    except:
                        continue
                if not result:
                    # If no results, try loading all and filtering in Python
                    query = f'SELECT * FROM "{parquet_path}"'
                    all_results = self.duckdb_conn.execute(query).fetchall()
                    all_columns = [desc[0] for desc in self.duckdb_conn.description]
                    source_col_idx = None
                    for idx, col in enumerate(all_columns):
                        if col.lower() in ('source', '_source'):
                            source_col_idx = idx
                            break
                    if source_col_idx is not None:
                        result = [row for row in all_results if str(row[source_col_idx] or '').upper() == source_name.upper()]
            else:
                # Load all projects
                query = f'SELECT * FROM "{parquet_path}"'
                result = self.duckdb_conn.execute(query).fetchall()
            
            columns = [desc[0] for desc in self.duckdb_conn.description]
            
            projects = []
            for row in result:
                project_dict = dict(zip(columns, row))
                # Only add _source if it doesn't already exist (for integrated files)
                if '_source' not in project_dict and 'source' in project_dict:
                    project_dict['_source'] = project_dict.get('source', source_name)
                elif source_name and '_source' not in project_dict:
                    project_dict['_source'] = source_name
                projects.append(project_dict)
            
            return projects
        except Exception as e:
            print(f"⚠️  Error loading from Parquet: {e}")
            return []
    
    def _filter_projects_by_source(self, projects: List[Dict], source_name: str) -> List[Dict]:
        """Filter projects by source name from in-memory data"""
        if not projects:
            return []
        
        # Handle multiple source name variations
        source_variations = {
            'SSP': ['SSP', 'FLOOD'],
            'Flood': ['SSP', 'FLOOD'],
            'DIME': ['DIME'],
            'PhilGEPS': ['PHILGEPS'],
            'Infrawatch': ['INFRAWATCH', 'MICROSITE'],
            'Microsite': ['INFRAWATCH', 'MICROSITE'],
        }
        
        valid_sources = source_variations.get(source_name, [source_name.upper()])
        
        filtered = []
        for project in projects:
            source = (project.get('_source') or project.get('source') or '').upper()
            if source in valid_sources:
                filtered.append(project)
        
        return filtered

    async def process_projects(self, congressmen_data: Dict, districts_data: Dict, 
                              district_lookup_dict: Dict, contractor_lookup_dict: Dict,
                              contractor_inverted_index: Dict) -> List[Dict]:
        """Process projects from integrated Parquet file using O(1) lookup dictionaries"""
        all_projects = []
        
        # Pre-calculate location data ONCE for all chunks
        print("🌍 Pre-calculating location data for optimized matching...")
        known_provinces_set, known_cities_set = self._extract_provinces_and_cities_from_data(congressmen_data, district_lookup_dict)
        known_provinces = sorted(list(known_provinces_set))
        known_cities = sorted(list(known_cities_set))
        location_context_map = getattr(self, 'location_dicts', {}).get('location_context_map', None) if hasattr(self, 'location_dicts') else None
        print(f"✅ Location data ready: {len(known_provinces)} provinces, {len(known_cities)} cities")

        # Check if classified file exists (highest priority) - BUT skip if force_reclassify is True
        use_classified = CLASSIFIED_PARQUET.exists() and not self.force_reclassify
        # Check if integrated file exists
        use_integrated = INTEGRATED_PARQUET.exists()
        
        if use_classified:
            print(f"📊 Using CLASSIFIED Parquet file: {CLASSIFIED_PARQUET}")
            print("💾 Loading ALL classified projects into memory...")
            
            # Load ALL data into memory ONCE
            all_projects_data = self.load_projects_from_parquet(CLASSIFIED_PARQUET, source_name=None)
            print(f"✅ Loaded {len(all_projects_data)} classified projects into memory")
            
            # Process each source type from the in-memory data
            sources = [
                ("SSP", self._process_flood_chunk),
                ("DIME", self._process_dime_chunk),
                ("PhilGEPS", self._process_philgeps_chunk),
                ("Microsite", self._process_infrawatch_chunk),
            ]
            
            for source_name, process_func in sources:
                try:
                    # Filter from in-memory data
                    projects = self._filter_projects_by_source(all_projects_data, source_name)
                    if projects:
                        print(f"📊 Filtered {len(projects)} {source_name} projects from memory")
                        print(f"🔍 About to create chunks with max_workers={self.max_workers}...")
                        chunks = self._chunk_list(projects, self.max_workers)
                        print(f"🔧 Created {len(chunks)} chunks for {source_name} processing")
                        
                        futures = []
                        for chunk in chunks:
                            futures.append(self.executor.submit(
                                process_func, chunk, congressmen_data, districts_data,
                                district_lookup_dict, contractor_lookup_dict, contractor_inverted_index,
                                known_provinces, known_cities, location_context_map
                            ))
                        
                        prev_count = len(all_projects)
                        loop = asyncio.get_running_loop()
                        tasks = [asyncio.wrap_future(future, loop=loop) for future in futures]
                        
                        for completed_task in asyncio.as_completed(tasks):
                            result = await completed_task
                            all_projects.extend(result)
                            
                        print(f"✅ Processed {len(all_projects) - prev_count} {source_name} projects")
                except Exception as e:
                    print(f"Error processing {source_name} projects: {e}")
                    import traceback
                    traceback.print_exc()

        elif use_integrated:
            print(f"📊 Using integrated Parquet file: {INTEGRATED_PARQUET}")
            print("💾 Loading ALL projects into memory (utilizing 64GB RAM)...")
            
            # Load ALL data into memory ONCE - this is much faster than reading multiple times
            all_projects_data = self.load_projects_from_parquet(INTEGRATED_PARQUET, source_name=None)
            print(f"✅ Loaded {len(all_projects_data)} total projects into memory")
            
            # Process each source type from the in-memory data
            # Map source values to processing functions
            # Note: source column values may vary (SSP/Flood, DIME, PhilGEPS, Infrawatch/Microsite)
            sources = [
                ("SSP", self._process_flood_chunk),
                ("DIME", self._process_dime_chunk),
                ("PhilGEPS", self._process_philgeps_chunk),
                ("Microsite", self._process_infrawatch_chunk),  # Alternative name
            ]
            
            for source_name, process_func in sources:
                try:
                    # Filter from in-memory data instead of reading from disk
                    projects = self._filter_projects_by_source(all_projects_data, source_name)
                    if projects:
                        print(f"📊 Filtered {len(projects)} {source_name} projects from memory")
                        print(f"🔍 About to create chunks with max_workers={self.max_workers}...")
                        chunks = self._chunk_list(projects, self.max_workers)
                        print(f"🔧 Created {len(chunks)} chunks for {source_name} processing")
                        
                        # Submit tasks directly to ThreadPoolExecutor for better thread utilization
                        futures = []
                        for i, chunk in enumerate(chunks):
                            # Pass pre-calculated location data to avoid re-calculation in every chunk
                            futures.append(self.executor.submit(
                                process_func, chunk, congressmen_data, districts_data,
                                district_lookup_dict, contractor_lookup_dict, contractor_inverted_index,
                                known_provinces, known_cities, location_context_map
                            ))
                        print(f"🚀 Submitted {len(futures)} futures to executor for {source_name}")
                        
                        prev_count = len(all_projects)
                        # Convert futures to awaitables using asyncio.wrap_future for proper async handling
                        loop = asyncio.get_running_loop()
                        tasks = [asyncio.wrap_future(future, loop=loop) for future in futures]
                        
                        # Use as_completed for better responsiveness and memory management
                        completed = 0
                        for completed_task in asyncio.as_completed(tasks):
                            result = await completed_task
                            all_projects.extend(result)
                            completed += 1
                            if completed % max(1, len(tasks) // 10) == 0:  # Log every 10%
                                print(f"⏳ Progress: {completed}/{len(tasks)} chunks completed for {source_name}")
                            
                        print(f"✅ Processed {len(all_projects) - prev_count} {source_name} projects")
                except Exception as e:
                    print(f"Error processing {source_name} projects: {e}")
                    import traceback
                    traceback.print_exc()
        else:
            # Fallback to separate files
            print("⚠️  Integrated file not found, using separate Parquet files")
            print("💾 Loading ALL projects into memory (utilizing 64GB RAM)...")
            
            # Load all separate files into memory ONCE
            all_flood_projects = self.load_projects_from_parquet(FLOOD_PARQUET, source_name=None)
            all_dime_projects = self.load_projects_from_parquet(DIME_PARQUET, source_name=None) if DIME_PARQUET.exists() else []
            all_philgeps_projects = self.load_projects_from_parquet(PHILGEPS_PARQUET, source_name=None) if PHILGEPS_PARQUET.exists() else []
            all_infrawatch_projects = self.load_projects_from_parquet(INFRAWATCH_PARQUET, source_name=None) if INFRAWATCH_PARQUET.exists() else []
            
            total_loaded = len(all_flood_projects) + len(all_dime_projects) + len(all_philgeps_projects) + len(all_infrawatch_projects)
            print(f"✅ Loaded {total_loaded} total projects into memory")
            print(f"   - Flood/SSP: {len(all_flood_projects)}")
            print(f"   - DIME: {len(all_dime_projects)}")
            print(f"   - PhilGEPS: {len(all_philgeps_projects)}")
            print(f"   - Infrawatch: {len(all_infrawatch_projects)}")
            
            # Process SSP/Flood projects
            try:
                # Filter from in-memory data
                flood_projects = [p for p in all_flood_projects if p.get('_source', p.get('source', '')).upper() in ('SSP', 'FLOOD')]
                print(f"📊 Filtered {len(flood_projects)} flood/SSP projects from memory")
                flood_chunks = self._chunk_list(flood_projects, self.max_workers)
                # Submit tasks directly to ThreadPoolExecutor for better thread utilization
                flood_futures = [
                    self.executor.submit(
                        self._process_flood_chunk, chunk, congressmen_data, districts_data,
                        district_lookup_dict, contractor_lookup_dict, contractor_inverted_index,
                        known_provinces, known_cities, location_context_map
                    )
                    for chunk in flood_chunks
                ]
                # Convert futures to awaitables using asyncio.wrap_future
                loop = asyncio.get_running_loop()
                flood_tasks = [asyncio.wrap_future(future, loop=loop) for future in flood_futures]
                for completed_task in asyncio.as_completed(flood_tasks):
                    chunk_results = await completed_task
                    all_projects.extend(chunk_results)
                print(f"✅ Processed {len([p for p in all_projects if p.get('source') == 'SSP'])} flood/SSP projects")
            except Exception as e:
                print(f"Error processing flood/SSP projects: {e}")
                import traceback
                traceback.print_exc()
            
            # Process DIME projects
            try:
                # Filter from in-memory data
                dime_projects = [p for p in all_dime_projects if p.get('_source', p.get('source', '')).upper() == 'DIME']
                if dime_projects:
                    print(f"📊 Filtered {len(dime_projects)} DIME projects from memory")
                    dime_chunks = self._chunk_list(dime_projects, self.max_workers)
                    # Submit tasks directly to ThreadPoolExecutor for better thread utilization
                    dime_futures = [
                        self.executor.submit(
                            self._process_dime_chunk, chunk, congressmen_data, districts_data,
                            district_lookup_dict, contractor_lookup_dict, contractor_inverted_index,
                            known_provinces, known_cities, location_context_map
                        )
                        for chunk in dime_chunks
                    ]
                    # Convert futures to awaitables using asyncio.wrap_future
                    loop = asyncio.get_running_loop()
                    dime_tasks = [asyncio.wrap_future(future, loop=loop) for future in dime_futures]
                    for completed_task in asyncio.as_completed(dime_tasks):
                        result = await completed_task
                        all_projects.extend(result)
                    print(f"✅ Processed {len(all_projects)} DIME projects (matched)")
            except Exception as e:
                print(f"Error processing DIME projects: {e}")
                import traceback
                traceback.print_exc()
            
            # Process PhilGEPS projects
            try:
                # Filter from in-memory data
                philgeps_projects = [p for p in all_philgeps_projects if p.get('_source', p.get('source', '')).upper() == 'PHILGEPS']
                if philgeps_projects:
                    print(f"📊 Filtered {len(philgeps_projects)} PhilGEPS contracts from memory")
                    philgeps_chunks = self._chunk_list(philgeps_projects, self.max_workers)
                    # Submit tasks directly to ThreadPoolExecutor for better thread utilization
                    philgeps_futures = [
                        self.executor.submit(
                            self._process_philgeps_chunk, chunk, congressmen_data, districts_data,
                            district_lookup_dict, contractor_lookup_dict, contractor_inverted_index,
                            known_provinces, known_cities, location_context_map
                        )
                        for chunk in philgeps_chunks
                    ]
                    # Convert futures to awaitables using asyncio.wrap_future
                    loop = asyncio.get_running_loop()
                    philgeps_tasks = [asyncio.wrap_future(future, loop=loop) for future in philgeps_futures]
                    dime_count = len(all_projects)
                    for completed_task in asyncio.as_completed(philgeps_tasks):
                        result = await completed_task
                        all_projects.extend(result)
                    print(f"✅ Processed {len(all_projects) - dime_count} PhilGEPS projects (matched)")
            except Exception as e:
                print(f"Error processing PhilGEPS projects: {e}")
                import traceback
                traceback.print_exc()
            
            # Process Infrawatch projects
            try:
                # Filter from in-memory data
                infrawatch_projects = [p for p in all_infrawatch_projects if p.get('_source', p.get('source', '')).upper() in ('INFRAWATCH', 'MICROSITE')]
                if infrawatch_projects:
                    print(f"📊 Filtered {len(infrawatch_projects)} Infrawatch projects from memory")
                    infrawatch_chunks = self._chunk_list(infrawatch_projects, self.max_workers)
                    # Submit tasks directly to ThreadPoolExecutor for better thread utilization
                    infrawatch_futures = [
                        self.executor.submit(
                            self._process_infrawatch_chunk, chunk, congressmen_data, districts_data,
                            district_lookup_dict, contractor_lookup_dict, contractor_inverted_index,
                            known_provinces, known_cities, location_context_map
                        )
                        for chunk in infrawatch_chunks
                    ]
                    # Convert futures to awaitables using asyncio.wrap_future
                    loop = asyncio.get_running_loop()
                    infrawatch_tasks = [asyncio.wrap_future(future, loop=loop) for future in infrawatch_futures]
                    prev_count = len(all_projects)
                    for completed_task in asyncio.as_completed(infrawatch_tasks):
                        result = await completed_task
                        all_projects.extend(result)
                    print(f"✅ Processed {len(all_projects) - prev_count} Infrawatch projects (matched)")
            except Exception as e:
                print(f"Error processing Infrawatch projects: {e}")
                import traceback
                traceback.print_exc()
        
        return all_projects

    def _build_district_lookup(self, congressmen_data: Dict, districts_data: Dict):
        """Build global district lookup dictionary: district -> municipalities/barangays
        Uses DuckDB for fast lookups if available, otherwise uses in-memory data
        """
        self.district_lookup.clear()
        
        # Try to load from DuckDB first (much faster)
        duckdb_path = PARQUET_DIR / 'dynasty_data.duckdb'
        if duckdb_path.exists():
            try:
                self._build_district_lookup_from_duckdb(duckdb_path, congressmen_data)
                return
            except Exception as e:
                print(f"⚠️  Failed to load district lookup from DuckDB: {e}, using in-memory data")
        
        # Fallback to in-memory data
        # Get districts from districts_data
        districts_info = districts_data.get('districts', {})
        
        for cm_name, cm_data in congressmen_data.items():
            district_number = cm_data.get('district_number')
            provinces = cm_data.get('provinces', [])
            is_city_district = cm_data.get('is_city_district', False)
            
            if not district_number or not provinces:
                continue
            
            province_name = provinces[0]
            district_key = f"{province_name} {district_number} District"
            
            # Initialize district entry
            if district_key not in self.district_lookup:
                self.district_lookup[district_key] = {
                    'municipalities': set(),
                    'barangays': set(),
                    'is_city': is_city_district,
                    'province': province_name
                }
            
            # Add barangays (for city districts) - check both cm_data and districts_data
            if is_city_district:
                # First, try from congressmen data
                for brgy in cm_data.get('barangays', []):
                    if brgy:
                        brgy_upper = brgy.upper().strip()
                        self.district_lookup[district_key]['barangays'].add(brgy_upper)
                        # Also add without "BRGY" prefix
                        brgy_clean = re.sub(r'^(BRGY\.?|BARANGAY)\s+', '', brgy_upper, flags=re.IGNORECASE)
                        if brgy_clean:
                            self.district_lookup[district_key]['barangays'].add(brgy_clean)
                
                # Also check districts_data for barangays
                # Try to find the province/city in districts_data
                province_key = None
                for key in districts_info.keys():
                    if key.upper() == province_name.upper():
                        province_key = key
                        break
                
                if province_key:
                    province_district_info = districts_info[province_key]
                    barangays_by_district = province_district_info.get('barangays', {})
                    
                    # Normalize district number to match districts.json format
                    # districts.json uses "1st District", "2nd District", "Lone District", etc.
                    district_str = str(district_number).strip()
                    if district_str.upper() in ('LONE', 'LONE DISTRICT'):
                        district_key_normalized = 'Lone District'
                    elif district_str.isdigit():
                        # Convert "1" -> "1st District", "2" -> "2nd District", etc.
                        num = int(district_str)
                        if num == 1:
                            district_key_normalized = '1st District'
                        elif num == 2:
                            district_key_normalized = '2nd District'
                        elif num == 3:
                            district_key_normalized = '3rd District'
                        else:
                            district_key_normalized = f'{num}th District'
                    elif 'DISTRICT' in district_str.upper():
                        # Already in format like "1st District"
                        district_key_normalized = district_str
                    else:
                        # Try to match as-is
                        district_key_normalized = district_str
                    
                    # Try exact match first
                    if district_key_normalized in barangays_by_district:
                        for brgy in barangays_by_district[district_key_normalized]:
                            if brgy:
                                brgy_upper = str(brgy).upper().strip()
                                self.district_lookup[district_key]['barangays'].add(brgy_upper)
                                # Also add without "BRGY" prefix
                                brgy_clean = re.sub(r'^(BRGY\.?|BARANGAY)\s+', '', brgy_upper, flags=re.IGNORECASE)
                                if brgy_clean:
                                    self.district_lookup[district_key]['barangays'].add(brgy_clean)
                    else:
                        # Try case-insensitive match
                        for key in barangays_by_district.keys():
                            if key.upper() == district_key_normalized.upper():
                                for brgy in barangays_by_district[key]:
                                    if brgy:
                                        brgy_upper = str(brgy).upper().strip()
                                        self.district_lookup[district_key]['barangays'].add(brgy_upper)
                                        # Also add without "BRGY" prefix
                                        brgy_clean = re.sub(r'^(BRGY\.?|BARANGAY)\s+', '', brgy_upper, flags=re.IGNORECASE)
                                        if brgy_clean:
                                            self.district_lookup[district_key]['barangays'].add(brgy_clean)
                                break
            
            # Add municipalities (for province districts)
            else:
                # First, try from congressmen data
                for mun in cm_data.get('district_municipalities', []):
                    if mun:
                        self.district_lookup[district_key]['municipalities'].add(mun.upper().strip())
                
                # Also check districts_data for municipalities
                province_key = None
                for key in districts_info.keys():
                    if key.upper() == province_name.upper():
                        province_key = key
                        break
                
                if province_key:
                    province_district_info = districts_info[province_key]
                    municipalities_map = province_district_info.get('municipalities', {})
                    
                    # Normalize district number to match districts.json format
                    district_str = str(district_number).strip()
                    if district_str.upper() in ('LONE', 'LONE DISTRICT'):
                        district_key_normalized = 'Lone District'
                    elif district_str.isdigit():
                        num = int(district_str)
                        if num == 1:
                            district_key_normalized = '1st District'
                        elif num == 2:
                            district_key_normalized = '2nd District'
                        elif num == 3:
                            district_key_normalized = '3rd District'
                        else:
                            district_key_normalized = f'{num}th District'
                    elif 'DISTRICT' in district_str.upper():
                        district_key_normalized = district_str
                    else:
                        district_key_normalized = district_str
                    
                    # Add municipalities that map to this district
                    for mun_name, mun_district in municipalities_map.items():
                        mun_district_str = str(mun_district).strip()
                        if (mun_district_str.upper() == district_key_normalized.upper() or
                            mun_district_str.upper() == district_str.upper()):
                            self.district_lookup[district_key]['municipalities'].add(mun_name.upper().strip())
        
        print(f"✅ Built district lookup: {len(self.district_lookup)} districts")
        total_municipalities = sum(len(d['municipalities']) for d in self.district_lookup.values())
        total_barangays = sum(len(d['barangays']) for d in self.district_lookup.values())
        print(f"   - {total_municipalities} municipalities, {total_barangays} barangays")
    
    def _build_district_lookup_from_duckdb(self, duckdb_path: Path, congressmen_data: Dict):
        """Build district lookup from DuckDB tables (much faster)"""
        import duckdb
        
        conn = duckdb.connect(str(duckdb_path))
        try:
            # Load all districts
            district_rows = conn.execute("SELECT DISTINCT district_key, province_name, is_city FROM districts").fetchall()
            
            for row in district_rows:
                district_key, province_name, is_city = row
                if district_key not in self.district_lookup:
                    self.district_lookup[district_key] = {
                        'municipalities': set(),
                        'barangays': set(),
                        'is_city': bool(is_city),
                        'province': province_name
                    }
            
            # Load municipalities
            mun_rows = conn.execute("SELECT district_key, municipality FROM district_municipalities").fetchall()
            for row in mun_rows:
                district_key, municipality = row
                if district_key in self.district_lookup:
                    self.district_lookup[district_key]['municipalities'].add(municipality.upper().strip())
            
            # Load barangays from districts
            brgy_rows = conn.execute("SELECT district_key, barangay FROM district_barangays").fetchall()
            for row in brgy_rows:
                district_key, barangay = row
                if district_key in self.district_lookup:
                    self.district_lookup[district_key]['barangays'].add(barangay.upper().strip())
            
            # Also load barangays from congressmen_barangays
            cm_brgy_rows = conn.execute("SELECT district_key, barangay FROM congressmen_barangays").fetchall()
            for row in cm_brgy_rows:
                district_key, barangay = row
                if district_key in self.district_lookup:
                    self.district_lookup[district_key]['barangays'].add(barangay.upper().strip())
            
            # Also populate from congressmen_data for any missing districts
            for cm_name, cm_data in congressmen_data.items():
                district_number = cm_data.get('district_number')
                provinces = cm_data.get('provinces', [])
                is_city_district = cm_data.get('is_city_district', False)
                
                if not district_number or not provinces:
                    continue
                
                province_name = provinces[0]
                district_key = f"{province_name} {district_number} District"
                
                if district_key not in self.district_lookup:
                    self.district_lookup[district_key] = {
                        'municipalities': set(),
                        'barangays': set(),
                        'is_city': is_city_district,
                        'province': province_name
                    }
                
                # Add barangays from congressmen data
                if is_city_district:
                    for brgy in cm_data.get('barangays', []):
                        if brgy:
                            brgy_upper = brgy.upper().strip()
                            self.district_lookup[district_key]['barangays'].add(brgy_upper)
                            brgy_clean = re.sub(r'^(BRGY\.?|BARANGAY)\s+', '', brgy_upper, flags=re.IGNORECASE)
                            if brgy_clean:
                                self.district_lookup[district_key]['barangays'].add(brgy_clean)
                
                # Add municipalities from congressmen data
                else:
                    for mun in cm_data.get('district_municipalities', []):
                        if mun:
                            self.district_lookup[district_key]['municipalities'].add(mun.upper().strip())
            
            print(f"✅ Built district lookup from DuckDB: {len(self.district_lookup)} districts")
            total_municipalities = sum(len(d['municipalities']) for d in self.district_lookup.values())
            total_barangays = sum(len(d['barangays']) for d in self.district_lookup.values())
            print(f"   - {total_municipalities} municipalities, {total_barangays} barangays")
        finally:
            conn.close()

    async def generate_cache(self):
        """Generate the cached JSON file using DuckDB"""
        print("🚀 Starting dynasty-projects cache generation (DuckDB version - Parquet only)...")
        try:
    
            # Ensure latest districts and congressmen config are pulled from DB
            self._refresh_source_json()
            
            # Load config
            config_data, districts_data = await self.load_config()
            print(f"✅ Loaded config with {len(config_data.get('target_congressmen', []))} congressmen")
            
            # Check if parquet files are available
            political_dynasties_available = POLITICAL_DYNASTIES_PARQUET.exists()
            if not political_dynasties_available:
                print("⚠️  political_dynasties.parquet not found. Using config-only data.")
            else:
                print(f"✅ Found political_dynasties.parquet at {POLITICAL_DYNASTIES_PARQUET}")
    
                # Get congressmen data (no longer needs PostgreSQL connection)
                congressmen_data = await self.get_congressmen_data(
                    None,  # No longer passing dynasty_conn
                    config_data,
                    districts_data,
                    political_dynasties_available
                )
            print(f"✅ Loaded {len(congressmen_data)} congressmen")
            
            # DEBUG: Inspect Mikee Romero and other potentially problematic congressmen
            for name, data in congressmen_data.items():
                if "Mikee Romero" in name or "Romero" in name:
                    print(f"\n🔍 DEBUG: {name}")
                    print(f"   Provinces: {data.get('provinces')}")
                    print(f"   District: {data.get('district_number')}")
                    print(f"   Contractors: {data.get('contractors')}")
                    # print(f"   Patterns: {data.get('contractor_patterns')}") 
            
            # Build global district lookup dictionary
            self._build_district_lookup(congressmen_data, districts_data)
                
            # Pre-processing validation: ensure city districts and barangay data are present
            city_district_count = sum(1 for d in self.district_lookup.values() if d.get('is_city'))
            total_barangays = sum(len(d.get('barangays', [])) for d in self.district_lookup.values())
            total_municipalities = sum(len(d.get('municipalities', [])) for d in self.district_lookup.values())
            print(f"🔎 District lookup stats -> districts: {len(self.district_lookup)}, city_districts: {city_district_count}, municipalities: {total_municipalities}, barangays: {total_barangays}")
            if city_district_count == 0 or total_barangays == 0:
                print("❌ City districts and/or barangay lists not loaded. Exiting before parquet processing.")
                import sys
                sys.exit(1)
            
            # Build name normalization map early (before matching)
            print("🔧 Building name normalization map...")
            self.name_normalization_map = self._build_name_normalization_map(congressmen_data)
            # Build reverse map: all variations -> canonical name
            self.canonical_name_map = {}
            normalized_to_variations = {}
            for canonical_name, normalized in self.name_normalization_map.items():
                if normalized not in normalized_to_variations:
                    normalized_to_variations[normalized] = []
                normalized_to_variations[normalized].append(canonical_name)
                # Map each variation to the canonical (shortest) name
                canonical = min(normalized_to_variations[normalized], key=len)
                self.canonical_name_map[canonical_name] = canonical
            print(f"✅ Built name normalization map: {len(self.canonical_name_map)} name variations mapped")
            
            # Build O(1) lookup dictionaries for optimized matching
            print("🔧 Building O(1) lookup dictionaries for optimized matching...")
            district_lookup_dict, contractor_lookup_dict, contractor_inverted_index = self._build_lookup_dictionaries(congressmen_data, districts_data)
            print(f"✅ Built lookup dictionaries: {len(district_lookup_dict)} district keys, {len(contractor_lookup_dict)} contractor keys")
            print(f"✅ Built inverted index: {len(contractor_inverted_index)} tokens")
            
            # Build location dictionaries (provinces, cities, municipalities, barangays, directional variants, context map)
            print("🔧 Building location dictionaries from data...")
            location_dicts = self._build_location_dictionaries(congressmen_data, district_lookup_dict, districts_data)
            self.location_dicts = location_dicts  # Store as instance variable for use throughout
            print(f"✅ Built location dictionaries:")
            print(f"   - {len(location_dicts['provinces'])} provinces")
            print(f"   - {len(location_dicts['cities'])} cities")
            print(f"   - {len(location_dicts['municipalities'])} municipalities")
            print(f"   - {len(location_dicts['barangays'])} barangays")
            print(f"   - {len(location_dicts['directional_map'])} directional variants")
            print(f"   - {len(location_dicts['location_context_map'])} location contexts")
            
            # Process projects from Parquet files
            all_projects = await self.process_projects(
                congressmen_data,
                districts_data,
                district_lookup_dict,
                contractor_lookup_dict,
                contractor_inverted_index
            )
            print(f"✅ Processed {len(all_projects)} projects")
            
            # Save classified projects to Parquet for future runs
            try:
                print(f"💾 Saving classified projects to {CLASSIFIED_PARQUET}...")
                # Use pandas to create DataFrame, then DuckDB to write to Parquet
                # This ensures we persist the classification columns (project_district, etc.)
                df = pd.DataFrame(all_projects)
                # Convert any set/list columns to strings if needed, or let DuckDB handle it
                # DuckDB handles lists fine in Parquet
                duckdb.sql("SELECT * FROM df").write_parquet(str(CLASSIFIED_PARQUET))
                print(f"✅ Saved classified projects to {CLASSIFIED_PARQUET}")
            except Exception as e:
                print(f"⚠️  Failed to save classified projects to Parquet: {e}")
                import traceback
                traceback.print_exc()
            
            # Update skipped counter from results (since parallel processing doesn't share instance variables)
            # Count skipped projects before deduplication
            total_skipped = len([p for p in all_projects if p.get('_skipped_reclassification')])
            self.progress_counters['skipped'] = total_skipped
            
            # Display final summary
            print(f"\n📊 Final Processing Summary:")
            print(f"   Total projects processed: {self.progress_counters['total_processed']}")
            print(f"   ✅ Districts matched: {self.progress_counters['districts_matched']}")
            print(f"      - City districts: {self.progress_counters['city_districts']}")
            print(f"      - Province districts: {self.progress_counters['province_districts']}")
            print(f"   📍 Location matches:")
            print(f"      - Municipalities: {self.progress_counters['municipality_matched']}")
            print(f"      - Barangays: {self.progress_counters['barangay_matched']}")
            print(f"   👷 Contractors matched: {self.progress_counters['contractors_matched']}")
            print(f"   👤 Unique congressmen: {len(self.progress_counters['congressmen_matched'])}")
            print(f"   ❌ Unmatched: {self.progress_counters['unmatched']}")
            print()
            
            # Deduplicate and add cross-database bonus
            # Original logic: deduplicate by project key, track all sources and all congressmen
            projects_by_key = {}
            for proj in all_projects:
                source_label = self._normalize_source_label(proj.get('source', 'Unknown'))
                proj['source'] = source_label
                key = proj.get('meilisearch_id') or self._build_project_key(proj)
                
                # Determine primary congressman (district takes precedence)
                primary_congressman = proj.get('district_congressman') or proj.get('contractor_congressman') or 'Unknown'
                proj['congressman'] = primary_congressman
                
                # Determine match_type (district takes precedence)
                if proj.get('district_congressman'):
                    proj['match_type'] = 'district'
                elif proj.get('contractor_congressman'):
                    proj['match_type'] = 'contractor'
                else:
                    proj['match_type'] = 'unknown'
                
                if key not in projects_by_key:
                    projects_by_key[key] = {
                        'project': proj.copy(),
                        'sources': set(),
                        'congressmen': set()
                    }
                else:
                    merged_project = self._merge_project_records(projects_by_key[key]['project'], proj)
                    projects_by_key[key]['project'] = merged_project
                
                projects_by_key[key]['sources'].add(source_label)
                # Track both district and contractor congressmen
                if proj.get('district_congressman'):
                    projects_by_key[key]['congressmen'].add(proj.get('district_congressman'))
                if proj.get('contractor_congressman'):
                    projects_by_key[key]['congressmen'].add(proj.get('contractor_congressman'))
            
            # Build unique projects list
            unique_projects = []
            for key, data in projects_by_key.items():
                proj = data['project'].copy()
                sources_count = len(data['sources'])
                
                # Preserve the congressmen set for individual cache creation
                proj['_all_congressmen'] = list(data['congressmen'])
                
                # New scoring system:
                # 1. Base score: 1 point per 2M (max 60)
                amount = proj.get('amount', 0)
                if isinstance(amount, str):
                    # Handle string amounts like "₱270,194,706"
                    amount_str = amount.replace('₱', '').replace(',', '').strip()
                    try:
                        amount = float(amount_str)
                    except (ValueError, AttributeError):
                        amount = 0
                
                amount_in_millions = amount / 1_000_000
                base_score = min(60, int(amount_in_millions / 2))  # 1 point per 2M, max 60
                
                # 2. Add +10 per database (capped per project)
                db_bonus = min(40, sources_count * 10)
                
                # 3. Calculate total score
                current_score = base_score + db_bonus
                
                # 4. City-wide and null-year matches retain full score (handled via district assignment rules)
                
                proj['match_score'] = current_score
                proj['sources_count'] = sources_count
                proj['sources_list'] = sorted(list(data['sources']))
                
                # Keep the primary congressman from district match (or contractor if no district)
                if not proj.get('congressman'):
                    proj['congressman'] = proj.get('district_congressman') or proj.get('contractor_congressman') or 'Unknown'
                
                unique_projects.append(proj)
            
            # Sort by match_score descending, then by amount descending
            unique_projects.sort(key=lambda x: (x.get('match_score', 0), x.get('amount', 0)), reverse=True)
            
            # Calculate summary
            ssp_count = len([p for p in unique_projects if 'SSP' in (p.get('sources_list', []))])
            # Count both 'Microsite' and 'Infrawatch' as Infrawatch (normalization may vary)
            microsite_count = len([p for p in unique_projects if 'Microsite' in (p.get('sources_list', [])) or 'Infrawatch' in (p.get('sources_list', []))])
            flood_count = len([p for p in unique_projects if p.get('is_flood_related') == True])
            # Count projects by match type
            # Note: A project can have both district and contractor matches, but match_type indicates the primary match
            # For summary, we should count:
            # - district_projects: projects with district match (primary or secondary)
            # - contractor_projects: projects with contractor match (primary or secondary)
            district_projects_count = len([p for p in unique_projects if p.get('district_congressman')])
            contractor_projects_count = len([p for p in unique_projects if p.get('contractor_congressman')])
            # Also count by primary match_type for backward compatibility
            district_primary_count = len([p for p in unique_projects if p.get('match_type') == 'district'])
            contractor_primary_count = len([p for p in unique_projects if p.get('match_type') == 'contractor'])
            
            summary = {
                "total": len(unique_projects),
                "dime": len([p for p in unique_projects if 'DIME' in (p.get('sources_list', []))]),
                "philgeps": len([p for p in unique_projects if 'PhilGEPS' in (p.get('sources_list', []))]),
                "ssp": ssp_count,
                "infrawatch": microsite_count,
                "microsite": microsite_count,
                "district_projects": district_projects_count,  # Count all projects with district match
                "contractor_projects": contractor_projects_count,  # Count all projects with contractor match
                "district_primary": district_primary_count,  # Projects where district is primary match
                "contractor_primary": contractor_primary_count,  # Projects where contractor is primary match
                "flood_projects": flood_count
            }
            
            # Calculate congressman statistics for charts
            congressman_stats = {}
            for proj in unique_projects:
                # Count both district and contractor congressmen
                congressmen_to_count = set()
                if proj.get('district_congressman'):
                    congressmen_to_count.add(proj.get('district_congressman'))
                if proj.get('contractor_congressman'):
                    congressmen_to_count.add(proj.get('contractor_congressman'))
                
                for congressman in congressmen_to_count:
                    if not congressman_stats.get(congressman):
                        congressman_stats[congressman] = {
                            "name": congressman,
                            "count": 0,
                            "total_cost": 0
                        }
                    
                    congressman_stats[congressman]["count"] += 1
                    
                    # Parse amount
                    amount = proj.get('amount', 0)
                    if isinstance(amount, str):
                        amount_str = amount.replace('₱', '').replace(',', '').strip()
                        try:
                            amount = float(amount_str)
                        except (ValueError, AttributeError):
                            amount = 0
                    else:
                        amount = float(amount) if amount else 0
                    
                    congressman_stats[congressman]["total_cost"] += amount
            
            # Convert to sorted array for chart data
            chart_data = sorted(
                list(congressman_stats.values()),
                key=lambda x: x["count"],
                reverse=True
            )
            chart_top10_by_count = chart_data[:10]
            chart_top10_by_cost = sorted(
                list(congressman_stats.values()),
                key=lambda x: x["total_cost"],
                reverse=True
            )[:10]
            
            # Calculate totals for chart_data
            for stat in chart_data:
                stat["average_cost"] = stat["total_cost"] / stat["count"] if stat["count"] else 0
            
            # Prepare chart data for counts and costs
            chart_data_by_count = [
                {
                    "name": stat["name"],
                    "count": stat["count"],
                    "total_cost": stat["total_cost"]
                }
                for stat in chart_data
            ]
            
            chart_data_by_cost = sorted(
                [
                    {
                        "name": stat["name"],
                        "count": stat["count"],
                        "total_cost": stat["total_cost"]
                    }
                    for stat in chart_data
                ],
                key=lambda x: x["total_cost"],
                reverse=True
            )
            
            # Helper function to parse amount consistently
            def parse_amount(amount):
                if isinstance(amount, (int, float)):
                    return float(amount) if amount else 0
                elif isinstance(amount, str):
                    amount_str = amount.replace('₱', '').replace(',', '').strip()
                    try:
                        return float(amount_str) if amount_str else 0
                    except (ValueError, AttributeError):
                        return 0
                else:
                    return 0
            
            # Calculate dashboard statistics
            total_cost_all = sum(stat["total_cost"] for stat in chart_data)
            district_count = summary['district_projects']
            contractor_count = summary['contractor_projects']
            district_cost = sum(
                parse_amount(proj.get('amount', 0))
                for proj in unique_projects if proj.get('match_type') == 'district'
            )
            contractor_cost = sum(
                parse_amount(proj.get('amount', 0))
                for proj in unique_projects if proj.get('match_type') == 'contractor'
            )
            
            flood_cost = sum(
                parse_amount(proj.get('amount', 0))
                for proj in unique_projects if proj.get('is_flood_related') == True
            )
            
            dashboard_stats = {
                "total_cost_all": total_cost_all,
                "total_projects": summary['total'],
                "district_count": district_count,
                "district_cost": district_cost,
                "contractor_count": contractor_count,
                "contractor_cost": contractor_cost,
                "flood_count": flood_count,
                "flood_cost": flood_cost
            }
            
            print("ℹ️  Combined cache file generation skipped (file too large and unused)")
            
            # Create individual cache files for each congressman
            print(f"\n📁 Creating individual cache files for each congressman...")
            cache_base_dir = Path(__file__).parent.parent / 'static' / 'data'
            
            # CRITICAL: Clear all existing congressman cache directories before writing new ones
            # This ensures we don't accumulate stale data from previous runs and is faster than clearing one by one
            print("🧹 Clearing existing congressman cache directories...")
            import shutil
            cleared_count = 0
            for item in cache_base_dir.iterdir():
                if item.is_dir() and item.name.startswith('congressman-projects-'):
                    shutil.rmtree(item)
                    cleared_count += 1
            if cleared_count > 0:
                print(f"   🗑️  Removed {cleared_count} congressman cache directories")
            
            # Build name normalization map to merge duplicate name variations
            print("🔧 Building name normalization map...")
            name_normalization_map = self._build_name_normalization_map(congressmen_data)
            # Also build reverse map: normalized -> list of all variations
            normalized_to_variations = {}
            for canonical_name, normalized in name_normalization_map.items():
                if normalized not in normalized_to_variations:
                    normalized_to_variations[normalized] = []
                normalized_to_variations[normalized].append(canonical_name)
            
            # Get all congressmen from config (not just those with projects)
            all_congressmen_names = set()
            for cm_config in config_data.get('target_congressmen', []):
                all_congressmen_names.add(cm_config.get('display_name'))
            
            # Also include any congressmen that have projects (in case they're not in config)
            for proj in unique_projects:
                if proj.get('district_congressman'):
                    all_congressmen_names.add(proj.get('district_congressman'))
                if proj.get('contractor_congressman'):
                    all_congressmen_names.add(proj.get('contractor_congressman'))
            
            # Also include all deputy speakers from CSV file
            import csv
            deputy_speakers_csv = Path(__file__).parent.parent / 'database' / 'Philippine_Deputy_Speakers_2016-2025.csv'
            if deputy_speakers_csv.exists():
                with open(deputy_speakers_csv, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        name = row.get('Name', '').strip()
                        if name:
                            all_congressmen_names.add(name)
            
            for congressman_name in sorted(all_congressmen_names):
                # Get normalized name and all variations
                normalized_name = self._normalize_congressman_name(congressman_name)
                name_variations = normalized_to_variations.get(normalized_name, [congressman_name])
                
                # Filter projects for this congressman
                # Include projects where this congressman (or any name variation) is district_congressman, contractor_congressman, or in _all_congressmen
                congressman_projects = []
                for p in unique_projects:
                    # Check if this congressman or any name variation matches the project
                    district_match = p.get('district_congressman') in name_variations
                    contractor_match = p.get('contractor_congressman') in name_variations
                    all_congressmen_match = any(variation in p.get('_all_congressmen', []) for variation in name_variations)
                    
                    if district_match or contractor_match or all_congressmen_match:
                        
                        # RE-VALIDATE: Check if this congressman should actually match this project
                        # This prevents Metro Manila projects from appearing in Manila district caches
                        should_include = False
                        
                        # Get project location and congressman's province for validation
                        # Try to get data from any name variation
                        cm_data = None
                        for variation in name_variations:
                            if variation in congressmen_data:
                                cm_data = congressmen_data[variation]
                                break
                        
                        location = p.get('location', '').upper()
                        cm_provinces = cm_data.get('provinces', []) if cm_data else []
                        
                        # CRITICAL: Check Metro Manila FIRST, before accepting direct matches
                        if cm_provinces:
                            cm_province = cm_provinces[0].upper()
                            # Special check: Prevent METRO MANILA from matching MANILA districts
                            if cm_province == 'MANILA' and 'METRO MANILA' in location:
                                should_include = False
                                # Skip this project entirely for this congressman
                            # Check for direct match (any variation)
                            elif district_match or contractor_match:
                                should_include = True
                            # For _all_congressmen matches, allow unless it's Metro Manila
                            elif all_congressmen_match:
                                should_include = True
                        else:
                            # No province info, use default logic
                            if district_match or contractor_match or all_congressmen_match:
                                should_include = True
                        
                        if not should_include:
                            continue
                        
                        # Create a copy with this congressman as the primary congressman
                        proj_copy = p.copy()
                        proj_copy['congressman'] = congressman_name
                        # Remove the internal _all_congressmen field before saving
                        proj_copy.pop('_all_congressmen', None)
                        
                        # Fix match_type: set it based on how THIS congressman was matched, not globally
                        if district_match and congressman_name in name_variations:
                            # This congressman was matched via district
                            proj_copy['match_type'] = 'district'
                        elif contractor_match and congressman_name in name_variations:
                            # This congressman was matched via contractor
                            proj_copy['match_type'] = 'contractor'
                        # Otherwise keep the existing match_type
                        
                        congressman_projects.append(proj_copy)
                
                # Calculate congressman-specific statistics
                # Count projects matched to any name variation
                congressman_total_cost = sum(parse_amount(p.get('amount', 0)) for p in congressman_projects)
                congressman_district_count = len([p for p in congressman_projects if p.get('district_congressman') in name_variations])
                congressman_contractor_count = len([p for p in congressman_projects if p.get('contractor_congressman') in name_variations])
                congressman_district_cost = sum(parse_amount(p.get('amount', 0)) for p in congressman_projects if p.get('district_congressman') in name_variations)
                congressman_contractor_cost = sum(parse_amount(p.get('amount', 0)) for p in congressman_projects if p.get('contractor_congressman') in name_variations)
                congressman_flood_count = len([p for p in congressman_projects if p.get('is_flood_related') == True])
                congressman_flood_cost = sum(parse_amount(p.get('amount', 0)) for p in congressman_projects if p.get('is_flood_related') == True)
                
                congressman_summary = {
                    "total": len(congressman_projects),
                    "dime": len([p for p in congressman_projects if 'DIME' in (p.get('sources_list', []))]),
                    "philgeps": len([p for p in congressman_projects if 'PhilGEPS' in (p.get('sources_list', []))]),
                    "ssp": len([p for p in congressman_projects if 'SSP' in (p.get('sources_list', []))]),
                    "infrawatch": len([p for p in congressman_projects if 'Infrawatch' in (p.get('sources_list', []))]),
                    "microsite": len([p for p in congressman_projects if 'Infrawatch' in (p.get('sources_list', []))]),
                    "district_projects": congressman_district_count,
                    "contractor_projects": congressman_contractor_count,
                    "flood_projects": congressman_flood_count
                }
                
                congressman_dashboard_stats = {
                    "total_cost_all": congressman_total_cost,
                    "total_projects": len(congressman_projects),
                    "district_count": congressman_district_count,
                    "district_cost": congressman_district_cost,
                    "contractor_count": congressman_contractor_count,
                    "contractor_cost": congressman_contractor_cost,
                    "flood_count": congressman_flood_count,
                    "flood_cost": congressman_flood_cost
                }
                
                # Normalize congressman name for directory name
                congressman_normalized = congressman_name.lower().replace(" ", "-").replace(".", "").replace(",", "").replace("'", "")
                congressman_cache_dir = cache_base_dir / f'congressman-projects-{congressman_normalized}'
                congressman_cache_dir.mkdir(parents=True, exist_ok=True)
                
                # Save congressman-specific cache
                congressman_cache_data = {
                    "success": True,
                    "congressman": congressman_name,
                    "projects": congressman_projects,
                    "summary": congressman_summary,
                    "dashboard_stats": congressman_dashboard_stats,
                    "generated_at": datetime.now().isoformat(),
                    "cache_version": "1.0"
                }
                
                congressman_cache_file = congressman_cache_dir / 'all-projects-cache.json'
                with open(congressman_cache_file, 'w', encoding='utf-8') as f:
                    json.dump(congressman_cache_data, f, indent=2, ensure_ascii=False)
                
                # Save summary.json for consistency with province cache structure
                summary_data = {
                    "congressman": congressman_name,
                    "summary": congressman_summary,
                    "total_cost": congressman_total_cost,
                    "generated_at": datetime.now().isoformat()
                }
                summary_file = congressman_cache_dir / 'summary.json'
                with open(summary_file, 'w', encoding='utf-8') as f:
                    json.dump(summary_data, f, indent=2, ensure_ascii=False)
                
                if len(congressman_projects) > 0:
                    print(f"   ✅ {congressman_name}: {len(congressman_projects)} projects, ₱{congressman_total_cost:,.2f}")
                else:
                    print(f"   ✅ {congressman_name}: 0 projects (empty cache created)")
            
            print(f"\n✅ Individual cache files created for {len(all_congressmen_names)} congressmen")
            
            # Print final summary with flood counts
            print(f"\n📊 Final Summary (Total projects):")
            print(f"   Total projects: {summary['total']}")
            print(f"   DIME: {summary['dime']}")
            print(f"   PhilGEPS: {summary['philgeps']}")
            print(f"   SSP: {summary['ssp']}")
            print(f"   Infrawatch: {summary['infrawatch']}")
            print(f"   District projects: {summary['district_projects']}")
            print(f"   Contractor projects: {summary['contractor_projects']}")
            print(f"   🌊 Flood-related projects: {summary['flood_projects']} (₱{flood_cost:,.2f})")
            print(f"   Total congressmen covered: {len([name for name in all_congressmen_names if any(p.get('district_congressman') == name or p.get('contractor_congressman') == name for p in unique_projects)])}")
            if not self.force_reclassify:
                print(f"   ⏭️  Skipped (already classified): {self.progress_counters['skipped']}")
            
            # Update aggregated leaderboard so the UI reflects the new cache immediately
            self._regenerate_top_congressmen_cache()
            
            print("✅ Cache generation complete")
        
        finally:

            self.duckdb_conn.close()
            # Shutdown ThreadPoolExecutor
            if hasattr(self, 'executor'):
                self.executor.shutdown(wait=True)

async def main():
    parser = argparse.ArgumentParser(description='Generate dynasty projects cache')
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force reclassification of all projects, even if they already have all 4 classification columns filled'
    )
    args = parser.parse_args()
    
    generator = DynastyProjectsCacheGeneratorDuckDB(force_reclassify=args.force)
    
    if args.force:
        print("🔄 FORCE MODE: Reclassifying ALL projects (ignoring existing classifications)")
    else:
        print("ℹ️  Normal mode: Skipping projects that are already fully classified")
    
    await generator.generate_cache()

if __name__ == '__main__':
    asyncio.run(main())

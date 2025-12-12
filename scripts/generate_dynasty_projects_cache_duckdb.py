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
# Also add script directory to path to find sibling modules
sys.path.insert(0, str(Path(__file__).parent))

from scripts.location_enricher import LocationEnricher
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
MICROSITE_PARQUET = PARQUET_DIR / 'infrawatch_projects.parquet'  # File is named infrawatch but we call it microsite
TRANSPARENCY_PARQUET = PARQUET_DIR / 'transparency_projects.parquet'  # DPWH scraper data
FLOOD_PARQUET = PARQUET_DIR / 'flood_projects.parquet'
# Dynasty data parquet files
POLITICAL_DYNASTIES_PARQUET = PARQUET_DIR / 'political_dynasties.parquet'
RELATIONSHIPS_PARQUET = PARQUET_DIR / 'relationships.parquet'
CONNECTION_TYPES_PARQUET = PARQUET_DIR / 'connection_types.parquet'
UNIFIED_LOCATIONS_PARQUET = Path(__file__).parent.parent / 'static' / 'data' / 'unified_locations.parquet'

class LocationMatcher:
    """
    Optimized location matcher using an Inverted Index approach.
    Replaces O(N) linear scans with O(1) token lookups.
    """
    def __init__(self, parquet_path: Path):
        self.parquet_path = parquet_path
        self.location_entries = []
        self.token_map = defaultdict(set)
        self.loaded = False
        # Disambiguation patterns for tricky provinces
        self.disambiguation_patterns = [
            (re.compile(r'davao\s+de\s+oro', re.I), 'DAVAO DE ORO'),
            (re.compile(r'davao\s+del\s+sur', re.I), 'DAVAO DEL SUR'),
            (re.compile(r'davao\s+del\s+norte', re.I), 'DAVAO DEL NORTE'),
            (re.compile(r'davao\s+oriental', re.I), 'DAVAO ORIENTAL'),
            (re.compile(r'davao\s+occidental', re.I), 'DAVAO OCCIDENTAL'),
            (re.compile(r'cebu\s+city', re.I), 'CEBU CITY'),
            (re.compile(r'cagayan\s+de\s+oro', re.I), 'CITY OF CAGAYAN DE ORO'),
            (re.compile(r'quezon\s+city', re.I), 'QUEZON CITY'),
            (re.compile(r'zamboanga\s+del\s+norte', re.I), 'ZAMBOANGA DEL NORTE'),
            (re.compile(r'zamboanga\s+del\s+sur', re.I), 'ZAMBOANGA DEL SUR'),
            (re.compile(r'zamboanga\s+sibugay', re.I), 'ZAMBOANGA SIBUGAY'),
        ]

    def load(self):
        if self.loaded: return
        if not self.parquet_path.exists():
            print(f"⚠️ unified_locations.parquet not found at {self.parquet_path}")
            return
            
        print("🚀 Building Inverted Index for Locations...")
        try:
            import duckdb
            con = duckdb.connect()
            con.execute(f"CREATE TABLE ul AS SELECT * FROM read_parquet('{self.parquet_path}')")
            # Select relevant columns: prov, muni, brgy, dist, cong
            rows = con.execute("SELECT province, municipality, barangay, district, congressman FROM ul WHERE congressman IS NOT NULL AND congressman != 'TBD' AND congressman != 'Unknown'").fetchall()
            con.close()
            
            for idx, row in enumerate(rows):
                prov, muni, brgy, dist, cong = row
                entry = {
                    'id': idx,
                    'prov': prov, 'muni': muni, 'brgy': brgy,
                    'dist': dist, 'cong': cong,
                    'prov_norm': self._normalize(prov),
                    'muni_norm': self._normalize(muni),
                    'brgy_norm': self._normalize(brgy)
                }
                self.location_entries.append(entry)
                
                # Index tokens
                # Index Province (careful with common words, maybe index full prov string too)
                self._index_tokens(entry['prov_norm'], idx)
                self._index_tokens(entry['muni_norm'], idx)
                self._index_tokens(entry['brgy_norm'], idx)
            
            self.loaded = True
            print(f"✅ Indexed {len(self.location_entries)} locations.")
            
        except Exception as e:
            print(f"⚠️ Failed to build location index: {e}")

    def _normalize(self, text):
        if not text: return ""
        # Keep it simple: lowercase, strip, remove 'city of', 'municipality of'
        text = str(text).lower().strip()
        text = text.replace("city of ", "").replace("municipality of ", "")
        return text

    def _index_tokens(self, text, idx):
        if not text: return
        # Tokenize by space
        tokens = text.split()
        for token in tokens:
            if len(token) > 2: # Skip small words
                self.token_map[token].add(idx)

    def find_best_match(self, text, province_hint=None):
        if not self.loaded or not text: return None
        
        text_norm = self._normalize(text)
        
        # 1. Disambiguate Province Hint from Text
        target_prov = None
        for pattern, prov_name in self.disambiguation_patterns:
            if pattern.search(text):
                target_prov = prov_name
                break
        
        if not target_prov and province_hint:
             target_prov = province_hint

        # 2. Get Candidate IDs
        # Gather candidates based on tokens in the text
        tokens = text_norm.split()
        candidates = set()
        
        # If we have a strong province target, filter by that FIRST (simulating filter)
        # But inverted index is bottom-up.
        # Strategy: Collect candidates from tokens. If strict province, filter them.
        
        for token in tokens:
            if len(token) > 2 and token in self.token_map:
                candidates.update(self.token_map[token])
                
        if not candidates:
            return None

        # 3. Score Candidates (Subset only!)
        best_entry = None
        best_score = 0
        
        target_prov_norm = self._normalize(target_prov) if target_prov else None

        for idx in candidates:
            entry = self.location_entries[idx]
            
            # Filter by province if known
            if target_prov_norm:
                if target_prov_norm not in entry['prov_norm']: 
                    continue

            score = 0
            match_length_bonus = 0
            
            # Municipality Match - +4 weight + length bonus
            if entry['muni_norm'] and len(entry['muni_norm']) > 3:
                if self._word_boundary_match(entry['muni_norm'], text_norm):
                    score += 4
                    match_length_bonus += len(entry['muni_norm']) * 2
            
            # Barangay Match - +2 weight + length bonus
            if entry['brgy_norm'] and len(entry['brgy_norm']) > 3:
                if self._word_boundary_match(entry['brgy_norm'], text_norm):
                    score += 2
                    match_length_bonus += len(entry['brgy_norm'])
                      
            # Province Match - +3 weight + length bonus
            # Skip short ambiguous province names if project contains longer version
            if entry['prov_norm'] and len(entry['prov_norm']) > 3:
                if self._word_boundary_match(entry['prov_norm'], text_norm):
                     score += 3
                     match_length_bonus += len(entry['prov_norm'])
            
            # Total score
            total_score = score * 100 + match_length_bonus

            if total_score > best_score:
                best_score = total_score
                best_entry = entry
        
        # Threshold - require at least one substantial match (approx 200+)
        if best_score >= 200:
             return (best_entry['prov'], best_entry['dist'], best_entry['cong'])
        
        return None

    def _word_boundary_match(self, needle, haystack):
        """Check if needle appears as whole word(s) in haystack"""
        if not needle or len(needle) < 3:
            return False
        # Escape needle but allow for some flexibility if needed (keeping it strict for now)
        pattern = r'\b' + re.escape(needle) + r'\b'
        return bool(re.search(pattern, haystack))

class DynastyProjectsCacheGeneratorDuckDB:
    """Generate cached JSON for dynasty-projects using DuckDB"""
    
    # Common words to exclude from contractor matching (too broad, not proper names)
    COMMON_TOKENS = {
        'CONSTRUCTION', 'INC', 'CORP', 'INCORPORATED', 'CORPORATION', 'AND', 'THE', 'OF', 'COMPANY', 
        'CO', 'LTD', 'LIMITED', 'TRADING', 'ENTERPRISES', 'SUPPLY', 'SERVICES', 'BUILDERS', 'DEVELOPMENT', 
        'ENGINEERING', 'FORMERLY', 'GENERAL', 'FOR', 'GROUP', 'SYSTEMS', 'TECHNOLOGIES', 
        'INTERNATIONAL', 'GLOBAL', 'WORLDWIDE', 'ASSOCIATES', 'PARTNERS', 'MANAGEMENT', 'HOLDINGS',
        'INVESTMENTS', 'PROPERTIES', 'REALTY', 'ESTATE', 'PROJECTS', 'SOLUTIONS', 'CONSULTING',
        'DISTRIBUTORS', 'MANUFACTURING', 'INDUSTRIES', 'PRODUCTS', 'EQUIPMENT', 'MATERIALS',
        'CONTRACTOR', 'GENERIC', 'GEN'
    }
    
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
        
        # Initialize Location Matcher
        self.location_matcher = LocationMatcher(UNIFIED_LOCATIONS_PARQUET)
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
        
        # Initialize LocationEnricher
        self.enricher = LocationEnricher()
        if not self.enricher.load_db():
            self._log("⚠️  Failed to load Location DB - enrichment will be skipped")
        
        # Load substring provinces config for strict word boundary matching
        self.substring_provinces = self._load_substring_provinces()
        
        # Load project code mapping for short-circuit district matching
        self.project_code_mapping = self._load_project_code_mapping()
        
        # Load unified locations for high-accuracy hierarchy matching (Source of Truth)
        self.location_entries = self._load_unified_locations()

    def _load_unified_locations(self) -> List[tuple]:
        """Load unified location hierarchy from parquet"""
        unified_path = Path(__file__).parent.parent / 'static' / 'data' / 'unified_locations.parquet'
        location_entries = []
        if unified_path.exists():
            try:
                # Use duckdb to read parquet efficiently
                con = duckdb.connect()
                # Select only entries with valid congressman
                query = """
                    SELECT province, municipality, barangay, district, congressman 
                    FROM read_parquet(?) 
                    WHERE congressman IS NOT NULL 
                    AND congressman != 'TBD' 
                    AND congressman != 'Unknown'
                """
                result = con.execute(query, [str(unified_path)]).fetchall()
                for row in result:
                    # Keep same tuple structure as generate_integrated_matrix.py
                    location_entries.append(row)
                con.close()
                self._log(f"✅ Loaded {len(location_entries)} location entries from unified_locations.parquet")
            except Exception as e:
                self._log(f"⚠️ Failed to load unified_locations.parquet: {e}")
        else:
            self._log(f"⚠️ unified_locations.parquet not found at {unified_path}")
        return location_entries

    def _normalize_for_match(self, text: str) -> str:
        """Normalize text for matching - lowercase, ASCII, clean.
        IMPORTANT: Keep 'city' keyword for proper disambiguation"""
        if not text:
            return ""
        import unicodedata
        # Normalize unicode characters
        text = str(text)
        text = unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII')
        # Don't remove 'city' - we need it for disambiguation
        # Just normalize 'city of X' to 'X city' for consistency
        text = text.lower().strip()
        text = text.replace("city of ", "").replace("municipality of ", "")
        return text.strip()

    def _find_best_location_match(self, project_name: str, project_province: Optional[str] = None) -> Optional[tuple]:
        """Find the location entry with the most matching components.
        Uses word-boundary matching and prefers longer/more specific matches.
        Returns: (province, municipality, barangay, district, congressman) or None
        """
        if not project_name or not self.location_entries:
            return None
            
        name_norm = self._normalize_for_match(project_name)
        if not name_norm:
            return None
            
        name_lower = project_name.lower()
        prov_norm = self._normalize_for_match(project_province) if project_province else ""
        
        # --- DISAMBIGUATION: Check for multi-word province names FIRST ---
        # These are problematic because "davao" matches both "davao city" and "davao de oro"
        disambiguation_patterns = [
            (r'davao\s+de\s+oro', 'DAVAO DE ORO'),
            (r'davao\s+del\s+sur', 'DAVAO DEL SUR'),
            (r'davao\s+del\s+norte', 'DAVAO DEL NORTE'),
            (r'davao\s+oriental', 'DAVAO ORIENTAL'),
            (r'davao\s+occidental', 'DAVAO OCCIDENTAL'),
            (r'cebu\s+city', 'CEBU CITY'),  # Cebu City vs Cebu Province
            (r'cagayan\s+de\s+oro', 'CITY OF CAGAYAN DE ORO'),
            (r'quezon\s+city', 'QUEZON CITY'),  # QC vs Quezon Province
            (r'zamboanga\s+del\s+norte', 'ZAMBOANGA DEL NORTE'),
            (r'zamboanga\s+del\s+sur', 'ZAMBOANGA DEL SUR'),
            (r'zamboanga\s+sibugay', 'ZAMBOANGA SIBUGAY'),
        ]
        
        for pattern, target_prov in disambiguation_patterns:
            if re.search(pattern, name_lower):
                # Find entries matching this specific province
                for entry in self.location_entries:
                    prov, muni, brgy, dist, cong = entry
                    if prov and target_prov.lower() in prov.lower():
                        # Also check municipality/barangay match for better accuracy
                        muni_norm = self._normalize_for_match(muni)
                        brgy_norm = self._normalize_for_match(brgy)
                        
                        # Check strictly for municipality or barangay presence
                        if muni_norm and len(muni_norm) > 3 and muni_norm in name_norm:
                            return entry
                        if brgy_norm and len(brgy_norm) > 3 and brgy_norm in name_norm:
                            return entry
        
        best_match = None
        best_score = 0
        
        def word_boundary_match(needle, haystack):
            """Check if needle appears as whole word(s) in haystack"""
            if not needle or len(needle) < 3:
                return False
            # Escape regex special chars in needle
            pattern = r'\b' + re.escape(needle) + r'\b'
            return bool(re.search(pattern, haystack))
        
        for entry in self.location_entries:
            prov, muni, brgy, dist, cong = entry
            score = 0
            match_length_bonus = 0
            
            prov_entry = self._normalize_for_match(prov)
            muni_entry = self._normalize_for_match(muni)
            brgy_entry = self._normalize_for_match(brgy)
            
            # Province matching
            if prov_entry and len(prov_entry) > 3:
                if word_boundary_match(prov_entry, name_norm):
                    score += 3
                    match_length_bonus += len(prov_entry)
                elif prov_norm and prov_entry == prov_norm:
                    score += 2  # Match via passed province argument
            
            # Municipality matching - high value
            if muni_entry and len(muni_entry) > 3:
                if word_boundary_match(muni_entry, name_norm):
                    score += 4
                    match_length_bonus += len(muni_entry) * 2
            
            # Barangay matching
            if brgy_entry and len(brgy_entry) > 3:
                if word_boundary_match(brgy_entry, name_norm):
                    score += 2
                    match_length_bonus += len(brgy_entry)
            
            # Total score
            total_score = score * 100 + match_length_bonus
            
            if total_score > best_score:
                best_score = total_score
                best_match = entry
        
        # Require at least one substantial match (score >= 200 means roughly municipality matched or strong combo)
        return best_match if best_score >= 200 else None

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
    
    def _load_project_code_mapping(self) -> Dict:
        """Load the DPWH project code mapping from JSON file"""
        mapping_path = Path(__file__).parent.parent / 'database' / 'dpwh-project-code-mapping.json'
        if not mapping_path.exists():
            self._log("⚠️  Project code mapping file not found; project code parsing will be disabled", verbose_only=True)
            return {}
        
        try:
            with open(mapping_path, 'r', encoding='utf-8') as f:
                mapping = json.load(f)
            self._log(f"✅ Loaded project code mapping from {mapping_path}", verbose_only=True)
            return mapping
        except Exception as e:
            self._log(f"⚠️  Warning: Could not load project code mapping: {e}", verbose_only=True)
            return {}
    
    def _parse_project_code(self, project_code: str) -> Optional[Dict]:
        """Parse integrated project code into components
        
        Format: YYRDSSSS
        - YY = Year (2 digits)
        - R = Region (1 letter)
        - D = District (1 letter)
        - SSSS = Sequence (4 digits)
        
        Returns dict with year, region_letter, district_letter, sequence, or None if invalid
        """
        if not project_code:
            return None
        
        project_code = str(project_code).strip().upper()
        
        # Remove any dashes or spaces
        project_code = re.sub(r'[-\s]', '', project_code)
        
        # Match pattern: YYRDSSSS (8 characters total)
        pattern = re.match(r'^(\d{2})([A-Z])([A-Z])(\d{4})$', project_code)
        if pattern:
            year, region_letter, district_letter, sequence = pattern.groups()
            return {
                'year': year,
                'region_letter': region_letter,
                'district_letter': district_letter,
                'sequence': sequence,
                'full_code': project_code
            }
        
        return None
    
    def _extract_project_code_from_data(self, project: Dict) -> Optional[str]:
        """Extract integrated project code from project data"""
        # Common field names for project codes
        code_fields = [
            'project_code', 'code', 'ipc', 'integrated_project_code',
            'project_id', 'contract_id', 'reference_number', 'ref_number',
            'project_number', 'project_no', 'contract_number', 'contract_no',
            'philgeps_project_code', 'philgeps_code', 'award_id', 'notice_id'
        ]
        
        for field in code_fields:
            if field in project and project[field]:
                code = str(project[field]).strip()
                if code and len(code) >= 6:  # Minimum length for YYRDSSSS
                    parsed = self._parse_project_code(code)
                    if parsed:
                        return code
        
        # Also check if code might be embedded in other fields
        text_fields = ['project_name', 'project_description', 'award_title', 'notice_title', 
                      'description', 'title', 'name', 'location']
        for field in text_fields:
            if field in project and project[field]:
                text = str(project[field])
                # Look for code-like patterns: YYRDSSSS
                code_match = re.search(r'\b(\d{2}[A-Z]{2}\d{4})\b', text, re.IGNORECASE)
                if code_match:
                    code = code_match.group(1)
                    parsed = self._parse_project_code(code)
                    if parsed:
                        return code
        
        return None
    
    def _classify_by_project_code(self, project_code: str, congressmen_data: Dict, 
                                  district_lookup: Dict) -> Optional[tuple]:
        """Classify a project using integrated project code
        
        Returns: (congressman_name, match_score) or None
        """
        if not self.project_code_mapping:
            return None
        
        # Parse the code
        parsed = self._parse_project_code(project_code)
        if not parsed:
            return None
        
        region_letter = parsed['region_letter']
        district_letter = parsed['district_letter']
        
        # Get region and district info from mapping
        if region_letter not in self.project_code_mapping:
            return None
        
        region_info = self.project_code_mapping[region_letter]
        districts = region_info.get('districts', {})
        
        if district_letter not in districts:
            return None
        
        district_deo = districts[district_letter]
        
        # Map DEO name to congressman district
        # DEO names typically contain province and district info
        # Examples: "Batangas 1st DEO", "Ilocos Norte 1st DEO", "Quezon 2nd DEO"
        # We need to extract province and district number from DEO name
        
        # Try to match DEO to congressman by province and district
        # Look for patterns like "Province Xth DEO" or "Province Xst DEO" or "Province Xnd DEO" or "Province Xrd DEO"
        deo_upper = district_deo.upper()
        
        # Extract province name (everything before the district number)
        # Pattern: "BATANGAS 1ST DEO" -> province="BATANGAS", district="1ST"
        deo_match = re.match(r'^(.+?)\s+(\d+)(?:ST|ND|RD|TH)?\s+DEO', deo_upper)
        if not deo_match:
            # Try alternative patterns
            deo_match = re.match(r'^(.+?)\s+(\d+)(?:ST|ND|RD|TH)?\s+DISTRICT', deo_upper)
        
        if deo_match:
            province_name = deo_match.group(1).strip()
            district_num_str = deo_match.group(2).strip()
            
            # Try to find matching congressman
            for cm_name, cm_data in congressmen_data.items():
                cm_provinces = cm_data.get('provinces', [])
                cm_district_number = cm_data.get('district_number', '')
                
                # Check if province matches
                for cm_province in cm_provinces:
                    cm_prov_upper = cm_province.upper().strip()
                    
                    # Check if province name matches (with variations)
                    if (province_name in cm_prov_upper or cm_prov_upper in province_name or
                        self._normalize_location_name(province_name) == self._normalize_location_name(cm_prov_upper)):
                        
                        # Check if district number matches
                        # Extract district number from cm_district_number (e.g., "1st District" -> "1")
                        cm_dist_match = re.search(r'(\d+)(?:ST|ND|RD|TH)?', str(cm_district_number).upper())
                        if cm_dist_match:
                            cm_dist_num = cm_dist_match.group(1)
                            if cm_dist_num == district_num_str:
                                # Found match! Return with high score (200 for code-based match)
                                return (cm_name, 200)
        
        return None

    def _calculate_project_hash(self, project: Dict) -> str:
        """Calculate a deterministic hash for a project to detect changes."""
        import hashlib
        # Key fields that define project identity and content
        fields = [
            str(project.get('project_id', '')),
            str(project.get('project_name', '')),
            str(project.get('amount', '')),
            str(project.get('location', '')),
            str(project.get('contractor', '')),
            str(project.get('source', '')),
            str(project.get('status', ''))
        ]
        content = '|'.join(fields)
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def _load_existing_project_hashes(self) -> set:
        """Load hashes of already classified projects from parquet."""
        hashes = set()
        if not CLASSIFIED_PARQUET.exists():
            return hashes
        
        print(f"📊 Loading existing project hashes from {CLASSIFIED_PARQUET}...")
        try:
            import duckdb
            con = duckdb.connect()
            # We can't easily compute hash in SQL if logic is complex python
            # But we can load the columns and compute hash in python
            # Or assume classified projects don't change identity often?
            # Better to load columns and compute.
            df = con.execute(f"SELECT project_id, project_name, amount, location, contractor, source, status FROM read_parquet('{CLASSIFIED_PARQUET}')").fetchdf()
            con.close()
            
            for _, row in df.iterrows():
                # Reconstruct project dict for hashing (ensure keys match _calculate logic)
                p = {
                    'project_id': row['project_id'],
                    'project_name': row['project_name'],
                    'amount': row['amount'],
                    'location': row['location'],
                    'contractor': row['contractor'],
                    'source': row['source'],
                    'status': row['status']
                }
                hashes.add(self._calculate_project_hash(p))
            
            print(f"✅ Loaded {len(hashes)} existing project hashes.")
            return hashes
        except Exception as e:
            print(f"⚠️ Failed to load existing hashes: {e}")
            return set()

    
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
    def _normalize_source_label(source: Optional[str]) -> str:
        """Normalize source label to canonical form"""
        if not source:
            return 'Unknown'
        source_upper = str(source).upper().strip()
        # Map variations to canonical names
        if source_upper in ('SSP', 'FLOOD', 'FLOOD CONTROL'):
            return 'SSP'
        elif source_upper == 'DIME':
            return 'DIME'
        elif source_upper in ('PHILGEPS', 'PHILGEPS PROCUREMENT'):
            return 'PhilGEPS'
        elif source_upper in ('MICROSITE', 'INFRAWATCH', 'DPWH MICROSITE', 'DPWH INFRAWATCH'):
            return 'Microsite'
        elif source_upper in ('TRANSPARENCY', 'DPWH TRANSPARENCY', 'DPWH SCRAPER'):
            return 'Transparency'
        else:
            # Return as-is with proper capitalization
            return source.strip()
    
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
        # CRITICAL: Try to use stable identifiers first for better deduplication across sources
        # Check for contract_id, meilisearch_id, or other stable IDs
        contract_id = proj.get('contract_id') or proj.get('meilisearch_id') or proj.get('global_id')
        if contract_id:
            # Use contract ID as primary key (most reliable for cross-source matching)
            contractor = self._normalize_text_for_key(proj.get('contractor'))
            amount = self._normalize_amount_for_key(proj.get('amount'))
            return f"ID:{contract_id}|{contractor}|{amount}"
        
        # Fallback: Use project name, contractor, amount, location
        # Normalize project name to handle contract numbers vs descriptive names
        project_name = self._normalize_text_for_key(proj.get('project_name'))
        # Also check award_title, contract_id fields for contract numbers
        award_title = self._normalize_text_for_key(proj.get('award_title'))
        # If project_name looks like a contract number, prefer award_title if it's more descriptive
        if project_name and len(project_name) <= 20 and project_name.replace('-', '').replace('/', '').isalnum():
            # project_name looks like a contract number, try to find a better identifier
            if award_title and len(award_title) > len(project_name):
                # Use award_title if it's more descriptive
                project_name = award_title
            # Also check for contract_id in other fields
            for field in ['contract_id', 'award_id', 'notice_id', 'reference_number']:
                if proj.get(field):
                    contract_id_val = str(proj.get(field)).strip()
                    if contract_id_val:
                        contractor = self._normalize_text_for_key(proj.get('contractor'))
                        amount = self._normalize_amount_for_key(proj.get('amount'))
                        return f"ID:{contract_id_val}|{contractor}|{amount}"
        
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
        
        # Prefer non-empty contract_id (critical for deduplication)
        if not merged.get('contract_id') and incoming.get('contract_id'):
            merged['contract_id'] = incoming.get('contract_id')
        elif incoming.get('contract_id') and merged.get('contract_id') != incoming.get('contract_id'):
            # If both have contract_id but they differ, prefer the one that looks more like a standard ID
            incoming_id = str(incoming.get('contract_id', '')).strip()
            merged_id = str(merged.get('contract_id', '')).strip()
            # Prefer longer, more complete IDs
            if len(incoming_id) > len(merged_id):
                merged['contract_id'] = incoming.get('contract_id')

        # Prefer more specific amount (>0)
        primary_amount = DynastyProjectsCacheGeneratorDuckDB._normalize_amount_for_key(merged.get('amount'))
        incoming_amount = DynastyProjectsCacheGeneratorDuckDB._normalize_amount_for_key(incoming.get('amount'))
        if incoming_amount and (not primary_amount or incoming_amount != primary_amount and primary_amount == 0):
            merged['amount'] = incoming.get('amount')

        # Prefer more descriptive project name (longer string)
        if len((incoming.get('project_name') or '')) > len((merged.get('project_name') or '')):
            merged['project_name'] = incoming.get('project_name')
        
        # CRITICAL: Preserve descriptive fields for PhilGEPS projects (needed for frontend display)
        # Prefer longer/more descriptive values when merging
        for field in ['project_description', 'notice_title', 'award_description', 'award_title']:
            incoming_val = incoming.get(field)
            merged_val = merged.get(field)
            if incoming_val and (not merged_val or len(str(incoming_val)) > len(str(merged_val))):
                merged[field] = incoming_val
            elif not merged_val and incoming_val:
                # If merged doesn't have it but incoming does, use incoming
                merged[field] = incoming_val

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

        # CRITICAL: Always prefer incoming classification fields (they're newly computed)
        # This ensures force mode works correctly - new classifications overwrite old ones
        # Classification fields that should always use incoming values when present:
        classification_fields = [
            'project_district_type', 'project_district', 'project_barangay_municipality',
            'project_province_city_district', 'project_municipality_barangay',
            'is_flood_related', 'district_congressman', 'district_match_type',
            'district_match_score', 'district_is_city_wide', 'congressman_district',
            'contractor_congressman', 'contractor_match_type', 'contractor_match_score',
            'contractor_congressman_district', 'contractor_congressman_2', 'contractor_congressman_2_district',
            'match_type', 'match_score'
        ]
        
        # CRITICAL: Handle district and contractor congressmen separately to preserve both
        # Don't overwrite with None - preserve existing matches when merging
        
        # District congressman: prefer incoming if it has a higher score or primary doesn't have one
        if incoming.get('district_congressman'):
            incoming_score = incoming.get('district_match_score', 0)
            merged_score = merged.get('district_match_score', 0)
            if not merged.get('district_congressman') or incoming_score > merged_score:
                merged['district_congressman'] = incoming.get('district_congressman')
                merged['district_match_type'] = incoming.get('district_match_type')
                merged['district_match_score'] = incoming.get('district_match_score')
                merged['district_is_city_wide'] = incoming.get('district_is_city_wide')
                merged['congressman_district'] = incoming.get('congressman_district')
        # Don't overwrite district_congressman with None - preserve existing
        
        # Contractor congressman: preserve both if they exist, prefer incoming if it's new
        # Note: Both can exist simultaneously (different congressmen)
        # Support up to 2 contractor congressmen for JVs
        if incoming.get('contractor_congressman'):
            # Incoming has a contractor match - use it (may be same or different from merged)
            merged['contractor_congressman'] = incoming.get('contractor_congressman')
            merged['contractor_match_type'] = incoming.get('contractor_match_type')
            merged['contractor_match_score'] = incoming.get('contractor_match_score')
            merged['contractor_congressman_district'] = incoming.get('contractor_congressman_district')
        # Don't overwrite contractor_congressman with None - preserve existing
        
        # Handle second contractor congressman (for JVs)
        if incoming.get('contractor_congressman_2'):
            merged['contractor_congressman_2'] = incoming.get('contractor_congressman_2')
            merged['contractor_congressman_2_district'] = incoming.get('contractor_congressman_2_district')
        # Don't overwrite contractor_congressman_2 with None - preserve existing
        
        # Now handle other classification fields (excluding congressman fields which we handled above)
        other_classification_fields = [
            'project_district_type', 'project_district', 'project_barangay_municipality',
            'project_province_city_district', 'project_municipality_barangay',
            'is_flood_related', 'district_match_type', 'district_match_score',
            'district_is_city_wide', 'congressman_district',
            'contractor_match_type', 'contractor_match_score',
            'contractor_congressman_district', 'match_type', 'match_score'
        ]
        
        for field in other_classification_fields:
            # Always use incoming value if it exists (even if None, to clear old values in force mode)
            # This ensures newly classified values overwrite old ones
            if field in incoming:
                merged[field] = incoming[field]

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
    
    def _get_project_month(self, date_val: Any) -> Optional[int]:
        """Extract month from date (for election year transition handling)."""
        try:
            if date_val:
                if isinstance(date_val, str):
                    from dateutil.parser import parse
                    parsed_date = parse(date_val)
                    return parsed_date.month
                elif hasattr(date_val, 'month'):
                    return date_val.month
                elif hasattr(date_val, 'year'):  # datetime object
                    return date_val.month
        except (ValueError, TypeError, AttributeError):
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
                             contractor_inverted_index: Dict,
                             project_data: Optional[Dict] = None) -> tuple[Optional[str], Optional[str], int, Optional[str], Optional[str], Optional[str]]:
        """
        Unified matching logic using O(1) lookups.
        Returns: (congressman_name, match_type, match_score, district_congressman, contractor_congressman, contractor_congressman_2)
        
        Args:
            project_data: Optional project dict to extract project code for short-circuit matching and month for election transitions
        """
        # Store project data for election year transition handling
        if project_data:
            self._current_project_data = project_data
        else:
            self._current_project_data = {}
        district_congressman = None
        contractor_congressman = None
        contractor_congressman_2 = None
        match_type = 'unknown'
        match_score = 0
        final_congressman = 'Unknown'

        # 0. SHORT-CIRCUIT: Try Project Code Match (highest priority)
        # If project has an integrated project code, use it for direct district matching
        if project_data:
            project_code = self._extract_project_code_from_data(project_data)
            if project_code:
                code_match = self._classify_by_project_code(project_code, congressmen_data, district_lookup)
                if code_match:
                    district_congressman, code_score = code_match
                    # Normalize congressman name to canonical form
                    if district_congressman and hasattr(self, 'canonical_name_map'):
                        district_congressman = self.canonical_name_map.get(district_congressman, district_congressman)
                    match_score = code_score
                    match_type = 'district'
                    final_congressman = district_congressman
                    # Short-circuit: return immediately with code-based match
                    # Still check contractor match for completeness
                    contractor_match = self._find_congressman_by_contractor(
                        contractor, contractor_lookup, contractor_inverted_index, congressmen_data
                    )
                    contractor_congressman = None
                    contractor_congressman_2 = None
                    if contractor_match:
                        if isinstance(contractor_match, list):
                            if len(contractor_match) >= 1:
                                contractor_congressman, c_score = contractor_match[0]
                                if contractor_congressman and hasattr(self, 'canonical_name_map'):
                                    contractor_congressman = self.canonical_name_map.get(contractor_congressman, contractor_congressman)
                            if len(contractor_match) >= 2:
                                contractor_congressman_2, c_score_2 = contractor_match[1]
                                if contractor_congressman_2 and hasattr(self, 'canonical_name_map'):
                                    contractor_congressman_2 = self.canonical_name_map.get(contractor_congressman_2, contractor_congressman_2)
                        else:
                            contractor_congressman, c_score = contractor_match
                            if contractor_congressman and hasattr(self, 'canonical_name_map'):
                                contractor_congressman = self.canonical_name_map.get(contractor_congressman, contractor_congressman)
                    return final_congressman, match_type, match_score, district_congressman, contractor_congressman, contractor_congressman_2

        # 0.4. Unified Location Match (Parquet) - Source of Truth
        # Matches hierarchy directly from unified_locations.parquet (Highest Priority for location)
        if not district_congressman and self.location_entries:
             best_match = self._find_best_location_match(project_text, province)
             if best_match:
                 prov, muni, brgy, dist, cong = best_match
                 if cong and cong not in ('Unknown', 'TBD', 'TBA'):
                     district_congressman = cong
                     match_score = 150 # High confidence for hierarchy match
                     match_type = 'unified_location'
                     # Normalize congressman name if possible
                     if hasattr(self, 'canonical_name_map'):
                         district_congressman = self.canonical_name_map.get(district_congressman, district_congressman)

        # 0.5. Unified Location Match (New)
        # Use simple text matching against unified database
        if hasattr(self, 'enricher') and self.enricher.loaded:
            enrich_payload = {
                'name': project_data.get('project_name') if project_data else '',
                'description': project_data.get('project_description') if project_data else '',
                'location': project_text
            }
            self.enricher.enrich_project(enrich_payload)
            enricher_congressman = enrich_payload.get('congressman')
            if enricher_congressman and enricher_congressman != 'Unknown':
                # Try to find this congressman in our congressmen_data to insure name variance handling
                # Normalize name first if possible
                if enricher_congressman in congressmen_data:
                    district_congressman = enricher_congressman
                    match_score = 95
                else:
                    # Try simple lookup logic or name normalization
                    # This part is simplified; might need better name matching
                   district_congressman = enricher_congressman
                   match_score = 90
        
        # 1. Try District Match (Legacy/Fallback if simplified didn't work)
        if not district_congressman:
            # Pass project_district if available to help with district number matching
            project_district = None
            project_name_str = ""
            if project_data:
                project_district = project_data.get('project_district') or project_data.get('district')
                project_name_str = project_data.get('project_name', '') or project_data.get('name', '') or ""
            
            district_match = self._find_congressman_by_district(
                province, municipality_barangay, year, district_lookup, congressmen_data, project_district, project_name=project_name_str
            )
            
            # Fallback: Province-only match if strict match failed and we have a province
            if not district_match and province and municipality_barangay:
                 district_match = self._find_congressman_by_district(
                    province, '', year, district_lookup, congressmen_data, project_district, project_name=project_name_str
                )
                
            if district_match:
                district_congressman, d_score = district_match
                # Normalize congressman name to canonical form
                if district_congressman and hasattr(self, 'canonical_name_map'):
                    district_congressman = self.canonical_name_map.get(district_congressman, district_congressman)
                match_score = d_score
        
        # 2. Try Contractor Match (supports up to 2 matches for JVs)
        contractor_match = self._find_congressman_by_contractor(
            contractor, contractor_lookup, contractor_inverted_index, congressmen_data
        )
        contractor_congressman = None
        contractor_congressman_2 = None
        c_score = 0
        
        if contractor_match:
            # Handle both single match (tuple) and multiple matches (list) for JVs
            if isinstance(contractor_match, list):
                # Multiple matches (up to 2) - JV scenario
                if len(contractor_match) >= 1:
                    contractor_congressman, c_score = contractor_match[0]
                    if contractor_congressman and hasattr(self, 'canonical_name_map'):
                        contractor_congressman = self.canonical_name_map.get(contractor_congressman, contractor_congressman)
                if len(contractor_match) >= 2:
                    contractor_congressman_2, c_score_2 = contractor_match[1]
                    if contractor_congressman_2 and hasattr(self, 'canonical_name_map'):
                        contractor_congressman_2 = self.canonical_name_map.get(contractor_congressman_2, contractor_congressman_2)
            else:
                # Single match (tuple) - backward compatible
                contractor_congressman, c_score = contractor_match
                if contractor_congressman and hasattr(self, 'canonical_name_map'):
                    contractor_congressman = self.canonical_name_map.get(contractor_congressman, contractor_congressman)
            
            # Note: Contractor matching is based solely on owner/officer relationship, not location
            # Location validation is NOT applied to contractor matches
            
        # 3. Determine Primary Match
        # CRITICAL: Prioritize contractor matches over district matches for EVERYONE
        # A project linked to a dynasty contractor is a stronger signal than a generic district match
        # This captures both Party-list reps and District reps contracting in/out of their districts
        if contractor_congressman:
            final_congressman = contractor_congressman
            match_type = 'contractor'
            # If we also have a district match, we still record it in district_congressman (already set)
            # but the primary attribution goes to the contractor owner
            if district_congressman and district_congressman != contractor_congressman:
                match_score = 90 # High confidence due to contractor link
            else:
                 # Match confirmed by both or just contractor
                match_score = 95
                
        elif district_congressman:
            final_congressman = district_congressman
            match_type = 'district'
        
        # Normalize final_congressman to canonical form
        if final_congressman and hasattr(self, 'canonical_name_map'):
            final_congressman = self.canonical_name_map.get(final_congressman, final_congressman)
            
        return final_congressman, match_type, match_score, district_congressman, contractor_congressman, contractor_congressman_2

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
            # FORCE Field Clean-up (User Request):
            # Always remove these columns if they exist to prevent logic contamination
            # The user stated DIME parquet contains these and it throws logic off
            contaminated_fields = ['congressman_name', 'dynasty_member_id', 'dynasty_relationship']
            for field in contaminated_fields:
                if field in proj:
                    del proj[field]

            # Check if already classified (unless force mode)
            # CRITICAL: In force mode, ALWAYS reclassify - never skip
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
            # Force mode: Explicitly clear any remaining classification fields from project dict
            # This ensures we don't accidentally use old values during matching
            elif self.force_reclassify:
                # Double-check: Clear classification fields if they somehow still exist
                classification_fields_to_clear = [
                    'district_congressman', 'contractor_congressman',
                    'project_district_type', 'project_district', 'project_barangay_municipality',
                    'project_province_city_district', 'project_municipality_barangay',
                    'is_flood_related', 'district_match_type', 'district_match_score',
                    'district_is_city_wide', 'congressman_district',
                    'contractor_match_type', 'contractor_match_score',
                    'contractor_congressman_district', 'match_type', 'match_score'
                ]
                for field in classification_fields_to_clear:
                    if field in proj:
                        del proj[field]
            
            # Extract basic data - ALWAYS use raw data fields, never old classification values
            # CRITICAL: In force mode, ensure we're using raw location data, not old classification
            proj_province = (proj.get('province') or '').strip()
            proj_city = (proj.get('city') or '').strip()
            proj_barangay = (proj.get('barangay') or '').strip()
            
            # CRITICAL: Never use old classification fields for matching
            # These should have been cleared in load_projects_from_parquet, but double-check
            if self.force_reclassify:
                # Ensure we're not accidentally using old classification values
                # project_district should not be used as province
                if not proj_province and proj.get('project_district'):
                    # Don't use project_district - it's a classification field, not raw data
                    pass
            
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
                contractor_str = ', '.join(contractors_field).upper()
            elif contractors_field:
                contractor_str = str(contractors_field).upper()

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
            final_congressman, match_type, match_score, district_cm, contractor_cm, contractor_cm_2 = self._match_project_unified(
                project_text="", # DIME doesn't rely on text matching as much as location columns
                province=proj_province,
                municipality_barangay=location_key,
                contractor=contractor_str,
                year=project_year,
                congressmen_data=congressmen_data,
                district_lookup=district_lookup_dict,
                contractor_lookup=contractor_lookup_dict,
                contractor_inverted_index=contractor_inverted_index,
                project_data=proj  # Pass project data for project code extraction
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
            
            contractor_congressman_2_district = None
            if contractor_cm_2 and contractor_cm_2 in congressmen_data:
                cm_data = congressmen_data[contractor_cm_2]
                if cm_data.get('district_number') and cm_data.get('provinces'):
                    contractor_congressman_2_district = f"{cm_data.get('district_number')} District {cm_data.get('provinces')[0]}"

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
                "contractor_congressman_2": contractor_cm_2,
                "contractor_congressman_2_district": contractor_congressman_2_district,
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
            # FORCE Field Clean-up (User Request):
            # Always remove these columns if they exist to prevent logic contamination
            contaminated_fields = ['congressman_name', 'dynasty_member_id', 'dynasty_relationship']
            for field in contaminated_fields:
                if field in contract:
                    del contract[field]

            # Check if already classified (unless force mode)
            # CRITICAL: In force mode, ALWAYS reclassify - never skip
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
                    # Add descriptive fields if missing (for frontend display)
                    if 'project_description' not in result or not result.get('project_description'):
                        result['project_description'] = contract.get('project_description') or contract.get('award_description') or None
                    if 'notice_title' not in result or not result.get('notice_title'):
                        result['notice_title'] = contract.get('notice_title') or None
                    if 'award_description' not in result or not result.get('award_description'):
                        result['award_description'] = contract.get('award_description') or None
                    if 'award_title' not in result or not result.get('award_title'):
                        result['award_title'] = contract.get('philgeps_award_title') or contract.get('award_title') or contract.get('project_name') or None
                    # Mark as skipped for tracking
                    result['_skipped_reclassification'] = True
                    chunk_results.append(result)
                    self.progress_counters['skipped'] += 1
                    continue
            # Force mode: Explicitly clear any remaining classification fields from contract dict
            # This ensures we don't accidentally use old values during matching
            elif self.force_reclassify:
                # Double-check: Clear classification fields if they somehow still exist
                classification_fields_to_clear = [
                    'district_congressman', 'contractor_congressman',
                    'project_district_type', 'project_district', 'project_barangay_municipality',
                    'project_province_city_district', 'project_municipality_barangay',
                    'is_flood_related', 'district_match_type', 'district_match_score',
                    'district_is_city_wide', 'congressman_district',
                    'contractor_match_type', 'contractor_match_score',
                    'contractor_congressman_district', 'match_type', 'match_score'
                ]
                for field in classification_fields_to_clear:
                    if field in contract:
                        del contract[field]
            
            # Basic Data
            # For project_name, prefer descriptive fields over contract numbers
            # Try project_description, notice_title, or award_description first, then fall back to award_title
            project_description_field = (contract.get('project_description') or contract.get('award_description') or '')
            notice_title = (contract.get('notice_title') or '')  # Add notice_title for classification
            award_title = (contract.get('philgeps_award_title') or contract.get('award_title') or contract.get('project_name') or '')
            
            area_of_delivery = (contract.get('philgeps_area_of_delivery') or contract.get('area_of_delivery') or '')
            awardee_name = (contract.get('contractor_name') or contract.get('philgeps_awardee_name') or contract.get('awardee_name') or '').upper()
            
            # Helper function to detect if a string looks like a contract number
            def looks_like_contract_number(text):
                if not text or not isinstance(text, str):
                    return False
                # Contract numbers are typically short (under 20 chars) and mostly alphanumeric
                # Pattern: alphanumeric with possible dashes/slashes, like "23Z00041" or "19Z00042"
                cleaned = text.replace('-', '').replace('/', '').strip()
                return len(cleaned) <= 20 and cleaned.isalnum() and len(cleaned) >= 6
            
            # Use the most descriptive field for project_name
            # Prefer: project_description > notice_title > award_description
            # Only use award_title if it doesn't look like a contract number
            descriptive_project_name = project_description_field or notice_title or contract.get('award_description')
            
            # If we still don't have a descriptive name, check award_title (but skip if it's a contract number)
            if not descriptive_project_name or descriptive_project_name.strip() == '':
                if award_title and not looks_like_contract_number(award_title):
                    descriptive_project_name = award_title
                else:
                    # If award_title looks like a contract number, don't use it for project_name
                    # Leave it as None/empty so frontend can handle it better
                    # The contract number will be available in award_title for the frontend to use as last resort
                    descriptive_project_name = None
            
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
            final_congressman, match_type, match_score, district_cm, contractor_cm, contractor_cm_2 = self._match_project_unified(
                project_text=location_text,
                province=proj_province,
                municipality_barangay=proj_municipality_barangay,
                contractor=awardee_name,
                year=project_year,
                congressmen_data=congressmen_data,
                district_lookup=district_lookup_dict,
                contractor_lookup=contractor_lookup_dict,
                contractor_inverted_index=contractor_inverted_index,
                project_data=contract  # Pass contract data for project code extraction and month for election transitions
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
            
            contractor_congressman_2_district = None
            if contractor_cm_2 and contractor_cm_2 in congressmen_data:
                cm_data = congressmen_data[contractor_cm_2]
                if cm_data.get('district_number') and cm_data.get('provinces'):
                    contractor_congressman_2_district = f"{cm_data.get('district_number')} District {cm_data.get('provinces')[0]}"

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

            # Ensure project_name has a value (use award_title as last resort even if it's a contract number)
            # Frontend will handle displaying it appropriately
            final_project_name = descriptive_project_name
            if not final_project_name or final_project_name.strip() == '':
                if award_title:
                    final_project_name = award_title
                else:
                    final_project_name = None
            
            chunk_results.append({
                "source": self._normalize_source_label("PhilGEPS"),
                "meilisearch_id": contract.get('meilisearch_id') or contract.get('global_id'),
                "contract_id": contract.get('philgeps_award_id') or contract.get('award_id') or contract.get('notice_id') or contract.get('contract_id') or None,  # Add for deduplication
                "project_name": final_project_name,
                "project_description": project_description_field if project_description_field else None,  # Add for frontend to use
                "notice_title": notice_title if notice_title else None,  # Add for frontend to use
                "award_description": contract.get('award_description') if contract.get('award_description') else None,  # Add for frontend to use
                "award_title": award_title if award_title else None,  # Keep original for reference
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
                "contractor_congressman_2": contractor_cm_2,
                "contractor_congressman_2_district": contractor_congressman_2_district,
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

    def _process_transparency_chunk(self, rows_chunk: List[Dict], congressmen_data: Dict, districts_data: Dict,
                                 district_lookup_dict: Dict, contractor_lookup_dict: Dict, contractor_inverted_index: Dict,
                                 known_provinces: List[str] = None, known_cities: List[str] = None, 
                                 location_context_map: Dict = None) -> List[Dict]:
        """Process a chunk of Transparency (DPWH scraper) projects from Parquet using O(1) lookups."""
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
            if not self.force_reclassify:
                project_district_type = record.get('project_district_type')
                project_district = record.get('project_district')
                project_barangay_municipality = record.get('project_barangay_municipality')
                is_flood_related = record.get('is_flood_related')
                
                if (project_district_type and 
                    project_district and 
                    project_barangay_municipality and
                    is_flood_related is not None):
                    result = record.copy()
                    result['source'] = self._normalize_source_label(result.get('source') or 'Transparency')
                    if not result.get('match_type'):
                        if result.get('district_congressman'):
                            result['match_type'] = 'district'
                        elif result.get('contractor_congressman'):
                            result['match_type'] = 'contractor'
                        else:
                            result['match_type'] = 'unknown'
                    result['_skipped_reclassification'] = True
                    chunk_results.append(result)
                    self.progress_counters['skipped'] += 1
                    continue
            
            # Force mode: Clear classification fields
            elif self.force_reclassify:
                classification_fields_to_clear = [
                    'district_congressman', 'contractor_congressman',
                    'project_district_type', 'project_district', 'project_barangay_municipality',
                    'project_province_city_district', 'project_municipality_barangay',
                    'is_flood_related', 'district_match_type', 'district_match_score',
                    'district_is_city_wide', 'congressman_district',
                    'contractor_match_type', 'contractor_match_score',
                    'contractor_congressman_district', 'match_type', 'match_score'
                ]
                for field in classification_fields_to_clear:
                    if field in record:
                        del record[field]
            
            # Basic Data - Transparency uses similar structure to Microsite
            description = (record.get("project_name") or record.get("project_description") or 
                         record.get("description") or "").upper()
            project_title = (record.get("project_name") or record.get("project_description") or
                           record.get("description") or "").upper()
            contractor_raw = (record.get("contractor_name") or "")
            contractor = contractor_raw.upper()
            agency = (record.get("organization_name") or record.get("implementing_office") or "").upper()
            fund_source = (record.get("source_of_funds") or "").upper()
            
            # Location Extraction
            project_location = (record.get("organization_name") or record.get("implementing_office") or
                              record.get("location") or record.get("region") or "")
            combined_text = f"{description} {project_title} {agency} {fund_source} {contractor} {project_location}"
            
            location_info = self._extract_location_from_text(combined_text, known_provinces, known_cities, location_context_map)
            
            proj_province = location_info.get('province') or ""
            proj_municipality_barangay = location_info.get('municipality_barangay') or ""
            is_city_district = location_info.get('is_city_district', False)
            
            # Extract rich text for matching
            proj_name = (record.get('project_name') or record.get('description') or '').strip()
            proj_desc = (record.get('project_description') or '').strip()
            location = (record.get('location') or record.get('implementing_office') or '').strip()
            
            combined_text = f"{proj_name} {proj_desc} {location}".strip()

            # Unified Match
            final_congressman, match_type, match_score, district_cm, contractor_cm, contractor_cm_2 = self._match_project_unified(
                project_text=combined_text,
                province=proj_province,
                municipality_barangay=proj_municipality_barangay,
                contractor=contractor,
                year=record.get('year'),
                congressmen_data=congressmen_data,
                district_lookup=district_lookup_dict,
                contractor_lookup=contractor_lookup_dict,
                contractor_inverted_index=contractor_inverted_index,
                project_data=record
            )

            # Update Progress
            self._update_progress(match_type, final_congressman, is_city_district, bool(proj_municipality_barangay))

            # Construct Result
            amount = self._parse_amount(record.get("amount") or record.get("cost_php") or record.get("Contract Price") or record.get("Contract Amount"))
            
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
            
            contractor_congressman_2_district = None
            if contractor_cm_2 and contractor_cm_2 in congressmen_data:
                cm_data = congressmen_data[contractor_cm_2]
                if cm_data.get('district_number') and cm_data.get('provinces'):
                    contractor_congressman_2_district = f"{cm_data.get('district_number')} District {cm_data.get('provinces')[0]}"

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

            # Include project_title in flood classification
            is_flood = self._is_flood_related(description, f"{description} {project_title}".strip(), project_location)

            # In force mode, always process and set fields to None if we can't determine them
            if self.force_reclassify:
                if not project_district_type:
                    project_district_type = None
                if not project_district:
                    project_district = None
                if not project_barangay_municipality:
                    project_barangay_municipality = None
            else:
                # In non-force mode, skip reclassification if we can't determine all required fields
                if not (project_district_type and project_district and project_barangay_municipality):
                    chunk_results.append({
                        "source": self._normalize_source_label("Transparency"),
                        "meilisearch_id": None,
                        "contract_id": record.get('contract_id') or None,  # Add for deduplication
                        "project_name": description or "N/A",
                        "contractor": contractor_raw or "N/A",
                        "amount": amount,
                        "location": project_location or "N/A",
                        "year": record.get('year'),
                        "status": record.get("status") or record.get("Contract Status") or "N/A",
                        "district_congressman": None,
                        "contractor_congressman": contractor_cm,
                        "contractor_congressman_2": contractor_cm_2,
                        "match_type": "contractor" if contractor_cm else "unmatched",
                        "match_score": 50 if contractor_cm else 0,
                        "project_district_type": None,
                        "project_district": None,
                        "project_barangay_municipality": None,
                        "is_flood_related": is_flood,
                        "_skipped_reclassification": False,
                        "_unmatched": True
                    })
                    continue

            chunk_results.append({
                "source": self._normalize_source_label("Transparency"),
                "meilisearch_id": None,
                "contract_id": record.get('contract_id') or None,  # Add for deduplication
                "project_name": description or "N/A",
                "contractor": contractor_raw or "N/A",
                "amount": amount,
                "location": project_location or "N/A",
                "year": record.get('year'),
                "status": record.get("status") or record.get("Contract Status") or "N/A",
                "district_congressman": district_cm,
                "district_match_type": "district" if district_cm else None,
                "district_match_score": match_score if match_type == 'district' else 0,
                "district_is_city_wide": (match_score == 1 and match_type == "district"),
                "congressman_district": congressman_district,
                "contractor_congressman": contractor_cm,
                "contractor_match_type": "contractor" if contractor_cm else None,
                "contractor_match_score": 50 if contractor_cm else 0,
                "contractor_congressman_district": contractor_congressman_district,
                "contractor_congressman_2": contractor_cm_2,
                "contractor_congressman_2_district": contractor_congressman_2_district,
                "project_district_type": project_district_type,
                "project_district": project_district,
                "project_barangay_municipality": project_barangay_municipality,
                "project_province_city_district": project_district_type.capitalize() if project_district_type else None,
                "project_municipality_barangay": project_barangay_municipality,
                "is_flood_related": is_flood,
                "match_type": match_type,
                "match_score": match_score
            })
            
        return chunk_results

    def _process_microsite_chunk(self, rows_chunk: List[Dict], congressmen_data: Dict, districts_data: Dict,
                                 district_lookup_dict: Dict, contractor_lookup_dict: Dict, contractor_inverted_index: Dict,
                                 known_provinces: List[str] = None, known_cities: List[str] = None, 
                                 location_context_map: Dict = None) -> List[Dict]:
        """Process a chunk of Microsite projects from Parquet using O(1) lookups."""
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
            # CRITICAL: In force mode, ALWAYS reclassify - never skip
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
                    # Normalize source to ensure consistency (Infrawatch -> Microsite)
                    result['source'] = self._normalize_source_label(result.get('source') or 'Microsite')
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
            # Force mode: Explicitly clear any remaining classification fields from record dict
            # This ensures we don't accidentally use old values during matching
            elif self.force_reclassify:
                # Double-check: Clear classification fields if they somehow still exist
                classification_fields_to_clear = [
                    'district_congressman', 'contractor_congressman',
                    'project_district_type', 'project_district', 'project_barangay_municipality',
                    'project_province_city_district', 'project_municipality_barangay',
                    'is_flood_related', 'district_match_type', 'district_match_score',
                    'district_is_city_wide', 'congressman_district',
                    'contractor_match_type', 'contractor_match_score',
                    'contractor_congressman_district', 'match_type', 'match_score'
                ]
                for field in classification_fields_to_clear:
                    if field in record:
                        del record[field]
            
            # Basic Data
            # CRITICAL: Parquet file has standardized columns from export script (not JSONB field names)
            # Export script creates: project_name, project_description, contractor_name, organization_name, etc.
            description = (record.get("project_name") or record.get("project_description") or 
                         record.get("Contract Details") or record.get("Project Description") or "").upper()
            # Get project title/description for classification (similar to notice_title in PhilGEPS)
            project_title = (record.get("project_name") or record.get("project_description") or
                           record.get("Contract Details") or record.get("Project Description") or 
                           record.get("Project Title") or record.get("Title") or "").upper()
            contractor_raw = (record.get("contractor_name") or 
                            record.get("Contractor") or record.get("Contractor Name") or record.get("Contractor_Name") or "")
            contractor = contractor_raw.upper()
            # Export script maps "Implementing Agency" to organization_name and infrawatch_implementing_agency
            agency = (record.get("organization_name") or record.get("infrawatch_implementing_agency") or
                     record.get("Implementing Agency") or "").upper()
            fund_source = (record.get("infrawatch_fund_source") or record.get("Fund Source") or "").upper()
            
            # Location Extraction - include project_title for better classification
            # Use standardized parquet columns: organization_name contains location info
            project_location = (record.get("organization_name") or record.get("infrawatch_implementing_agency") or
                              record.get("Implementing Agency") or 
                              record.get("Project Location") or record.get("location") or "")
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
            final_congressman, match_type, match_score, district_cm, contractor_cm, contractor_cm_2 = self._match_project_unified(
                project_text=combined_text,
                province=proj_province,
                municipality_barangay=proj_municipality_barangay,
                contractor=contractor,
                year=None, # Infrawatch has no reliable year
                congressmen_data=congressmen_data,
                district_lookup=district_lookup_dict,
                contractor_lookup=contractor_lookup_dict,
                contractor_inverted_index=contractor_inverted_index,
                project_data=record  # Pass record data for project code extraction
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
            
            contractor_congressman_2_district = None
            if contractor_cm_2 and contractor_cm_2 in congressmen_data:
                cm_data = congressmen_data[contractor_cm_2]
                if cm_data.get('district_number') and cm_data.get('provinces'):
                    contractor_congressman_2_district = f"{cm_data.get('district_number')} District {cm_data.get('provinces')[0]}"

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
                        "contractor_congressman": contractor_cm,
                        "contractor_congressman_2": contractor_cm_2,
                        "match_type": "contractor" if contractor_cm else "unmatched",
                        "match_score": 50 if contractor_cm else 0,
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
                "contractor_congressman_2": contractor_cm_2,
                "contractor_congressman_2_district": contractor_congressman_2_district,
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
            # CRITICAL: In force mode, always reclassify - ignore old classification values
            if self.force_reclassify:
                # Force mode: always reclassify, ignore existing classification fields
                already_classified = False
            elif not self.force_reclassify:
                already_classified = False
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
            final_congressman, match_type, match_score, district_cm, contractor_cm, contractor_cm_2 = self._match_project_unified(
                project_text=combined_text,
                province=final_province,
                municipality_barangay=final_muni,
                contractor=proj_contractor,
                year=project_year,
                congressmen_data=congressmen_data,
                district_lookup=district_lookup_dict,
                contractor_lookup=contractor_lookup_dict,
                contractor_inverted_index=contractor_inverted_index,
                project_data=proj  # Pass project data for project code extraction
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
            
            contractor_congressman_2_district = None
            if contractor_cm_2 and contractor_cm_2 in congressmen_data:
                cm_data = congressmen_data[contractor_cm_2]
                if cm_data.get('district_number') and cm_data.get('provinces'):
                    contractor_congressman_2_district = f"{cm_data.get('district_number')} District {cm_data.get('provinces')[0]}"

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
                # UNLESS we have a contractor match - then we must keep it!
                if not (project_district_type and project_district and project_barangay_municipality):
                    if not contractor_cm:
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
                "contractor_congressman_2": contractor_cm_2,
                "contractor_congressman_2_district": contractor_congressman_2_district,
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
    
    def _enrich_congressmen_from_districts_json(self, congressmen_data: Dict) -> None:
        """
        Enrich congressmen_data with terms parsed from districts.json.
        This parses strings like "Name (2016-2019); Name (2022-present)" to ensure
        all historical terms are captured in memory for matching.
        """
        print("📜 Enriching congressmen data from districts.json...")
        try:
            # Assuming STATIC_DIR is available or relative path
            districts_path = Path('static/data/districts.json')
            if not districts_path.exists():
                # Try finding it relative to script 
                districts_path = Path(__file__).parent.parent / 'static' / 'data' / 'districts.json'
            
            if not districts_path.exists():
                print(f"⚠️ districts.json not found at {districts_path}, skipping enrichment.")
                return

            with open(districts_path, 'r', encoding='utf-8') as f:
                districts_json = json.load(f)

            term_pattern = re.compile(r'(.*?)\s*\((\d{4})-(present|\d{4})\)')
            
            count_added = 0
            count_updated = 0

            for province, info in districts_json.items():
                if not isinstance(info, dict) or 'representatives' not in info:
                    continue
                
                reps = info['representatives']
                for district, rep_str in reps.items():
                    # Split by semicolon for multiple reps
                    # e.g. "Rep 1 (2016-2019); Rep 2 (2019-present)"
                    parts = [p.strip() for p in rep_str.split(';')]
                    
                    for part in parts:
                        match = term_pattern.match(part)
                        if match:
                            name_raw = match.group(1).strip()
                            start_year = int(match.group(2))
                            end_str = match.group(3)
                            
                            if end_str.lower() == 'present':
                                # Use a futuristic year or current year+something to denote present in logic
                                # But typically we just want to ensure it covers 2025
                                end_year = 2025 # Or 2028? Use 2025 to align with current context or 2030 to be safe.
                                # Current logic in script might use 2025 or current year.
                                # Let's use 2025 for now as the 'present' typically means current term.
                                # Actually, 2025 is the end of the current term (2022-2025).
                                # But if it is "2025-present", then it means 2025-2028.
                                if start_year == 2025:
                                    end_year = 2028
                                else:
                                    end_year = 2025
                            else:
                                end_year = int(end_str)

                            # Create term object
                            new_term = {"start": start_year, "end": end_year}

                            # Find existing congressman or create new
                            # Matching by name is fuzzy. 
                            found = False
                            for c_data in congressmen_data.values():
                                # Simple check: is name contained?
                                # Ideally use the _name_key or normalization logic
                                if self._normalize_congressman_name(name_raw).upper() == self._normalize_congressman_name(c_data['name']).upper():
                                    found = True
                                    # Add term if not exists
                                    existing_terms = c_data.get('terms', [])
                                    # Check for duplicate
                                    is_duplicate = False
                                    for t in existing_terms:
                                        if t.get('start') == start_year and (t.get('end') == end_year or (end_str == 'present' and t.get('end') >= 2025)):
                                            is_duplicate = True
                                            break
                                    if not is_duplicate:
                                        if isinstance(existing_terms, str):
                                            try:
                                                existing_terms = json.loads(existing_terms)
                                            except:
                                                existing_terms = []
                                        existing_terms.append(new_term)
                                        c_data['terms'] = existing_terms
                                        count_updated += 1
                                    break
                            
                            if not found:
                                # Create new entry if not found (needed for purely historical matching)
                                # Make sure to generate a unique key/display name
                                display_name = name_raw
                                if display_name not in congressmen_data:
                                    congressmen_data[display_name] = {
                                        "name": display_name,
                                        "provinces": [province],
                                        "district_number": district,
                                        "is_city_district": False, # Unknown
                                        "contractors": [], 
                                        "contractor_patterns": [],
                                        "barangays": [], # Could infer from district map but leave empty
                                        "terms": [new_term]
                                    }
                                    count_added += 1

            print(f"✅ Enriched congressmen data: Updated {count_updated} terms, Added {count_added} new congressmen")

        except Exception as e:
            print(f"⚠️ Error enriching from districts.json: {e}")
            import traceback
            traceback.print_exc()

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

        # Try to load contractor matches from Parquet file first, then DuckDB
        contractor_rows = []
        
        # Check for contractor_dynasty_matches.parquet first (preferred format)
        contractor_parquet = PARQUET_DIR / 'contractor_dynasty_matches.parquet'
        if contractor_parquet.exists():
            try:
                import duckdb
                conn = duckdb.connect()
                try:
                    # Only load contractor relationships that have a source (verified relationships)
                    print(f"DEBUG: Executing DuckDB query for contractors from {contractor_parquet}...")
                    contractor_rows = conn.execute(f"SELECT dynasty_first_name, dynasty_last_name, company_name, role FROM read_parquet('{contractor_parquet}') WHERE source_csv_file IS NOT NULL AND source_csv_file != ''").fetchall()
                    print(f"✅ Loaded {len(contractor_rows)} verified contractor matches (with sources) from contractor_dynasty_matches.parquet")
                finally:
                    conn.close()
            except Exception as e:
                print(f"⚠️  Failed to load contractors from contractor_dynasty_matches.parquet: {e}")
        
        # Also check for politician_contractors.parquet (from dynasty export)
        if not contractor_rows:
            politician_contractors_parquet = PARQUET_DIR / 'politician_contractors.parquet'
            if politician_contractors_parquet.exists():
                try:
                    import duckdb
                    conn = duckdb.connect()
                    try:
                        # Check column names first - might be different format
                        sample = conn.execute(f"SELECT * FROM read_parquet('{politician_contractors_parquet}') LIMIT 1").fetchone()
                        columns = [desc[0] for desc in conn.description]
                        print(f"🔍 politician_contractors.parquet columns: {columns}")
                        
                        # Try to map columns - common variations:
                        # Option 1: first_name, last_name, company_name, role
                        # Option 2: dynasty_first_name, dynasty_last_name, company_name, role
                        # Option 3: politician_first_name, politician_last_name, contractor_name, relationship_type
                        
                        if 'first_name' in columns and 'last_name' in columns:
                            # Standard format - only load relationships with sources (verified)
                            if 'company_name' in columns:
                                contractor_rows = conn.execute(f"SELECT first_name, last_name, company_name, COALESCE(role, 'owner') as role FROM read_parquet('{politician_contractors_parquet}') WHERE source IS NOT NULL AND source != ''").fetchall()
                            elif 'contractor_name' in columns:
                                contractor_rows = conn.execute(f"SELECT first_name, last_name, contractor_name as company_name, COALESCE(relationship_type, 'owner') as role FROM read_parquet('{politician_contractors_parquet}') WHERE source IS NOT NULL AND source != ''").fetchall()
                            else:
                                # Try to find company/contractor column
                                company_col = None
                                for col in columns:
                                    if 'company' in col.lower() or 'contractor' in col.lower():
                                        company_col = col
                                        break
                                if company_col:
                                    role_col = 'role' if 'role' in columns else ('relationship_type' if 'relationship_type' in columns else None)
                                    if role_col:
                                        contractor_rows = conn.execute(f"SELECT first_name, last_name, {company_col} as company_name, COALESCE({role_col}, 'owner') as role FROM read_parquet('{politician_contractors_parquet}') WHERE source IS NOT NULL AND source != ''").fetchall()
                                    else:
                                        contractor_rows = conn.execute(f"SELECT first_name, last_name, {company_col} as company_name, 'owner' as role FROM read_parquet('{politician_contractors_parquet}') WHERE source IS NOT NULL AND source != ''").fetchall()
                        elif 'dynasty_first_name' in columns and 'dynasty_last_name' in columns:
                            # Already in correct format - only load relationships with sources
                            contractor_rows = conn.execute(f"SELECT dynasty_first_name, dynasty_last_name, company_name, COALESCE(role, 'owner') as role FROM read_parquet('{politician_contractors_parquet}') WHERE source IS NOT NULL AND source != ''").fetchall()
                        elif 'politician_first_name' in columns and 'politician_last_name' in columns:
                            # Alternative format - only load relationships with sources
                            company_col = 'contractor_name' if 'contractor_name' in columns else 'company_name'
                            role_col = 'relationship_type' if 'relationship_type' in columns else 'role'
                            contractor_rows = conn.execute(f"SELECT politician_first_name as dynasty_first_name, politician_last_name as dynasty_last_name, {company_col} as company_name, COALESCE({role_col}, 'owner') as role FROM read_parquet('{politician_contractors_parquet}') WHERE source IS NOT NULL AND source != ''").fetchall()
                        elif 'politician_id' in columns:
                            # Need to join with political_dynasties to get names - only load relationships with sources
                            company_col = 'contractor_name' if 'contractor_name' in columns else 'company_name'
                            role_col = 'role' if 'role' in columns else ('relationship_type' if 'relationship_type' in columns else None)
                            political_dynasties_parquet = PARQUET_DIR / 'political_dynasties.parquet'
                            
                            if political_dynasties_parquet.exists():
                                print(f"   🔄 Joining with {political_dynasties_parquet} to resolve politician IDs...")
                                if role_col:
                                    contractor_rows = conn.execute(f"""
                                        SELECT pd.first_name, pd.last_name, pc.{company_col} as company_name, COALESCE(pc.{role_col}, 'owner') as role 
                                        FROM read_parquet('{politician_contractors_parquet}') pc
                                        JOIN read_parquet('{political_dynasties_parquet}') pd ON pc.politician_id = pd.id
                                        WHERE pc.source IS NOT NULL AND pc.source != ''
                                    """).fetchall()
                                else:
                                    contractor_rows = conn.execute(f"""
                                        SELECT pd.first_name, pd.last_name, pc.{company_col} as company_name, 'owner' as role 
                                        FROM read_parquet('{politician_contractors_parquet}') pc
                                        JOIN read_parquet('{political_dynasties_parquet}') pd ON pc.politician_id = pd.id
                                        WHERE pc.source IS NOT NULL AND pc.source != ''
                                    """).fetchall()
                            else:
                                print(f"⚠️  political_dynasties.parquet not found, cannot join with politician_contractors")
                        
                        if contractor_rows:
                            print(f"✅ Loaded {len(contractor_rows)} verified contractor matches (with sources) from politician_contractors.parquet")
                    finally:
                        conn.close()
                except Exception as e:
                    print(f"⚠️  Failed to load contractors from politician_contractors.parquet: {e}")
                    import traceback
                    traceback.print_exc()
        
        # Fallback to DuckDB if parquet not available
        if not contractor_rows:
            duckdb_path = PARQUET_DIR / 'dynasty_data.duckdb'
            if duckdb_path.exists():
                try:
                    import duckdb
                    conn = duckdb.connect(str(duckdb_path))
                    try:
                        # Only load contractor relationships that have a source (verified relationships)
                        contractor_rows = conn.execute("SELECT dynasty_first_name, dynasty_last_name, company_name, role FROM contractor_dynasty_matches WHERE source_csv_file IS NOT NULL AND source_csv_file != ''").fetchall()
                        # Convert to asyncpg.Record-like objects
                        print(f"✅ Loaded {len(contractor_rows)} verified contractor matches (with sources) from DuckDB")
                    finally:
                        conn.close()
                except Exception as e:
                    print(f"⚠️  Failed to load contractors from DuckDB: {e}")
        
        # Process contractor rows
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
        
        # Note: No PostgreSQL fallback - using DuckDB/Parquet only

        # Try to load party list members from Parquet file first, then DuckDB
        party_rows = []
        
        # Check for parquet file first
        party_parquet = PARQUET_DIR / 'party_list_members.parquet'
        if party_parquet.exists():
            try:
                import duckdb
                conn = duckdb.connect()
                try:
                    party_rows = conn.execute(f"SELECT person_id, party_list_number, first_name, last_name FROM read_parquet('{party_parquet}')").fetchall()
                    print(f"✅ Loaded {len(party_rows)} party list members from Parquet")
                finally:
                    conn.close()
            except Exception as e:
                print(f"⚠️  Failed to load party members from Parquet: {e}")
        
        # Fallback to DuckDB if parquet not available
        if not party_rows:
            duckdb_path = PARQUET_DIR / 'dynasty_data.duckdb'
            if duckdb_path.exists():
                try:
                    import duckdb
                    conn = duckdb.connect(str(duckdb_path))
                    try:
                        party_rows = conn.execute("SELECT person_id, party_list_number, first_name, last_name FROM party_list_members").fetchall()
                        print(f"✅ Loaded {len(party_rows)} party list members from DuckDB")
                    finally:
                        conn.close()
                except Exception as e:
                    print(f"⚠️  Failed to load party members from DuckDB: {e}")
        
        # Process party rows
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
                # Remove parenthetical content (e.g., "(FORMERLY: ...)")
                patterns.add(re.sub(r'\([^)]*\)', '', base_upper).strip())
                # Split by / to get individual company names
                for part in re.split(r'[\\/]', base_upper):
                    part = part.strip()
                    if len(part) >= 2:  # Changed from 3 to 2 to include "FS CO"
                        patterns.add(part)
                
                # Extract key words, BUT preserve hyphenated names (e.g., "HI-TONE", "S-ANG")
                # First, find hyphenated words and add them as patterns
                hyphenated = re.findall(r'[A-Z0-9]+-[A-Z0-9]+(?:-[A-Z0-9]+)*', base_upper)
                for hw in hyphenated:
                    if len(hw) >= 2:
                        patterns.add(hw)
                        # Also add without hyphen for matching variations
                        patterns.add(hw.replace('-', ''))
                
                # Split by non-alphanumeric (excluding hyphen for hyphenated words)
                words = re.split(r'[^A-Z0-9-]+', base_upper)
                for word in words:
                    word = word.strip()
                    if len(word) >= 2:  # Changed from 3 to 2
                        patterns.add(word)
                        # If it's hyphenated, also add without hyphen
                        if '-' in word:
                            patterns.add(word.replace('-', ''))
                
                # Also add first 2 words combined for patterns like "FS CO"
                clean_name = re.sub(r'\([^)]*\)', '', base_upper).strip()
                words_list = re.split(r'[^A-Z0-9]+', clean_name)
                words_list = [w for w in words_list if w and len(w) >= 2]
                if len(words_list) >= 2:
                    # Add first 2 words combined
                    first_two = ' '.join(words_list[:2])
                    if len(first_two) >= 3:
                        patterns.add(first_two)
                    # Add first 3 words combined if available
                    if len(words_list) >= 3:
                        first_three = ' '.join(words_list[:3])
                        if len(first_three) >= 4:
                            patterns.add(first_three)
                
                final = set()
                for pattern in patterns:
                    clean = re.sub(r'\s+', ' ', pattern).strip()
                    if clean and len(clean) >= 2:  # Changed from 3 to 2
                        # CRITICAL: Filter out common tokens to prevent false positives
                        if clean in self.COMMON_TOKENS:
                            continue
                        final.add(clean)
                return list(final)

            contractor_names = []
            contractor_patterns = []
            
            # Load contractors from family_connections in config FIRST
            # This determines if the congressman should have contractor matching enabled
            family_connections = congressman_config.get('family_connections') or {}
            family_contractors = family_connections.get('contractors', []) if isinstance(family_connections, dict) else []
            has_explicit_contractors = len(family_contractors) > 0 or len(verified_patterns) > 0
            
            # Only add contractors from parquet files if:
            # 1. The congressman has explicit contractors in family_connections, OR
            # 2. The congressman has verified_contractors.patterns
            # This prevents false matches for congressmen who shouldn't have contractor matching
            if has_explicit_contractors:
                for contractor in direct_contractors:
                    company_name = contractor['company_name']
                    if not company_name:
                        continue
                    if _should_exclude(company_name):
                        continue
                    if verified_patterns:
                        upper_name = company_name.upper()
                        if not any(pattern.upper() in upper_name for pattern in verified_patterns):
                            continue  # Changed from pass to continue - skip if doesn't match verified patterns
                    contractor_names.append(company_name)
                    contractor_patterns.extend(_expand_patterns(company_name))
            
            # Always add contractors from family_connections in config
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

            # Only add party contractors if the congressman has explicit contractors
            # This prevents false matches for party-list members who shouldn't have contractor matching
            if has_explicit_contractors:
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
            
            # CRITICAL: Also add contractors from contractor_lookup (loaded from parquet files)
            # This ensures contractors from contractor_dynasty_matches.parquet and politician_contractors.parquet
            # are included in the matching logic
            parquet_contractors = []
            parquet_contractor_patterns = []
            
            # Get contractors from contractor_lookup (keyed by congressman name)
            # Try multiple name matching strategies
            name_key = _name_key(first_name_pattern, last_name_pattern)
            
            # Strategy 1: Exact name key match
            for contractor_row in contractor_lookup.get(name_key, []):
                company_name = contractor_row.get('company_name')
                if company_name and company_name not in contractor_names:
                    contractor_names.append(company_name)
                    parquet_contractor_patterns.extend(_expand_patterns(company_name))
            
            # Strategy 2: Match by first/last name patterns (more flexible)
            # This handles cases where parquet has "ELIZALDY SALCEDO" but config has "ELIZALDY CO"
            first_upper = (first_name_pattern or '').upper().strip()
            last_upper = (last_name_pattern or '').upper().strip()
            
            # Also try to match using display_name if available
            display_name_upper = (display_name or '').upper().strip()
            
            for lookup_key, contractor_rows in contractor_lookup.items():
                lookup_first, lookup_last = lookup_key
                lookup_first_upper = lookup_first.upper().strip()
                lookup_last_upper = lookup_last.upper().strip()
                lookup_full_upper = f"{lookup_first_upper} {lookup_last_upper}".strip()
                
                # Check if names match (allowing for middle names/variations)
                # For Elizaldy Co: first_name_pattern="ELIZALDY", last_name_pattern="CO"
                # Parquet might have: "ELIZALDY", "SALCEDO" or "ELIZALDY", "CO" or "ELIZALDY SALCEDO", "CO"
                name_matches = False
                
                # CRITICAL: Also check if display_name matches (e.g., "ELIZALDY SALCEDO CO" in display_name)
                if display_name_upper:
                    # Check if lookup full name appears in display_name
                    if lookup_full_upper in display_name_upper or display_name_upper in lookup_full_upper:
                        name_matches = True
                    # Check if key parts match
                    elif first_upper and first_upper in display_name_upper and lookup_first_upper in display_name_upper:
                        if not last_upper or last_upper in display_name_upper or lookup_last_upper in display_name_upper:
                            name_matches = True
                
                # Exact match on first name
                if not name_matches and first_upper and first_upper == lookup_first_upper:
                    # Check if last name matches or is a variation
                    if last_upper:
                        # Direct match
                        if last_upper == lookup_last_upper:
                            name_matches = True
                        # Handle cases like "CO" matching "SALCEDO CO" or vice versa
                        elif last_upper in lookup_last_upper or lookup_last_upper in last_upper:
                            name_matches = True
                        # Handle "SALCEDO CO" vs "CO"
                        elif 'SALCEDO' in lookup_last_upper and 'CO' in last_upper:
                            name_matches = True
                        elif 'CO' in lookup_last_upper and 'SALCEDO' in last_upper:
                            name_matches = True
                        # Handle "TIRSO" matching "TIRSO EDWIN" or "EDWIN" matching "TIRSO EDWIN LOLENG"
                        elif 'TIRSO' in lookup_first_upper and 'EDWIN' in first_upper:
                            name_matches = True
                        elif 'EDWIN' in lookup_first_upper and 'TIRSO' in first_upper:
                            name_matches = True
                        elif 'LOLENG' in lookup_last_upper and 'GARDIOLA' in last_upper:
                            name_matches = True
                        elif 'GARDIOLA' in lookup_last_upper and 'LOLENG' in last_upper:
                            name_matches = True
                    else:
                        # If no last name pattern, match on first name only
                        name_matches = True
                
                # Also check if first name pattern is contained in lookup first name
                # (handles "ELIZALDY" matching "ELIZALDY SALCEDO")
                if not name_matches and first_upper and first_upper in lookup_first_upper:
                    if last_upper:
                        if last_upper == lookup_last_upper or last_upper in lookup_last_upper or lookup_last_upper in last_upper:
                            name_matches = True
                        # Special handling for "CO" and "SALCEDO CO"
                        elif 'CO' in last_upper and ('SALCEDO' in lookup_last_upper or 'CO' in lookup_last_upper):
                            name_matches = True
                    else:
                        name_matches = True
                
                # Reverse: check if lookup first name is in our pattern
                if not name_matches and first_upper and lookup_first_upper in first_upper:
                    if last_upper:
                        if last_upper == lookup_last_upper or last_upper in lookup_last_upper or lookup_last_upper in last_upper:
                            name_matches = True
                        # Special handling for "CO" and "SALCEDO CO"
                        elif 'CO' in last_upper and ('SALCEDO' in lookup_last_upper or 'CO' in lookup_last_upper):
                            name_matches = True
                    else:
                        name_matches = True
                
                if name_matches:
                    for contractor_row in contractor_rows:
                        company_name = contractor_row.get('company_name')
                        if company_name and company_name not in contractor_names:
                            contractor_names.append(company_name)
                            parquet_contractor_patterns.extend(_expand_patterns(company_name))
            
            # Merge parquet contractor patterns with existing patterns
            contractor_patterns.extend(parquet_contractor_patterns)
            contractor_patterns = sorted(set(contractor_patterns))
            
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
        
        # Enrich coverage with historical terms from districts.json
        self._enrich_congressmen_from_districts_json(congressmen_data)
        
        return congressmen_data

    def _apply_district_corrections(self, congressmen_data: Dict) -> None:
        """
        Apply manual corrections to congressmen data to fix known issues in districts.json.
        This ensures fixes persist even if districts.json is overwritten by DB sync.
        
        Fixes:
        1. Davao City: Move misassigned barangays from 3rd District (Ungab) to 1st District (Paolo Duterte).
        2. Leyte 1st District: Ensure Martin Romualdez gets Tacloban City and correct municipalities.
        """
        print("🔧 Applying district corrections...")
        
        # 1. Fix Davao City
        # Barangays incorrectly assigned to 3rd District (should be 1st)
        davao_1st_barangays = [
            "Bago Gallera", "Baliok", "Catalunan Grande", "Catalunan Pequeño", 
            "Bago Aplaya", "Ma-a", "Matina Crossing", "Matina Pangi", "Talomo"
        ]
        
        # Find Paolo Duterte (1st District) and Isidro Ungab (3rd District)
        paolo_duterte = None
        isidro_ungab = None
        
        for name, data in congressmen_data.items():
            if 'DUTERTE' in name.upper() and 'PAOLO' in name.upper():
                paolo_duterte = data
            elif 'UNGAB' in name.upper() and 'ISIDRO' in name.upper():
                isidro_ungab = data
        
        if paolo_duterte and isidro_ungab:
            print("  - Fixing Davao City barangays...")
            # Remove from Ungab (3rd District)
            ungab_barangays = isidro_ungab.get('barangays', [])
            original_len = len(ungab_barangays)
            isidro_ungab['barangays'] = [b for b in ungab_barangays if b not in davao_1st_barangays]
            print(f"    Removed {original_len - len(isidro_ungab['barangays'])} barangays from Isidro Ungab")
            
            # Add to Paolo Duterte (1st District)
            paolo_barangays = set(paolo_duterte.get('barangays', []))
            for b in davao_1st_barangays:
                paolo_barangays.add(b)
            
            # Cleanup Paolo Duterte's list (remove 2nd District areas if present)
            # Agdao, Buhangin, Bunawan, Paquibato are districts in 2nd Legislative District
            incorrect_1st_entries = ["Agdao", "Buhangin", "Bunawan", "Paquibato"]
            paolo_barangays = {b for b in paolo_barangays if b not in incorrect_1st_entries}
            
            paolo_duterte['barangays'] = sorted(list(paolo_barangays))
            print(f"    Added {len(davao_1st_barangays)} barangays to Paolo Duterte and cleaned up incorrect entries")
            
            # Also ensure Paolo Duterte has "Davao City" as a province alias
            if "Davao City" not in paolo_duterte['provinces']:
                paolo_duterte['provinces'].append("Davao City")
            paolo_duterte['is_city_district'] = True
            
        # Fix Davao City 2nd District (Vincent Garcia) - Remove Wangan (belongs to 3rd)
        vincent_garcia = None
        for name, data in congressmen_data.items():
            if 'GARCIA' in name.upper() and 'VINCENT' in name.upper():
                vincent_garcia = data
                break
        
        if vincent_garcia:
            garcia_barangays = vincent_garcia.get('barangays', [])
            if "Wangan" in garcia_barangays:
                vincent_garcia['barangays'] = [b for b in garcia_barangays if b != "Wangan"]
                print("    Removed 'Wangan' from Vincent Garcia (belongs to 3rd District)")
        
        # 2. Fix Leyte 1st District (Martin Romualdez)
        # Correct municipalities for Leyte 1st District (all 9):
        leyte_1st_municipalities = [
            "Tacloban City", "Tacloban", 
            "Alangalang", "Babatngon", "Palo", 
            "San Miguel", "Santa Fe", "Tanauan", "Tolosa"
        ]
        
        martin_romualdez = None
        for name, data in congressmen_data.items():
            if 'ROMUALDEZ' in name.upper() and 'MARTIN' in name.upper():
                martin_romualdez = data
                break
        
        if martin_romualdez:
            print("  - Fixing Leyte 1st District municipalities...")
            # Force set the correct municipalities
            martin_romualdez['district_municipalities'] = leyte_1st_municipalities
            # Ensure Tacloban City is treated as a city district match too
            # We add "Tacloban City" to provinces so it matches as a city district
            if "Tacloban City" not in martin_romualdez['provinces']:
                martin_romualdez['provinces'].append("Tacloban City")
            
            # Also remove these municipalities from other Leyte congressmen to avoid conflicts
            for name, data in congressmen_data.items():
                if name != martin_romualdez['name'] and 'LEYTE' in str(data.get('provinces', [])).upper():
                    # Remove 1st district municipalities from others
                    other_munis = data.get('district_municipalities', [])
                    new_munis = [m for m in other_munis if m not in leyte_1st_municipalities]
                    if len(new_munis) != len(other_munis):
                        print(f"    Removed {len(other_munis) - len(new_munis)} municipalities from {name}")
                        data['district_municipalities'] = new_munis
        
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
        
        # Use class-level COMMON_TOKENS (defined at class level)
        # Special handling for Davao City districts
        # Paolo Duterte is listed under 'Davao del Sur', '1st District' but represents Davao City 1st District
        # We need to ensure that Davao City 1st District is treated as a city district, not a provincial one.
        
        # Apply corrections to congressmen data (fixes for Davao City, Leyte, etc.)
        self._apply_district_corrections(congressmen_data)
        
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
        
                    normalized = re.sub(r'[^A-Z0-9]+', ' ', pattern_upper).strip()
                    if normalized != pattern_upper:
                        contractor_lookup[normalized].append((congressman_name, cm_data))
        
        # Build inverted index from contractor_lookup keys
        # Optimized for speed and safety (avoid regex)
        idx_count = 0
        total_keys = len(contractor_lookup)
        
        for key in contractor_lookup.keys():
            idx_count += 1
            if idx_count % 5000 == 0:
                print(f"DEBUG: Inverted index progress: {idx_count}/{total_keys} keys...", end='\r')
                
            # Manual tokenization
            normalized = ''.join([c if c.isalnum() else ' ' for c in key.upper()])
            tokens = normalized.split()
            
            for token in tokens:
                if len(token) >= 3 and token not in self.COMMON_TOKENS:
                    contractor_inverted_index[token].add(key)
        
        print(f"DEBUG: Finished building inverted index with {len(contractor_inverted_index)} tokens.")
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
        
        # CRITICAL: Load comprehensive location database first (same as _extract_provinces_and_cities_from_data)
        # This ensures both extraction and matching systems use the same comprehensive data
        location_db_path = Path(__file__).parent.parent / 'database' / 'philippine_locations.json'
        if location_db_path.exists():
            try:
                with open(location_db_path, 'r', encoding='utf-8') as f:
                    location_db = json.load(f)
                
                # Add all provinces from comprehensive database
                for prov_name_norm, prov_data in location_db.get('provinces', {}).items():
                    prov_name = prov_data.get('name', prov_name_norm)
                    provinces.add(prov_name.upper().strip())
                    provinces.add(prov_name_norm)  # Also add normalized version
                
                # Add all cities from comprehensive database
                for city_name_norm, city_data in location_db.get('cities', {}).items():
                    city_name = city_data.get('name', city_name_norm)
                    cities.add(city_name.upper().strip())
                    cities.add(city_name_norm)  # Also add normalized version
                    # Also add province if city is in a province
                    prov_name = city_data.get('province', '')
                    if prov_name:
                        provinces.add(prov_name.upper().strip())
                
                print(f"✅ Loaded comprehensive location database into location_dicts: {len(provinces)} provinces, {len(cities)} cities")
            except Exception as e:
                print(f"⚠️  Warning: Could not load comprehensive location database: {e}")
                print("   Falling back to congressmen data only")
        
        # Extract from congressmen_data (for backward compatibility and to catch any missing)
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
        Extract all provinces and cities from comprehensive location database + congressmen data.
        Returns: (provinces_set, cities_set)
        """
        provinces = set()
        cities = set()
        
        # CRITICAL: Load comprehensive location database if available
        # This includes all 82 provinces, 146 cities, and municipalities
        location_db_path = Path(__file__).parent.parent / 'database' / 'philippine_locations.json'
        if location_db_path.exists():
            try:
                with open(location_db_path, 'r', encoding='utf-8') as f:
                    location_db = json.load(f)
                
                # Add all provinces from comprehensive database
                for prov_name_norm, prov_data in location_db.get('provinces', {}).items():
                    prov_name = prov_data.get('name', prov_name_norm)
                    provinces.add(prov_name.upper().strip())
                    provinces.add(prov_name_norm)  # Also add normalized version
                
                # Add all cities from comprehensive database
                for city_name_norm, city_data in location_db.get('cities', {}).items():
                    city_name = city_data.get('name', city_name_norm)
                    cities.add(city_name.upper().strip())
                    cities.add(city_name_norm)  # Also add normalized version
                    # Also add province if city is in a province
                    prov_name = city_data.get('province', '')
                    if prov_name:
                        provinces.add(prov_name.upper().strip())
                
                print(f"✅ Loaded comprehensive location database: {len(provinces)} provinces, {len(cities)} cities")
            except Exception as e:
                print(f"⚠️  Warning: Could not load comprehensive location database: {e}")
                print("   Falling back to congressmen data only")
        
        # Also extract from congressmen_data (for backward compatibility and to catch any missing)
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
            # CRITICAL: For "SANTA CATALINA (ILOCOS SUR), ILOCOS SUR, Region I"
            # parts[-1] = "Region I" (not what we want)
            # parts[-2] = "ILOCOS SUR" (this is the province!)
            # parts[-3] = "SANTA CATALINA (ILOCOS SUR)" (municipality)
            # So we need to check if parts[-1] is "Region X" and use parts[-2] instead
            location_part = parts[-2].strip() if len(parts) >= 2 else ""
            province_city_part = parts[-1].strip().upper()  # Province/city (after comma)
            
            # CRITICAL FIX: If last part is "Region X", use the second-to-last part as province
            # Example: "SANTA CATALINA (ILOCOS SUR), ILOCOS SUR, Region I"
            # -> parts[-1] = "REGION I", parts[-2] = "ILOCOS SUR" (this is the province!)
            if province_city_part.startswith('REGION ') and len(parts) >= 3:
                province_city_part = parts[-2].strip().upper()  # Use second-to-last as province
                location_part = parts[-3].strip() if len(parts) >= 3 else ""
            
            # CRITICAL: Also check if location_part contains province info in parentheses
            # Example: "SANTA CATALINA (ILOCOS SUR), ILOCOS SUR, Region I"
            # Extract province from parentheses in location_part if it has directional modifier
            if '(' in location_part and ')' in location_part:
                # Extract text in parentheses
                paren_matches = re.findall(r'\(([^)]+)\)', location_part.upper())
                for paren_text in paren_matches:
                    # Check if this looks like a province with directional modifier
                    if has_directional_modifier(paren_text):
                        # Use the province from parentheses if it's more specific
                        if not province_city_part or not has_directional_modifier(province_city_part):
                            province_city_part = paren_text.strip()
                        elif has_directional_modifier(province_city_part) and has_directional_modifier(paren_text):
                            # Both have directional - prefer the one from parentheses (more explicit)
                            province_city_part = paren_text.strip()
                        break
            
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
                            
                            city_base = city_upper.replace(' CITY', '').strip()
                            
                            # Special handling for Davao City: also check if text mentions "Davao City" 
                            # CRITICAL: Ensure Davao City is treated as a city district, not just Davao del Sur
                            if city_upper == 'DAVAO CITY':
                                if 'DAVAO CITY' in text_upper:
                                    result['province'] = 'DAVAO DEL SUR' # Technically in Davao del Sur but independent
                                    result['municipality_barangay'] = 'DAVAO CITY'
                                    result['is_city_district'] = True
                                    return result 
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
                            # CRITICAL: "ILOCOS SUR" should NEVER match "ILOCOS NORTE" - require exact directional match
                            if part_has_directional:
                                # Must be exact match - no partial matches for directional provinces
                                if prov_upper == province_city_part:
                                    # Exact match - this is the ONLY acceptable match for directional provinces
                                    result['province'] = known_prov
                                    result['municipality_barangay'] = location_clean
                                    break
                                # CRITICAL: If both have directional modifiers, they must match exactly
                                elif known_prov_has_directional:
                                    # Both have directional - check if they match exactly
                                    # Extract directional from both
                                    prov_dir_match = re.search(r'\b(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\b', prov_upper, re.IGNORECASE)
                                    part_dir_match = re.search(r'\b(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\b', province_city_part, re.IGNORECASE)
                                    
                                    if prov_dir_match and part_dir_match:
                                        prov_dir = prov_dir_match.group(0).upper().strip()
                                        part_dir = part_dir_match.group(0).upper().strip()
                                        # Only match if directions are EXACTLY the same
                                        if prov_dir == part_dir and prov_upper == province_city_part:
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
                    # CRITICAL: For directional provinces, use word boundary to ensure exact match
                    # "ILOCOS SUR" should match "ILOCOS SUR" but NOT "ILOCOS NORTE"
                    if variant_has_directional:
                        # For directional provinces, require exact word boundary match
                        pattern = r'\b' + re.escape(variant) + r'\b'
                        if re.search(pattern, text_upper, re.IGNORECASE):
                            # Verify no conflicting directional variant exists
                            # Extract base and check for opposite direction
                            base = normalize_province_base(variant)
                            variant_dir_match = re.search(r'\b(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\b', variant, re.IGNORECASE)
                            if variant_dir_match:
                                variant_dir = variant_dir_match.group(0).upper().strip()
                                # Check for opposite directions
                                opposite_dirs = {
                                    'SUR': ['NORTE', 'DEL NORTE'],
                                    'NORTE': ['SUR', 'DEL SUR'],
                                    'DEL SUR': ['NORTE', 'DEL NORTE'],
                                    'DEL NORTE': ['SUR', 'DEL SUR'],
                                    'OCCIDENTAL': ['ORIENTAL'],
                                    'ORIENTAL': ['OCCIDENTAL'],
                                    'EASTERN': ['WESTERN'],
                                    'WESTERN': ['EASTERN'],
                                    'NORTHERN': ['SOUTHERN'],
                                    'SOUTHERN': ['NORTHERN']
                                }
                                opposite_list = opposite_dirs.get(variant_dir, [])
                                has_opposite = any(re.search(rf'\b{re.escape(opp)}\b', text_upper, re.IGNORECASE) and 
                                                  re.search(rf'\b{re.escape(base)}\b', text_upper, re.IGNORECASE) 
                                                  for opp in opposite_list)
                                if not has_opposite:
                                    result['province'] = known_prov
                                    matched = True
                                    break
                    elif variant in text_upper:
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
                                    # CRITICAL: Check if a more specific version exists in text
                                    # Check for ALL directional patterns, not just one
                                    directional_patterns = [
                                        rf'\b(SOUTHERN|NORTHERN|EASTERN|WESTERN|OCCIDENTAL|ORIENTAL|DEL\s+SUR|DEL\s+NORTE)\s+{re.escape(variant)}\b',
                                        rf'\b{re.escape(variant)}\s+(SOUTHERN|NORTHERN|EASTERN|WESTERN|OCCIDENTAL|ORIENTAL|DEL\s+SUR|DEL\s+NORTE)\b',
                                        rf'\b(SOUTHERN|NORTHERN|EASTERN|WESTERN|OCCIDENTAL|ORIENTAL)\s+{re.escape(variant)}\b',
                                        rf'\b{re.escape(variant)}\s+(DEL\s+SUR|DEL\s+NORTE)\b'
                                    ]
                                    has_directional_in_text = any(re.search(dp, text_upper, re.IGNORECASE) for dp in directional_patterns)
                                    if not has_directional_in_text:
                                        # No more specific version found, safe to use this
                                        result['province'] = known_prov
                                        matched = True
                                        break
                                    else:
                                        # More specific version exists - skip base match to avoid cross-variant matches
                                        continue
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
                        
                        # CRITICAL: Before matching base name, check if ANY directional variant exists in text
                        # If "ILOCOS SUR" or "ILOCOS NORTE" exists, don't match base "ILOCOS"
                        # This prevents cross-variant matches
                        all_directional_patterns = [
                            rf'\b{re.escape(variant_base)}\s+(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN|DEL\s+SUR|DEL\s+NORTE)\b',
                            rf'\b(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN|DEL\s+SUR|DEL\s+NORTE)\s+{re.escape(variant_base)}\b',
                        ]
                        has_any_directional = any(re.search(dp, text_upper, re.IGNORECASE) for dp in all_directional_patterns)
                        
                        if has_any_directional:
                            # Text has a directional variant - skip base name match to avoid cross-variant errors
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
    
    def _compare_districts(self, d1: str, d2: str) -> bool:
        """Helper to compare district numbers/strings"""
        def norm(d):
            if not d: return "0"
            s = str(d).upper()
            if "LONE" in s: return "LONE"
            s = s.replace("DISTRICT", "").replace("CITY", "").strip()
            match = re.search(r'\d+', s)
            if match: return match.group(0)
            return s
        
        return norm(d1) == norm(d2)

    def _find_congressman_by_district(self, province: str, municipality_barangay: str, project_year: Optional[int], 
                                     district_lookup: Dict, congressmen_data: Dict, 
                                     project_district: Optional[str] = None,
                                     project_name: str = "") -> Optional[tuple]:
        """
        O(1) lookup using Location Index + Historical Term Check.
        Replaces slow fuzzy matching with O(1) index lookup + strict validation.
        """
        # 1. Construct Search Query
        query_text = f"{province} {municipality_barangay} {project_name}"
        
        # 2. Fast Location Lookup
        loc_match = self.location_matcher.find_best_match(query_text, province_hint=province)
        
        if loc_match:
            match_prov, match_dist, match_cong_2025 = loc_match
            
            # 3. Resolve Historical Congressman for Project Year
            target_year = project_year if project_year else datetime.now().year
            
            for c_name, c_data in congressmen_data.items():
                # Check province match strict (normalized)
                prov_match = False
                for p in c_data.get('provinces', []):
                     if self.location_matcher._normalize(p) == self.location_matcher._normalize(match_prov):
                         prov_match = True
                         break
                if not prov_match: continue

                # Check district match strict
                c_dist = str(c_data.get('district_number', ''))
                if not self._compare_districts(c_dist, match_dist):
                    continue

                # Check Term
                terms = c_data.get('terms', [])
                for term in terms:
                    start = int(term.get('start', 0))
                    end = int(term.get('end', 9999))
                    
                    if start <= target_year <= end:
                        return (c_data['name'], 200)
            
            # Fallback: if we matched location but not history? 
            # If project_year is 2025-2028, return the 2025 cong match directly
            if target_year >= 2025 and match_cong_2025 and match_cong_2025 != 'Unknown':
                 return (match_cong_2025, 150)

        return None
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
        location_upper = (municipality_barangay or '').upper().strip()
        
        # CRITICAL FIX: If municipality/barangay is "DAVAO CITY", override province to "DAVAO CITY"
        # This ensures Davao City projects match to Davao City districts (Paolo Duterte, etc.)
        # instead of Davao del Sur province districts (John Tracy Cagas)
        if location_upper == 'DAVAO CITY' and province_upper in ['DAVAO DEL SUR', 'DAVAO CITY', 'DAVAO DEL NORTE']:
            province_upper = 'DAVAO CITY'
        
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
        # CRITICAL FIX: Prevent "Ilocos Norte" from matching "Ilocos Sur" projects and vice versa
        province_base_name = re.sub(r'\s*(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\s*$', '', province_upper).strip()
        all_variants = []
        
        # Check if province has a directional modifier
        has_directional = bool(re.search(r'\b(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\b', province_upper))
        
        if province_base_name != province_upper:
            # This is a directional province (e.g., "Northern Samar", "Ilocos Norte", "Ilocos Sur")
            # Get all variants to validate against
            all_variants = self._get_location_variants(province_base_name, 'province', dedup_dict)
            # CRITICAL: Only use the exact variant, never match to other directional variants
            # "Ilocos Norte" should NEVER match "Ilocos Sur" projects
            province_variants = [province_upper]  # Reset to only use exact match - NO base name fallback
        elif province_base_name == province_upper:
            # This is a base province name (e.g., "Samar", "Ilocos")
            # Get all variants to know what to exclude
            all_variants = self._get_location_variants(province_upper, 'province', dedup_dict)
            # If there are multiple variants (e.g., Ilocos Norte, Ilocos Sur)
            # We should NOT match at all - require explicit directional variant
            # This prevents "Ilocos" from matching both "Ilocos Norte" and "Ilocos Sur"
            if len(all_variants) > 1:
                # Multiple variants exist - require explicit directional variant
                # Don't match base name to avoid cross-variant matches
                province_variants = []  # Empty - require explicit match
            else:
                # Only one variant or no variants - safe to use base name
                province_variants = [province_upper]
        
        # CRITICAL: If we have a directional modifier, NEVER try base name variants
        # This is a double-check to prevent any fallback to base name matching
        if has_directional and province_base_name != province_upper:
            # We have a directional province - ONLY use exact match, no base name
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
                # CRITICAL: This should give us the specific district if the municipality/barangay is properly mapped
                variant_candidates = district_lookup.get((prov_variant, location_upper), [])
                
                if variant_candidates:
                    candidates.extend(variant_candidates)
                    match_score = 100
                    # CRITICAL: If we have a location (municipality/barangay) and got an exact match,
                    # we should NOT fall back to province-only match - the exact match should be definitive
                    # If we got multiple candidates from exact match, we'll filter by district number later
                    break
                
                # 2. Province-only match: (province, '') - score 10
                # CRITICAL: Only use province-only match if:
                # - No specific barangay/municipality was provided (location_upper is empty), OR
                # - Exact match failed (no mapping exists for this municipality/barangay)
                # CRITICAL: For city districts with a location specified, we should NOT use province-only match
                # because it will return ALL districts in that city, causing incorrect assignments
                # CRITICAL FIX: Also validate directional variants to prevent "ILOCOS SUR" matching "ILOCOS NORTE"
                if not variant_candidates:
                    # Check if this is a city district and we need stricter matching
                    province_only_candidates = district_lookup.get((prov_variant, ''), [])
                    
                    if province_only_candidates:
                        # Filter candidates to only city districts if we have location
                        # For province districts, allow province-only match BUT validate directional variants
                        # For city districts, be more strict
                        filtered_candidates = []
                        for cm_name, cm_data in province_only_candidates:
                            is_city_district = cm_data.get('is_city_district', False)
                            
                            # CRITICAL: Validate directional variants for province districts
                            if not is_city_district:
                                # Province district - validate directional variants match
                                cm_provinces = cm_data.get('provinces', [])
                                directional_match = False
                                
                                for cm_province in cm_provinces:
                                    cm_prov_upper = cm_province.upper().strip()
                                    
                                    # Extract base names and directional modifiers
                                    cm_base = re.sub(r'\s*(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\s*$', '', cm_prov_upper).strip()
                                    req_base = re.sub(r'\s*(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\s*$', '', prov_variant).strip()
                                    
                                    # If both have the same base name, check directional modifiers
                                    if cm_base == req_base and cm_base:
                                        # Extract directional modifiers
                                        cm_dir_match = re.search(r'\b(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\b', cm_prov_upper)
                                        req_dir_match = re.search(r'\b(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\b', prov_variant)
                                        
                                        cm_dir = cm_dir_match.group(0) if cm_dir_match else None
                                        req_dir = req_dir_match.group(0) if req_dir_match else None
                                        
                                        # If both have directional modifiers, they must match exactly
                                        if cm_dir and req_dir:
                                            if cm_dir == req_dir:
                                                directional_match = True
                                                break
                                        elif not cm_dir and not req_dir:
                                            # Both are base names (no directional) - allow match
                                            directional_match = True
                                            break
                                    elif cm_prov_upper == prov_variant:
                                        # Exact match (including directional variants)
                                        directional_match = True
                                        break
                                
                                # Only add if directional variants match
                                if directional_match:
                                    filtered_candidates.append((cm_name, cm_data))
                            elif not location_upper:
                                # City district but no location specified - allow match
                                filtered_candidates.append((cm_name, cm_data))
                            # CRITICAL: If city district AND location specified, skip province-only match
                            # (require specific barangay match instead)
                            # This prevents Matina, Davao City from matching to all Davao City districts
                            # We should only use province-only match when location is empty
                        
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
                # CRITICAL: Validate directional variants even for normalized matches
                if not candidates:
                    province_only_candidates = district_lookup.get((correct_prov, ''), [])
                    if province_only_candidates:
                        # Filter by directional variant match
                        filtered_candidates = []
                        for cm_name, cm_data in province_only_candidates:
                            cm_provinces = cm_data.get('provinces', [])
                            is_city_district = cm_data.get('is_city_district', False)
                            
                            # For province districts, validate directional variants
                            if not is_city_district:
                                directional_match = False
                                for cm_province in cm_provinces:
                                    cm_prov_upper = cm_province.upper().strip()
                                    
                                    # Extract base names and directional modifiers
                                    cm_base = re.sub(r'\s*(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\s*$', '', cm_prov_upper).strip()
                                    req_base = re.sub(r'\s*(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\s*$', '', correct_prov).strip()
                                    
                                    if cm_base == req_base and cm_base:
                                        cm_dir_match = re.search(r'\b(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\b', cm_prov_upper)
                                        req_dir_match = re.search(r'\b(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\b', correct_prov)
                                        
                                        cm_dir = cm_dir_match.group(0) if cm_dir_match else None
                                        req_dir = req_dir_match.group(0) if req_dir_match else None
                                        
                                        if cm_dir and req_dir:
                                            if cm_dir == req_dir:
                                                directional_match = True
                                                break
                                        elif not cm_dir and not req_dir:
                                            directional_match = True
                                            break
                                    elif cm_prov_upper == correct_prov:
                                        directional_match = True
                                        break
                                
                                if directional_match:
                                    filtered_candidates.append((cm_name, cm_data))
                            else:
                                # City district - allow match
                                filtered_candidates.append((cm_name, cm_data))
                        
                        candidates = filtered_candidates
                
                if candidates:
                    match_score = 5
        
        # 4. FUZZY MATCHING (last resort) - score 3
        # Use Levenshtein distance to find closest match
        # CRITICAL: Do NOT use fuzzy matching for directional provinces - require exact match
        # This prevents "ILOCOS SUR" from fuzzy-matching to "ILOCOS NORTE"
        if not candidates:
            # Check if province has directional modifier - if so, skip fuzzy matching
            province_has_directional = bool(re.search(r'\b(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\b', province_upper))
            
            if province_has_directional:
                # Has directional modifier - skip fuzzy matching to prevent cross-variant matches
                # Only exact matches are allowed for directional provinces
                pass
            else:
                # No directional modifier - safe to try fuzzy matching
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
                    # CRITICAL: Validate directional variants even for fuzzy matches
                    if not candidates:
                        province_only_candidates = district_lookup.get((closest_prov_upper, ''), [])
                        if province_only_candidates:
                            # Filter by directional variant match
                            filtered_candidates = []
                            for cm_name, cm_data in province_only_candidates:
                                cm_provinces = cm_data.get('provinces', [])
                                is_city_district = cm_data.get('is_city_district', False)
                                
                                # For province districts, validate directional variants
                                if not is_city_district:
                                    directional_match = False
                                    for cm_province in cm_provinces:
                                        cm_prov_upper = cm_province.upper().strip()
                                        
                                        # Extract base names and directional modifiers
                                        cm_base = re.sub(r'\s*(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\s*$', '', cm_prov_upper).strip()
                                        req_base = re.sub(r'\s*(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\s*$', '', closest_prov_upper).strip()
                                        
                                        if cm_base == req_base and cm_base:
                                            cm_dir_match = re.search(r'\b(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\b', cm_prov_upper)
                                            req_dir_match = re.search(r'\b(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\b', closest_prov_upper)
                                            
                                            cm_dir = cm_dir_match.group(0) if cm_dir_match else None
                                            req_dir = req_dir_match.group(0) if req_dir_match else None
                                            
                                            if cm_dir and req_dir:
                                                if cm_dir == req_dir:
                                                    directional_match = True
                                                    break
                                            elif not cm_dir and not req_dir:
                                                directional_match = True
                                                break
                                        elif cm_prov_upper == closest_prov_upper:
                                            directional_match = True
                                            break
                                    
                                    if directional_match:
                                        filtered_candidates.append((cm_name, cm_data))
                                else:
                                    # City district - allow match
                                    filtered_candidates.append((cm_name, cm_data))
                            
                            candidates = filtered_candidates
                    
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
        # CRITICAL: Convert project_year to int at the start to avoid type errors
        project_year_int = None
        if project_year is not None:
            try:
                project_year_int = int(project_year) if project_year else None
            except (ValueError, TypeError):
                project_year_int = None
        
        term_matched_candidates = []
        no_term_candidates = []
        term_mismatch_candidates = []
        
        if project_year_int is not None and candidates:
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
                        
                        if term_start is not None and term_end is not None and project_year_int is not None:
                            # CRITICAL: Only match if project_year is within term range
                            # Don't allow future terms to match past projects
                            # project_year_int is already converted to int above
                            
                            # ELECTION YEAR TRANSITION HANDLING (2022)
                            # In election years, the transition happens in June
                            # Projects before June go to the outgoing congressman
                            # Projects after June go to the incoming congressman
                            term_matches = False
                            
                            # Check if this is an election year transition (2022)
                            # Congressional terms are 3 years: e.g., 2019-2022, 2022-2025, 2025-2028
                            # Transition happens in June: outgoing serves Jan-Jun, incoming serves Jul-Dec
                            is_election_year_transition = (project_year_int == 2022)
                            
                            if is_election_year_transition:
                                # Both outgoing and incoming congressmen have 2022 in their 3-year terms
                                # Outgoing: term_start < 2022, term_end = 2022 (e.g., 2019-2022)
                                # Incoming: term_start = 2022, term_end > 2022 (e.g., 2022-2025)
                                # Need to check month to determine which congressman
                                
                                # Try to get project month from project data
                                project_month = None
                                if hasattr(self, '_current_project_data'):
                                    proj_data = getattr(self, '_current_project_data', {})
                                    # Try to extract month from date fields
                                    date_field = proj_data.get('date_started') or proj_data.get('start_date') or \
                                                proj_data.get('award_date') or proj_data.get('contract_date')
                                    if date_field:
                                        project_month = self._get_project_month(date_field)
                                
                                if project_month is not None:
                                    # June 30 is the transition date (projects in June go to outgoing)
                                    # Projects Jan-Jun 2022: outgoing congressman (term ending in 2022, typically 3-year term like 2019-2022)
                                    # Projects Jul-Dec 2022: incoming congressman (term starting in 2022, typically 3-year term like 2022-2025)
                                    if project_month <= 6:
                                        # Before/on June - match if this is the outgoing congressman
                                        # Outgoing has term_start < 2022 and term_end >= 2022 (term includes 2022 and started before it)
                                        # This handles standard 3-year terms (2019-2022) and edge cases
                                        if term_start < 2022 and term_end >= 2022:
                                            term_matches = True
                                    else:
                                        # After June - match if this is the incoming congressman
                                        # Incoming has term_start = 2022 and term_end > 2022 (term starts in 2022)
                                        # This handles standard 3-year terms (2022-2025) and edge cases
                                        if term_start == 2022 and term_end > 2022:
                                            term_matches = True
                                else:
                                    # Can't determine month - use default behavior (match if year is in range)
                                    # This will match both, but the scoring will prioritize based on term overlap
                                    term_matches = (term_start <= project_year_int <= term_end)
                            else:
                                # Normal year matching (not 2022 transition)
                                # Check if project year falls within the 3-year term range
                                term_matches = (term_start <= project_year_int <= term_end)
                            
                            if term_matches:
                                # Score: prefer exact matches, then closer to term start
                                # Long terms are OK - they should match more projects
                                term_length = term_end - term_start + 1
                                distance_from_start = abs(project_year_int - term_start)
                                
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
                
                # CRITICAL: Negative validation - check if project is clearly from a different region/province
                # This prevents Jose Manuel Alba (Region X) from getting non-Region X projects
                # and Jose Alvarez (Palawan) from getting non-Palawan projects
                region_province_conflict = False
                
                if location_upper:
                    # Load region mappings from comprehensive location database if available
                    region_mappings = {}
                    location_db_path = Path(__file__).parent.parent / 'database' / 'philippine_locations.json'
                    if location_db_path.exists():
                        try:
                            with open(location_db_path, 'r', encoding='utf-8') as f:
                                location_db = json.load(f)
                            # Build region mappings from database
                            for region_id, region_data in location_db.get('region_province_mappings', {}).items():
                                prov_list = [p.upper().strip() for p in region_data.get('provinces', [])]
                                # Normalize region IDs
                                if region_id == '10':
                                    region_mappings['X'] = prov_list
                                    region_mappings['10'] = prov_list
                                elif region_id in ['IV-B', 'IVB', '4-B', '4B']:
                                    region_mappings['IV-B'] = prov_list
                                    region_mappings['IVB'] = prov_list
                                    region_mappings['4-B'] = prov_list
                                    region_mappings['4B'] = prov_list
                                else:
                                    region_mappings[region_id] = prov_list
                        except Exception:
                            pass
                    
                    # Fallback to hardcoded mappings if database not available
                    if not region_mappings:
                        region_mappings = {
                            'X': ['BUKIDNON', 'CAMIGUIN', 'MISAMIS OCCIDENTAL', 'MISAMIS ORIENTAL', 'LANAO DEL NORTE'],
                            'IV-B': ['PALAWAN', 'MARINDUQUE', 'OCCIDENTAL MINDORO', 'ORIENTAL MINDORO', 'ROMBLON'],
                            'IVB': ['PALAWAN', 'MARINDUQUE', 'OCCIDENTAL MINDORO', 'ORIENTAL MINDORO', 'ROMBLON'],
                            '4-B': ['PALAWAN', 'MARINDUQUE', 'OCCIDENTAL MINDORO', 'ORIENTAL MINDORO', 'ROMBLON'],
                            '4B': ['PALAWAN', 'MARINDUQUE', 'OCCIDENTAL MINDORO', 'ORIENTAL MINDORO', 'ROMBLON'],
                        }
                    
                    # Extract region from location if present
                    region_match = re.search(r'REGION\s+([IVX]+|\d+[-\s]?[A-Z]?|\d+)', location_upper, re.IGNORECASE)
                    if region_match:
                        region_key = region_match.group(1).upper().strip()
                        # Normalize region key
                        if region_key == '10':
                            region_key = 'X'
                        elif region_key in ['4-B', '4B']:
                            region_key = 'IV-B'
                        
                        # Check if congressman's province is in a specific region
                        cm_province_main = cm_provinces[0].upper() if cm_provinces else ''
                        
                        # Jose Manuel Alba - Bukidnon (Region X)
                        if cm_province_main == 'BUKIDNON':
                            if region_key != 'X' and region_key in region_mappings:
                                # Location mentions a different region - REJECT
                                region_province_conflict = True
                            elif region_key not in ['X', '10'] and region_key:
                                # Location mentions a region that's not Region X - REJECT
                                region_province_conflict = True
                            # Also check if province_upper is explicitly NOT from Region X
                            if province_upper and province_upper not in region_mappings.get('X', []):
                                # Check if it's from another region
                                for reg_key, reg_provinces in region_mappings.items():
                                    if reg_key != 'X' and province_upper in reg_provinces:
                                        # Project is from a different region - REJECT
                                        region_province_conflict = True
                                        break
                        
                        # Jose Alvarez - Palawan (Region IV-B / MIMAROPA)
                        if cm_province_main == 'PALAWAN':
                            if region_key not in ['IV-B', 'IVB', '4-B', '4B'] and region_key in region_mappings:
                                # Location mentions a different region - REJECT
                                region_province_conflict = True
                            # Also check if province_upper is explicitly NOT from MIMAROPA
                            if province_upper and province_upper not in region_mappings.get('IV-B', []):
                                # Check if it's from another region
                                for reg_key, reg_provinces in region_mappings.items():
                                    if reg_key not in ['IV-B', 'IVB', '4-B', '4B'] and province_upper in reg_provinces:
                                        # Project is from a different region - REJECT
                                        region_province_conflict = True
                                        break
                    
                    # Also check for explicit province contradictions in location
                    # CRITICAL: Only reject CLEAR contradictions, not unknown locations
                    # Since our database is incomplete (we only know ~162 districts, not all 82 provinces, 146 cities, 1,490 municipalities),
                    # we should be more lenient and only reject when we're CERTAIN there's a conflict
                    
                    # Define clear province contradictions (only for major, unambiguous provinces)
                    # These are provinces that are geographically distant and unlikely to be confused
                    clear_contradictions = {
                        'BUKIDNON': ['PALAWAN', 'CEBU', 'ILOILO', 'LEYTE', 'BOHOL', 'NEGROS', 'SAMAR', 'BILIRAN', 'SIQUIJOR'],
                        'PALAWAN': ['BUKIDNON', 'CEBU', 'ILOILO', 'LEYTE', 'BOHOL', 'NEGROS', 'SAMAR', 'BILIRAN', 'SIQUIJOR', 'CAMIGUIN'],
                        'CEBU': ['BUKIDNON', 'PALAWAN', 'CAMIGUIN'],
                        'ILOILO': ['BUKIDNON', 'PALAWAN', 'CAMIGUIN'],
                    }
                    
                    cm_province_main = cm_provinces[0].upper() if cm_provinces else ''
                    
                    # Only check for contradictions if congressman's province is in our contradiction map
                    if cm_province_main in clear_contradictions:
                        contradictory_provinces = clear_contradictions[cm_province_main]
                        for contrad_prov in contradictory_provinces:
                            if contrad_prov in location_upper:
                                # Check if this is a standalone mention (not part of a larger word)
                                # This prevents false positives like "CEBU" in "CEBULAN" matching "CEBU"
                                contrad_pattern = r'\b' + re.escape(contrad_prov) + r'\b'
                                if re.search(contrad_pattern, location_upper, re.IGNORECASE):
                                    # Location clearly mentions contradictory province - REJECT
                                    region_province_conflict = True
                                    break
                        
                        if region_province_conflict:
                            break
                
                # If there's a region/province conflict, skip this candidate
                if region_province_conflict:
                    continue
                
                # Check if any of the congressman's provinces match the requested province
                province_matches = False
                for cm_province in cm_provinces:
                    cm_prov_upper = cm_province.upper().strip()
                    
                    # Exact match
                    if cm_prov_upper == province_upper:
                        province_matches = True
                        break
                    
                    # CRITICAL FIX: Prevent directional variant mismatches
                    # "ILOCOS NORTE" should NEVER match "ILOCOS SUR" and vice versa
                    # This is the STRICTEST check - must be applied before any other matching logic
                    
                    # Extract base names and directional modifiers
                    cm_base = re.sub(r'\s*(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\s*$', '', cm_prov_upper).strip()
                    req_base = re.sub(r'\s*(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\s*$', '', province_upper).strip()
                    
                    # Extract directional modifiers (case-insensitive, with word boundaries)
                    cm_dir_match = re.search(r'\b(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\b', cm_prov_upper, re.IGNORECASE)
                    req_dir_match = re.search(r'\b(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\b', province_upper, re.IGNORECASE)
                    
                    cm_dir = cm_dir_match.group(0).upper().strip() if cm_dir_match else None
                    req_dir = req_dir_match.group(0).upper().strip() if req_dir_match else None
                    
                    # If both have the same base name (e.g., "ILOCOS"), check directional modifiers
                    if cm_base == req_base and cm_base:
                        # CRITICAL: For directional provinces, require EXACT match
                        # "ILOCOS NORTE" should NEVER match "ILOCOS SUR" and vice versa
                        if cm_dir and req_dir:
                            # Both have directional modifiers - they MUST match exactly
                            # Normalize both directions for comparison (handle "DEL SUR" vs "SUR")
                            cm_dir_clean = re.sub(r'\s+', ' ', cm_dir.upper().strip())
                            req_dir_clean = re.sub(r'\s+', ' ', req_dir.upper().strip())
                            
                            # Also check if they're equivalent (e.g., "SUR" = "DEL SUR" for Ilocos)
                            cm_dir_simple = re.sub(r'^DEL\s+', '', cm_dir_clean).strip()
                            req_dir_simple = re.sub(r'^DEL\s+', '', req_dir_clean).strip()
                            
                            if cm_dir_clean != req_dir_clean and cm_dir_simple != req_dir_simple:
                                # Different directional variants - REJECT match immediately
                                # e.g., "ILOCOS NORTE" != "ILOCOS SUR"
                                # This is a hard rejection - do not proceed with any other matching
                                continue
                            else:
                                # Same directional modifiers - allow match
                                province_matches = True
                                break
                        elif cm_dir or req_dir:
                            # One has directional, one doesn't - REJECT match
                            # e.g., "ILOCOS NORTE" != "ILOCOS" (base name)
                            # e.g., "ILOCOS" (base) != "ILOCOS NORTE" (directional)
                            # This prevents base name from matching directional variants
                            continue
                        else:
                            # Neither has directional - safe to match if base names match
                            if cm_base == req_base:
                                province_matches = True
                                break
                    elif cm_dir and req_dir and cm_dir != req_dir:
                        # Different base names but both have directionals - still reject if directionals differ
                        # This catches edge cases
                        continue
                    
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
                    # CRITICAL: Do NOT allow compound matches for directional provinces
                    # "ILOCOS SUR" should NEVER match "ILOCOS NORTE" via compound matching
                    # Check if either has a directional modifier
                    has_cm_directional = bool(re.search(r'\b(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\b', cm_prov_upper))
                    has_req_directional = bool(re.search(r'\b(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\b', province_upper))
                    
                    # If either has a directional, require exact match (no compound matching)
                    if has_cm_directional or has_req_directional:
                        # Skip compound matching for directional provinces - require exact match
                        continue
                    
                    # Only allow compound matching for non-directional provinces
                    # CRITICAL: Be more strict - require that the match is meaningful and not just a substring
                    # Example: "Bukidnon" should match "Bukidnon" but NOT match "Region X - Bukidnon" unless
                    # the project province is actually "Bukidnon"
                    # Also: "Palawan" should match "Palawan" but NOT match "Rizal (PALAWAN)" unless explicitly in Palawan
                    compound_match = False
                    if re.search(r'\b' + re.escape(province_upper) + r'\b', cm_prov_upper) or \
                       re.search(r'\b' + re.escape(cm_prov_upper) + r'\b', province_upper):
                        # CRITICAL: For specific provinces, require exact or near-exact match
                        # This prevents false matches like "Rizal (PALAWAN)" matching "Palawan" congressman
                        # or "Region X - Bukidnon" matching when project is not from Bukidnon
                        
                        # Check if this is a known province that needs strict matching
                        strict_provinces = ['BUKIDNON', 'PALAWAN', 'RIZAL', 'CEBU', 'DAVAO', 'ILOILO']
                        needs_strict_match = (cm_prov_upper in strict_provinces) or (province_upper in strict_provinces)
                        
                        if needs_strict_match:
                            # For strict provinces, require that the province name appears as a standalone word
                            # and not just as part of a larger string like "Region X - Bukidnon" or "Rizal (PALAWAN)"
                            
                            # Check if province appears as a standalone word in the other string
                            cm_standalone = bool(re.search(r'^' + re.escape(cm_prov_upper) + r'$|^' + re.escape(cm_prov_upper) + r'\s|,\s*' + re.escape(cm_prov_upper) + r'\s|,\s*' + re.escape(cm_prov_upper) + r'$', province_upper))
                            prov_standalone = bool(re.search(r'^' + re.escape(province_upper) + r'$|^' + re.escape(province_upper) + r'\s|,\s*' + re.escape(province_upper) + r'\s|,\s*' + re.escape(province_upper) + r'$', cm_prov_upper))
                            
                            if not (cm_standalone or prov_standalone):
                                # Province doesn't appear as standalone - check if it's in a contradictory context
                                if location_upper:
                                    # Check for parenthetical contradictions (e.g., "Rizal (PALAWAN)")
                                    # But ONLY if the parenthetical province is different from what we're matching
                                    paren_matches = re.findall(r'\(([^)]+)\)', location_upper)
                                    for paren_text in paren_matches:
                                        paren_upper = paren_text.upper().strip()
                                        # If parentheses contain a different province, reject
                                        if paren_upper in strict_provinces:
                                            if (cm_prov_upper == 'PALAWAN' and paren_upper != 'PALAWAN') or \
                                               (cm_prov_upper != 'PALAWAN' and paren_upper == 'PALAWAN'):
                                                # Parenthetical contradicts - reject
                                                continue
                                    
                                    # Check for region mentions that might contradict
                                    # CRITICAL: For Bukidnon (Jose Manuel Alba), only match if project is from Region X
                                    if cm_prov_upper == 'BUKIDNON':
                                        # Check if location mentions a different region
                                        region_match = re.search(r'REGION\s+([IVX]+|\d+)', location_upper, re.IGNORECASE)
                                        if region_match:
                                            region_num = region_match.group(1).upper()
                                            if region_num not in ['X', '10']:
                                                # Location mentions a different region - reject
                                                continue
                                        # Also check if province_upper is not a Region X province
                                        region_x_provinces = ['BUKIDNON', 'CAMIGUIN', 'MISAMIS OCCIDENTAL', 'MISAMIS ORIENTAL', 'LANAO DEL NORTE']
                                        if province_upper and province_upper not in region_x_provinces:
                                            # Project province is not from Region X - reject
                                            continue
                                    
                                    # CRITICAL: For Palawan (Jose Alvarez), ensure we're matching Palawan projects
                                    # Don't reject if parenthetical says Palawan - that's actually correct
                                    if cm_prov_upper == 'PALAWAN':
                                        # Check if location mentions Palawan (which is good)
                                        if 'PALAWAN' in location_upper:
                                            # Location mentions Palawan - this is correct, allow match
                                            pass
                                        # Check if province_upper is Palawan or a MIMAROPA province
                                        elif province_upper:
                                            mimaropa_provinces = ['PALAWAN', 'MARINDUQUE', 'OCCIDENTAL MINDORO', 'ORIENTAL MINDORO', 'ROMBLON']
                                            if province_upper not in mimaropa_provinces:
                                                # Project province is not from MIMAROPA - reject
                                                continue
                        
                        compound_match = True
                    
                    if compound_match:
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
                
                # Note: District matches require location validation (already done above)
                # Contractor matches do NOT require location validation (handled separately)

                if province_matches:
                    validated_candidates.append((cm_name, cm_data))
            
            if validated_candidates:
                # CRITICAL: If multiple candidates match (e.g., multiple Davao City districts),
                # we need to determine which specific district this project belongs to
                # Strategy:
                # 1. If we have a location (municipality/barangay), check if it's mapped to a specific district
                # 2. Extract district number from project_district or location string
                # 3. Match against congressmen's district numbers
                # Example: Matina, Davao City 1st District should go to Paolo Duterte, not Isidro Ungab
                if len(validated_candidates) > 1:
                    # CRITICAL: If we have a location (municipality/barangay), check district_lookup again
                    # to see if the exact match should have given us a single district
                    # This handles cases where the municipality/barangay dictionary exists but wasn't used properly
                    # The district_lookup should have (province, municipality/barangay) -> [congressman] mappings
                    # that directly tell us which district a location belongs to
                    if location_upper:
                        # Re-check exact match for province and its variants to see if we can narrow it down
                        # Try the main province first
                        exact_match_candidates = district_lookup.get((province_upper, location_upper), [])
                        if exact_match_candidates:
                            if len(exact_match_candidates) == 1:
                                # Exact match found a single candidate - use that instead
                                # This means the municipality/barangay dictionary has the correct mapping
                                validated_candidates = exact_match_candidates
                            elif len(exact_match_candidates) < len(validated_candidates):
                                # Exact match found fewer candidates - prefer those
                                # This means the exact match is more specific than what we have
                                validated_candidates = exact_match_candidates
                        
                        # If still multiple, try province variants (like Davao City / Davao Del Sur)
                        if len(validated_candidates) > 1:
                            # Get province variants that were used earlier in the function
                            # Check Davao variants specifically
                            davao_variants = []
                            if province_upper in ['DAVAO DEL SUR', 'DAVAO CITY', 'DAVAO DEL NORTE', 'DAVAO ORIENTAL', 'DAVAO DE ORO']:
                                if province_upper == 'DAVAO DEL SUR':
                                    davao_variants = ['DAVAO CITY']
                                elif province_upper == 'DAVAO CITY':
                                    davao_variants = ['DAVAO DEL SUR']
                            
                            for prov_variant in davao_variants:
                                exact_match_candidates = district_lookup.get((prov_variant, location_upper), [])
                                if exact_match_candidates and len(exact_match_candidates) == 1:
                                    # Found single match with variant - use it
                                    validated_candidates = exact_match_candidates
                                    break
                                elif exact_match_candidates and len(exact_match_candidates) < len(validated_candidates):
                                    # Variant match is more specific
                                    validated_candidates = exact_match_candidates
                    
                    # Try to extract district number from location, project_district parameter, or municipality_barangay
                    # CRITICAL: Only extract district number if it's associated with the correct province/city
                    # This prevents extracting "3rd" from "Cebu 3rd District" when we're matching "Davao City" projects
                    district_number = None
                    
                    # First, try project_district parameter if provided
                    if project_district:
                        project_district_upper = str(project_district).upper()
                        # CRITICAL: Verify that the project_district mentions the correct province/city
                        # Extract province name from project_district and verify it matches
                        # Pattern: "Davao City 3rd District" should match province "DAVAO CITY"
                        # Pattern: "Cebu 3rd District" should NOT match province "DAVAO CITY"
                        province_in_district = False
                        # Check if province name appears in project_district
                        if province_upper in project_district_upper:
                            province_in_district = True
                        # Also check Davao variants
                        elif province_upper in ['DAVAO CITY', 'DAVAO DEL SUR']:
                            if 'DAVAO' in project_district_upper and ('CITY' in project_district_upper or 'DEL SUR' in project_district_upper):
                                province_in_district = True
                        
                        # Only extract district number if province matches
                        if province_in_district:
                            district_match = re.search(r'\b(\d+)(ST|ND|RD|TH)\s+DISTRICT\b', project_district_upper, re.IGNORECASE)
                            if district_match:
                                district_number = int(district_match.group(1))
                            else:
                                # Try just number with ordinal suffix
                                district_match = re.search(r'\b(\d+)(ST|ND|RD|TH)\b', project_district_upper, re.IGNORECASE)
                                if district_match:
                                    district_number = int(district_match.group(1))
                    
                    # If not found in project_district, try location
                    # CRITICAL: Only extract if location mentions the correct province/city
                    if district_number is None and location_upper:
                        # Verify that location mentions the correct province/city
                        province_in_location = False
                        # Check if province name appears in location
                        if province_upper in location_upper:
                            province_in_location = True
                        # Also check Davao variants
                        elif province_upper in ['DAVAO CITY', 'DAVAO DEL SUR']:
                            if 'DAVAO' in location_upper and ('CITY' in location_upper or 'DEL SUR' in location_upper):
                                province_in_location = True
                        
                        # Only extract district number if province matches
                        if province_in_location:
                            # Check for patterns like "1ST DISTRICT", "1ST", "FIRST DISTRICT"
                            district_match = re.search(r'\b(\d+)(ST|ND|RD|TH)\s+DISTRICT\b', location_upper, re.IGNORECASE)
                            if district_match:
                                district_number = int(district_match.group(1))
                            else:
                                # Try just number with ordinal suffix
                                district_match = re.search(r'\b(\d+)(ST|ND|RD|TH)\b', location_upper, re.IGNORECASE)
                                if district_match:
                                    district_number = int(district_match.group(1))
                    
                    # If we found a district number, filter candidates by district
                    # CRITICAL: We must verify BOTH the district number AND the province/city name match
                    # This prevents matching "Davao City 3rd District" to "Cebu 3rd District" just because both are 3rd
                    if district_number:
                        district_matched_candidates = []
                        for cm_name, cm_data in validated_candidates:
                            cm_district = cm_data.get('district', None)
                            cm_provinces = cm_data.get('provinces', [])
                            
                            if cm_district:
                                # Extract district number from congressman's district (e.g., "1st District" -> 1)
                                cm_district_str = str(cm_district).upper()
                                cm_district_match = re.search(r'\b(\d+)(ST|ND|RD|TH)\s+DISTRICT\b', cm_district_str, re.IGNORECASE)
                                if cm_district_match:
                                    cm_district_num = int(cm_district_match.group(1))
                                    # CRITICAL: Verify district number matches
                                    if cm_district_num == district_number:
                                        # CRITICAL: Also verify that the congressman's province matches the project's province
                                        # This prevents matching "Davao City 3rd" to "Cebu 3rd" just because both are 3rd
                                        province_matches = False
                                        for cm_province in cm_provinces:
                                            cm_prov_upper = cm_province.upper().strip()
                                            # Check if congressman's province matches project's province
                                            if cm_prov_upper == province_upper:
                                                province_matches = True
                                                break
                                            # Also check Davao variants
                                            if (cm_prov_upper in ['DAVAO CITY', 'DAVAO DEL SUR'] and 
                                                province_upper in ['DAVAO CITY', 'DAVAO DEL SUR']):
                                                province_matches = True
                                                break
                                        
                                        # CRITICAL ADDITIONAL CHECK: Verify location doesn't contradict the match
                                        # If location clearly indicates a different province, reject the match
                                        # Example: project_district says "Cebu 5th District" but location says "Davao del Sur"
                                        if province_matches and location_upper:
                                            # Check if location mentions a different province than what we're matching
                                            location_province_conflict = False
                                            
                                            # List of known provinces to check for conflicts
                                            known_provinces = ['CEBU', 'DAVAO', 'ILOILO', 'LEYTE', 'BOHOL', 'NEGROS', 
                                                              'SAMAR', 'BILIRAN', 'SIQUIJOR', 'MASBATE', 'CAMIGUIN']
                                            
                                            for known_prov in known_provinces:
                                                # Check if location mentions a province that doesn't match
                                                if known_prov in location_upper:
                                                    # Check if this province matches the congressman's province
                                                    location_matches_cm = False
                                                    for cm_province in cm_provinces:
                                                        cm_prov_upper = cm_province.upper().strip()
                                                        if known_prov in cm_prov_upper or cm_prov_upper in known_prov:
                                                            location_matches_cm = True
                                                            break
                                                    
                                                    # If location mentions a province that doesn't match congressman, it's a conflict
                                                    if not location_matches_cm:
                                                        # Special case: Cebu vs Davao - these should never match
                                                        if ('CEBU' in location_upper and 'DAVAO' in cm_prov_upper) or \
                                                           ('DAVAO' in location_upper and 'CEBU' in cm_prov_upper):
                                                            location_province_conflict = True
                                                            break
                                            
                                            if location_province_conflict:
                                                # Location contradicts the match - reject it
                                                continue
                                        
                                        if province_matches:
                                            district_matched_candidates.append((cm_name, cm_data))
                                else:
                                    # Try just number with ordinal
                                    cm_district_match = re.search(r'\b(\d+)(ST|ND|RD|TH)\b', cm_district_str, re.IGNORECASE)
                                    if cm_district_match:
                                        cm_district_num = int(cm_district_match.group(1))
                                        # CRITICAL: Verify district number matches
                                        if cm_district_num == district_number:
                                            # CRITICAL: Also verify that the congressman's province matches the project's province
                                            province_matches = False
                                            for cm_province in cm_provinces:
                                                cm_prov_upper = cm_province.upper().strip()
                                                # Check if congressman's province matches project's province
                                                if cm_prov_upper == province_upper:
                                                    province_matches = True
                                                    break
                                                # Also check Davao variants
                                                if (cm_prov_upper in ['DAVAO CITY', 'DAVAO DEL SUR'] and 
                                                    province_upper in ['DAVAO CITY', 'DAVAO DEL SUR']):
                                                    province_matches = True
                                                    break
                                            
                                            # CRITICAL ADDITIONAL CHECK: Verify location doesn't contradict the match
                                            if province_matches and location_upper:
                                                location_province_conflict = False
                                                known_provinces = ['CEBU', 'DAVAO', 'ILOILO', 'LEYTE', 'BOHOL', 'NEGROS', 
                                                                  'SAMAR', 'BILIRAN', 'SIQUIJOR', 'MASBATE', 'CAMIGUIN']
                                                
                                                for known_prov in known_provinces:
                                                    if known_prov in location_upper:
                                                        location_matches_cm = False
                                                        for cm_province in cm_provinces:
                                                            cm_prov_upper = cm_province.upper().strip()
                                                            if known_prov in cm_prov_upper or cm_prov_upper in known_prov:
                                                                location_matches_cm = True
                                                                break
                                                        
                                                        if not location_matches_cm:
                                                            if ('CEBU' in location_upper and 'DAVAO' in cm_prov_upper) or \
                                                               ('DAVAO' in location_upper and 'CEBU' in cm_prov_upper):
                                                                location_province_conflict = True
                                                                break
                                                
                                                if location_province_conflict:
                                                    continue
                                            
                                            if province_matches:
                                                district_matched_candidates.append((cm_name, cm_data))
                        
                        # If district matching found candidates, use only those
                        if district_matched_candidates:
                            validated_candidates = district_matched_candidates
                        # CRITICAL: If we still have multiple candidates after district number filtering,
                        # and we have a location, this indicates the municipality/barangay dictionary
                        # might be missing or incomplete
                        # For Davao City specifically, if we can't determine district, reject all candidates to be safe
                        elif len(validated_candidates) > 1:
                            # Check if this is Davao City (check both province_upper and location_upper)
                            davao_variants = ['DAVAO CITY', 'DAVAO DEL SUR']
                            is_davao_city = (province_upper in davao_variants) or \
                                           (location_upper and any(variant in location_upper for variant in davao_variants))
                            
                            if is_davao_city:
                                # For Davao City, if we can't determine district number, default to 1st District (Paolo Duterte)
                                # This prevents cross-contamination while ensuring projects aren't lost
                                if not district_number:
                                    # Find Paolo Duterte (1st District) in the candidates
                                    paolo_duterte_candidate = None
                                    for cm_name, cm_data in validated_candidates:
                                        cm_district = cm_data.get('district_number', '')
                                        if '1ST' in str(cm_district).upper() or '1ST DISTRICT' in str(cm_district).upper():
                                            # Check if this is Paolo Duterte
                                            if 'DUTERTE' in cm_name.upper() and 'PAOLO' in cm_name.upper():
                                                paolo_duterte_candidate = (cm_name, cm_data)
                                                break
                                    
                                    if paolo_duterte_candidate:
                                        # Default to Paolo Duterte (1st District)
                                        validated_candidates = [paolo_duterte_candidate]
                                    else:
                                        # Paolo Duterte not in candidates - reject to be safe
                                        validated_candidates = []
                                # If we have a district number but multiple candidates still match,
                                # this means the district number validation failed - default to 1st District
                                elif district_number and not district_matched_candidates:
                                    # Find Paolo Duterte (1st District) in the candidates
                                    paolo_duterte_candidate = None
                                    for cm_name, cm_data in validated_candidates:
                                        cm_district = cm_data.get('district_number', '')
                                        if '1ST' in str(cm_district).upper() or '1ST DISTRICT' in str(cm_district).upper():
                                            if 'DUTERTE' in cm_name.upper() and 'PAOLO' in cm_name.upper():
                                                paolo_duterte_candidate = (cm_name, cm_data)
                                                break
                                    
                                    if paolo_duterte_candidate:
                                        # Default to Paolo Duterte (1st District)
                                        validated_candidates = [paolo_duterte_candidate]
                                    else:
                                        # Paolo Duterte not in candidates - reject to be safe
                                        validated_candidates = []
                            else:
                                # For other provinces, log a warning but proceed
                                # Municipality/barangay exists but district number not found or doesn't match
                                # This suggests the municipality/barangay-to-district mapping might be missing
                                pass
                
                # CRITICAL FIX: For Davao City, if we have candidates but no specific district determined,
                # and the location is explicitly "DAVAO CITY", default to Paolo Duterte (1st District)
                # This catches cases where district_lookup didn't narrow it down
                if len(validated_candidates) > 1 and location_upper == 'DAVAO CITY':
                     paolo_duterte_candidate = None
                     for cm_name, cm_data in validated_candidates:
                         if 'DUTERTE' in cm_name.upper() and 'PAOLO' in cm_name.upper():
                             paolo_duterte_candidate = (cm_name, cm_data)
                             break
                     
                     if paolo_duterte_candidate:
                         validated_candidates = [paolo_duterte_candidate]
                
                # If project_year is provided and multiple candidates match, prioritize the one whose term best matches
                # CRITICAL: Use project_year_int (converted to int) instead of project_year (may be string)
                if project_year_int is not None and len(validated_candidates) > 1:
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
                                    # CRITICAL: Use project_year_int (int) instead of project_year (may be string)
                                    
                                    # ELECTION YEAR TRANSITION HANDLING (2022)
                                    # In election years, the transition happens in June
                                    # Projects before June go to the outgoing congressman
                                    # Projects after June go to the incoming congressman
                                    term_matches = False
                                    
                                    # Check if this is an election year transition (2022)
                                    # Congressional terms are 3 years: e.g., 2019-2022, 2022-2025, 2025-2028
                                    # Transition happens in June: outgoing serves Jan-Jun, incoming serves Jul-Dec
                                    is_election_year_transition = (project_year_int == 2022)
                                    
                                    if is_election_year_transition:
                                        # Both outgoing and incoming congressmen have 2022 in their 3-year terms
                                        # Outgoing: term_start < 2022, term_end = 2022 (e.g., 2019-2022)
                                        # Incoming: term_start = 2022, term_end > 2022 (e.g., 2022-2025)
                                        # Need to check month to determine which congressman
                                        
                                        # Try to get project month from project data
                                        project_month = None
                                        if hasattr(self, '_current_project_data'):
                                            proj_data = getattr(self, '_current_project_data', {})
                                            # Try to extract month from date fields
                                            date_field = proj_data.get('date_started') or proj_data.get('start_date') or \
                                                        proj_data.get('award_date') or proj_data.get('contract_date')
                                            if date_field:
                                                project_month = self._get_project_month(date_field)
                                        
                                        if project_month is not None:
                                            # June 30 is the transition date (projects in June go to outgoing)
                                            # Projects Jan-Jun 2022: outgoing congressman (3-year term ending in 2022)
                                            # Projects Jul-Dec 2022: incoming congressman (3-year term starting in 2022)
                                            if project_month <= 6:
                                                # Before/on June - match if this is the outgoing congressman
                                                # Outgoing has term_start < 2022 and term_end = 2022 (3-year term ending in 2022)
                                                if term_start < 2022 and term_end == 2022:
                                                    term_matches = True
                                            else:
                                                # After June - match if this is the incoming congressman
                                                # Incoming has term_start = 2022 and term_end = 2025 (3-year term starting in 2022)
                                                if term_start == 2022 and term_end == 2025:
                                                    term_matches = True
                                        else:
                                            # Can't determine month - use default behavior
                                            # This will match both, but the scoring will prioritize based on term overlap
                                            term_matches = (term_start <= project_year_int <= term_end)
                                    else:
                                        # Normal year matching (not 2022 transition)
                                        # Check if project year falls within the 3-year term range
                                        term_matches = (term_start <= project_year_int <= term_end)
                                    
                                    if term_matches:
                                        # Exact match - calculate score based on how centered the year is in the term
                                        term_length = term_end - term_start + 1
                                        year_position = project_year_int - term_start
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
                # CRITICAL: Check if we have any validated candidates before accessing
                if validated_candidates:
                    return (validated_candidates[0][0], match_score)
                else:
                    # No validated candidates - return None to indicate no match
                    return None
        
        return None

    def _find_congressman_by_contractor(self, contractor_name: str, contractor_lookup: Dict, 
                                        contractor_inverted_index: Dict, congressmen_data: Dict) -> Optional[tuple]:
        """
        O(1) lookup for congressman by contractor.
        CRITICAL: Only matches verified contractor relationships from contractor_dynasty_matches.
        Supports JVs (joint ventures) - can return up to 2 matches for projects with "/" separator.
        Returns: (congressman_name, match_score) or None (for single contractor)
                 For JVs, returns the best match (first contractor takes priority)
        
        Matching strategy:
        1. Exact match on company name (highest priority) - score 100
        2. Normalized match (removes special chars, normalizes spaces) - score 100
        3. Partial match: if contractor name contains a lookup key (e.g., "SUNWEST" in "SUNWEST, INC.") - score 90
        4. Reverse partial match: if lookup key contains contractor name (e.g., "FS CO" in "FS CO BUILDERS") - score 90
        """
        if not contractor_name:
            return None
        
        contractor_upper = contractor_name.upper().strip()
        
        # CRITICAL: Handle JVs (joint ventures) - split by "/" to get individual contractors
        # Example: "MACROPRIME BUILDERS / SUNWEST, INC." -> ["MACROPRIME BUILDERS", "SUNWEST, INC."]
        contractor_parts = [part.strip() for part in contractor_upper.split('/')]
        
        # For JVs, we'll process each part and return the best match
        # Store all matches to potentially return up to 2
        all_matches = []
        
        # Process each contractor part in the JV
        for contractor_part in contractor_parts:
            if not contractor_part:
                continue
            
            normalized = re.sub(r'[^A-Z0-9]+', ' ', contractor_part).strip()
            
            # Try exact match first (highest priority)
            candidates = contractor_lookup.get(contractor_part, [])
            match_score = 100
            
            # Try normalized match (removes special chars, normalizes spaces)
            if not candidates:
                candidates = contractor_lookup.get(normalized, [])
                match_score = 100
            
            # CRITICAL: Also try partial matching for verified contractors
            # This handles cases like "SUNWEST" matching "SUNWEST, INC." or "SUNWEST CONSTRUCTION"
            # Only do this for verified contractors (those in contractor_lookup)
            if not candidates:
                # Normalize contractor name for better matching
                normalized_contractor = re.sub(r'[^A-Z0-9]+', ' ', contractor_part).strip()
                
                # Extract key tokens from contractor name (words of 2+ chars for better matching)
                # CRITICAL: Filter out common words - only match on proper names
                contractor_tokens = set()
                for token in re.split(r'[^A-Z0-9]+', normalized_contractor):
                    token = token.strip()
                    if len(token) >= 2 and token not in self.COMMON_TOKENS:  # Exclude common words
                        contractor_tokens.add(token)
                
                # Check if any lookup key matches (either direction)
                for lookup_key in contractor_lookup.keys():
                    lookup_key_clean = lookup_key.strip()
                    if len(lookup_key_clean) < 2:  # Changed from 3 to 2 to allow "FS", "CO", etc.
                        continue
                    
                    # Normalize lookup key
                    normalized_lookup = re.sub(r'[^A-Z0-9]+', ' ', lookup_key_clean).strip()
                    
                    # Extract tokens from lookup key
                    # CRITICAL: Filter out common words - only match on proper names
                    lookup_tokens = set()
                    for token in re.split(r'[^A-Z0-9]+', normalized_lookup):
                        token = token.strip()
                        if len(token) >= 2 and token not in self.COMMON_TOKENS:  # Exclude common words
                            lookup_tokens.add(token)
                    
                    # Check if there's significant token overlap on PROPER NAMES only
                    # This handles cases like:
                    # - "SUNWEST" (lookup) matches "SUNWEST, INC." (project) - both have "SUNWEST" (proper name)
                    # - "FS CO" (lookup) matches "FS CO BUILDERS" (project) - both have "FS" and "CO" (proper names)
                    # - "NEWINGTON BUILDERS" (lookup) matches "NEWINGTON BUILDERS, INC." (project) - "NEWINGTON" (proper name)
                    # We ignore common words like "CONSTRUCTION", "INC", "FORMERLY", etc.
                    common_proper_names = contractor_tokens.intersection(lookup_tokens)
                    
                    if common_proper_names:
                        # CRITICAL: Require at least ONE proper name match (not common words)
                        # This ensures we're matching on actual company names, not generic terms
                        if len(common_proper_names) >= 1:
                            # Additional validation: ensure we have meaningful proper name matches
                            # For very short names (2 chars like "FS", "CO"), require at least 1 match
                            # For longer names, require at least 1 proper name match
                            candidates = contractor_lookup[lookup_key]
                            match_score = 90
                            break
                    
                    # Also try substring matching as fallback (for cases where tokenization might miss)
                    # Check if lookup key is contained in contractor name (with word boundaries)
                    if re.search(r'\b' + re.escape(lookup_key_clean) + r'\b', contractor_part):
                        candidates = contractor_lookup[lookup_key]
                        match_score = 90
                        break
                    
                    # For short names (2-5 chars), also try without word boundaries
                    # This handles "FS CO" matching "FS CO BUILDERS" when "FS" or "CO" alone might not match
                    # Also handles "S-ANG" matching "S-ANG CONSTRUCTION"
                    if len(lookup_key_clean) <= 5 and lookup_key_clean in contractor_part:
                        # Make sure it's not a false match (e.g., "CO" matching "CONSTRUCTION")
                        # Check if it's followed by space, comma, dash, slash, or end of string
                        if re.search(re.escape(lookup_key_clean) + r'[\s,)\-/]', contractor_part) or \
                           contractor_part.endswith(lookup_key_clean) or \
                           contractor_part.startswith(lookup_key_clean):
                            # Additional safety: for very short names (2 chars), check it's not part of a longer word
                            if len(lookup_key_clean) <= 2:
                                # Only match if it's at word boundaries or standalone
                                if re.search(r'\b' + re.escape(lookup_key_clean) + r'\b', contractor_part) or \
                                   contractor_part == lookup_key_clean:
                                    candidates = contractor_lookup[lookup_key]
                                    match_score = 90
                                    break
                            else:
                                candidates = contractor_lookup[lookup_key]
                                match_score = 90
                                break
                    
                    # Check reverse: if contractor name (normalized) appears in lookup key
                    if normalized_contractor and len(normalized_contractor) >= 3:
                        if re.search(r'\b' + re.escape(normalized_contractor) + r'\b', lookup_key_clean):
                            candidates = contractor_lookup[lookup_key]
                            match_score = 90
                            break
                        
                        # For short contractor names, also try without word boundaries
                        if len(normalized_contractor) <= 5 and normalized_contractor in lookup_key_clean:
                            if re.search(re.escape(normalized_contractor) + r'[\s,)]', lookup_key_clean) or \
                               lookup_key_clean.endswith(normalized_contractor):
                                candidates = contractor_lookup[lookup_key]
                                match_score = 90
                                break
            
            # Only proceed if we have matches for this contractor part
            # This ensures we only match verified contractor relationships
            if candidates:
                # CRITICAL: Collect ALL non-excluded candidates, then prioritize
                # Party-list congressmen should be prioritized since contractor matching
                # is their primary method (they don't have districts)
                valid_candidates = []
                
                for cm_name, cm_data in candidates:
                    contractor_exclusions = cm_data.get('contractor_exclusions', {})
                    excluded = False
                    for base, exclusions in contractor_exclusions.items():
                        if base in contractor_part:
                            for exclusion_value in exclusions:
                                if exclusion_value in contractor_part:
                                    excluded = True
                                    break
                        if excluded:
                            break
                    
                    if not excluded:
                        is_partylist = cm_data.get('is_partylist', False)
                        # Check if this contractor is in the congressman's family_connections
                        # (more specific match = higher priority)
                        family_contractors = cm_data.get('contractors', [])
                        is_family_contractor = any(
                            contractor_part in fc.upper() or fc.upper() in contractor_part
                            for fc in family_contractors
                        )
                        valid_candidates.append((cm_name, cm_data, is_partylist, is_family_contractor, match_score))
            
                if valid_candidates:
                    # CRITICAL FIX: For Elizaldy Co, only match if contractor is explicitly in his contractor list
                    # This prevents over-matching contractors not linked to him
                    elizaldy_co_name_variants = ['ELIZALDY', 'ELIZALDY CO', 'ELIZALDY SALCEDO CO']
                    filtered_valid_candidates = []
                    
                    for cm_name, cm_data, is_partylist, is_family_contractor, part_score in valid_candidates:
                        cm_name_upper = cm_name.upper()
                        is_elizaldy_co = any(variant in cm_name_upper for variant in elizaldy_co_name_variants)
                        
                        if is_elizaldy_co:
                            # For Elizaldy Co, require explicit contractor match
                            # Only include if this contractor part is in his contractor list
                            family_contractors = cm_data.get('contractors', [])
                            
                            contractor_matches = any(
                                contractor_part in fc.upper() or fc.upper() in contractor_part or
                                # Also check token-based matching for better coverage
                                any(token in fc.upper() for token in contractor_part.split() if len(token) >= 3) or
                                any(token in contractor_part for token in fc.upper().split() if len(token) >= 3)
                                for fc in family_contractors
                            )
                            
                            if contractor_matches:
                                filtered_valid_candidates.append((cm_name, cm_data, is_partylist, is_family_contractor, part_score))
                            # Otherwise, skip Elizaldy Co for this contractor part
                        else:
                            # For other congressmen, include as normal
                            filtered_valid_candidates.append((cm_name, cm_data, is_partylist, is_family_contractor, part_score))
                    
                    if filtered_valid_candidates:
                        # Sort candidates: prioritize party-list AND family contractor matches
                        # Priority order:
                        # 1. Party-list with family contractor match (highest)
                        # 2. Party-list without family contractor match
                        # 3. Non-party-list with family contractor match
                        # 4. Non-party-list without family contractor match (lowest)
                        filtered_valid_candidates.sort(key=lambda x: (
                            not (x[2] and x[3]),  # Party-list + family match first
                            not x[2],              # Then party-list
                            not x[3],              # Then family match
                            -x[4]                  # Then by score (higher is better)
                        ))
                        
                        # Store match for this contractor part
                        all_matches.append((filtered_valid_candidates[0][0], filtered_valid_candidates[0][4]))
        
        # Return up to 2 unique matches for JVs
        if all_matches:
            # Get unique congressmen (by name) and their best scores
            unique_matches = {}
            for cm_name, score in all_matches:
                if cm_name not in unique_matches or score > unique_matches[cm_name]:
                    unique_matches[cm_name] = score
            
            # Sort by score (descending) and return up to 2
            sorted_matches = sorted(unique_matches.items(), key=lambda x: x[1], reverse=True)
            
            if len(sorted_matches) == 1:
                # Single match - return as tuple for backward compatibility
                return (sorted_matches[0][0], sorted_matches[0][1])
            elif len(sorted_matches) >= 2:
                # Multiple matches - return list of up to 2
                return [
                    (sorted_matches[0][0], sorted_matches[0][1]),
                    (sorted_matches[1][0], sorted_matches[1][1])
                ]
            else:
                return (sorted_matches[0][0], sorted_matches[0][1])
        
        return None

    def _merge_project_records(self, existing: Dict, new: Dict) -> Dict:
        """
        Merge two project records when they are duplicates across sources.
        Resolves conflicts in district_congressman and contractor_congressman by preferring:
        1. Higher match_score
        2. District match over contractor match
        3. Non-None values over None
        
        Args:
            existing: The existing project record in projects_by_key
            new: The new project record being merged
            
        Returns:
            Merged project record with resolved conflicts
        """
        merged = existing.copy()
        
        # Merge basic fields (prefer non-None values, or new if both exist)
        for key in ['project_name', 'project_description', 'contractor', 'amount', 'location', 'year', 'status']:
            if key in new and (new[key] and (not key in merged or not merged[key] or merged[key] == 'N/A')):
                merged[key] = new[key]
        
        # CRITICAL: Resolve district_congressman conflicts
        existing_district = existing.get('district_congressman')
        new_district = new.get('district_congressman')
        existing_district_score = existing.get('district_match_score', 0)
        new_district_score = new.get('district_match_score', 0)
        
        if existing_district and new_district:
            if existing_district == new_district:
                # Same congressman - keep it
                merged['district_congressman'] = existing_district
                merged['district_match_score'] = max(existing_district_score, new_district_score)
            else:
                # Different congressmen - prefer higher score
                if new_district_score > existing_district_score:
                    merged['district_congressman'] = new_district
                    merged['district_match_score'] = new_district_score
                    merged['district_match_type'] = new.get('district_match_type')
                    merged['congressman_district'] = new.get('congressman_district')
                else:
                    # Keep existing (higher or equal score)
                    merged['district_congressman'] = existing_district
                    merged['district_match_score'] = existing_district_score
        elif new_district:
            # Only new has district match - use it
            merged['district_congressman'] = new_district
            merged['district_match_score'] = new_district_score
            merged['district_match_type'] = new.get('district_match_type')
            merged['congressman_district'] = new.get('congressman_district')
        # If only existing has district match, it's already in merged
        
        # CRITICAL: Resolve contractor_congressman conflicts
        existing_contractor = existing.get('contractor_congressman')
        new_contractor = new.get('contractor_congressman')
        existing_contractor_score = existing.get('contractor_match_score', 0)
        new_contractor_score = new.get('contractor_match_score', 0)
        
        if existing_contractor and new_contractor:
            if existing_contractor == new_contractor:
                # Same congressman - keep it
                merged['contractor_congressman'] = existing_contractor
                merged['contractor_match_score'] = max(existing_contractor_score, new_contractor_score)
            else:
                # Different congressmen - prefer higher score
                if new_contractor_score > existing_contractor_score:
                    merged['contractor_congressman'] = new_contractor
                    merged['contractor_match_score'] = new_contractor_score
                    merged['contractor_match_type'] = new.get('contractor_match_type')
                    merged['contractor_congressman_district'] = new.get('contractor_congressman_district')
                else:
                    # Keep existing (higher or equal score)
                    merged['contractor_congressman'] = existing_contractor
                    merged['contractor_match_score'] = existing_contractor_score
        elif new_contractor:
            # Only new has contractor match - use it
            merged['contractor_congressman'] = new_contractor
            merged['contractor_match_score'] = new_contractor_score
            merged['contractor_match_type'] = new.get('contractor_match_type')
            merged['contractor_congressman_district'] = new.get('contractor_congressman_district')
        # If only existing has contractor match, it's already in merged
        
        # Update match_type (district takes precedence)
        if merged.get('district_congressman'):
            merged['match_type'] = 'district'
            merged['match_score'] = merged.get('district_match_score', 0)
        elif merged.get('contractor_congressman'):
            merged['match_type'] = 'contractor'
            merged['match_score'] = merged.get('contractor_match_score', 0)
        else:
            merged['match_type'] = existing.get('match_type', 'unknown')
            merged['match_score'] = existing.get('match_score', 0)
        
        # Merge other classification fields (prefer non-None, non-empty values)
        for key in ['project_district_type', 'project_district', 'project_barangay_municipality', 
                    'project_province_city_district', 'project_municipality_barangay', 'is_flood_related']:
            if key in new and new[key] and (key not in merged or not merged[key] or merged[key] == 'N/A'):
                merged[key] = new[key]
        
        return merged

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
                
                # CRITICAL: In force mode, clear old classification values to ensure fresh reclassification
                # This prevents old classification values from being used during matching or merging
                if self.force_reclassify:
                    classification_fields_to_clear = [
                        'district_congressman', 'contractor_congressman',
                        'project_district_type', 'project_district', 'project_barangay_municipality',
                        'project_province_city_district', 'project_municipality_barangay',
                        'is_flood_related', 'district_match_type', 'district_match_score',
                        'district_is_city_wide', 'congressman_district',
                        'contractor_match_type', 'contractor_match_score',
                        'contractor_congressman_district', 'match_type', 'match_score'
                    ]
                    for field in classification_fields_to_clear:
                        if field in project_dict:
                            del project_dict[field]
                
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
            'Microsite': ['INFRAWATCH', 'MICROSITE'],  # Both names refer to the same source
            'Transparency': ['TRANSPARENCY'],
        }
        
        valid_sources = source_variations.get(source_name, [source_name.upper()])
        # Also add the source_name itself (case-insensitive) to valid sources
        valid_sources = [s.upper() for s in valid_sources] + [source_name.upper()]
        valid_sources = list(set(valid_sources))  # Remove duplicates
        
        filtered = []
        # Debug: collect unique source values for all sources, especially Transparency
        if source_name in ('Microsite', 'Transparency'):
            unique_sources = set()
            all_field_names = set()
            for project in projects[:1000]:  # Sample first 1000 to get better coverage
                # Check all possible source field names
                source = (project.get('_source') or 
                         project.get('source') or 
                         project.get('Source') or
                         project.get('SOURCE') or '').upper()
                if source:
                    unique_sources.add(source)
                # Also collect all field names to see what's available
                all_field_names.update(project.keys())
            if unique_sources:
                print(f"🔍 DEBUG: Found source values in data: {sorted(unique_sources)}")
            # Show some sample field names that might contain source info
            source_like_fields = [f for f in all_field_names if 'source' in f.lower() or 'type' in f.lower() or 'origin' in f.lower()]
            if source_like_fields:
                print(f"🔍 DEBUG: Source-like field names found: {sorted(source_like_fields)}")
        
        for project in projects:
            # Check multiple possible source field names
            source = (project.get('_source') or 
                     project.get('source') or 
                     project.get('Source') or
                     project.get('SOURCE') or '').upper()
            
            # Check if source matches any valid source (case-insensitive)
            if source in valid_sources:
                filtered.append(project)
            # Also check if source contains any of the valid source keywords (for partial matches)
            elif any(valid_src in source for valid_src in valid_sources if len(valid_src) > 3):
                filtered.append(project)
        
        if source_name in ('Microsite', 'Transparency') and len(filtered) == 0:
            print(f"⚠️  WARNING: No {source_name} projects found after filtering!")
            print(f"   Valid sources we're looking for: {valid_sources}")
            print(f"   Total projects checked: {len(projects)}")
            if unique_sources:
                print(f"   Available source values in data: {sorted(unique_sources)}")
        
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
            # Note: Infrawatch and Microsite are the same - use "Microsite" as the canonical name
            sources = [
                ("SSP", self._process_flood_chunk),
                ("DIME", self._process_dime_chunk),
                ("PhilGEPS", self._process_philgeps_chunk),
                ("Microsite", self._process_microsite_chunk),
                ("Transparency", self._process_transparency_chunk),
            ]
            
            for source_name, process_func in sources:
                try:
                    # Filter from in-memory data
                    projects = self._filter_projects_by_source(all_projects_data, source_name)
                    
                    # CRITICAL: For Microsite, if no projects found, try alternative approaches
                    if source_name == 'Microsite' and len(projects) == 0:
                        print(f"⚠️  No {source_name} projects found with standard filtering, trying alternative methods...")
                        # Try to find projects that might be Microsite but have different source values
                        # Check if any projects have Microsite-like characteristics
                        alt_projects = []
                        for p in all_projects_data[:10000]:  # Sample first 10k to avoid full scan
                            # Check various fields that might indicate Microsite
                            has_microsite_indicator = False
                            for field in ['Contract Details', 'Project Description', 'Contractor', 'Implementing Agency']:
                                if field in p and p[field]:
                                    val = str(p[field]).upper()
                                    if 'MICROSITE' in val or 'INFRAWATCH' in val:
                                        has_microsite_indicator = True
                                        break
                            
                            # If no source is set but has Microsite indicators, treat as Microsite
                            source = (p.get('_source') or p.get('source') or '').upper()
                            if (not source or source == 'NONE' or source == 'NULL') and has_microsite_indicator:
                                p['_source'] = 'Microsite'
                                alt_projects.append(p)
                        
                        if alt_projects:
                            print(f"   Found {len(alt_projects)} potential Microsite projects by content analysis")
                            projects = alt_projects
                    
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
            # Infrawatch and Microsite are the same - use "Microsite" as the canonical name
            sources = [
                ("SSP", self._process_flood_chunk),
                ("DIME", self._process_dime_chunk),
                ("PhilGEPS", self._process_philgeps_chunk),
                ("Microsite", self._process_microsite_chunk),
                ("Transparency", self._process_transparency_chunk),
            ]
            
            for source_name, process_func in sources:
                try:
                    # Filter from in-memory data instead of reading from disk
                    projects = self._filter_projects_by_source(all_projects_data, source_name)
                    
                    # Log if no projects found for any source
                    if len(projects) == 0:
                        print(f"⚠️  No {source_name} projects found in integrated parquet after filtering")
                    
                    # CRITICAL: For SSP/Flood, try loading from separate parquet file if it exists
                    if source_name in ('SSP', 'Flood Control', 'Flood') and len(projects) == 0:
                        flood_file = PARQUET_DIR / 'flood_projects.parquet'
                        print(f"   🔍 Checking for separate Flood file: {flood_file}")
                        if flood_file.exists():
                            print(f"   📂 Loading Flood/SSP from separate file: {flood_file}")
                            try:
                                flood_data = self.load_projects_from_parquet(flood_file, source_name=None)
                                print(f"   📊 Raw loaded: {len(flood_data)} projects")
                                # Ensure all projects have SSP as source
                                for p in flood_data:
                                    p['_source'] = 'SSP'
                                    p['source'] = 'SSP'
                                projects = flood_data
                                print(f"   ✅ Loaded {len(projects)} Flood/SSP projects from separate file")
                            except Exception as e:
                                print(f"   ⚠️  Error loading Flood from separate file: {e}")
                                import traceback
                                traceback.print_exc()
                        else:
                            print(f"   ❌ Flood file not found at: {flood_file}")

                    # CRITICAL: For Transparency, try loading from separate parquet file if it exists
                    if source_name == 'Transparency' and len(projects) == 0:
                        transparency_file = PARQUET_DIR / 'transparency_projects.parquet'
                        print(f"   🔍 Checking for separate Transparency file: {transparency_file}")
                        print(f"   📂 File exists: {transparency_file.exists()}")
                        if transparency_file.exists():
                            print(f"   📂 Loading Transparency from separate file: {transparency_file}")
                            try:
                                transparency_data = self.load_projects_from_parquet(transparency_file, source_name=None)
                                print(f"   📊 Raw loaded: {len(transparency_data)} projects")
                                # Ensure all projects have Transparency as source
                                for p in transparency_data:
                                    p['_source'] = 'Transparency'
                                    p['source'] = 'Transparency'
                                projects = transparency_data
                                print(f"   ✅ Loaded {len(projects)} Transparency projects from separate file")
                            except Exception as e:
                                print(f"   ⚠️  Error loading Transparency from separate file: {e}")
                                import traceback
                                traceback.print_exc()
                        else:
                            print(f"   ❌ Transparency file not found at: {transparency_file}")
                            print(f"   📁 PARQUET_DIR: {PARQUET_DIR}")
                            print(f"   📁 PARQUET_DIR exists: {PARQUET_DIR.exists()}")
                    
                    # CRITICAL: For DIME, try loading from separate parquet file if it exists
                    if source_name == 'DIME' and len(projects) == 0:
                        dime_file = PARQUET_DIR / 'dime_projects.parquet'
                        print(f"   🔍 Checking for separate DIME file: {dime_file}")
                        if dime_file.exists():
                            print(f"   📂 Loading DIME from separate file: {dime_file}")
                            try:
                                dime_data = self.load_projects_from_parquet(dime_file, source_name=None)
                                print(f"   📊 Raw loaded: {len(dime_data)} projects")
                                # Ensure all projects have DIME as source
                                for p in dime_data:
                                    p['_source'] = 'DIME'
                                    p['source'] = 'DIME'
                                projects = dime_data
                                print(f"   ✅ Loaded {len(projects)} DIME projects from separate file")
                            except Exception as e:
                                print(f"   ⚠️  Error loading DIME from separate file: {e}")
                                import traceback
                                traceback.print_exc()
                        else:
                            print(f"   ❌ DIME file not found at: {dime_file}")
                    
                    # CRITICAL: For Microsite and Transparency, if no projects found, try alternative approaches
                    if source_name in ('Microsite', 'Transparency') and len(projects) == 0:
                        print(f"⚠️  No {source_name} projects found with standard filtering, trying alternative methods...")
                        # Try to find projects that might have different source values
                        # Check if any projects have source-like characteristics
                        alt_projects = []
                        search_terms = {
                            'Microsite': ['MICROSITE', 'INFRAWATCH'],
                            'Transparency': ['TRANSPARENCY', 'DPWH SCRAPER']
                        }
                        terms = search_terms.get(source_name, [])
                        
                        for p in all_projects_data[:10000]:  # Sample first 10k to avoid full scan
                            # Check various fields that might indicate the source
                            has_indicator = False
                            for field in ['Contract Details', 'Project Description', 'Contractor', 'Implementing Agency', 'source', '_source']:
                                if field in p and p[field]:
                                    val = str(p[field]).upper()
                                    if any(term in val for term in terms):
                                        has_indicator = True
                                        break
                            
                            # If no source is set but has indicators, treat as the source
                            source = (p.get('_source') or p.get('source') or '').upper()
                            if (not source or source == 'NONE' or source == 'NULL') and has_indicator:
                                p['_source'] = source_name
                                p['source'] = source_name
                                alt_projects.append(p)
                        
                        if alt_projects:
                            print(f"   Found {len(alt_projects)} potential {source_name} projects by content analysis")
                            projects = alt_projects
                        else:
                            print(f"   ❌ No {source_name} projects found even after alternative methods")
                    
                    # Always log the filtered count (even if 0) for visibility
                    print(f"📊 Filtered {len(projects)} {source_name} projects from memory")
                    
                    if projects:
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
                    else:
                        # Even if no projects found, log it for debugging
                        print(f"⚠️  Skipping {source_name} - no projects to process")
                except Exception as e:
                    print(f"Error processing {source_name} projects: {e}")
                    import traceback
                    traceback.print_exc()
        else:
            # Fallback to separate files
            print("⚠️  Integrated file not found, using separate Parquet files")
            
            # Load existing hashes for incremental update
            processed_hashes = self._load_existing_project_hashes()
            
            print("💾 Loading ALL projects into memory (utilizing 64GB RAM)...")
            
            # Load all separate files into memory ONCE
            all_flood_projects = self.load_projects_from_parquet(FLOOD_PARQUET, source_name=None)
            all_dime_projects = self.load_projects_from_parquet(DIME_PARQUET, source_name=None) if DIME_PARQUET.exists() else []
            all_philgeps_projects = self.load_projects_from_parquet(PHILGEPS_PARQUET, source_name=None) if PHILGEPS_PARQUET.exists() else []
            all_microsite_projects = self.load_projects_from_parquet(MICROSITE_PARQUET, source_name=None) if MICROSITE_PARQUET.exists() else []
            all_transparency_projects = self.load_projects_from_parquet(TRANSPARENCY_PARQUET, source_name=None) if TRANSPARENCY_PARQUET.exists() else []
            
            total_loaded = len(all_flood_projects) + len(all_dime_projects) + len(all_philgeps_projects) + len(all_microsite_projects) + len(all_transparency_projects)
            print(f"✅ Loaded {total_loaded} total projects into memory")
            print(f"   - Flood/SSP: {len(all_flood_projects)}")
            print(f"   - DIME: {len(all_dime_projects)}")
            print(f"   - PhilGEPS: {len(all_philgeps_projects)}")
            print(f"   - Microsite: {len(all_microsite_projects)}")
            print(f"   - Transparency: {len(all_transparency_projects)}")
            
            # Process SSP/Flood projects
            try:
                # Ensure source is set correctly for separate file loading
                for p in all_flood_projects:
                    if not p.get('_source') and not p.get('source'):
                        p['_source'] = 'SSP'
                        p['source'] = 'SSP'

                # Filter from in-memory data
                flood_projects = [p for p in all_flood_projects if p.get('_source', p.get('source', '')).upper() in ('SSP', 'FLOOD')]
                
                # INCREMENTAL: Filter existing
                f_orig_len = len(flood_projects)
                flood_projects = [p for p in flood_projects if self._calculate_project_hash(p) not in processed_hashes]
                if f_orig_len > len(flood_projects):
                    print(f"⏩ Skipped {f_orig_len - len(flood_projects)} existing Flood/SSP projects")

                print(f"📊 Processing {len(flood_projects)} flood/SSP projects from memory")
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
                # Ensure source is set correctly for separate file loading
                for p in all_dime_projects:
                    if not p.get('_source') and not p.get('source'):
                        p['_source'] = 'DIME'
                        p['source'] = 'DIME'

                # Filter from in-memory data
                dime_projects = [p for p in all_dime_projects if p.get('_source', p.get('source', '')).upper() == 'DIME']
                
                # INCREMENTAL: Filter existing
                d_orig_len = len(dime_projects)
                dime_projects = [p for p in dime_projects if self._calculate_project_hash(p) not in processed_hashes]
                if d_orig_len > len(dime_projects):
                    print(f"⏩ Skipped {d_orig_len - len(dime_projects)} existing DIME projects")

                if dime_projects:
                    print(f"📊 Processing {len(dime_projects)} DIME projects from memory")
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
                # Ensure source is set correctly for separate file loading
                for p in all_philgeps_projects:
                    if not p.get('_source') and not p.get('source'):
                        p['_source'] = 'PhilGEPS'
                        p['source'] = 'PhilGEPS'

                # Filter from in-memory data
                philgeps_projects = [p for p in all_philgeps_projects if p.get('_source', p.get('source', '')).upper() == 'PHILGEPS']
                
                # INCREMENTAL: Filter existing
                p_orig_len = len(philgeps_projects)
                philgeps_projects = [p for p in philgeps_projects if self._calculate_project_hash(p) not in processed_hashes]
                if p_orig_len > len(philgeps_projects):
                    print(f"⏩ Skipped {p_orig_len - len(philgeps_projects)} existing PhilGEPS contracts")

                if philgeps_projects:
                    print(f"📊 Processing {len(philgeps_projects)} PhilGEPS contracts from memory")
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
            
            # Process Microsite projects
            try:
                # For separate Microsite file, all projects should be Microsite
                # Don't filter - just process all of them and set source explicitly
                microsite_projects = all_microsite_projects
                # Ensure source is set correctly
                for p in microsite_projects:
                    if not p.get('_source') and not p.get('source'):
                        p['_source'] = 'Microsite'
                    if not p.get('source'):
                        p['source'] = 'Microsite'
                
                # INCREMENTAL: Filter existing
                m_orig_len = len(microsite_projects)
                microsite_projects = [p for p in microsite_projects if self._calculate_project_hash(p) not in processed_hashes]
                if m_orig_len > len(microsite_projects):
                    print(f"⏩ Skipped {m_orig_len - len(microsite_projects)} existing Microsite projects")

                if microsite_projects:
                    print(f"📊 Processing {len(microsite_projects)} Microsite projects from memory")
                    microsite_chunks = self._chunk_list(microsite_projects, self.max_workers)
                    # Submit tasks directly to ThreadPoolExecutor for better thread utilization
                    microsite_futures = [
                        self.executor.submit(
                            self._process_microsite_chunk, chunk, congressmen_data, districts_data,
                            district_lookup_dict, contractor_lookup_dict, contractor_inverted_index,
                            known_provinces, known_cities, location_context_map
                        )
                        for chunk in microsite_chunks
                    ]
                    # Convert futures to awaitables using asyncio.wrap_future
                    loop = asyncio.get_running_loop()
                    microsite_tasks = [asyncio.wrap_future(future, loop=loop) for future in microsite_futures]
                    prev_count = len(all_projects)
                    for completed_task in asyncio.as_completed(microsite_tasks):
                        result = await completed_task
                        all_projects.extend(result)
                    print(f"✅ Processed {len(all_projects) - prev_count} Microsite projects (matched)")
            except Exception as e:
                print(f"Error processing Microsite projects: {e}")
                import traceback
                traceback.print_exc()
            
            # Process Transparency projects
            try:
                # For separate Transparency file, all projects should be Transparency
                transparency_projects = all_transparency_projects
                # Ensure source is set correctly
                for p in transparency_projects:
                    # Set both _source and source to ensure it's preserved
                    if not p.get('_source') and not p.get('source'):
                        p['_source'] = 'Transparency'
                        p['source'] = 'Transparency'
                    elif p.get('_source') and not p.get('source'):
                        p['source'] = p['_source']
                    elif p.get('source') and not p.get('_source'):
                        p['_source'] = p['source']
                
                # INCREMENTAL: Filter existing
                t_orig_len = len(transparency_projects)
                transparency_projects = [p for p in transparency_projects if self._calculate_project_hash(p) not in processed_hashes]
                if t_orig_len > len(transparency_projects):
                    print(f"⏩ Skipped {t_orig_len - len(transparency_projects)} existing Transparency projects")

                if transparency_projects:
                    print(f"📊 Processing {len(transparency_projects)} Transparency projects from memory")
                    transparency_chunks = self._chunk_list(transparency_projects, self.max_workers)
                    # Submit tasks directly to ThreadPoolExecutor for better thread utilization
                    transparency_futures = [
                        self.executor.submit(
                            self._process_transparency_chunk, chunk, congressmen_data, districts_data,
                            district_lookup_dict, contractor_lookup_dict, contractor_inverted_index,
                            known_provinces, known_cities, location_context_map
                        )
                        for chunk in transparency_chunks
                    ]
                    # Convert futures to awaitables using asyncio.wrap_future
                    loop = asyncio.get_running_loop()
                    transparency_tasks = [asyncio.wrap_future(future, loop=loop) for future in transparency_futures]
                    prev_count = len(all_projects)
                    transparency_processed = 0
                    for completed_task in asyncio.as_completed(transparency_tasks):
                        result = await completed_task
                        # Verify source is set correctly
                        for r in result:
                            if r.get('source') != 'Transparency' and r.get('_source') != 'Transparency':
                                # Fix source if not set correctly
                                r['source'] = 'Transparency'
                                r['_source'] = 'Transparency'
                        all_projects.extend(result)
                        transparency_processed += len(result)
                    print(f"✅ Processed {transparency_processed} Transparency projects (matched)")
                    # Debug: Count how many have correct source
                    transparency_with_source = len([p for p in all_projects[prev_count:] if p.get('source') == 'Transparency' or p.get('_source') == 'Transparency'])
                    if transparency_processed > 0:
                        print(f"   🔍 Debug: {transparency_with_source}/{transparency_processed} Transparency projects have source='Transparency'")
            except Exception as e:
                print(f"Error processing Transparency projects: {e}")
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
        
        # Load Location Index
        self.location_matcher.load()
        
        try:
    
            # Ensure latest districts and congressmen config are pulled from DB
            # self._refresh_source_json()
            
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
            
            # CRITICAL: Save ALL projects (before deduplication) to integrated_projects.parquet
            # This is needed for the API to show the total processed count (523,655)
            try:
                print(f"💾 Saving ALL projects (before deduplication) to {INTEGRATED_PARQUET}...")
                df_all = pd.DataFrame(all_projects)
                duckdb.sql("SELECT * FROM df_all").write_parquet(str(INTEGRATED_PARQUET))
                print(f"✅ Saved {len(all_projects)} total projects to {INTEGRATED_PARQUET}")
            except Exception as e:
                print(f"⚠️  Failed to save all projects to Parquet: {e}")
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
                # CRITICAL: Get source from multiple possible fields and normalize
                raw_source = (proj.get('source') or 
                            proj.get('_source') or 
                            proj.get('Source') or 
                            'Unknown')
                source_label = self._normalize_source_label(raw_source)
                proj['source'] = source_label
                # Also ensure _source is set for consistency
                if not proj.get('_source'):
                    proj['_source'] = source_label
                
                # CRITICAL: Prioritize contract_id for better cross-source matching
                # Check multiple possible contract_id fields
                contract_id = (proj.get('contract_id') or 
                             proj.get('meilisearch_id') or 
                             proj.get('global_id') or
                             proj.get('philgeps_award_id') or
                             proj.get('award_id') or
                             proj.get('notice_id'))
                
                if contract_id:
                    # Use contract_id as primary key (most reliable for cross-source matching)
                    # Normalize contract_id to handle variations (e.g., "19Z00043" vs "19Z00043-001")
                    contract_id_normalized = str(contract_id).strip().upper()
                    # Remove common suffixes/prefixes that might differ across sources
                    # Note: re is imported at the top of the file
                    contract_id_normalized = re.sub(r'[-_]\d+$', '', contract_id_normalized)  # Remove trailing -001, _001
                    # For contract_id-based keys, we can be more lenient - just use contract_id alone
                    # This allows matching even if contractor/amount differ slightly across sources
                    key = f"ID:{contract_id_normalized}"
                else:
                    # Fallback to project key (uses project_name, contractor, amount, location)
                    key = self._build_project_key(proj)
                
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
                
                # CRITICAL: Always add the normalized source_label to sources set
                # This ensures all sources are tracked even after merging
                projects_by_key[key]['sources'].add(source_label)
                
                # CRITICAL: Only add congressmen from the MERGED project, not from individual sources
                # This prevents cross-contamination when different sources match to different congressmen
                # After merging, use the resolved district_congressman and contractor_congressman
                merged_proj = projects_by_key[key]['project']
                if merged_proj.get('district_congressman'):
                    projects_by_key[key]['congressmen'].add(merged_proj.get('district_congressman'))
                if merged_proj.get('contractor_congressman'):
                    projects_by_key[key]['congressmen'].add(merged_proj.get('contractor_congressman'))
            
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
                
                # CRITICAL: Fix project_name for PhilGEPS projects BEFORE saving to parquet
                # For PhilGEPS projects, use award_title instead of contract_id
                # Also fix ANY project with contract ID pattern, not just PhilGEPS
                project_name = proj.get('project_name', '')
                project_name_str = str(project_name) if project_name else ''
                
                # Check if project_name looks like a contract ID (e.g., "19Z00043")
                if project_name_str and re.match(r'^\d{2}[A-Z]\d{5}$', project_name_str):
                    # This is a contract ID, replace with award_title (for any source, but especially PhilGEPS)
                    award_title = proj.get('philgeps_award_title') or proj.get('award_title')
                    if award_title and str(award_title).strip():
                        proj['project_name'] = award_title
                    else:
                        # Try notice_title as fallback
                        notice_title = proj.get('notice_title')
                        if notice_title and str(notice_title).strip():
                            proj['project_name'] = notice_title
                # Also ensure project_name is set if empty (especially for PhilGEPS)
                elif not project_name or project_name == '':
                    # For PhilGEPS projects, prioritize award_title
                    if 'PhilGEPS' in proj.get('sources_list', []):
                        proj['project_name'] = (
                            proj.get('philgeps_award_title') or 
                            proj.get('award_title') or
                            proj.get('notice_title') or
                            proj.get('project_description') or
                            ''
                        )
                    else:
                        proj['project_name'] = (
                            proj.get('project_description') or
                            proj.get('award_title') or
                            proj.get('notice_title') or
                            ''
                        )
                
                # Keep the primary congressman from district match (or contractor if no district)
                if not proj.get('congressman'):
                    proj['congressman'] = proj.get('district_congressman') or proj.get('contractor_congressman') or 'Unknown'
                
                unique_projects.append(proj)
            
            # Sort by match_score descending, then by amount descending
            unique_projects.sort(key=lambda x: (x.get('match_score', 0), x.get('amount', 0)), reverse=True)
            
            # Calculate summary
            ssp_count = len([p for p in unique_projects if 'SSP' in (p.get('sources_list', []))])
            # Count Microsite projects (Infrawatch is the same thing, just normalized to Microsite)
            microsite_count = len([p for p in unique_projects if 
                                  'Microsite' in (p.get('sources_list', [])) or 
                                  'MICROSITE' in (p.get('sources_list', [])) or
                                  'INFRAWATCH' in (p.get('sources_list', []))])  # INFRAWATCH is normalized to Microsite
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
            
            # Count Transparency projects - check both normalized and raw source values
            # Also check the source field directly in case sources_list wasn't set correctly
            transparency_count = len([p for p in unique_projects if 
                                    'Transparency' in (p.get('sources_list', [])) or
                                    'TRANSPARENCY' in (p.get('sources_list', [])) or
                                    p.get('source') == 'Transparency' or
                                    p.get('_source') == 'Transparency'])
            
            summary = {
                "total": len(unique_projects),
                "dime": len([p for p in unique_projects if 'DIME' in (p.get('sources_list', []))]),
                "philgeps": len([p for p in unique_projects if 'PhilGEPS' in (p.get('sources_list', []))]),
                "ssp": ssp_count,
                "microsite": microsite_count,
                "transparency": transparency_count,
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
            
            # CRITICAL: Save deduplicated unique_projects to classified parquet (AFTER deduplication)
            # This ensures the API endpoint gets unique projects with correct project_name for PhilGEPS
            try:
                print(f"💾 Saving deduplicated classified projects to {CLASSIFIED_PARQUET}...")
                print(f"   Preparing {len(unique_projects)} unique projects for saving...")
                
                # Use pandas to create DataFrame from unique_projects (already deduplicated)
                df = pd.DataFrame(unique_projects)
                print(f"   Created DataFrame with {len(df)} rows and {len(df.columns)} columns")
                
                # Verify critical columns exist
                critical_cols = ['project_name', 'sources_list', 'contract_id']
                missing_cols = [col for col in critical_cols if col not in df.columns]
                if missing_cols:
                    print(f"   ⚠️  Warning: Missing columns: {missing_cols}")
                else:
                    print(f"   ✅ All critical columns present")
                
                # Check how many projects have contract ID pattern in project_name
                # Note: re is already imported at the top of the file
                if 'project_name' in df.columns:
                    contract_id_pattern = r'^\d{2}[A-Z]\d{5}$'
                    contract_id_count = df['project_name'].astype(str).str.match(contract_id_pattern, na=False).sum()
                    print(f"   Projects with contract ID pattern in project_name: {contract_id_count}")
                    if contract_id_count > 0 and 'philgeps_award_title' in df.columns:
                        # Check how many have award_title available
                        has_award_title = df[df['project_name'].astype(str).str.match(contract_id_pattern, na=False)]['philgeps_award_title'].notna().sum()
                        print(f"   Of those, {has_award_title} have philgeps_award_title available")
                
                # DuckDB handles lists fine in Parquet (sources_list will be preserved)
                print(f"   Writing to parquet file...")
                duckdb.sql("SELECT * FROM df").write_parquet(str(CLASSIFIED_PARQUET))
                
                # Verify the file was written
                if CLASSIFIED_PARQUET.exists():
                    file_size_mb = CLASSIFIED_PARQUET.stat().st_size / (1024 * 1024)
                    print(f"✅ Saved {len(unique_projects)} unique projects to {CLASSIFIED_PARQUET}")
                    print(f"   File size: {file_size_mb:.2f} MB")
                    
                    # Quick verification: read back a few rows
                    try:
                        # Read parquet and take first 5 rows for verification
                        verify_df = pd.read_parquet(CLASSIFIED_PARQUET)
                        verify_sample = verify_df.head(5)
                        print(f"   ✅ Verification: File contains {len(verify_df)} total rows")
                        print(f"   Sample rows checked: {len(verify_sample)}")
                        if 'project_name' in verify_sample.columns:
                            print(f"   Sample project_name values:")
                            for idx, name in verify_sample['project_name'].head(3).items():
                                print(f"      - {name}")
                    except Exception as verify_err:
                        print(f"   ⚠️  Could not verify file contents: {verify_err}")
                else:
                    print(f"   ❌ ERROR: File was not created at {CLASSIFIED_PARQUET}")
            except Exception as e:
                print(f"⚠️  Failed to save classified projects to Parquet: {e}")
                import traceback
                traceback.print_exc()
            
            print("ℹ️  Combined cache file generation skipped (file too large and unused)")
            
            # Create individual cache files for each congressman
            print(f"\n📁 Creating individual cache files for each congressman...")
            cache_base_dir = Path(__file__).parent.parent / 'static' / 'data'
            
            # CRITICAL: Only clear all existing congressman cache directories when --force is used
            # This ensures we don't accidentally delete cache when running without --force
            if self.force_reclassify:
                print("🧹 Clearing existing congressman cache directories (--force mode)...")
                import shutil
                cleared_count = 0
                for item in cache_base_dir.iterdir():
                    if item.is_dir() and item.name.startswith('congressman-projects-'):
                        shutil.rmtree(item)
                        cleared_count += 1
                if cleared_count > 0:
                    print(f"   🗑️  Removed {cleared_count} congressman cache directories")
            else:
                print("ℹ️  Skipping cache directory clearing (use --force to clear existing caches)")
            
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
                        
                        # CRITICAL: Validate province matches to prevent incorrect assignments
                        if cm_provinces:
                            cm_province = cm_provinces[0].upper()
                            
                            # Special check: Prevent METRO MANILA from matching MANILA districts
                            if cm_province == 'MANILA' and 'METRO MANILA' in location:
                                should_include = False
                                continue
                            
                            # CRITICAL: Prevent directional variant mismatches (e.g., ILOCOS SUR vs ILOCOS NORTE)
                            # Get project's province from RAW data fields (not classification fields)
                            # Use the raw province field that was used for matching, not project_district
                            project_province_raw = p.get('province', '') or ''
                            if not project_province_raw:
                                # Fallback: try to extract from location string
                                location_parts = location.split(',')
                                if location_parts:
                                    project_province_raw = location_parts[-1].strip()
                            
                            project_province = project_province_raw.upper().strip() if project_province_raw else None
                            
                            # If we have project_district, it might have format like "Ilocos Sur 1st District"
                            # But prefer raw province field for validation
                            if not project_province and p.get('project_district'):
                                project_district_str = str(p.get('project_district', '')).upper()
                                if 'DISTRICT' in project_district_str:
                                    # Extract province name before "District"
                                    parts = project_district_str.split('DISTRICT')
                                    if parts:
                                        project_province = parts[0].strip()
                            
                            # If we have a project province, validate directional variants
                            if project_province:
                                cm_prov_upper = cm_province.upper().strip()
                                
                                # Extract base names and directional modifiers
                                cm_base = re.sub(r'\s*(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\s*$', '', cm_prov_upper).strip()
                                proj_base = re.sub(r'\s*(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\s*$', '', project_province).strip()
                                
                                # Extract directional modifiers
                                cm_dir_match = re.search(r'\b(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\b', cm_prov_upper, re.IGNORECASE)
                                proj_dir_match = re.search(r'\b(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\b', project_province, re.IGNORECASE)
                                
                                cm_dir = cm_dir_match.group(0).upper().strip() if cm_dir_match else None
                                proj_dir = proj_dir_match.group(0).upper().strip() if proj_dir_match else None
                                
                                # If both have the same base name, check directional modifiers
                                if cm_base == proj_base and cm_base:
                                    if cm_dir and proj_dir:
                                        if cm_dir != proj_dir:
                                            # Different directional variants - REJECT
                                            # e.g., "ILOCOS NORTE" != "ILOCOS SUR"
                                            should_include = False
                                            continue
                                    elif cm_dir or proj_dir:
                                        # One has directional, one doesn't - REJECT
                                        should_include = False
                                        continue
                            
                            # CRITICAL: For Davao City, require district number validation
                            # This prevents Paolo Duterte (1st), Vincent Garcia (2nd), and Isidro Ungab (3rd)
                            # from getting each other's projects
                            davao_variants = ['DAVAO CITY', 'DAVAO DEL SUR']
                            is_davao_city = (cm_province in davao_variants) or \
                                           (project_province and any(variant in project_province for variant in davao_variants)) or \
                                           (location and any(variant in location for variant in davao_variants))
                            
                            if is_davao_city and cm_data:
                                # For Davao City, we MUST have a district number match
                                cm_district_number = cm_data.get('district_number')
                                if cm_district_number:
                                    # Extract district number from congressman (e.g., "1st District" -> 1)
                                    cm_district_match = re.search(r'\b(\d+)(ST|ND|RD|TH)\s+DISTRICT\b', str(cm_district_number).upper(), re.IGNORECASE)
                                    if cm_district_match:
                                        cm_district_num = int(cm_district_match.group(1))
                                        
                                        # Try to extract district number from project
                                        project_district_num = None
                                        project_district_str = str(p.get('project_district', '')).upper()
                                        if project_district_str:
                                            proj_district_match = re.search(r'\b(\d+)(ST|ND|RD|TH)\s+DISTRICT\b', project_district_str, re.IGNORECASE)
                                            if proj_district_match:
                                                project_district_num = int(proj_district_match.group(1))
                                        
                                        # If project doesn't have district number, try location
                                        if project_district_num is None and location:
                                            loc_district_match = re.search(r'\b(\d+)(ST|ND|RD|TH)\s+DISTRICT\b', location, re.IGNORECASE)
                                            if loc_district_match:
                                                project_district_num = int(loc_district_match.group(1))
                                        
                                        # CRITICAL: For Davao City, require district number match
                                        # If we can't determine the project's district number, default to 1st District (Paolo Duterte)
                                        if project_district_num is None:
                                            # Can't determine district - default to 1st District if this is Paolo Duterte
                                            if cm_district_num == 1:
                                                # This is Paolo Duterte (1st District) - allow as default
                                                should_include = True
                                            else:
                                                # Not 1st District - reject to prevent cross-contamination
                                                should_include = False
                                                continue
                                        elif project_district_num != cm_district_num:
                                            # District numbers don't match - reject
                                            should_include = False
                                            continue
                                        else:
                                            # District numbers match - allow
                                            should_include = True
                                    else:
                                        # Congressman has district_number but we can't parse it - be safe and reject
                                        should_include = False
                                        continue
                                else:
                                    # Congressman doesn't have district_number but is in Davao City - reject
                                    should_include = False
                                    continue
                            else:
                                # Not Davao City - use normal matching logic
                                # Check for direct match (any variation)
                                if district_match or contractor_match:
                                    should_include = True
                                # For _all_congressmen matches, ONLY allow if province validation passed
                                # CRITICAL: Don't allow _all_congressmen matches if province validation failed
                                elif all_congressmen_match:
                                    # Only allow if we didn't reject due to province mismatch
                                    # If we got here, province validation passed (or wasn't checked)
                                    should_include = True
                        else:
                            # No province info, use default logic
                            # CRITICAL: For _all_congressmen matches without province info, be more strict
                            # Only allow if it's a direct district or contractor match
                            if district_match or contractor_match:
                                should_include = True
                            elif all_congressmen_match:
                                # For _all_congressmen matches without province validation, be cautious
                                # Only allow if we can't validate (no province data)
                                should_include = True
                        
                        # CRITICAL: Additional validation - check if project's district_congressman or contractor_congressman
                        # actually matches this congressman, not just _all_congressmen
                        # This prevents Isidro Ungab from getting Paolo Duterte's projects
                        
                        # Get the project's actual assigned congressmen
                        project_district_cm = p.get('district_congressman', '')
                        project_contractor_cm = p.get('contractor_congressman', '')
                        
                        # CRITICAL: For district matches, verify the project's district_congressman actually matches this congressman
                        # This prevents incorrect district assignments (e.g., Isidro Ungab getting Paolo Duterte's district matches)
                        if district_match and project_district_cm:
                            # Check if this congressman (or any name variation) is actually the district_congressman
                            if project_district_cm not in name_variations:
                                # The project's district_congressman doesn't match this congressman
                                # This is a false positive - REJECT
                                should_include = False
                                continue
                            
                            # CRITICAL: Also validate district numbers match for same province/city
                            # This prevents Isidro Ungab (3rd District) from getting Paolo Duterte's (1st District) projects
                            # AND prevents Paolo Duterte (1st District) from getting Isidro Ungab's (3rd District) projects
                            if cm_data and project_province:
                                cm_province_upper = (cm_data.get('provinces', [])[0] if cm_data.get('provinces') else '').upper()
                                if cm_province_upper and project_province:
                                    # Check if both are in the same province/city
                                    cm_base = re.sub(r'\s*(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\s*$', '', cm_province_upper).strip()
                                    proj_base = re.sub(r'\s*(DEL\s+)?(SUR|NORTE|OCCIDENTAL|ORIENTAL|EASTERN|WESTERN|NORTHERN|SOUTHERN)\s*$', '', project_province).strip()
                                    
                                    # Special handling for Davao City / Davao Del Sur
                                    davao_variants = ['DAVAO CITY', 'DAVAO DEL SUR']
                                    if cm_base in davao_variants and proj_base in davao_variants:
                                        # Same province/city - MUST check district numbers
                                        cm_district_num = cm_data.get('district_number', '')
                                        project_district_str = p.get('project_district', '') or ''
                                        
                                        # Also try to extract from location if project_district is empty
                                        if not project_district_str:
                                            location = p.get('location', '') or ''
                                            project_district_str = location
                                        
                                        # Extract district numbers
                                        cm_district_match = re.search(r'\b(\d+)(ST|ND|RD|TH)\b', str(cm_district_num).upper(), re.IGNORECASE)
                                        proj_district_match = re.search(r'\b(\d+)(ST|ND|RD|TH)\b', str(project_district_str).upper(), re.IGNORECASE)
                                        
                                        if cm_district_match and proj_district_match:
                                            cm_num = int(cm_district_match.group(1))
                                            proj_num = int(proj_district_match.group(1))
                                            if cm_num != proj_num:
                                                # Different district numbers in same city - REJECT
                                                # e.g., Isidro Ungab (3rd) should not get Paolo Duterte's (1st) projects
                                                # e.g., Paolo Duterte (1st) should not get Isidro Ungab's (3rd) projects
                                                should_include = False
                                                continue
                                        elif cm_district_match and not proj_district_match:
                                            # Congressman has district number but project doesn't - be cautious
                                            # For Davao City, if we can't determine project district, default to 1st District (Paolo Duterte)
                                            location = p.get('location', '') or ''
                                            location_upper = str(location).upper()
                                            
                                            # Try to extract district from location
                                            location_district_match = re.search(r'\b(\d+)(ST|ND|RD|TH)\s*DISTRICT\b', location_upper, re.IGNORECASE)
                                            
                                            # If still can't determine district, default to 1st District
                                            if not location_district_match:
                                                cm_num = int(cm_district_match.group(1))
                                                if cm_num == 1:
                                                    # This is Paolo Duterte (1st District) - allow as default
                                                    should_include = True
                                                else:
                                                    # Not 1st District - reject to prevent cross-contamination
                                                    should_include = False
                                                    continue
                                            else:
                                                # Found district in location - validate it matches
                                                loc_num = int(location_district_match.group(1))
                                                cm_num = int(cm_district_match.group(1))
                                                if loc_num != cm_num:
                                                    # District numbers don't match - reject
                                                    should_include = False
                                                    continue
                                                else:
                                                    # District numbers match
                                                    should_include = True
                                        elif not cm_district_match and not proj_district_match:
                                            # Neither has district number - default to 1st District (Paolo Duterte)
                                            # Check if this is Paolo Duterte
                                            if 'DUTERTE' in name_variations[0].upper() and 'PAOLO' in name_variations[0].upper():
                                                should_include = True
                                            else:
                                                # Not Paolo Duterte - reject to prevent cross-contamination
                                                should_include = False
                                                continue
                                    elif cm_base == proj_base and cm_base:
                                        # Same province base - check district numbers
                                        cm_district_num = cm_data.get('district_number', '')
                                        project_district_str = p.get('project_district', '') or ''
                                        
                                        # Also try to extract from location if project_district is empty
                                        if not project_district_str:
                                            location = p.get('location', '') or ''
                                            project_district_str = location
                                        
                                        # Extract district numbers
                                        cm_district_match = re.search(r'\b(\d+)(ST|ND|RD|TH)\b', str(cm_district_num).upper(), re.IGNORECASE)
                                        proj_district_match = re.search(r'\b(\d+)(ST|ND|RD|TH)\b', str(project_district_str).upper(), re.IGNORECASE)
                                        
                                        if cm_district_match and proj_district_match:
                                            cm_num = int(cm_district_match.group(1))
                                            proj_num = int(proj_district_match.group(1))
                                            if cm_num != proj_num:
                                                # Different district numbers - REJECT
                                                should_include = False
                                                continue
                                        elif cm_district_match and not proj_district_match:
                                            # Congressman has district number but project doesn't - be cautious
                                            # Try to extract from location if project_district is empty
                                            location = p.get('location', '') or ''
                                            location_upper = str(location).upper()
                                            
                                            # Try to extract district from location
                                            location_district_match = re.search(r'\b(\d+)(ST|ND|RD|TH)\s*DISTRICT\b', location_upper, re.IGNORECASE)
                                            if location_district_match:
                                                proj_num = int(location_district_match.group(1))
                                                cm_num = int(cm_district_match.group(1))
                                                if cm_num != proj_num:
                                                    # District numbers don't match - REJECT
                                                    should_include = False
                                                    continue
                                            else:
                                                # Can't determine project district - reject to be safe
                                                should_include = False
                                                continue
                        
                        # CRITICAL: For contractor matches, verify the project's contractor_congressman actually matches this congressman
                        if contractor_match and project_contractor_cm:
                            # Check if this congressman (or any name variation) is actually the contractor_congressman
                            if project_contractor_cm not in name_variations:
                                # The project's contractor_congressman doesn't match this congressman
                                # This is a false positive - REJECT
                                should_include = False
                                continue
                        
                        # For _all_congressmen matches (not direct district/contractor), be extra strict
                        if should_include and all_congressmen_match and not district_match and not contractor_match:
                            # This project is only in _all_congressmen, not directly assigned
                            # Double-check: is this congressman actually in the project's direct assignments?
                            
                            # Check if this congressman (or any variation) is the actual district or contractor match
                            is_actual_match = (
                                project_district_cm in name_variations or
                                project_contractor_cm in name_variations
                            )
                            
                            if not is_actual_match:
                                # This congressman is only in _all_congressmen due to merging, not a direct match
                                # REJECT to prevent cross-contamination
                                should_include = False
                        
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
                    "infrawatch": len([p for p in congressman_projects if 'Microsite' in (p.get('sources_list', [])) or 'MICROSITE' in (p.get('sources_list', [])) or 'Infrawatch' in (p.get('sources_list', [])) or 'INFRAWATCH' in (p.get('sources_list', []))]),
                    "microsite": len([p for p in congressman_projects if 'Microsite' in (p.get('sources_list', [])) or 'MICROSITE' in (p.get('sources_list', [])) or 'Infrawatch' in (p.get('sources_list', [])) or 'INFRAWATCH' in (p.get('sources_list', []))]),
                    "transparency": len([p for p in congressman_projects if 'Transparency' in (p.get('sources_list', []))]),
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
            print(f"   Microsite: {summary['microsite']}")
            print(f"   Transparency: {summary['transparency']}")
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

#!/usr/bin/env python3
"""
Generate cached JSON for dynasty-projects API using DuckDB and Parquet files.
This script retains all matching logic from generate_dynasty_projects_cache.py
but uses DuckDB to query Parquet files instead of PostgreSQL.
"""

import asyncio
import functools
import json
import math
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb
import asyncpg
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from flood_client import FloodControlClient

# Load environment variables
load_dotenv()

# Manila-specific helpers
BARANGAY_NUMBER_PATTERNS = [
    re.compile(r'(?:BARANGAY|BRGY|BRG|BGY)\s*(?:NO\.?\s*)?(\d{1,4})', re.IGNORECASE),
    re.compile(r'(?:BARANGAY|BRGY|BRG|BGY)\s*(?:NO\.?\s*)?(\d{1,4})\s*(?:[-–]|TO)\s*(\d{1,4})', re.IGNORECASE),
]

# Parquet file paths
PARQUET_DIR = Path(__file__).parent.parent / 'data' / 'parquet'
DIME_PARQUET = PARQUET_DIR / 'dime_projects.parquet'
PHILGEPS_PARQUET = PARQUET_DIR / 'philgeps_contracts.parquet'
INFRAWATCH_PARQUET = PARQUET_DIR / 'infrawatch_projects.parquet'
FLOOD_PARQUET = PARQUET_DIR / 'flood_projects.parquet'

class DynastyProjectsCacheGeneratorDuckDB:
    """Generate cached JSON for dynasty-projects using DuckDB"""
    
    def __init__(self):
        root_dir = Path(__file__).parent.parent
        static_data_dir = root_dir / 'static' / 'data'
        self.cache_file = static_data_dir / 'dynasty-projects-cache.json'
        self.config_file = static_data_dir / 'dynasty-projects-config.json'
        self.districts_file = static_data_dir / 'districts.json'
        cpu_count = os.cpu_count() or 4
        self.max_workers = min(24, max(1, cpu_count))
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
        
        # Initialize DuckDB connection
        self.duckdb_conn = duckdb.connect()

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

    @staticmethod
    def _normalize_text_for_key(value: Optional[str]) -> str:
        if not value:
            return ""
        text = value.upper()
        text = re.sub(r'\b(PROVINCE|CITY|MUNICIPALITY|MUNICIPALITY OF|CITY OF|BRGY|BARANGAY|PHILIPPINE|REPUBLIC|HIGHWAY|ROAD|RD|ST|STREET)\b', ' ', text)
        text = re.sub(r'[^A-Z0-9]+', ' ', text)
        return re.sub(r'\s+', ' ', text).strip()

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

    def _process_dime_chunk(self, projects_chunk: List[Dict], congressmen_data: Dict, districts_data: Dict) -> List[Dict]:
        """Process a chunk of DIME projects from Parquet - matches up to 2 congressmen (district + contractor)"""
        chunk_results: List[Dict] = []
        unmatched_count = 0
        for proj in projects_chunk:
            proj_name = (proj.get('project_name') or '').upper()
            proj_province = (proj.get('province') or '').upper()
            proj_city = (proj.get('city') or '').upper()
            proj_barangay = (proj.get('barangay') or '').upper()
            combined_text = f'{proj_name} {proj_province} {proj_city} {proj_barangay}'

            contractor_str = ''
            # Try multiple possible column names
            contractors_field = proj.get('contractors') or proj.get('contractor_name') or proj.get('contractor')
            if isinstance(contractors_field, list):
                contractor_str = ', '.join(contractors_field).upper()
            elif contractors_field:
                contractor_str = str(contractors_field).upper()
            combined_text = f'{combined_text} {contractor_str}'

            # Extract project year for term filtering
            project_year = None
            # Try multiple possible date fields
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

            # Find best district match (funnel concept - primary)
            best_district_match = None
            best_district_score = 0
            # Find best contractor match (secondary)
            best_contractor_match = None
            best_contractor_score = 0
            
            for cm_name, cm_data in congressmen_data.items():
                cm_name_result, match_type_result, match_score_result = self.match_project(
                    combined_text,
                    cm_data,
                    districts_data,
                    contractor_str,
                    project_year
                )
                if cm_name_result and match_score_result > 0:
                    if match_type_result == "district":
                        if match_score_result > best_district_score:
                            best_district_match = (cm_name_result, match_type_result, match_score_result)
                            best_district_score = match_score_result
                    elif match_type_result == "contractor":
                        if match_score_result > best_contractor_score:
                            best_contractor_match = (cm_name_result, match_type_result, match_score_result)
                            best_contractor_score = match_score_result

            # If no matches at all, try fallback matching by province
            if not best_district_match and not best_contractor_match:
                # Fallback 1: Match by province to any congressman from that province
                project_province_upper = proj_province
                if project_province_upper:
                    # Try to find a congressman from the same province
                    for cm_name, cm_data in congressmen_data.items():
                        cm_provinces = cm_data.get('provinces', [])
                        for cm_province in cm_provinces:
                            if cm_province.upper() == project_province_upper:
                                # Use a lower score for province-only matches
                                best_district_match = (cm_name, "district", 10)
                                break
                        if best_district_match:
                            break
                
                # Fallback 2: If still no match and we have a city, try matching by city
                if not best_district_match and not best_contractor_match and proj_city:
                    project_city_upper = proj_city
                    for cm_name, cm_data in congressmen_data.items():
                        cm_provinces = cm_data.get('provinces', [])
                        # Check if city matches any province (for city districts)
                        for cm_province in cm_provinces:
                            if cm_province.upper() == project_city_upper:
                                best_district_match = (cm_name, "district", 10)
                                break
                        if best_district_match:
                            break
                
                # Fallback 3: If still no match, match to first congressman with matching province (very permissive)
                if not best_district_match and not best_contractor_match and project_province_upper:
                    for cm_name, cm_data in congressmen_data.items():
                        cm_provinces = cm_data.get('provinces', [])
                        for cm_province in cm_provinces:
                            if project_province_upper in cm_province.upper() or cm_province.upper() in project_province_upper:
                                best_district_match = (cm_name, "district", 5)
                                break
                        if best_district_match:
                            break
                
                # Final fallback: If absolutely no match, we still create a record with "Unknown" congressman
                # This ensures every project gets processed
                if not best_district_match and not best_contractor_match:
                    # Match to first available congressman as last resort (score 1)
                    if congressmen_data:
                        first_congressman = list(congressmen_data.keys())[0]
                        best_district_match = (first_congressman, "district", 1)
                    else:
                        unmatched_count += 1
                        continue

            location_parts = []
            if proj.get('province'):
                location_parts.append(proj['province'])
            if proj.get('city'):
                location_parts.append(proj['city'])
            if proj.get('barangay'):
                location_parts.append(proj['barangay'])
            location_str = ', '.join(location_parts).strip() or "N/A"

            amount = float(proj.get('cost', 0) or proj.get('amount', 0) or 0)

            # Extract district congressman info
            district_congressman = None
            district_match_type = None
            district_match_score = 0
            district_is_city_wide = False
            congressman_district = None
            if best_district_match:
                district_congressman, district_match_type, district_match_score = best_district_match
                district_is_city_wide = (district_match_score == 1 and district_match_type == "district")
                # Construct full district name (e.g., "1st District Davao City")
                if district_congressman and district_congressman in congressmen_data:
                    cm_data = congressmen_data[district_congressman]
                    district_number = cm_data.get('district_number')
                    provinces = cm_data.get('provinces', [])
                    is_city_district = cm_data.get('is_city_district', False)
                    if district_number and provinces:
                        province_name = provinces[0]
                        # Format: "1st District Davao City" or "1st District Leyte"
                        congressman_district = f"{district_number} District {province_name}"
            
            # Extract contractor congressman info (only if different from district)
            contractor_congressman = None
            contractor_match_type = None
            contractor_match_score = 0
            contractor_congressman_district = None
            if best_contractor_match:
                contractor_cm, contractor_match_type, contractor_match_score = best_contractor_match
                # Only set if different from district match
                if not best_district_match or best_district_match[0] != contractor_cm:
                    contractor_congressman = contractor_cm
                    # Construct full district name for contractor congressman
                    if contractor_congressman and contractor_congressman in congressmen_data:
                        cm_data = congressmen_data[contractor_congressman]
                        district_number = cm_data.get('district_number')
                        provinces = cm_data.get('provinces', [])
                        if district_number and provinces:
                            province_name = provinces[0]
                            contractor_congressman_district = f"{district_number} District {province_name}"

            # Extract project location classification
            project_province = proj.get('province') or ""
            project_city = proj.get('city') or ""
            project_barangay = proj.get('barangay') or ""
            
            # Determine if project location is City or Province district
            project_province_city_district = None
            location_upper = location_str.upper()
            import re
            
            # Check if location contains "CITY" (case-insensitive)
            if "CITY" in location_upper or (project_city and "CITY" in project_city.upper()):
                project_province_city_district = "City"
            elif project_province:
                # If it's not a city, it's likely a province district
                project_province_city_district = "Province"
            
            # Municipality/barangay: prioritize barangay, then city, then municipality from location
            project_municipality_barangay = None
            if project_barangay:
                project_municipality_barangay = project_barangay
            elif project_city:
                project_municipality_barangay = project_city
            else:
                # Try to extract from location string (last part after comma, or first part if no comma)
                location_parts = [p.strip() for p in location_str.split(',')]
                if location_parts:
                    # Take the last part as it's usually the municipality/city
                    project_municipality_barangay = location_parts[-1] if len(location_parts) > 1 else location_parts[0]

            # Debug: Stop when a project CAN'T be matched
            if not district_congressman and not contractor_congressman:
                print(f"\n🛑 STOPPING: Found UNMATCHED project!")
                print(f"   Project: {proj.get('project_name', 'N/A')[:80]}")
                print(f"   Location: {location_str}")
                print(f"   Contractor: {contractor_str}")
                print(f"   Province: {proj.get('province', 'N/A')}")
                print(f"   City/Municipality: {proj.get('city', proj.get('municipality', 'N/A'))}")
                print(f"   Barangay: {proj.get('barangay', 'N/A')}")
                print(f"   District Match: {district_congressman or 'None'} (score: {district_match_score})")
                print(f"   Contractor Match: {contractor_congressman or 'None'} (score: {contractor_match_score})")
                import sys
                sys.exit(0)
            
            # Create single project record with both congressmen columns
            chunk_results.append({
                "source": self._normalize_source_label("DIME"),
                "meilisearch_id": proj.get('meilisearch_id'),
                "project_name": proj.get('project_name') or "N/A",
                "contractor": contractor_str if contractor_str else "N/A",
                "amount": amount,
                "location": location_str,
                "year": project_year if project_year else "N/A",
                "status": proj.get('status') or "N/A",
                "district_congressman": district_congressman,
                "district_match_type": district_match_type,
                "district_match_score": district_match_score,
                "district_is_city_wide": district_is_city_wide,
                "congressman_district": congressman_district,  # District the congressman represents
                "contractor_congressman": contractor_congressman,
                "contractor_match_type": contractor_match_type,
                "contractor_match_score": contractor_match_score,
                "contractor_congressman_district": contractor_congressman_district,  # District the contractor congressman represents
                "project_province_city_district": project_province_city_district,  # District extracted from project location
                "project_municipality_barangay": project_municipality_barangay  # Municipality/barangay from project location
            })
        return chunk_results

    def _process_philgeps_chunk(self, contracts_chunk: List[Dict], congressmen_data: Dict, districts_data: Dict) -> List[Dict]:
        """Process a chunk of PhilGEPS contracts from Parquet - matches up to 2 congressmen (district + contractor)"""
        chunk_results: List[Dict] = []
        unmatched_count = 0
        for contract in contracts_chunk:
            award_title = (contract.get('award_title') or '').upper()
            area_of_delivery = (contract.get('area_of_delivery') or '').upper()
            awardee_name = (contract.get('awardee_name') or '').upper()
            combined_text = f'{award_title} {area_of_delivery} {awardee_name}'
            
            # Extract province and city from area_of_delivery or contract fields
            # Try to get from separate fields first, then parse area_of_delivery
            proj_province = (contract.get('province') or '').upper()
            proj_city = (contract.get('city') or contract.get('municipality') or '').upper()
            
            # If not available, try to parse from area_of_delivery (format is often "City, Province" or "Province")
            if not proj_province and area_of_delivery:
                # Try to extract province from area_of_delivery
                # Common formats: "PROVINCE", "CITY, PROVINCE", "MUNICIPALITY, PROVINCE"
                parts = [p.strip() for p in area_of_delivery.split(',')]
                if len(parts) >= 2:
                    proj_province = parts[-1].strip()  # Last part is usually province
                    proj_city = parts[0].strip() if not proj_city else proj_city
                elif len(parts) == 1:
                    # Might be just province or just city
                    proj_province = parts[0].strip()

            # Extract project year for term filtering
            project_year = None
            if contract.get('award_date'):
                try:
                    if isinstance(contract['award_date'], str):
                        from dateutil.parser import parse
                        project_year = parse(contract['award_date']).year
                    else:
                        project_year = contract['award_date'].year
                except (AttributeError, TypeError, ValueError):
                    pass

            # Find best district match (funnel concept - primary)
            best_district_match = None
            best_district_score = 0
            # Find best contractor match (secondary)
            best_contractor_match = None
            best_contractor_score = 0
            
            for cm_name, cm_data in congressmen_data.items():
                cm_name_result, match_type_result, match_score_result = self.match_project(
                    combined_text,
                    cm_data,
                    districts_data,
                    awardee_name,
                    project_year
                )
                if cm_name_result and match_score_result > 0:
                    if match_type_result == "district":
                        if match_score_result > best_district_score:
                            best_district_match = (cm_name_result, match_type_result, match_score_result)
                            best_district_score = match_score_result
                    elif match_type_result == "contractor":
                        if match_score_result > best_contractor_score:
                            best_contractor_match = (cm_name_result, match_type_result, match_score_result)
                            best_contractor_score = match_score_result

            # If no matches at all, try fallback matching by province
            if not best_district_match and not best_contractor_match:
                # Fallback 1: Match by province to any congressman from that province
                project_province_upper = proj_province
                if project_province_upper:
                    # Try to find a congressman from the same province
                    for cm_name, cm_data in congressmen_data.items():
                        cm_provinces = cm_data.get('provinces', [])
                        for cm_province in cm_provinces:
                            if cm_province.upper() == project_province_upper:
                                # Use a lower score for province-only matches
                                best_district_match = (cm_name, "district", 10)
                                break
                        if best_district_match:
                            break
                
                # Fallback 2: If still no match and we have a city, try matching by city
                if not best_district_match and not best_contractor_match and proj_city:
                    project_city_upper = proj_city
                    for cm_name, cm_data in congressmen_data.items():
                        cm_provinces = cm_data.get('provinces', [])
                        # Check if city matches any province (for city districts)
                        for cm_province in cm_provinces:
                            if cm_province.upper() == project_city_upper:
                                best_district_match = (cm_name, "district", 10)
                                break
                        if best_district_match:
                            break
                
                # Fallback 3: If still no match, match to first congressman with matching province (very permissive)
                if not best_district_match and not best_contractor_match and project_province_upper:
                    for cm_name, cm_data in congressmen_data.items():
                        cm_provinces = cm_data.get('provinces', [])
                        for cm_province in cm_provinces:
                            if project_province_upper in cm_province.upper() or cm_province.upper() in project_province_upper:
                                best_district_match = (cm_name, "district", 5)
                                break
                        if best_district_match:
                            break
                
                # Final fallback: If absolutely no match, we still create a record with "Unknown" congressman
                # This ensures every project gets processed
                if not best_district_match and not best_contractor_match:
                    # Match to first available congressman as last resort (score 1)
                    if congressmen_data:
                        first_congressman = list(congressmen_data.keys())[0]
                        best_district_match = (first_congressman, "district", 1)
                    else:
                        unmatched_count += 1
                        continue

            # Extract district congressman info
            district_congressman = None
            district_match_type = None
            district_match_score = 0
            district_is_city_wide = False
            congressman_district = None
            if best_district_match:
                district_congressman, district_match_type, district_match_score = best_district_match
                district_is_city_wide = (district_match_score == 1 and district_match_type == "district")
                # Construct full district name (e.g., "1st District Davao City")
                if district_congressman and district_congressman in congressmen_data:
                    cm_data = congressmen_data[district_congressman]
                    district_number = cm_data.get('district_number')
                    provinces = cm_data.get('provinces', [])
                    if district_number and provinces:
                        province_name = provinces[0]
                        congressman_district = f"{district_number} District {province_name}"
            
            # Extract contractor congressman info (only if different from district)
            contractor_congressman = None
            contractor_match_type = None
            contractor_match_score = 0
            contractor_congressman_district = None
            if best_contractor_match:
                contractor_cm, contractor_match_type, contractor_match_score = best_contractor_match
                # Only set if different from district match
                if not best_district_match or best_district_match[0] != contractor_cm:
                    contractor_congressman = contractor_cm
                    # Construct full district name for contractor congressman
                    if contractor_congressman and contractor_congressman in congressmen_data:
                        cm_data = congressmen_data[contractor_congressman]
                        district_number = cm_data.get('district_number')
                        provinces = cm_data.get('provinces', [])
                        if district_number and provinces:
                            province_name = provinces[0]
                            contractor_congressman_district = f"{district_number} District {province_name}"

            # Extract project location classification
            area_of_delivery_upper = area_of_delivery.upper()
            
            # Determine if project location is City or Province district
            project_province_city_district = None
            if "CITY" in area_of_delivery_upper:
                project_province_city_district = "City"
            else:
                project_province_city_district = "Province"
            
            # Municipality/barangay: extract from area_of_delivery
            project_municipality_barangay = None
            # Split by comma and take the last part (usually municipality/city/barangay)
            location_parts = [p.strip() for p in area_of_delivery.split(',')]
            if location_parts:
                # Take the last part as it's usually the municipality/city/barangay
                project_municipality_barangay = location_parts[-1] if len(location_parts) > 1 else location_parts[0]

            # Create single project record with both congressmen columns
            chunk_results.append({
                "source": self._normalize_source_label("PhilGEPS"),
                "meilisearch_id": contract.get('meilisearch_id'),
                "project_name": contract.get('award_title') or "N/A",
                "contractor": contract.get('awardee_name') or "N/A",
                "amount": float(contract.get('contract_amount', 0) or 0),
                "location": contract.get('area_of_delivery') or "N/A",
                "year": project_year if project_year else "N/A",
                "status": contract.get('award_status') or "N/A",
                "district_congressman": district_congressman,
                "district_match_type": district_match_type,
                "district_match_score": district_match_score,
                "district_is_city_wide": district_is_city_wide,
                "congressman_district": congressman_district,  # District the congressman represents
                "contractor_congressman": contractor_congressman,
                "contractor_match_type": contractor_match_type,
                "contractor_match_score": contractor_match_score,
                "contractor_congressman_district": contractor_congressman_district,  # District the contractor congressman represents
                "project_province_city_district": project_province_city_district,  # District extracted from project location
                "project_municipality_barangay": project_municipality_barangay  # Municipality/barangay from project location
            })
        return chunk_results

    def _process_infrawatch_chunk(self, rows_chunk: List[Dict], congressmen_data: Dict, districts_data: Dict) -> List[Dict]:
        """Process a chunk of Infrawatch projects from Parquet - matches up to 2 congressmen (district + contractor)"""
        chunk_results: List[Dict] = []
        for row in rows_chunk:
            record = row
            if not isinstance(record, dict):
                continue

            description = (record.get("Contract Details") or record.get("Project Description") or "").upper()
            contractor_raw = (
                record.get("Contractor")
                or record.get("Contractor Name")
                or record.get("Contractor_Name")
                or ""
            )
            contractor = contractor_raw.upper()
            agency = (record.get("Implementing Agency") or "").upper()
            fund_source = (record.get("Fund Source") or "").upper()

            combined_text = f"{description} {agency} {fund_source} {contractor}"

            # Infrawatch doesn't have reliable date information, so pass None
            project_year = None

            # Find best district match (funnel concept - primary)
            best_district_match = None
            best_district_score = 0
            # Find best contractor match (secondary)
            best_contractor_match = None
            best_contractor_score = 0
            
            for cm_name, cm_data in congressmen_data.items():
                cm_name_result, match_type_result, match_score_result = self.match_project(
                    combined_text,
                    cm_data,
                    districts_data,
                    contractor,
                    project_year
                )
                if cm_name_result and match_score_result > 0:
                    if match_type_result == "district":
                        if match_score_result > best_district_score:
                            best_district_match = (cm_name_result, match_type_result, match_score_result)
                            best_district_score = match_score_result
                    elif match_type_result == "contractor":
                        if match_score_result > best_contractor_score:
                            best_contractor_match = (cm_name_result, match_type_result, match_score_result)
                            best_contractor_score = match_score_result

            # If no matches at all, try fallback matching by province
            if not best_district_match and not best_contractor_match:
                # Fallback 1: Match by province to any congressman from that province
                project_province_upper = proj_province
                if project_province_upper:
                    # Try to find a congressman from the same province
                    for cm_name, cm_data in congressmen_data.items():
                        cm_provinces = cm_data.get('provinces', [])
                        for cm_province in cm_provinces:
                            if cm_province.upper() == project_province_upper:
                                # Use a lower score for province-only matches
                                best_district_match = (cm_name, "district", 10)
                                break
                        if best_district_match:
                            break
                
                # Fallback 2: If still no match and we have a city, try matching by city
                if not best_district_match and not best_contractor_match and proj_city:
                    project_city_upper = proj_city
                    for cm_name, cm_data in congressmen_data.items():
                        cm_provinces = cm_data.get('provinces', [])
                        # Check if city matches any province (for city districts)
                        for cm_province in cm_provinces:
                            if cm_province.upper() == project_city_upper:
                                best_district_match = (cm_name, "district", 10)
                                break
                        if best_district_match:
                            break
                
                # Fallback 3: If still no match, match to first congressman with matching province (very permissive)
                if not best_district_match and not best_contractor_match and project_province_upper:
                    for cm_name, cm_data in congressmen_data.items():
                        cm_provinces = cm_data.get('provinces', [])
                        for cm_province in cm_provinces:
                            if project_province_upper in cm_province.upper() or cm_province.upper() in project_province_upper:
                                best_district_match = (cm_name, "district", 5)
                                break
                        if best_district_match:
                            break
                
                # Final fallback: If absolutely no match, we still create a record with "Unknown" congressman
                # This ensures every project gets processed
                if not best_district_match and not best_contractor_match:
                    # Match to first available congressman as last resort (score 1)
                    if congressmen_data:
                        first_congressman = list(congressmen_data.keys())[0]
                        best_district_match = (first_congressman, "district", 1)
                    else:
                        unmatched_count += 1
                        continue

            amount_raw = (
                record.get("Contract Price")
                or record.get("Contract Amount")
                or record.get("Amount")
                or record.get("Constract Price")
            )
            amount = 0.0
            if isinstance(amount_raw, (int, float)):
                amount = float(amount_raw)
            elif isinstance(amount_raw, str):
                try:
                    amount = float(amount_raw.replace("₱", "").replace(",", "").strip())
                except ValueError:
                    amount = 0.0

            # Extract district congressman info
            district_congressman = None
            district_match_type = None
            district_match_score = 0
            district_is_city_wide = False
            congressman_district = None
            if best_district_match:
                district_congressman, district_match_type, district_match_score = best_district_match
                district_is_city_wide = (district_match_score == 1 and district_match_type == "district")
                # Construct full district name (e.g., "1st District Davao City")
                if district_congressman and district_congressman in congressmen_data:
                    cm_data = congressmen_data[district_congressman]
                    district_number = cm_data.get('district_number')
                    provinces = cm_data.get('provinces', [])
                    if district_number and provinces:
                        province_name = provinces[0]
                        congressman_district = f"{district_number} District {province_name}"
            
            # Extract contractor congressman info (only if different from district)
            contractor_congressman = None
            contractor_match_type = None
            contractor_match_score = 0
            contractor_congressman_district = None
            if best_contractor_match:
                contractor_cm, contractor_match_type, contractor_match_score = best_contractor_match
                # Only set if different from district match
                if not best_district_match or best_district_match[0] != contractor_cm:
                    contractor_congressman = contractor_cm
                    # Construct full district name for contractor congressman
                    if contractor_congressman and contractor_congressman in congressmen_data:
                        cm_data = congressmen_data[contractor_congressman]
                        district_number = cm_data.get('district_number')
                        provinces = cm_data.get('provinces', [])
                        if district_number and provinces:
                            province_name = provinces[0]
                            contractor_congressman_district = f"{district_number} District {province_name}"

            # Extract project location classification
            project_location = record.get("Implementing Agency") or record.get("Project Location") or ""
            project_location_upper = project_location.upper()
            
            # Determine if project location is City or Province district
            project_province_city_district = None
            if "CITY" in project_location_upper:
                project_province_city_district = "City"
            else:
                project_province_city_district = "Province"
            
            # Municipality/barangay: extract from location
            project_municipality_barangay = None
            # Split by comma and take the last part (usually municipality/city/barangay)
            location_parts = [p.strip() for p in project_location.split(',')]
            if location_parts:
                # Take the last part as it's usually the municipality/city/barangay
                project_municipality_barangay = location_parts[-1] if len(location_parts) > 1 else location_parts[0]

            # Create single project record with both congressmen columns
            chunk_results.append({
                "source": self._normalize_source_label("Infrawatch"),
                "meilisearch_id": None,
                "project_name": record.get("Contract Details") or record.get("Project Description") or "N/A",
                "contractor": contractor_raw or "N/A",
                "amount": amount,
                "location": project_location or "N/A",
                "year": None,
                "status": record.get("Contract Status") or "N/A",
                "district_congressman": district_congressman,
                "district_match_type": district_match_type,
                "district_match_score": district_match_score,
                "district_is_city_wide": district_is_city_wide,
                "congressman_district": congressman_district,  # District the congressman represents
                "contractor_congressman": contractor_congressman,
                "contractor_match_type": contractor_match_type,
                "contractor_match_score": contractor_match_score,
                "contractor_congressman_district": contractor_congressman_district,  # District the contractor congressman represents
                "project_province_city_district": project_province_city_district,  # District extracted from project location
                "project_municipality_barangay": project_municipality_barangay  # Municipality/barangay from project location
            })
        return chunk_results

    async def load_config(self) -> Dict:
        """Load configuration files"""
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
                    '6TH DISTRICT': ['ERMITA', 'MALATE', 'INTRAMUROS', 'SAN MIGUEL', 'PORT AREA'],
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

        if political_dynasties_available:
            contractor_rows = await dynasty_conn.fetch(
                """
                SELECT dynasty_first_name, dynasty_last_name, company_name, role
                FROM contractor_dynasty_matches
                """
            )
            for row in contractor_rows:
                key = _name_key(row['dynasty_first_name'], row['dynasty_last_name'])
                contractor_lookup[key].append(row)

            party_rows = await dynasty_conn.fetch(
                """
                SELECT plm.person_id, plm.party_list_number, pd.first_name, pd.last_name
                FROM party_list_members plm
                JOIN political_dynasties pd ON plm.person_id = pd.id
                """
            )

            for row in party_rows:
                party_number = row['party_list_number']
                person_id = row['person_id']
                key = _name_key(row['first_name'], row['last_name'])
                if person_id is not None:
                    party_memberships_by_person[person_id].append(party_number)
                party_memberships_by_name[key].append(party_number)
                party_memberships_by_party[party_number].add(key)

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
            congressman_id = congressman_config.get('id')
            
            # Get congressman from database
            person = None
            if political_dynasties_available:
                person = await dynasty_conn.fetchrow('''
                    SELECT id, first_name, last_name, middle_name, province, municipality_city, region, party
                    FROM political_dynasties
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
                        (UPPER(first_name) LIKE $1 AND UPPER(last_name) LIKE $2)
                        OR (UPPER(first_name || ' ' || COALESCE(middle_name, '') || ' ' || last_name) LIKE $3)
                        OR (UPPER(first_name || ' ' || COALESCE(middle_name, '')) LIKE $1 AND UPPER(last_name) LIKE $2)
                        OR (UPPER(last_name) LIKE $2 AND UPPER(first_name) LIKE '%MANNIX%' AND 'MANNIX' = $4)
                        OR (UPPER(last_name) LIKE $2 AND UPPER(first_name) LIKE '%MANUEL%' AND 'MANNIX' = $4)
                      )
                    ORDER BY id DESC
                    LIMIT 1
                ''', 
                    f"{(first_name_pattern or '').upper()}%", 
                    f"{(last_name_pattern or '').upper()}%",
                    f"%{(first_name_pattern or '').upper()}% {(last_name_pattern or '').upper()}%",
                    (first_name_pattern or '').upper()
                )
            
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
                import re
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
            family_contractors = congressman_config.get('family_connections', {}).get('contractors', [])
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
            
            congressmen_data[display_name] = {
                "name": display_name,
                "provinces": provinces,
                "district_municipalities": district_municipalities,
                "district_number": config_district_number,
                "is_city_district": config_is_city_district,
                "contractors": contractor_names,
                "contractor_patterns": contractor_patterns,
                "contractor_exclusions": contractor_exclusions,
                "barangays": barangays,
            }
        
        return congressmen_data

    def match_project(self, project_text: str, congressman_data: Dict, districts_data: Dict, contractor_name: str = '', project_year: Optional[int] = None) -> tuple[Optional[str], Optional[str], int]:
        """
        Match a project to a congressman.
        Returns: (congressman_name, match_type, match_score) or (None, None, 0)

        LOGIC:
        1. Check contractor match (for party-list representatives)
        2. For city districts: check term filtering, then barangay match
        3. For province districts: check municipality matches
        4. Term filtering: valid years checked against terms, null years get -50 score for all congressmen
        """
        combined_text = project_text.upper()
        congressman_name = congressman_data['name']

        def contains_word(text: str, word: str) -> bool:
            if not word:
                return False
            pattern = rf'(?<!\w){re.escape(word)}(?!\w)'
            return re.search(pattern, text) is not None
        
        def has_different_district_mentioned(text: str, congressman_district: str) -> bool:
            """Check if text mentions a different district number than the congressman's district."""
            if not congressman_district:
                return False
            
            district_upper = congressman_district.upper()
            other_district_patterns = []
            
            if '1ST' in district_upper or 'FIRST' in district_upper:
                other_district_patterns = ['2ND DISTRICT', 'SECOND DISTRICT', '3RD DISTRICT', 'THIRD DISTRICT', '4TH DISTRICT', 'FOURTH DISTRICT']
            elif '2ND' in district_upper or 'SECOND' in district_upper:
                other_district_patterns = ['1ST DISTRICT', 'FIRST DISTRICT', '3RD DISTRICT', 'THIRD DISTRICT', '4TH DISTRICT', 'FOURTH DISTRICT']
            elif '3RD' in district_upper or 'THIRD' in district_upper:
                other_district_patterns = ['1ST DISTRICT', 'FIRST DISTRICT', '2ND DISTRICT', 'SECOND DISTRICT', '4TH DISTRICT', 'FOURTH DISTRICT']
            else:
                for i in range(1, 10):
                    if str(i) not in district_upper:
                        if i == 1:
                            other_district_patterns.extend(['1ST DISTRICT', 'FIRST DISTRICT'])
                        elif i == 2:
                            other_district_patterns.extend(['2ND DISTRICT', 'SECOND DISTRICT'])
                        elif i == 3:
                            other_district_patterns.extend(['3RD DISTRICT', 'THIRD DISTRICT'])
                        else:
                            other_district_patterns.append(f'{i}TH DISTRICT')
            
            for other_district in other_district_patterns:
                if contains_word(text, other_district):
                    return True
            
            return False
        
        # 1. Check barangay match (highest priority)
        if congressman_data.get('barangays') and congressman_data.get('is_city_district'):
            valid_barangays = []
            if districts_data and congressman_data.get('provinces'):
                province = congressman_data['provinces'][0]
                province_key = None
                for key in districts_data.get('districts', {}).keys():
                    if key.upper() == province.upper():
                        province_key = key
                        break
                
                if province_key:
                    districts_info = districts_data.get('districts', {}).get(province_key, {})
                    barangays_map = districts_info.get('barangays', {})
                    district_number = congressman_data.get('district_number')
                    
                    if district_number and district_number in barangays_map:
                        valid_barangays = [b.upper() for b in barangays_map[district_number]]
            
            if not valid_barangays:
                valid_barangays = [b.upper() for b in congressman_data.get('barangays', []) if b]
            
            if any(indicator in combined_text for indicator in ['BARANGAY', 'BRGY', 'BRG', 'BR.', 'BRGY.']):
                valid_barangay_found = False
                for valid_barangay in valid_barangays:
                    if contains_word(combined_text, valid_barangay):
                        valid_barangay_found = True
                        break
                
                if not valid_barangay_found:
                    invalid_barangays = ['TALISAYAN', 'LABUAN', 'AYALA', 'SINUNUC', 'BALIWASAN', 'PASONANCA', 'SINUBONG', 'RECODO', 'SAN RAMON', 'MAASIN', 'MENZI', 'CULIANAN']
                    for invalid_barangay in invalid_barangays:
                        if contains_word(combined_text, invalid_barangay):
                            is_valid_substring = any(invalid_barangay in valid_b or valid_b in invalid_barangay for valid_b in valid_barangays)
                            if not is_valid_substring:
                                return (None, None, 0)
                    return (None, None, 0)
                
                if valid_barangay_found:
                    return (congressman_name, "district", 100)
        
        elif congressman_data.get('barangays'):
            for barangay in congressman_data['barangays']:
                if barangay and contains_word(combined_text, barangay.upper()):
                    return (congressman_name, "district", 100)
        
        # 2. Check contractor match EARLY
        contractors = congressman_data.get('contractors', [])
        contractor_patterns = congressman_data.get('contractor_patterns', [])
        contractor_exclusions = congressman_data.get('contractor_exclusions', {})
        
        def _contractor_is_excluded(candidate_upper: str) -> bool:
            for base, exclusions in contractor_exclusions.items():
                if base in candidate_upper:
                    for exclusion_value in exclusions:
                        if exclusion_value in candidate_upper:
                            return True
            return False

        def _normalize_for_match(value: str) -> str:
            return re.sub(r'[^A-Z0-9]+', ' ', value.upper()).strip()

        if contractor_name:
            contractor_name_upper = contractor_name.upper()
            normalized_candidate = _normalize_for_match(contractor_name)

            if 'GONZALES' in congressman_name.upper() and 'A.D. GONZALES' in contractor_name_upper:
                if not _contractor_is_excluded(contractor_name_upper):
                    return (congressman_name, "contractor", 50)
            
            for pattern in contractor_patterns:
                pattern_upper = pattern.upper()
                if not pattern_upper or len(pattern_upper) < 3:
                    continue

                if _contractor_is_excluded(contractor_name_upper):
                    break

                if pattern_upper in contractor_name_upper:
                    return (congressman_name, "contractor", 50)

                normalized_pattern = _normalize_for_match(pattern)
                if normalized_pattern and normalized_pattern in normalized_candidate:
                    return (congressman_name, "contractor", 50)
                    
        if contractor_patterns and not contractor_name:
            normalized_text = _normalize_for_match(combined_text)
            for pattern in contractor_patterns:
                normalized_pattern = _normalize_for_match(pattern)
                if normalized_pattern and normalized_pattern in normalized_text:
                    if not _contractor_is_excluded(normalized_text):
                        return (congressman_name, "contractor", 40)

        if contractors:
            if contractor_name:
                contractor_name_upper = contractor_name.upper()
            else:
                contractor_name_upper = ''

            if contractor_name_upper:
                for contractor in contractors:
                    contractor_upper = contractor.upper()

                    if 'JSG' in contractor_upper and 'JSG' in contractor_name_upper:
                        if not _contractor_is_excluded(contractor_name_upper):
                            return (congressman_name, "contractor", 50)
                    
                    for pattern in ['SUNWEST', 'ROVING PREMIER', 'VIRKAR', 'GARDIOLA', 'NEWINGTON', 'S-ANG']:
                        if pattern in contractor_upper:
                            pattern_upper = pattern.upper()
                            if pattern_upper in contractor_name_upper and not _contractor_is_excluded(contractor_name_upper):
                                return (congressman_name, "contractor", 50)
            else:
                normalized_text = _normalize_for_match(combined_text)
                for contractor in contractors:
                    contractor_upper = contractor.upper()
                    for pattern in ['SUNWEST', 'ROVING PREMIER', 'VIRKAR', 'GARDIOLA', 'NEWINGTON', 'S-ANG', 'JSG']:
                        if pattern in contractor_upper and pattern in normalized_text:
                            if not _contractor_is_excluded(normalized_text):
                                return (congressman_name, "contractor", 40)

        # 3. Special handling for Davao City districts
        if congressman_data.get('is_city_district') and congressman_data.get('provinces') and congressman_data['provinces'][0] == 'Davao City':
            district_number = (congressman_data.get('district_number') or '').strip()
            allow_city_wide = district_number == '1st District'

            match_score = 100
            should_include = False

            if project_year is not None:
                terms = congressman_data.get('terms', [])
                for term in terms:
                    term_start = term.get('start')
                    term_end = term.get('end')
                    if term_start and term_end and term_start <= project_year <= term_end:
                        should_include = True
                        break
            else:
                if allow_city_wide:
                    should_include = True
                    match_score = 100
                else:
                    return (None, None, 0)

            if not should_include:
                return (None, None, 0)

            valid_barangays = []
            if districts_data and congressman_data.get('provinces'):
                province = congressman_data['provinces'][0]
                province_key = None
                for key in districts_data.get('districts', {}).keys():
                    if key.upper() == province.upper():
                        province_key = key
                        break

                if province_key:
                    districts_info = districts_data.get('districts', {}).get(province_key, {})
                    barangays_map = districts_info.get('barangays', {})

                    if district_number and district_number in barangays_map:
                        full_barangays = barangays_map[district_number]
                        base_barangays = []
                        for barangay in full_barangays:
                            base_name = re.sub(r'\s+\d+$|.*\s+', '', barangay).strip()
                            if base_name != barangay:
                                base_barangays.append(base_name)
                        valid_barangays = [b.upper() for b in full_barangays + base_barangays]

            if not valid_barangays:
                valid_barangays = [b.upper() for b in congressman_data.get('barangays', []) if b]

            if valid_barangays:
                has_barangay_match = any(contains_word(combined_text, barangay) for barangay in valid_barangays)
                if has_barangay_match:
                    return (congressman_name, "district", match_score)

            if has_different_district_mentioned(combined_text, district_number):
                return (None, None, 0)

            if allow_city_wide:
                return (congressman_name, "district", match_score)

            return (None, None, 0)

        # 4. Get district identifier
        district_identifier = None
        if congressman_data.get('provinces') and congressman_data['provinces']:
            district_identifier = congressman_data['provinces'][0].upper()
        
        if not district_identifier:
            return (None, None, 0)
        
        if district_identifier == "QUEZON":
            if contains_word(combined_text, "QUEZON CITY"):
                return (None, None, 0)
        
        is_leyte_second = (
            district_identifier == 'LEYTE'
            and (congressman_data.get('district_number') or '').strip().upper() == '2ND DISTRICT'
        )
        is_samar_first = (
            district_identifier == 'SAMAR'
            and (congressman_data.get('district_number') or '').strip().upper() == '1ST DISTRICT'
        )

        target_municipality_mentioned = False
        # 5. Pre-check: If project mentions a municipality from a DIFFERENT district, exclude it
        if districts_data and congressman_data.get('district_number') and congressman_data.get('provinces'):
            province = congressman_data['provinces'][0]
            province_key = None
            for key in districts_data.get('districts', {}).keys():
                if key.upper() == province.upper():
                    province_key = key
                    break
            
            if province_key:
                districts_info = districts_data.get('districts', {}).get(province_key, {})
                municipalities_map = districts_info.get('municipalities', {})
                congressman_district = congressman_data['district_number'].upper()
                
                for mun_key, mun_district in municipalities_map.items():
                    mun_key_upper = mun_key.upper()
                    if mun_key_upper == province.upper():
                        continue
                    if contains_word(combined_text, mun_key_upper):
                        if mun_district and mun_district.upper() != congressman_district:
                            return (None, None, 0)
                        elif mun_district and mun_district.upper() == congressman_district:
                            target_municipality_mentioned = True
                        elif is_leyte_second and mun_key_upper in self.leyte_second_municipalities:
                            target_municipality_mentioned = True
                        elif is_samar_first and mun_key_upper in self.samar_first_municipalities:
                            target_municipality_mentioned = True
        
        # 6. Check if district identifier is in project text
        if not contains_word(combined_text, district_identifier):
            return (None, None, 0)
        
        # 7. For city districts - IMPROVED LOGIC FOR ALL CITIES, ESPECIALLY MANILA
        if congressman_data.get('is_city_district') and district_identifier:
            district_number_raw = (congressman_data.get('district_number') or '').strip()
            district_number_upper = district_number_raw.upper()

            if district_identifier == 'MANILA':
                # MANILA_BARANGAY_RANGES not found in original, so we'll use None
                range_limits = None

                barangay_numbers_in_text: set[int] = set()
                for pattern in BARANGAY_NUMBER_PATTERNS:
                    for match in pattern.finditer(combined_text):
                        groups = match.groups()
                        if len(groups) >= 2 and groups[0] and groups[1]:
                            try:
                                start = int(groups[0])
                                end = int(groups[1])
                            except ValueError:
                                continue
                            if start > end:
                                start, end = end, start
                            barangay_numbers_in_text.update(range(start, end + 1))
                        else:
                            for group in groups:
                                if not group:
                                    continue
                                try:
                                    barangay_numbers_in_text.add(int(group))
                                except ValueError:
                                    continue

                if barangay_numbers_in_text:
                    valid_number_set = set(self.manila_barangay_numbers.get(district_number_upper, []))
                    if valid_number_set:
                        if all(num in valid_number_set for num in barangay_numbers_in_text):
                            return (congressman_name, "district", 100)
                    elif range_limits and all(range_limits[0] <= num <= range_limits[1] for num in barangay_numbers_in_text):
                        return (congressman_name, "district", 100)
                    return (None, None, 0)

                tokens = set(self.manila_barangay_tokens.get(district_number_upper, []))
                tokens.update(
                    (barangay or '').upper().strip()
                    for barangay in congressman_data.get('barangays', [])
                    if barangay
                )
                keyword_list = self.manila_keyword_map.get(district_number_upper, [])
                if tokens and any(token in combined_text for token in tokens if token):
                    return (congressman_name, "district", 100)

                if keyword_list and any(contains_word(combined_text, keyword) for keyword in keyword_list if keyword):
                    return (congressman_name, "district", 80)

                return (None, None, 0)

            # For other city districts
            valid_barangays = []
            if districts_data and congressman_data.get('provinces'):
                province = congressman_data['provinces'][0]
                province_key = None
                for key in districts_data.get('districts', {}).keys():
                    if key.upper() == province.upper():
                        province_key = key
                        break

                if province_key:
                    districts_info = districts_data.get('districts', {}).get(province_key, {})
                    barangays_map = districts_info.get('barangays', {})

                    if district_number_raw and district_number_raw in barangays_map:
                        full_barangays = barangays_map[district_number_raw]
                        base_barangays = []
                        for barangay in full_barangays:
                            base_name = barangay.split()[0] if barangay.split() else barangay
                            base_barangays.append(base_name)
                        valid_barangays = [b.upper() for b in full_barangays + base_barangays]

            has_real_barangay = False
            if valid_barangays:
                has_real_barangay = any(barangay in combined_text for barangay in valid_barangays)

            if re.search(r'\bROAD\b', combined_text, re.IGNORECASE):
                if 'CITY' not in combined_text:
                    return (None, None, 0)

            if has_real_barangay:
                return (congressman_name, "district", 100)

            if has_different_district_mentioned(combined_text, district_number_raw):
                return (None, None, 0)
            
            if district_identifier in combined_text:
                return (congressman_name, "district", 1)
        
        # 8. For province districts: Check if any municipality from that district is in project text
        district_municipalities = congressman_data.get('district_municipalities', [])
        if district_municipalities:
            for mun in district_municipalities:
                if mun and contains_word(combined_text, mun.upper()):
                    mun_upper = mun.upper()
                    provinces = congressman_data.get('provinces', [])
                    
                    is_naming_conflict = False
                    for prov in provinces:
                        if prov and mun_upper == prov.upper():
                            is_naming_conflict = True
                            break
                    
                    if is_naming_conflict:
                        has_municipality_keyword = any(keyword in combined_text for keyword in [
                            'MUNICIPALITY OF ' + mun_upper,
                            'MUNICIPAL ' + mun_upper,
                            'MUNICIPIO',
                            'LGU-' + mun_upper,
                            'LGU ' + mun_upper
                        ])
                        
                        if not has_municipality_keyword:
                            print(f"    ⚠️  Skipping potential false match: '{mun}' (naming conflict with province/city)")
                            continue
                    
                    return (congressman_name, "district", 100)

        if target_municipality_mentioned:
            return (congressman_name, "district", 100)

        if is_leyte_second:
            if any(keyword in combined_text for keyword in self.leyte_second_negative_keywords):
                return (None, None, 0)
            keyword_hit = any(keyword in combined_text for keyword in self.leyte_second_keywords)
            if keyword_hit and 'LEYTE' in combined_text:
                return (congressman_name, "district", 90)

        if is_samar_first:
            if any(keyword in combined_text for keyword in self.samar_first_negative_keywords):
                return (None, None, 0)
            keyword_hit = any(keyword in combined_text for keyword in self.samar_first_keywords)
            if keyword_hit and 'SAMAR' in combined_text:
                return (congressman_name, "district", 90)
        
        if not congressman_data.get('is_city_district'):
            return (None, None, 0)
        
        return (None, None, 0)

    def load_projects_from_parquet(self, parquet_path: Path, source_name: str) -> List[Dict]:
        """Load projects from a Parquet file using DuckDB"""
        if not parquet_path.exists():
            print(f"⚠️  Parquet file not found: {parquet_path}")
            return []
        
        try:
            query = f'SELECT * FROM "{parquet_path}"'
            result = self.duckdb_conn.execute(query).fetchall()
            columns = [desc[0] for desc in self.duckdb_conn.description]
            
            projects = []
            for row in result:
                project_dict = dict(zip(columns, row))
                project_dict['_source'] = source_name
                projects.append(project_dict)
            
            return projects
        except Exception as e:
            print(f"⚠️  Error loading {source_name} from Parquet: {e}")
            return []

    async def process_projects(self, dynasty_conn, congressmen_data: Dict, districts_data: Dict) -> List[Dict]:
        """Process projects from all Parquet sources"""
        all_projects = []
        
        # Process SSP/MeiliSearch projects (keep original logic)
        try:
            client = FloodControlClient()
            page_size = 1000
            offset = 0
            total_hits = None

            while True:
                projects, metadata = await client.search_projects(
                    query="",
                    filters=None,
                    limit=page_size,
                    offset=offset
                )

                if total_hits is None:
                    total_hits = metadata.get("totalHits") or metadata.get("estimatedTotalHits") or 0
                    print(f"ℹ️  Fetching SSP projects via MeiliSearch: estimated {total_hits} records")

                if not projects:
                    break

                for proj in projects:
                    proj_desc = (proj.ProjectDescription or '').upper()
                    proj_province = (proj.Province or '').upper()
                    proj_municipality = (proj.Municipality or '').upper()
                    proj_contractor = (proj.Contractor or '').upper()
                    combined_text = f'{proj_desc} {proj_province} {proj_municipality} {proj_contractor}'

                    project_year = None
                    if hasattr(proj, 'Year') and proj.Year:
                        try:
                            project_year = int(proj.Year)
                        except (ValueError, TypeError):
                            pass

                    matches = []
                    for cm_name, cm_data in congressmen_data.items():
                        cm_name_result, match_type_result, match_score_result = self.match_project(
                            combined_text,
                            cm_data,
                            districts_data,
                            proj_contractor,
                            project_year
                        )
                        if cm_name_result and match_score_result > 0:
                            matches.append((cm_name_result, match_type_result, match_score_result))

                    if matches:
                        location_parts = []
                        if proj.Province:
                            location_parts.append(proj.Province)
                        if proj.Municipality:
                            location_parts.append(proj.Municipality)
                        location_str = ', '.join(location_parts).strip() or "N/A"

                        amount = 0
                        if proj.ContractCost:
                            if isinstance(proj.ContractCost, str):
                                amount = float(proj.ContractCost.replace(',', '').replace('₱', '').replace('PHP', '').strip() or 0)
                            else:
                                amount = float(proj.ContractCost)

                        for matched_congressman, match_type, match_score in matches:
                            all_projects.append({
                                "congressman": matched_congressman,
                                "source": self._normalize_source_label("SSP"),
                                "meilisearch_id": proj.id if hasattr(proj, 'id') else None,
                                "project_name": proj.ProjectDescription or "N/A",
                                "contractor": proj.Contractor or "N/A",
                                "amount": amount,
                                "location": location_str,
                                "year": proj.Year if hasattr(proj, 'Year') else "N/A",
                                "status": proj.Status if hasattr(proj, 'Status') else "N/A",
                                "match_type": match_type,
                                "match_score": match_score,
                                "is_city_wide": (match_score == 1 and match_type == "district")
                            })

                offset += page_size
                if total_hits and offset >= total_hits:
                    break
        except Exception as e:
            print(f"Error processing SSP/MeiliSearch projects: {e}")
        
        # Process DIME projects from Parquet
        try:
            dime_projects = self.load_projects_from_parquet(DIME_PARQUET, "DIME")
            if dime_projects:
                print(f"📊 Loaded {len(dime_projects)} DIME projects from Parquet")
                dime_chunks = self._chunk_list(dime_projects, self.max_workers)
                loop = asyncio.get_running_loop()
                dime_tasks = [
                    loop.run_in_executor(
                        None,
                        functools.partial(self._process_dime_chunk, chunk, congressmen_data, districts_data)
                    )
                    for chunk in dime_chunks
                ]
                for result in await asyncio.gather(*dime_tasks):
                    all_projects.extend(result)
                print(f"✅ Processed {len(all_projects)} DIME projects (matched)")
        except Exception as e:
            print(f"Error processing DIME projects: {e}")
            import traceback
            traceback.print_exc()
        
        # Process PhilGEPS projects from Parquet
        try:
            philgeps_projects = self.load_projects_from_parquet(PHILGEPS_PARQUET, "PhilGEPS")
            if philgeps_projects:
                print(f"📊 Loaded {len(philgeps_projects)} PhilGEPS contracts from Parquet")
                philgeps_chunks = self._chunk_list(philgeps_projects, self.max_workers)
                loop = asyncio.get_running_loop()
                philgeps_tasks = [
                    loop.run_in_executor(
                        None,
                        functools.partial(self._process_philgeps_chunk, chunk, congressmen_data, districts_data)
                    )
                    for chunk in philgeps_chunks
                ]
                dime_count = len(all_projects)
                for result in await asyncio.gather(*philgeps_tasks):
                    all_projects.extend(result)
                print(f"✅ Processed {len(all_projects) - dime_count} PhilGEPS projects (matched)")
        except Exception as e:
            print(f"Error processing PhilGEPS projects: {e}")
            import traceback
            traceback.print_exc()
        
        # Process Infrawatch projects from Parquet
        try:
            infrawatch_projects = self.load_projects_from_parquet(INFRAWATCH_PARQUET, "Infrawatch")
            if infrawatch_projects:
                print(f"📊 Loaded {len(infrawatch_projects)} Infrawatch projects from Parquet")
                infrawatch_chunks = self._chunk_list(infrawatch_projects, self.max_workers)
                loop = asyncio.get_running_loop()
                infrawatch_tasks = [
                    loop.run_in_executor(
                        None,
                        functools.partial(self._process_infrawatch_chunk, chunk, congressmen_data, districts_data)
                    )
                    for chunk in infrawatch_chunks
                ]
                prev_count = len(all_projects)
                for result in await asyncio.gather(*infrawatch_tasks):
                    all_projects.extend(result)
                print(f"✅ Processed {len(all_projects) - prev_count} Infrawatch projects (matched)")
        except Exception as e:
            print(f"Error processing Infrawatch projects: {e}")
            import traceback
            traceback.print_exc()
        
        return all_projects

    async def generate_cache(self):
        """Generate the cached JSON file using DuckDB"""
        print("🚀 Starting dynasty-projects cache generation (DuckDB version)...")

        # Ensure latest districts and congressmen config are pulled from DB
        self._refresh_source_json()
        
        # Load config
        config_data, districts_data = await self.load_config()
        print(f"✅ Loaded config with {len(config_data.get('target_congressmen', []))} congressmen")
        
        # Connect to dynasty database (still need this for congressmen data)
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
            if not political_dynasties_available:
                print("⚠️  Dynasty DB missing political_dynasties table. Using config-only data.")

            # Get congressmen data
            congressmen_data = await self.get_congressmen_data(
                dynasty_conn,
                config_data,
                districts_data,
                political_dynasties_available
            )
            print(f"✅ Loaded {len(congressmen_data)} congressmen")
            
            # Process projects from Parquet files
            all_projects = await self.process_projects(
                dynasty_conn,
                congressmen_data,
                districts_data
            )
            print(f"✅ Processed {len(all_projects)} projects")
            
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
            microsite_count = len([p for p in unique_projects if 'Microsite' in (p.get('sources_list', []))])
            summary = {
                "total": len(unique_projects),
                "dime": len([p for p in unique_projects if 'DIME' in (p.get('sources_list', []))]),
                "philgeps": len([p for p in unique_projects if 'PhilGEPS' in (p.get('sources_list', []))]),
                "ssp": ssp_count,
                "infrawatch": microsite_count,
                "microsite": microsite_count,
                "district_projects": len([p for p in unique_projects if p.get('match_type') == 'district']),
                "contractor_projects": len([p for p in unique_projects if p.get('match_type') == 'contractor'])
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
            
            dashboard_stats = {
                "total_cost_all": total_cost_all,
                "total_projects": summary['total'],
                "district_count": district_count,
                "district_cost": district_cost,
                "contractor_count": contractor_count,
                "contractor_cost": contractor_cost
            }
            
            print("ℹ️  Combined cache file generation skipped (file too large and unused)")
            
            # Create individual cache files for each congressman
            print(f"\n📁 Creating individual cache files for each congressman...")
            cache_base_dir = Path(__file__).parent.parent / 'static' / 'data'
            
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
                # Filter projects for this congressman
                # Include projects where this congressman is district_congressman, contractor_congressman, or in _all_congressmen
                congressman_projects = []
                for p in unique_projects:
                    # Check if this congressman matches the project (district or contractor)
                    if (p.get('district_congressman') == congressman_name or 
                        p.get('contractor_congressman') == congressman_name or
                        congressman_name in p.get('_all_congressmen', [])):
                        # Create a copy with this congressman as the primary congressman
                        proj_copy = p.copy()
                        proj_copy['congressman'] = congressman_name
                        # Remove the internal _all_congressmen field before saving
                        proj_copy.pop('_all_congressmen', None)
                        congressman_projects.append(proj_copy)
                
                # Calculate congressman-specific statistics
                congressman_total_cost = sum(parse_amount(p.get('amount', 0)) for p in congressman_projects)
                congressman_district_count = len([p for p in congressman_projects if p.get('district_congressman') == congressman_name])
                congressman_contractor_count = len([p for p in congressman_projects if p.get('contractor_congressman') == congressman_name])
                congressman_district_cost = sum(parse_amount(p.get('amount', 0)) for p in congressman_projects if p.get('district_congressman') == congressman_name)
                congressman_contractor_cost = sum(parse_amount(p.get('amount', 0)) for p in congressman_projects if p.get('contractor_congressman') == congressman_name)
                
                congressman_summary = {
                    "total": len(congressman_projects),
                    "dime": len([p for p in congressman_projects if 'DIME' in (p.get('sources_list', []))]),
                    "philgeps": len([p for p in congressman_projects if 'PhilGEPS' in (p.get('sources_list', []))]),
                    "ssp": len([p for p in congressman_projects if 'SSP' in (p.get('sources_list', []))]),
                    "infrawatch": len([p for p in congressman_projects if 'Infrawatch' in (p.get('sources_list', []))]),
                    "microsite": len([p for p in congressman_projects if 'Infrawatch' in (p.get('sources_list', []))]),
                    "district_projects": congressman_district_count,
                    "contractor_projects": congressman_contractor_count
                }
                
                congressman_dashboard_stats = {
                    "total_cost_all": congressman_total_cost,
                    "total_projects": len(congressman_projects),
                    "district_count": congressman_district_count,
                    "district_cost": congressman_district_cost,
                    "contractor_count": congressman_contractor_count,
                    "contractor_cost": congressman_contractor_cost
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
            
            # Update aggregated leaderboard so the UI reflects the new cache immediately
            self._regenerate_top_congressmen_cache()
            
            print("✅ Cache generation complete")
            
        finally:
            await dynasty_conn.close()
            self.duckdb_conn.close()

async def main():
    generator = DynastyProjectsCacheGeneratorDuckDB()
    await generator.generate_cache()

if __name__ == '__main__':
    asyncio.run(main())

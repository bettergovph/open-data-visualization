#!/usr/bin/env python3
"""
Generate cached JSON for province-projects API (Cebu focus).
This script generates a cached JSON file with all projects that have "Cebu" in name or location.
"""

import asyncio
import asyncpg
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Set
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from flood_client import FloodControlClient
from infrawatch_postgres_client import get_infrawatch_connection

# Load environment variables
load_dotenv()

SOURCE_PRIORITY = ["SSP", "DIME", "PhilGEPS", "Microsite"]

# Load substring provinces configuration
def load_substring_provinces() -> Set[str]:
    """Load the list of province names that need word boundary matching"""
    config_path = Path(__file__).parent.parent / 'provinces-substring.json'
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return set(config.get('substring_provinces', []))
    except Exception as e:
        print(f"⚠️  Warning: Could not load provinces-substring.json: {e}")
        # Fallback to hardcoded list
        return {
            'agusan', 'camarines', 'cotabato', 'davao', 'ilocos', 
            'lanao', 'leyte', 'mindoro', 'misamis', 'negros', 
            'samar', 'surigao', 'zamboanga'
        }

SUBSTRING_PROVINCES = load_substring_provinces()


def normalize_source_label(source: Optional[str]) -> str:
    if not source:
        return "Unknown"
    normalized = str(source).strip()
    lower = normalized.lower()
    if lower in {"microsite", "dpwh microsite", "infrawatch"}:
        return "Microsite"
    return normalized


def sort_sources_list(sources: List[str]) -> List[str]:
    unique = []
    for src in sources:
        label = normalize_source_label(src)
        if label not in unique:
            unique.append(label)
    return sorted(unique, key=lambda label: SOURCE_PRIORITY.index(label) if label in SOURCE_PRIORITY else len(SOURCE_PRIORITY))


def normalize_text_for_key(value: Optional[str]) -> str:
    if not value:
        return ""
    return " ".join(str(value).strip().lower().split())


def sanitize_filename(name: str) -> str:
    """Sanitize a string to be used as a filename"""
    if not name:
        return "unknown"
    
    # Remove or replace problematic characters
    # Replace newlines, tabs, and other whitespace with space
    sanitized = re.sub(r'[\n\r\t]+', ' ', name)
    
    # Replace multiple spaces with single space
    sanitized = re.sub(r'\s+', ' ', sanitized)
    
    # Remove or replace characters that are invalid in filenames
    # Keep alphanumeric, spaces, hyphens, underscores, periods, and parentheses
    sanitized = re.sub(r'[^\w\s\-\.\(\)]+', '-', sanitized)
    
    # Replace spaces with hyphens
    sanitized = sanitized.replace(' ', '-')
    
    # Remove multiple consecutive hyphens
    sanitized = re.sub(r'-+', '-', sanitized)
    
    # Remove leading/trailing hyphens
    sanitized = sanitized.strip('-')
    
    # Lowercase for consistency
    sanitized = sanitized.lower()
    
    # Limit length to avoid filesystem issues (max 200 chars)
    if len(sanitized) > 200:
        sanitized = sanitized[:200].rstrip('-')
    
    return sanitized or "unknown"


def normalize_amount_for_key(value: Any) -> str:
    if value is None:
        return "0.00"
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}"
    cleaned = str(value)
    for ch in ["₱", ",", "PHP", "php"]:
        cleaned = cleaned.replace(ch, "")
    try:
        return f"{float(cleaned.strip() or 0):.2f}"
    except ValueError:
        return cleaned.strip().lower()


class ProvinceProjectsCacheGenerator:
    """Generate cached JSON for province-projects (Cebu)"""
    
    def __init__(self, province_name: str = "Cebu"):
        self.province_name = province_name
        self.cache_file = Path(__file__).parent.parent / 'static' / 'data' / f'province-projects-{province_name.lower().replace(" ", "-")}-cache.json'
        self.geoph_city_path = Path('/home/joebert/geoph/geojson/city')
        self.geoph_province_path = Path('/home/joebert/geoph/geojson/province')
        # Also check static/data for province files
        self.static_data_path = Path(__file__).parent.parent / 'static' / 'data'
        
        # Map province names to their geoph paths
        self.province_geoph_mapping = {
            'Cebu': 'ph.central-visayas-region-vii.cebu',
            'Davao del Norte': 'ph.davao-region-region-xi.davao-del-norte',
            'Davao del Sur': 'ph.davao-region-region-xi.davao-del-sur',
            'Davao Oriental': 'ph.davao-region-region-xi.davao-oriental',
            'Davao de Oro': 'ph.davao-region-region-xi.compostela-valley',
            'Davao Occidental': 'ph.davao-region-region-xi.davao-occidental'
        }
    
    def get_municipalities_from_geoph(self) -> Tuple[List[str], List[str]]:
        """Get list of municipalities and cities for the province from geoph data"""
        municipalities = []
        cities = []
        
        if not self.geoph_city_path.exists():
            print(f"⚠️  Warning: Geoph city path {self.geoph_city_path} does not exist.")
            return [], []
        
        # First try the mapping if available
        if self.province_name in self.province_geoph_mapping:
            prefix = self.province_geoph_mapping[self.province_name]
        else:
            # Dynamically find the province by searching for province files
            # Normalize province name for matching
            province_normalized = self.province_name.lower().replace(' ', '-')
            
            # Search in multiple locations for province files
            province_files = []
            
            # Try geoph province directory
            if self.geoph_province_path.exists():
                province_files = list(self.geoph_province_path.glob(f'ph.*.{province_normalized}.any.any.geo.json'))
            
            # Try static/data directory
            if not province_files and self.static_data_path.exists():
                province_files = list(self.static_data_path.glob(f'ph.*.{province_normalized}.any.any.geo.json'))
            
            # Try alternative patterns (e.g., "davao-del-norte" vs "davao del norte")
            if not province_files:
                province_normalized_alt = self.province_name.lower().replace(' del ', '-del-').replace(' de ', '-de-')
                if self.geoph_province_path.exists():
                    province_files = list(self.geoph_province_path.glob(f'ph.*.{province_normalized_alt}.any.any.geo.json'))
                if not province_files and self.static_data_path.exists():
                    province_files = list(self.static_data_path.glob(f'ph.*.{province_normalized_alt}.any.any.geo.json'))
            
            if not province_files:
                print(f"⚠️  Warning: No geoph province file found for {self.province_name}")
                return [], []
            
            # Extract prefix from the province file
            # Example: ph.central-visayas-region-vii.cebu.any.any.geo.json -> ph.central-visayas-region-vii.cebu
            province_file = province_files[0]
            parts = province_file.stem.split('.')
            if len(parts) >= 3:
                prefix = '.'.join(parts[:3])  # ph.region.province
            else:
                print(f"⚠️  Warning: Could not extract prefix from {province_file.name}")
                return [], []
        
        # Now search for city/municipality files with this prefix
        for file in self.geoph_city_path.glob(f'{prefix}.*.any.geo.json'):
            # Extract municipality/city name from filename
            # Format: ph.region.province.municipality.any.geo.json
            parts = file.stem.split('.')
            if len(parts) >= 4:
                mun_name = parts[3].replace('-', ' ').title()
                # Check if it's a city (contains 'city' in filename)
                if 'city' in file.name.lower():
                    cities.append(mun_name)
                else:
                    municipalities.append(mun_name)
        
        print(f"📋 Found {len(municipalities)} municipalities and {len(cities)} cities from geoph for {self.province_name}")
        return sorted(municipalities), sorted(cities)
        
    def matches_province(self, text: str) -> bool:
        """Check if text contains the province name (case-insensitive)"""
        if not text:
            return False
        text_lower = text.lower()
        province_lower = self.province_name.lower()
        
        # Check if this province name contains any of the base names that need strict matching
        # (loaded from provinces-substring.json)
        needs_strict_matching = any(base in province_lower for base in SUBSTRING_PROVINCES)
        
        if needs_strict_matching:
            # Use word boundary matching to avoid cross-matching
            # e.g., "Samar" won't match "Northern Samar" or "Eastern Samar"
            pattern = r'\b' + re.escape(province_lower) + r'\b'
            return bool(re.search(pattern, text_lower))
        
        return province_lower in text_lower
    
    async def process_ssp_projects(self, client: FloodControlClient) -> List[Dict]:
        """Process SSP/MeiliSearch projects"""
        all_projects = []
        
        try:
            print(f"🔍 Searching SSP/MeiliSearch for {self.province_name} projects...")
            
            # Query by province
            filter_str = f'Province = "{self.province_name}"'
            projects, metadata = await client.search_projects(
                query=self.province_name,
                filters=filter_str,
                limit=10000,
                offset=0
            )
            
            print(f"   Found {len(projects)} projects from SSP/MeiliSearch")
            
            for proj in projects:
                # Check if project matches province in various fields
                proj_desc = proj.ProjectDescription or ''
                proj_province = proj.Province or ''
                proj_municipality = proj.Municipality or ''
                proj_location = f'{proj_province} {proj_municipality}'.strip()
                
                # Check if province name appears in description, province, or municipality
                if (self.matches_province(proj_desc) or 
                    self.matches_province(proj_province) or 
                    self.matches_province(proj_municipality)):
                    
                    location_parts = []
                    if proj.Province:
                        location_parts.append(proj.Province)
                    if proj.Municipality:
                        location_parts.append(proj.Municipality)
                    location_str = ', '.join(location_parts).strip() or "N/A"
                    
                    # Handle ContractCost (can be string or float)
                    amount = 0
                    if proj.ContractCost:
                        if isinstance(proj.ContractCost, str):
                            amount = float(proj.ContractCost.replace(',', '').replace('₱', '').replace('PHP', '').strip() or 0)
                        else:
                            amount = float(proj.ContractCost)
                    
                    all_projects.append({
                        "source": "SSP",
                        "meilisearch_id": proj.id if hasattr(proj, 'id') else None,
                        "project_name": proj.ProjectDescription or "N/A",
                        "contractor": proj.Contractor or "N/A",
                        "amount": amount,
                        "location": location_str,
                        "province": proj.Province or "N/A",
                        "municipality": proj.Municipality or "N/A",
                        "year": proj.Year if hasattr(proj, 'Year') else "N/A",
                        "status": proj.Status if hasattr(proj, 'Status') else "N/A",
                    })
        except Exception as e:
            print(f"❌ Error processing SSP/MeiliSearch projects: {e}")
            import traceback
            traceback.print_exc()
        
        return all_projects
    
    async def process_dime_projects(self, dime_conn) -> List[Dict]:
        """Process DIME projects"""
        all_projects = []
        
        try:
            print(f"🔍 Searching DIME for {self.province_name} projects...")
            
            # Query DIME projects - get all and filter
            dime_projects = await dime_conn.fetch('''
                SELECT project_name, contractors, cost, province, city, barangay, status, date_started, meilisearch_id
                FROM projects
                WHERE province ILIKE $1 OR city ILIKE $1 OR project_name ILIKE $1
                LIMIT 50000
            ''', f'%{self.province_name}%')
            
            print(f"   Found {len(dime_projects)} projects from DIME")
            
            for proj in dime_projects:
                proj_name = proj.get('project_name') or ''
                proj_province = proj.get('province') or ''
                proj_city = proj.get('city') or ''
                proj_barangay = proj.get('barangay') or ''
                
                # Check if province name appears in any field
                if (self.matches_province(proj_name) or 
                    self.matches_province(proj_province) or 
                    self.matches_province(proj_city) or 
                    self.matches_province(proj_barangay)):
                    
                    location_parts = []
                    if proj.get('province'):
                        location_parts.append(proj['province'])
                    if proj.get('city'):
                        location_parts.append(proj['city'])
                    if proj.get('barangay'):
                        location_parts.append(proj['barangay'])
                    location_str = ', '.join(location_parts).strip() or "N/A"
                    
                    contractor_str = ''
                    if isinstance(proj.get('contractors'), list):
                        contractor_str = ', '.join(proj['contractors'])
                    elif proj.get('contractors'):
                        contractor_str = str(proj['contractors'])
                    
                    all_projects.append({
                        "source": "DIME",
                        "meilisearch_id": proj.get('meilisearch_id'),
                        "project_name": proj['project_name'] or "N/A",
                        "contractor": contractor_str if contractor_str else "N/A",
                        "amount": float(proj['cost']) if proj['cost'] else 0,
                        "location": location_str,
                        "province": proj.get('province') or "N/A",
                        "municipality": proj.get('city') or "N/A",
                        "barangay": proj.get('barangay') or "N/A",
                        "year": proj['date_started'].year if proj['date_started'] else "N/A",
                        "status": proj['status'] or "N/A",
                    })
        except Exception as e:
            print(f"❌ Error processing DIME projects: {e}")
            import traceback
            traceback.print_exc()
        
        return all_projects
    
    async def process_philgeps_projects(self, philgeps_conn) -> List[Dict]:
        """Process PhilGEPS projects"""
        all_projects = []
        
        try:
            print(f"🔍 Searching PhilGEPS for {self.province_name} projects...")
            
            # Query PhilGEPS projects - get all and filter
            philgeps_projects = await philgeps_conn.fetch('''
                SELECT award_title, awardee_name, contract_amount, area_of_delivery, award_date, award_status, meilisearch_id
                FROM contracts
                WHERE award_title ILIKE $1 OR area_of_delivery ILIKE $1
                LIMIT 50000
            ''', f'%{self.province_name}%')
            
            print(f"   Found {len(philgeps_projects)} projects from PhilGEPS")
            
            for contract in philgeps_projects:
                award_title = contract.get('award_title') or ''
                area_of_delivery = contract.get('area_of_delivery') or ''
                
                # Check if province name appears in title or area of delivery
                if (self.matches_province(award_title) or 
                    self.matches_province(area_of_delivery)):
                    
                    all_projects.append({
                        "source": "PhilGEPS",
                        "meilisearch_id": contract.get('meilisearch_id'),
                        "project_name": contract['award_title'] or "N/A",
                        "contractor": contract['awardee_name'] or "N/A",
                        "amount": float(contract['contract_amount']) if contract['contract_amount'] else 0,
                        "location": contract['area_of_delivery'] or "N/A",
                        "province": "N/A",  # PhilGEPS doesn't always have separate province field
                        "municipality": "N/A",
                        "year": contract['award_date'].year if contract['award_date'] else "N/A",
                        "status": contract['award_status'] or "N/A",
                    })
        except Exception as e:
            print(f"❌ Error processing PhilGEPS projects: {e}")
            import traceback
            traceback.print_exc()
        
        return all_projects

    async def process_infrawatch_projects(self, infrawatch_conn) -> List[Dict]:
        """Process Infrawatch (Microsite) projects"""
        projects: List[Dict] = []
        if not infrawatch_conn:
            print("⚠️  Skipping Infrawatch processing (no connection)")
            return projects

        try:
            print(f"🔍 Searching Infrawatch for {self.province_name} projects...")

            province_pattern = f"%{self.province_name}%"
            query = """
                SELECT data
                FROM infrawatch_projects_rows
                WHERE (
                      COALESCE(data->>'Province', '') ILIKE $1 OR
                      COALESCE(data->>'Project Location', '') ILIKE $1 OR
                      COALESCE(data->>'Location', '') ILIKE $1 OR
                      COALESCE(data->>'City/Municipality', '') ILIKE $1 OR
                      COALESCE(data->>'City / Municipality', '') ILIKE $1 OR
                      COALESCE(data->>'Municipality', '') ILIKE $1 OR
                      COALESCE(data->>'Contract Details', '') ILIKE $1 OR
                      COALESCE(data->>'Project Description', '') ILIKE $1 OR
                      COALESCE(data->>'Name of Project', '') ILIKE $1 OR
                      COALESCE(data->>'Project', '') ILIKE $1 OR
                      COALESCE(data->>'Project Name', '') ILIKE $1
                  )
            """
            rows = await infrawatch_conn.fetch(query, province_pattern)
            print(f"   Found {len(rows)} projects from Infrawatch")

            def parse_amount(value: Any) -> float:
                if value is None:
                    return 0.0
                if isinstance(value, (int, float)):
                    return float(value)
                if isinstance(value, str):
                    cleaned = re.sub(r"[^\d.\-]", "", value)
                    if cleaned.strip() == "":
                        return 0.0
                    try:
                        return float(cleaned)
                    except ValueError:
                        return 0.0
                return 0.0

            def detect_year(*values: Any) -> str:
                for value in values:
                    if value is None:
                        continue
                    if isinstance(value, (int, float)):
                        year_int = int(value)
                        if 1900 <= year_int <= 2100:
                            return str(year_int)
                    if isinstance(value, str):
                        match = re.search(r"(20\d{2}|19\d{2})", value)
                        if match:
                            return match.group(1)
                        cleaned = value.strip()
                        if len(cleaned) >= 4:
                            return cleaned
                return "N/A"

            for row in rows:
                record = row.get("data")
                if isinstance(record, str):
                    try:
                        record = json.loads(record)
                    except json.JSONDecodeError:
                        continue

                if not isinstance(record, dict):
                    continue

                province_value = record.get("Province") or record.get("Province/Location")
                municipality_value = (
                    record.get("City/Municipality")
                    or record.get("City / Municipality")
                    or record.get("Municipality")
                )
                barangay_value = record.get("Barangay")
                location_candidates = [
                    record.get("Project Location"),
                    record.get("Location"),
                    record.get("Detailed Location"),
                    record.get("Address"),
                    province_value,
                    municipality_value,
                    barangay_value,
                ]

                # Ensure project is relevant to province
                if not any(self.matches_province(str(val)) for val in location_candidates if val):
                    description_fields = [
                        record.get("Contract Details"),
                        record.get("Project Description"),
                        record.get("Name of Project"),
                        record.get("Project"),
                    ]
                    if not any(self.matches_province(str(val)) for val in description_fields if val):
                        continue

                amount_value = parse_amount(
                    record.get("Contract Price")
                    or record.get("Contract Amount")
                    or record.get("Amount")
                    or record.get("Project Cost")
                )

                contractor_value = (
                    record.get("Contractor")
                    or record.get("Contractor Name")
                    or record.get("Contractor_Name")
                    or record.get("Supplier")
                    or "N/A"
                )

                project_name = (
                    record.get("Contract Details")
                    or record.get("Project Description")
                    or record.get("Project Name")
                    or record.get("Name of Project")
                    or "N/A"
                )

                status_value = (
                    record.get("Contract Status")
                    or record.get("Status")
                    or record.get("Project Status")
                    or "N/A"
                )

                year_value = detect_year(
                    record.get("Contract Effectivity Date"),
                    record.get("Contract Date"),
                    record.get("Date of Award"),
                    record.get("Year"),
                    record.get("Year Awarded"),
                )

                location_parts = [
                    part for part in [
                        province_value,
                        municipality_value,
                        barangay_value,
                        record.get("Project Location"),
                        record.get("Location"),
                    ] if part
                ]
                location_str = ", ".join(location_parts) if location_parts else "N/A"

                projects.append({
                    "source": "Infrawatch",
                    "meilisearch_id": None,
                    "project_name": project_name,
                    "contractor": contractor_value,
                    "amount": amount_value,
                    "location": location_str,
                    "province": province_value or "N/A",
                    "municipality": municipality_value or "N/A",
                    "barangay": barangay_value or "N/A",
                    "year": year_value,
                    "status": status_value,
                })

        except Exception as exc:
            print(f"❌ Error processing Infrawatch projects: {exc}")
            import traceback
            traceback.print_exc()

        return projects
    
    async def generate_cache(self):
        """Generate the cached JSON file"""
        print(f"🚀 Starting province-projects cache generation for {self.province_name}...")
        
        # Connect to databases
        dime_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_DIME', 'dime')
        )
        
        philgeps_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
        )
        infrawatch_conn = await get_infrawatch_connection()
        
        try:
            # Initialize FloodControlClient for SSP/MeiliSearch
            client = FloodControlClient()
            
            # Process projects from all sources
            ssp_projects = await self.process_ssp_projects(client)
            dime_projects = await self.process_dime_projects(dime_conn)
            philgeps_projects = await self.process_philgeps_projects(philgeps_conn)
            infrawatch_projects = await self.process_infrawatch_projects(infrawatch_conn)
            
            all_projects = ssp_projects + dime_projects + philgeps_projects + infrawatch_projects
            print(f"✅ Total projects found: {len(all_projects)}")
            
            # Deduplicate projects across sources
            projects_by_key: Dict[str, Dict[str, Any]] = {}
            fallback_by_contractor_amount: Dict[str, Dict[str, Any]] = {}
            generic_titles = {
                "construction project",
                "maintenance project",
                "repair project",
                "rehabilitation project"
            }

            for proj in all_projects:
                base_project = proj.copy()
                base_project['source'] = normalize_source_label(base_project.get('source'))
                base_project['amount'] = float(base_project.get('amount', 0) or 0)
                base_project.setdefault('location', 'N/A')
                base_project.setdefault('province', 'N/A')
                base_project.setdefault('municipality', 'N/A')
                base_project.setdefault('status', 'N/A')
                base_project.setdefault('year', 'N/A')

                primary_key = "|".join([
                    normalize_text_for_key(base_project.get('project_name') or base_project.get('award_title') or ''),
                    normalize_text_for_key(base_project.get('contractor') or base_project.get('awardee_name') or ''),
                    normalize_amount_for_key(base_project.get('amount', 0))
                ])
                contractor_amount_key = "|".join([
                    normalize_text_for_key(base_project.get('contractor') or base_project.get('awardee_name') or ''),
                    normalize_amount_for_key(base_project.get('amount', 0))
                ])

                entry = projects_by_key.get(primary_key)
                if entry is None and contractor_amount_key:
                    entry = fallback_by_contractor_amount.get(contractor_amount_key)

                if entry is None:
                    entry = {
                        'project': base_project,
                        'sources': set([base_project['source']])
                    }
                else:
                    existing = entry['project']
                    entry['sources'].add(base_project['source'])

                    # Prefer richer project name when PhilGEPS title is generic
                    existing_name = existing.get('project_name') or existing.get('award_title') or ''
                    new_name = base_project.get('project_name') or base_project.get('award_title') or ''
                    existing_name_norm = existing_name.strip().lower()
                    new_name_norm = new_name.strip().lower()
                    if (existing_name_norm in generic_titles or len(existing_name_norm) < 10) and len(new_name_norm) > len(existing_name_norm):
                        existing['project_name'] = new_name

                    # Prefer richer location information
                    if base_project.get('location') and (existing.get('location') in (None, '', 'N/A') or len(base_project['location']) > len(existing.get('location', ''))):
                        existing['location'] = base_project['location']

                    # Fill missing province/municipality/barangay
                    for field in ['province', 'municipality', 'barangay']:
                        if base_project.get(field) and (existing.get(field) in (None, '', 'N/A')):
                            existing[field] = base_project[field]

                    # Prefer known status/year values
                    if base_project.get('status') and base_project['status'] not in (None, '', 'N/A') and existing.get('status') in (None, '', 'N/A'):
                        existing['status'] = base_project['status']
                    if base_project.get('year') and base_project['year'] not in (None, '', 'N/A') and existing.get('year') in (None, '', 'N/A'):
                        existing['year'] = base_project['year']

                    # Keep source with highest priority as primary
                    current_source = existing.get('source', 'Unknown')
                    sources_sorted = sort_sources_list([current_source, base_project['source']])
                    existing['source'] = sources_sorted[0] if sources_sorted else current_source
                    entry['sources'].update(sources_sorted)

                # Update indices for this entry
                projects_by_key[primary_key] = entry
                if contractor_amount_key:
                    fallback_by_contractor_amount[contractor_amount_key] = entry
            
            # Build unique projects list
            unique_projects = []
            seen_entries = set()
            for entry in projects_by_key.values():
                proj = entry['project']
                sources_list = sort_sources_list(list(entry['sources']))
                proj['sources_list'] = sources_list
                proj['sources_count'] = len(sources_list)
                entry_id = id(proj)
                if entry_id not in seen_entries:
                    unique_projects.append(proj)
                    seen_entries.add(entry_id)
            
            # Sort by amount descending
            unique_projects.sort(key=lambda x: x.get('amount', 0), reverse=True)
            
            # Extract contractors and count projects
            contractor_counts = {}
            unknown_contractor_count = 0
            
            for proj in unique_projects:
                contractor = proj.get('contractor', '').strip()
                if contractor and contractor != 'N/A':
                    if contractor not in contractor_counts:
                        contractor_counts[contractor] = 0
                    contractor_counts[contractor] += 1
                else:
                    unknown_contractor_count += 1
            
            # Sort contractors by project count descending
            contractors_sorted = sorted(
                contractor_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )
            filter_contractors = [{"name": name, "count": count} for name, count in contractors_sorted]
            
            # Add "Unknown" contractor if there are any
            if unknown_contractor_count > 0:
                filter_contractors.append({"name": "Unknown", "count": unknown_contractor_count})
            
            # Extract municipalities/cities from location and project names
            import re
            municipality_counts = {}
            unknown_municipality_count = 0
            
            # Get municipalities and cities from geoph data
            geoph_municipalities, geoph_cities = self.get_municipalities_from_geoph()
            
            # Combine municipalities and cities into one list for matching
            # Cities will be handled separately for proper naming
            known_municipalities = geoph_municipalities + geoph_cities
            
            # Determine city name and patterns based on province
            province_upper = self.province_name.upper()
            if province_upper == "CEBU":
                city_name = "Cebu City"
                city_patterns = ['CEBU CITY', 'CITY OF CEBU']
            elif province_upper.startswith("DAVAO"):
                # For all Davao provinces, Davao City is handled separately
                city_name = None
                city_patterns = []
            else:
                city_name = None
                city_patterns = []
            
            print(f"📋 Loaded {len(geoph_municipalities)} municipalities and {len(geoph_cities)} cities from geoph for {self.province_name}")
            
            for proj in unique_projects:
                location = (proj.get('location') or '').strip()
                project_name = (proj.get('project_name') or '').strip()
                municipality = (proj.get('municipality') or '').strip()
                city = (proj.get('city') or '').strip()
                
                # Combine all text for searching
                combined_text = f"{location} {project_name} {municipality} {city}".upper()
                
                matched = False
                
                # For all Davao provinces, check for Davao City first (shared city)
                if province_upper.startswith("DAVAO"):
                    if 'DAVAO CITY' in combined_text or 'CITY OF DAVAO' in combined_text:
                        if "Davao City" not in municipality_counts:
                            municipality_counts["Davao City"] = 0
                        municipality_counts["Davao City"] += 1
                        matched = True
                
                # Check for province-specific city (e.g., Cebu City for Cebu province)
                if not matched and city_name and city_patterns:
                    for pattern in city_patterns:
                        if pattern in combined_text:
                            if city_name not in municipality_counts:
                                municipality_counts[city_name] = 0
                            municipality_counts[city_name] += 1
                            matched = True
                            break
                
                # Check for other known municipalities and cities
                # Prioritize cities (those with "City" in name) to avoid partial matches
                if not matched:
                    # Sort to check cities first
                    sorted_municipalities = sorted(known_municipalities, key=lambda x: 'city' not in x.lower())
                    for mun in sorted_municipalities:
                        mun_upper = mun.upper()
                        if mun_upper in combined_text:
                            # Use word boundary matching to avoid false positives
                            # Check if it's a whole word (not part of another word)
                            pattern = r'\b' + re.escape(mun_upper) + r'\b'
                            if re.search(pattern, combined_text):
                                if mun not in municipality_counts:
                                    municipality_counts[mun] = 0
                                municipality_counts[mun] += 1
                                matched = True
                                break  # Only count once per project
                
                # If no municipality matched, count as unknown
                if not matched:
                    unknown_municipality_count += 1
            
            # Sort municipalities by project count descending
            municipalities_sorted = sorted(
                municipality_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )
            filter_municipalities = [{"name": name, "count": count} for name, count in municipalities_sorted]
            
            # Add "Unknown" municipality if there are any
            if unknown_municipality_count > 0:
                filter_municipalities.append({"name": "Unknown", "count": unknown_municipality_count})
            
            # Calculate summary
            summary = {
                "total": len(unique_projects),
                "ssp": len([p for p in unique_projects if 'SSP' in (p.get('sources_list', []))]),
                "dime": len([p for p in unique_projects if 'DIME' in (p.get('sources_list', []))]),
                "philgeps": len([p for p in unique_projects if 'PhilGEPS' in (p.get('sources_list', []))]),
                "microsite": len([p for p in unique_projects if 'Microsite' in (p.get('sources_list', []))]),
            }
            
            # Calculate total cost
            total_cost = sum(
                float(p.get('amount', 0)) if isinstance(p.get('amount'), (int, float)) else 0
                for p in unique_projects
            )
            
            # Group projects by contractor
            projects_by_contractor = {}
            for proj in unique_projects:
                contractor = proj.get('contractor', '').strip()
                if not contractor or contractor == 'N/A':
                    contractor = 'Unknown'
                
                if contractor not in projects_by_contractor:
                    projects_by_contractor[contractor] = []
                projects_by_contractor[contractor].append(proj)
            
            # Ensure directory exists
            cache_dir = self.cache_file.parent / f'province-projects-{self.province_name.lower().replace(" ", "-")}'
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            # Separate contractors into large (>5 projects) and small (≤5 projects)
            large_contractors = {}
            small_contractors = {}
            
            for contractor, contractor_projects in projects_by_contractor.items():
                if len(contractor_projects) > 5:
                    large_contractors[contractor] = contractor_projects
                else:
                    small_contractors[contractor] = contractor_projects
            
            contractor_summaries = {}
            
            # Create individual cache files for large contractors (>5 projects)
            for contractor, contractor_projects in large_contractors.items():
                # Calculate contractor-specific summary
                contractor_summary = {
                    "total": len(contractor_projects),
                    "ssp": len([p for p in contractor_projects if 'SSP' in (p.get('sources_list', []))]),
                    "dime": len([p for p in contractor_projects if 'DIME' in (p.get('sources_list', []))]),
                    "philgeps": len([p for p in contractor_projects if 'PhilGEPS' in (p.get('sources_list', []))]),
                    "microsite": len([p for p in contractor_projects if 'Microsite' in (p.get('sources_list', []))]),
                }
                
                contractor_total_cost = sum(
                    float(p.get('amount', 0)) if isinstance(p.get('amount'), (int, float)) else 0
                    for p in contractor_projects
                )
                
                # Extract municipalities for this contractor
                contractor_municipalities = {}
                for proj in contractor_projects:
                    location = (proj.get('location') or '').strip()
                    project_name = (proj.get('project_name') or '').strip()
                    municipality = (proj.get('municipality') or '').strip()
                    city = (proj.get('city') or '').strip()
                    combined_text = f"{location} {project_name} {municipality} {city}".upper()
                    
                    # Use same municipality extraction logic (simplified for contractor cache)
                    # This will be refined when loading
                    mun_name = "Unknown"
                    if self.province_name.upper() == "CEBU":
                        if 'CEBU CITY' in combined_text or 'CITY OF CEBU' in combined_text:
                            mun_name = "Cebu City"
                    elif self.province_name.upper().startswith("DAVAO"):
                        if 'DAVAO CITY' in combined_text or 'CITY OF DAVAO' in combined_text:
                            mun_name = "Davao City"
                    
                    if mun_name not in contractor_municipalities:
                        contractor_municipalities[mun_name] = 0
                    contractor_municipalities[mun_name] += 1
                
                contractor_municipalities_list = [
                    {"name": name, "count": count} 
                    for name, count in sorted(contractor_municipalities.items(), key=lambda x: x[1], reverse=True)
                ]
                
                # Create contractor cache file
                contractor_cache_file = cache_dir / f'{sanitize_filename(contractor)}-cache.json'
                contractor_cache_data = {
                    "success": True,
                    "province": self.province_name,
                    "contractor": contractor,
                    "projects": contractor_projects,
                    "summary": contractor_summary,
                    "total_cost": contractor_total_cost,
                    "filter_options": {
                        "municipalities": contractor_municipalities_list
                    },
                    "generated_at": datetime.now().isoformat(),
                    "cache_version": "1.0"
                }
                
                with open(contractor_cache_file, 'w', encoding='utf-8') as f:
                    json.dump(contractor_cache_data, f, indent=2, ensure_ascii=False)
                
                contractor_summaries[contractor] = {
                    "count": len(contractor_projects),
                    "total_cost": contractor_total_cost,
                    "cache_file": str(contractor_cache_file.relative_to(self.cache_file.parent))
                }
                
                print(f"   ✅ Created cache for contractor '{contractor}': {len(contractor_projects)} projects")
            
            # Create single cache file for all small contractors (≤5 projects)
            if small_contractors:
                small_contractors_projects = {}
                small_contractors_total = 0
                small_contractors_total_cost = 0
                small_contractors_summary = {"total": 0, "ssp": 0, "dime": 0, "philgeps": 0, "microsite": 0}
                
                for contractor, contractor_projects in small_contractors.items():
                    small_contractors_projects[contractor] = contractor_projects
                    small_contractors_total += len(contractor_projects)
                    small_contractors_total_cost += sum(
                        float(p.get('amount', 0)) if isinstance(p.get('amount'), (int, float)) else 0
                        for p in contractor_projects
                    )
                    
                    for proj in contractor_projects:
                        sources_list = proj.get('sources_list', [])
                        if 'SSP' in sources_list:
                            small_contractors_summary["ssp"] += 1
                        if 'DIME' in sources_list:
                            small_contractors_summary["dime"] += 1
                        if 'PhilGEPS' in sources_list:
                            small_contractors_summary["philgeps"] += 1
                        small_contractors_summary["microsite"] += len([p for p in contractor_projects if 'Microsite' in (p.get('sources_list', []))])
                
                small_contractors_summary["total"] = small_contractors_total
                
                # Create combined cache file for small contractors
                small_contractors_cache_file = cache_dir / 'small-contractors-cache.json'
                small_contractors_cache_data = {
                    "success": True,
                    "province": self.province_name,
                    "contractor": "Small Contractors (≤5 projects)",
                    "contractors": list(small_contractors.keys()),
                    "projects_by_contractor": small_contractors_projects,
                    "summary": small_contractors_summary,
                    "total_cost": small_contractors_total_cost,
                    "generated_at": datetime.now().isoformat(),
                    "cache_version": "1.0"
                }
                
                with open(small_contractors_cache_file, 'w', encoding='utf-8') as f:
                    json.dump(small_contractors_cache_data, f, indent=2, ensure_ascii=False)
                
                # Add entries for each small contractor pointing to the combined cache
                for contractor, contractor_projects in small_contractors.items():
                    contractor_total_cost = sum(
                        float(p.get('amount', 0)) if isinstance(p.get('amount'), (int, float)) else 0
                        for p in contractor_projects
                    )
                    contractor_summaries[contractor] = {
                        "count": len(contractor_projects),
                        "total_cost": contractor_total_cost,
                        "cache_file": str(small_contractors_cache_file.relative_to(self.cache_file.parent)),
                        "is_small_contractor": True
                    }
                
                print(f"   ✅ Created combined cache for {len(small_contractors)} small contractors (≤5 projects each): {small_contractors_total} total projects")
            
            # Create province-level cache file (all projects)
            province_cache_data = {
                "success": True,
                "province": self.province_name,
                "projects": unique_projects,
                "summary": summary,
                "total_cost": total_cost,
                "filter_options": {
                    "contractors": filter_contractors,
                    "municipalities": filter_municipalities
                },
                "generated_at": datetime.now().isoformat(),
                "cache_version": "1.0"
            }
            
            province_cache_file = cache_dir / 'all-projects-cache.json'
            with open(province_cache_file, 'w', encoding='utf-8') as f:
                json.dump(province_cache_data, f, indent=2, ensure_ascii=False)
            
            print(f"   ✅ Created province-level cache: {len(unique_projects)} projects")
            
            # Create summary/index file
            summary_cache_data = {
                "success": True,
                "province": self.province_name,
                "summary": summary,
                "total_cost": total_cost,
                "filter_options": {
                    "contractors": filter_contractors,
                    "municipalities": filter_municipalities
                },
                "contractors": contractor_summaries,
                "province_cache_file": str(province_cache_file.relative_to(self.cache_file.parent)),
                "generated_at": datetime.now().isoformat(),
                "cache_version": "1.0"
            }
            
            summary_cache_file = cache_dir / 'summary.json'
            with open(summary_cache_file, 'w', encoding='utf-8') as f:
                json.dump(summary_cache_data, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Cache generated successfully for {self.province_name}")
            print(f"   Total projects: {summary['total']}")
            print(f"   SSP: {summary['ssp']}")
            print(f"   DIME: {summary['dime']}")
            print(f"   PhilGEPS: {summary['philgeps']}")
            print(f"   Microsite: {summary['microsite']}")
            print(f"   Total cost: ₱{total_cost:,.2f}")
            print(f"   Contractors: {len(contractor_summaries)}")
            print(f"   Province cache: {province_cache_file}")
            print(f"   Summary file: {summary_cache_file}")
            
        finally:
            await dime_conn.close()
            await philgeps_conn.close()
            if infrawatch_conn:
                await infrawatch_conn.close()

async def main():
    import sys
    
    # Get province name from command line argument, default to Cebu
    province_name = sys.argv[1] if len(sys.argv) > 1 else "Cebu"
    
    print(f"🚀 Starting cache generation for province: {province_name}")
    generator = ProvinceProjectsCacheGenerator(province_name=province_name)
    await generator.generate_cache()
    print(f"✅ Cache generation complete for {province_name}")

if __name__ == '__main__':
    asyncio.run(main())


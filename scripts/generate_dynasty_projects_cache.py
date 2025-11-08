#!/usr/bin/env python3
"""
Generate cached JSON for dynasty-projects API.
This script fixes the matching logic and generates a cached JSON file.
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

import asyncpg
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from flood_client import FloodControlClient
from infrawatch_postgres_client import get_infrawatch_connection

# Load environment variables
load_dotenv()

class DynastyProjectsCacheGenerator:
    """Generate cached JSON for dynasty-projects"""
    
    def __init__(self):
        self.cache_file = Path(__file__).parent.parent / 'static' / 'data' / 'dynasty-projects-cache.json'
        self.config_file = Path(__file__).parent.parent / 'dynasty-projects-config.json'
        self.districts_file = Path(__file__).parent.parent / 'districts.json'
        cpu_count = os.cpu_count() or 4
        self.max_workers = min(24, max(1, cpu_count))
        self.verbose = os.getenv('DYNASTY_CACHE_VERBOSE', '0') == '1'
        self.chart_limit = 200

    def _log(self, message: str, *, verbose_only: bool = False) -> None:
        if verbose_only and not self.verbose:
            return
        print(message)

    def _atomic_write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + '.tmp')
        with open(temp_path, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
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
        primary_amount = DynastyProjectsCacheGenerator._normalize_amount_for_key(merged.get('amount'))
        incoming_amount = DynastyProjectsCacheGenerator._normalize_amount_for_key(incoming.get('amount'))
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

    def _process_dime_chunk(self, projects_chunk: List[Any], congressmen_data: Dict, districts_data: Dict) -> List[Dict]:
        chunk_results: List[Dict] = []
        for proj in projects_chunk:
            proj_name = (proj.get('project_name') or '').upper()
            proj_province = (proj.get('province') or '').upper()
            proj_city = (proj.get('city') or '').upper()
            proj_barangay = (proj.get('barangay') or '').upper()
            combined_text = f'{proj_name} {proj_province} {proj_city} {proj_barangay}'

            contractor_str = ''
            contractors_field = proj.get('contractors')
            if isinstance(contractors_field, list):
                contractor_str = ', '.join(contractors_field).upper()
            elif contractors_field:
                contractor_str = str(contractors_field).upper()
            combined_text = f'{combined_text} {contractor_str}'

            matches = []
            for cm_name, cm_data in congressmen_data.items():
                cm_name_result, match_type_result, match_score_result = self.match_project(
                    combined_text,
                    cm_data,
                    districts_data,
                    contractor_str
                )
                if cm_name_result and match_score_result > 0:
                    matches.append((cm_name_result, match_type_result, match_score_result))

            if not matches:
                continue

            location_parts = []
            if proj.get('province'):
                location_parts.append(proj['province'])
            if proj.get('city'):
                location_parts.append(proj['city'])
            if proj.get('barangay'):
                location_parts.append(proj['barangay'])
            location_str = ', '.join(location_parts).strip() or "N/A"

            amount = float(proj['cost']) if proj['cost'] else 0

            for matched_congressman, match_type, match_score in matches:
                if matched_congressman == "Ferdinand Martin Gomez Romualdez":
                    print(f"✅ Matched Romualdez (DIME): {proj['project_name'][:80]}... -> {location_str} [{match_type}:{match_score}]")
                chunk_results.append({
                    "congressman": matched_congressman,
                    "source": self._normalize_source_label("DIME"),
                    "meilisearch_id": proj.get('meilisearch_id'),
                    "project_name": proj['project_name'] or "N/A",
                    "contractor": contractor_str if contractor_str else "N/A",
                    "amount": amount,
                    "location": location_str,
                    "year": proj['date_started'].year if proj['date_started'] else "N/A",
                    "status": proj['status'] or "N/A",
                    "match_type": match_type,
                    "match_score": match_score,
                    "is_city_wide": (match_score == 1 and match_type == "district")
                })
        return chunk_results

    def _process_philgeps_chunk(self, contracts_chunk: List[Any], congressmen_data: Dict, districts_data: Dict) -> List[Dict]:
        chunk_results: List[Dict] = []
        for contract in contracts_chunk:
            award_title = (contract.get('award_title') or '').upper()
            area_of_delivery = (contract.get('area_of_delivery') or '').upper()
            awardee_name = (contract.get('awardee_name') or '').upper()
            combined_text = f'{award_title} {area_of_delivery} {awardee_name}'

            best_match = None
            best_score = 0
            for cm_name, cm_data in congressmen_data.items():
                cm_name_result, match_type_result, match_score_result = self.match_project(
                    combined_text,
                    cm_data,
                    districts_data,
                    awardee_name
                )
                if cm_name_result and match_score_result > best_score:
                    best_match = (cm_name_result, match_type_result, match_score_result)
                    best_score = match_score_result

            if not best_match:
                continue

            matched_congressman, match_type, match_score = best_match
            if matched_congressman == "Ferdinand Martin Gomez Romualdez":
                print(f"✅ Matched Romualdez (PhilGEPS): {contract.get('award_title','')[:80]}... -> {area_of_delivery} [{match_type}:{match_score}]")

            chunk_results.append({
                "congressman": matched_congressman,
                "source": self._normalize_source_label("PhilGEPS"),
                "meilisearch_id": contract.get('meilisearch_id'),
                "project_name": contract['award_title'] or "N/A",
                "contractor": contract['awardee_name'] or "N/A",
                "amount": float(contract['contract_amount']) if contract['contract_amount'] else 0,
                "location": contract['area_of_delivery'] or "N/A",
                "year": contract['award_date'].year if contract['award_date'] else "N/A",
                "status": contract['award_status'] or "N/A",
                "match_type": match_type,
                "match_score": match_score,
                "is_city_wide": (match_score == 1 and match_type == "district")
            })
        return chunk_results

    def _process_infrawatch_chunk(self, rows_chunk: List[Any], congressmen_data: Dict, districts_data: Dict) -> List[Dict]:
        chunk_results: List[Dict] = []
        for row in rows_chunk:
            if isinstance(row, dict):
                record = row.get("data")
            else:
                record = row["data"] if "data" in row else row[0]
            if isinstance(record, str):
                try:
                    record = json.loads(record)
                except json.JSONDecodeError:
                    continue
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

            matches = []
            for cm_name, cm_data in congressmen_data.items():
                cm_name_result, match_type_result, match_score_result = self.match_project(
                    combined_text,
                    cm_data,
                    districts_data,
                    contractor
                )
                if cm_name_result and match_score_result > 0:
                    matches.append((cm_name_result, match_type_result, match_score_result))

            if not matches:
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

            for matched_congressman, match_type, match_score in matches:
                if matched_congressman == "Ferdinand Martin Gomez Romualdez":
                    print(f"✅ Matched Romualdez (Infrawatch): {(record.get('Contract Details') or record.get('Project Description') or '')[:80]}... -> {(record.get('Implementing Agency') or record.get('Project Location') or 'N/A')} [{match_type}:{match_score}]")
                chunk_results.append({
                    "congressman": matched_congressman,
                    "source": self._normalize_source_label("Infrawatch"),
                    "meilisearch_id": None,
                    "project_name": record.get("Contract Details") or record.get("Project Description") or "N/A",
                    "contractor": contractor_raw or "N/A",
                    "amount": amount,
                    "location": record.get("Implementing Agency") or record.get("Project Location") or "N/A",
                    "year": None,
                    "status": record.get("Contract Status") or "N/A",
                    "match_type": match_type,
                    "match_score": match_score,
                    "is_city_wide": (match_score == 1 and match_type == "district")
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
        
        return config_data, districts_data
    
    async def get_congressmen_data(self, dynasty_conn, config_data: Dict, districts_data: Dict, political_dynasties_available: bool) -> Dict:
        """Get congressmen data from database"""
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
            # STRICT: No fallbacks - if we don't have municipalities from districts.json, we can't match
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
                    # CRITICAL: Only get municipalities for THIS district_number
                    # NO FALLBACK - if municipalities_map is empty or district_number doesn't match, district_municipalities stays empty
                    for mun_key, mun_district in municipalities_map.items():
                        if mun_district and mun_district.upper() == config_district_number.upper():
                            district_municipalities.append(mun_key)
            
            name_key = _name_key(person['first_name'], person['last_name'])
            if political_dynasties_available:
                direct_contractors = contractor_lookup.get(name_key, [])
            
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
                # Remove parenthetical segments
                patterns.add(re.sub(r'\([^)]*\)', '', base_upper).strip())
                # Split on common separators
                for part in re.split(r'[\\/]', base_upper):
                    part = part.strip()
                    if len(part) >= 3:
                        patterns.add(part)
                # Collapse multiple spaces
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
                # If verified_patterns provided, prefer matches that include them, but otherwise include everything
                if verified_patterns:
                    upper_name = company_name.upper()
                    if not any(pattern.upper() in upper_name for pattern in verified_patterns):
                        # Allow inclusion even if pattern not found, to keep politicontractors coverage
                        pass
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
            # (Party-list representatives like Gardiola match via contractors, not districts)
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
                "district_municipalities": district_municipalities,  # ONLY municipalities from districts.json for this district
                "district_number": config_district_number,
                "is_city_district": config_is_city_district,
                "contractors": contractor_names,
                "contractor_patterns": contractor_patterns,
                "contractor_exclusions": contractor_exclusions,
                "barangays": barangays,
            }
        
        return congressmen_data
    
    def match_project(self, project_text: str, congressman_data: Dict, districts_data: Dict, contractor_name: str = '') -> tuple[Optional[str], Optional[str], int]:
        """
        Match a project to a congressman.
        Returns: (congressman_name, match_type, match_score) or (None, None, 0)
        
        SIMPLE LOGIC:
        1. Check barangay match (highest priority)
        2. Check contractor match (for Gardiola/MBB and Co/Sunwest)
        3. Check if BOTH district identifier AND municipality from that district are in project text
        4. If both found, it's a match
        5. Exclude cities with same name as province (e.g., "Quezon City" != "Quezon Province")
        """
        combined_text = project_text.upper()
        congressman_name = congressman_data['name']

        def contains_word(text: str, word: str) -> bool:
            if not word:
                return False
            pattern = rf'(?<!\w){re.escape(word)}(?!\w)'
            return re.search(pattern, text) is not None
        
        # 1. Check barangay match (highest priority)
        # For city districts, if a barangay is mentioned, it MUST be in the 2nd District list
        if congressman_data.get('barangays') and congressman_data.get('is_city_district'):
            # Get valid barangays from districts.json
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
            
            # Also use barangays from congressman_data as fallback
            if not valid_barangays:
                valid_barangays = [b.upper() for b in congressman_data.get('barangays', []) if b]
            
            # Check if project mentions a barangay
            if any(indicator in combined_text for indicator in ['BARANGAY', 'BRGY', 'BRG', 'BR.', 'BRGY.']):
                # Check if any valid barangay is mentioned
                valid_barangay_found = False
                for valid_barangay in valid_barangays:
                    if contains_word(combined_text, valid_barangay):
                        valid_barangay_found = True
                        break
                
                # If barangay indicator exists but no valid barangay found, check for known invalid ones
                if not valid_barangay_found:
                    # Common non-2nd-district barangays that should be excluded
                    invalid_barangays = ['TALISAYAN', 'LABUAN', 'AYALA', 'SINUNUC', 'BALIWASAN', 'PASONANCA', 'SINUBONG', 'RECODO', 'SAN RAMON', 'MAASIN', 'MENZI', 'CULIANAN']
                    for invalid_barangay in invalid_barangays:
                        if contains_word(combined_text, invalid_barangay):
                            # Check if it's not a substring of a valid barangay
                            is_valid_substring = any(invalid_barangay in valid_b or valid_b in invalid_barangay for valid_b in valid_barangays)
                            if not is_valid_substring:
                                return (None, None, 0)  # Exclude - barangay not in 2nd District
                    
                    # If barangay indicator exists but neither valid nor known invalid barangay found,
                    # exclude to be safe (better to have fewer matches than wrong matches)
                    return (None, None, 0)
                
                # If valid barangay found, return match
                if valid_barangay_found:
                    return (congressman_name, "district", 100)
        
        # For non-city districts, check barangay matches
        elif congressman_data.get('barangays'):
            for barangay in congressman_data['barangays']:
                if barangay and contains_word(combined_text, barangay.upper()):
                    return (congressman_name, "district", 100)
        
        # 2. Check contractor match EARLY (for party-list representatives like Gardiola and Co)
        # This must happen before district checks, as some congressmen have no districts
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

            # Special-case Gonzales legacy rule
            if 'GONZALES' in congressman_name.upper() and 'A.D. GONZALES' in contractor_name_upper:
                if not _contractor_is_excluded(contractor_name_upper):
                    return (congressman_name, "contractor", 50)
            
            # Dynamic contractor pattern matching
            for pattern in contractor_patterns:
                pattern_upper = pattern.upper()
                if not pattern_upper or len(pattern_upper) < 3:
                    continue

                # Skip if excluded
                if _contractor_is_excluded(contractor_name_upper):
                    break

                # Direct substring match
                if pattern_upper in contractor_name_upper:
                    return (congressman_name, "contractor", 50)

                # Normalized comparison (remove punctuation, collapse spaces)
                normalized_pattern = _normalize_for_match(pattern)
                if normalized_pattern and normalized_pattern in normalized_candidate:
                    return (congressman_name, "contractor", 50)
                    
        # If contractor name not provided (e.g., Infrawatch text only), fall back to searching the combined text
        if contractor_patterns and not contractor_name:
            normalized_text = _normalize_for_match(combined_text)
            for pattern in contractor_patterns:
                normalized_pattern = _normalize_for_match(pattern)
                if normalized_pattern and normalized_pattern in normalized_text:
                    if not _contractor_is_excluded(normalized_text):
                        return (congressman_name, "contractor", 40)

        if contractors:
            # Legacy handling for specific patterns
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
                # No explicit contractor name on the record, attempt to match patterns in combined text
                normalized_text = _normalize_for_match(combined_text)
                for contractor in contractors:
                    contractor_upper = contractor.upper()
                    for pattern in ['SUNWEST', 'ROVING PREMIER', 'VIRKAR', 'GARDIOLA', 'NEWINGTON', 'S-ANG', 'JSG']:
                        if pattern in contractor_upper and pattern in normalized_text:
                            if not _contractor_is_excluded(normalized_text):
                                return (congressman_name, "contractor", 40)
        
        # 3. Get district identifier (province or city name)
        # If no district identifier, return None (unless we already matched via contractor above)
        district_identifier = None
        if congressman_data.get('provinces') and congressman_data['provinces']:
            district_identifier = congressman_data['provinces'][0].upper()
        
        if not district_identifier:
            return (None, None, 0)
        
        # 4. Exclusion check: If district identifier is a province name, exclude if the city with same name is mentioned
        # Example: "Quezon" (province) should NOT match "Quezon City" (Metro Manila)
        if district_identifier == "QUEZON":
            if contains_word(combined_text, "QUEZON CITY"):
                return (None, None, 0)  # This is Quezon City, not Quezon Province
        
        # 5. Pre-check: If project mentions a municipality from a DIFFERENT district, exclude it
        # This prevents Palompon (3rd District) from matching Romualdez (1st District)
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
                    # If municipality name is identical to the province name, skip exclusion checks to avoid false positives
                    if mun_key_upper == province.upper():
                        continue
                    # Use word boundary check to avoid partial matches (e.g., "Palompon" in "Palompon-Isabel")
                    # Check if municipality is mentioned as a whole word or with hyphen
                    if contains_word(combined_text, mun_key_upper):
                        # Check if it belongs to a DIFFERENT district
                        if mun_district and mun_district.upper() != congressman_district:
                            # Municipality from different district is mentioned - exclude!
                            return (None, None, 0)
        
        # 6. Check if district identifier is in project text
        if not contains_word(combined_text, district_identifier):
            return (None, None, 0)
        
        # 7. For city districts (like Zamboanga City), match all city projects
        # BUT only if no barangay indicator was found, or if a valid barangay was found
        # STRICT RULE: If project mentions "ROAD" (case insensitive), require "CITY" in project text
        if congressman_data.get('is_city_district') and district_identifier:
            # Check if barangay indicator exists
            has_barangay_indicator = any(indicator in combined_text for indicator in ['BARANGAY', 'BRGY', 'BRG', 'BR.', 'BRGY.'])
            
            if has_barangay_indicator:
                # If barangay indicator exists, we already checked for valid/invalid barangays above
                # If we reach here, it means no valid barangay was found and no invalid one was detected
                # In this case, we should NOT match (better to exclude uncertain matches)
                return (None, None, 0)
            
            # STRICT RULE: If project mentions "ROAD" (case insensitive), require "CITY" in project text
            # This prevents generic matches like "Manila Road" from matching Manila city councilors
            if re.search(r'\bROAD\b', combined_text, re.IGNORECASE):
                if 'CITY' not in combined_text:
                    # Project mentions ROAD but not CITY - exclude to avoid false matches
                    return (None, None, 0)
            
            # No barangay indicator - city-wide match is OK, but with lower score (1)
            # This ONLY applies to city districts
            if district_identifier in combined_text:
                return (congressman_name, "district", 1)  # Low score for city-wide matches
        
        # 8. For province districts: Check if any municipality from that district is in project text
        # For province districts, we MUST have a valid municipality match - no city-wide fallback
        district_municipalities = congressman_data.get('district_municipalities', [])
        if district_municipalities:
            for mun in district_municipalities:
                if mun and contains_word(combined_text, mun.upper()):
                    # CRITICAL: Check for naming conflicts
                    # If municipality name matches province/city name, require VERY strict validation
                    # Example: "Leyte" municipality in Leyte province - need more context
                    mun_upper = mun.upper()
                    provinces = congressman_data.get('provinces', [])
                    
                    # Check if municipality name matches the province name
                    is_naming_conflict = False
                    for prov in provinces:
                        if prov and mun_upper == prov.upper():
                            is_naming_conflict = True
                            break
                    
                    if is_naming_conflict:
                        # STRICT: For naming conflicts, require explicit "MUNICIPALITY" or "MUNICIPAL" keyword
                        # This prevents "Leyte province" from matching "Leyte municipality"
                        has_municipality_keyword = any(keyword in combined_text for keyword in [
                            'MUNICIPALITY OF ' + mun_upper,
                            'MUNICIPAL ' + mun_upper,
                            'MUNICIPIO',
                            'LGU-' + mun_upper,
                            'LGU ' + mun_upper
                        ])
                        
                        if not has_municipality_keyword:
                            # Log this for analysis
                            print(f"    ⚠️  Skipping potential false match: '{mun}' (naming conflict with province/city)")
                            continue  # Skip this municipality, check others
                    
                    # Found BOTH district identifier AND municipality from that district - match!
                    return (congressman_name, "district", 100)
        
        # For province districts, if we reach here without a municipality match, exclude it
        # (Only city districts allow city-wide matches)
        if not congressman_data.get('is_city_district'):
            return (None, None, 0)
        
        return (None, None, 0)
    
    async def process_projects(self, dynasty_conn, dime_conn, philgeps_conn, infrawatch_conn, congressmen_data: Dict, districts_data: Dict) -> List[Dict]:
        """Process projects from all databases"""
        all_projects = []
        
        # Process SSP/MeiliSearch projects
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
                    # Include contractor in combined text for matching
                    combined_text = f'{proj_desc} {proj_province} {proj_municipality} {proj_contractor}'

                    matches = []
                    for cm_name, cm_data in congressmen_data.items():
                        cm_name_result, match_type_result, match_score_result = self.match_project(
                            combined_text,
                            cm_data,
                            districts_data,
                            proj_contractor
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

                        # Handle ContractCost (can be string or float)
                        amount = 0
                        if proj.ContractCost:
                            if isinstance(proj.ContractCost, str):
                                amount = float(proj.ContractCost.replace(',', '').replace('₱', '').replace('PHP', '').strip() or 0)
                            else:
                                amount = float(proj.ContractCost)

                        for matched_congressman, match_type, match_score in matches:
                            if matched_congressman == "Ferdinand Martin Gomez Romualdez":
                                print(f"✅ Matched Romualdez (SSP): {proj.ProjectDescription[:80]}... -> {location_str} [{match_type}:{match_score}]")
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
        
        # Process DIME projects
        try:
            dime_projects = list(await dime_conn.fetch('''
                SELECT project_name, contractors, cost, province, city, barangay, status, date_started, meilisearch_id
                FROM projects
            '''))

            if dime_projects:
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
        except Exception as e:
            print(f"Error processing DIME projects: {e}")
        
        # Process PhilGEPS projects (similar logic)
        try:
            philgeps_projects = list(await philgeps_conn.fetch('''
                SELECT award_title, awardee_name, contract_amount, area_of_delivery, award_date, award_status, meilisearch_id
                FROM contracts
            '''))

            if philgeps_projects:
                philgeps_chunks = self._chunk_list(philgeps_projects, self.max_workers)
                loop = asyncio.get_running_loop()
                philgeps_tasks = [
                    loop.run_in_executor(
                        None,
                        functools.partial(self._process_philgeps_chunk, chunk, congressmen_data, districts_data)
                    )
                    for chunk in philgeps_chunks
                ]
                for result in await asyncio.gather(*philgeps_tasks):
                    all_projects.extend(result)
        except Exception as e:
            print(f"Error processing PhilGEPS projects: {e}")
        
        # Process Infrawatch projects (unmatched rows only)
        try:
            infrawatch_projects = await self.process_infrawatch_projects(infrawatch_conn, congressmen_data, districts_data)
            if infrawatch_projects:
                print(f"✅ Processed {len(infrawatch_projects)} Infrawatch projects")
                all_projects.extend(infrawatch_projects)
        except Exception as e:
            print(f"Error processing Infrawatch projects: {e}")
        
        return all_projects

    async def process_infrawatch_projects(self, infrawatch_conn, congressmen_data: Dict, districts_data: Dict) -> List[Dict]:
        """Match Infrawatch (unlinked) projects to congressmen."""
        projects: List[Dict] = []
        if not infrawatch_conn:
            return projects

        rows = list(await infrawatch_conn.fetch(
            """
            SELECT data
            FROM infrawatch_projects_rows
            WHERE philgeps_contract_id IS NULL
            """
        ))

        if not rows:
            return projects

        rows_chunks = self._chunk_list(rows, self.max_workers)
        loop = asyncio.get_running_loop()
        tasks = [
            loop.run_in_executor(
                None,
                functools.partial(self._process_infrawatch_chunk, chunk, congressmen_data, districts_data)
            )
            for chunk in rows_chunks
        ]

        for result in await asyncio.gather(*tasks):
            projects.extend(result)
        
        return projects
    
    async def generate_cache(self):
        """Generate the cached JSON file"""
        print("🚀 Starting dynasty-projects cache generation...")

        # Ensure latest districts and congressmen config are pulled from DB
        self._refresh_source_json()
        
        # Load config
        config_data, districts_data = await self.load_config()
        print(f"✅ Loaded config with {len(config_data.get('target_congressmen', []))} congressmen")
        
        # Connect to databases
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
        
        dime_conn = await asyncpg.connect(**{
            **common_db_kwargs,
            "database": os.getenv('POSTGRES_DB_DIME', 'dime')
        })
        
        philgeps_conn = await asyncpg.connect(**{
            **common_db_kwargs,
            "database": os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
        })

        infrawatch_conn = await get_infrawatch_connection()
        
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
            
            # Process projects
            all_projects = await self.process_projects(
                dynasty_conn,
                dime_conn,
                philgeps_conn,
                infrawatch_conn,
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
                projects_by_key[key]['congressmen'].add(proj.get('congressman', 'Unknown'))
            
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
                
                # 4. For city-type districts: penalize city-wide matches (no barangay) by -40
                # Check if this was a city-wide match using the is_city_wide flag
                is_city_wide = proj.get('is_city_wide', False)
                if is_city_wide:
                    # City-wide match - apply -40 penalty
                    current_score = max(0, current_score - 40)
                
                proj['match_score'] = current_score
                proj['sources_count'] = sources_count
                proj['sources_list'] = sorted(list(data['sources']))
                
                # Keep the original congressman from the first match for the combined cache
                # But preserve all congressmen in _all_congressmen for individual cache creation
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
                congressman = proj.get('congressman', 'Unknown')
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
            
            # Save combined cache file (for "all congressmen" view)
            cache_data = {
                "success": True,
                "projects": unique_projects,
                "summary": summary,
                "chart_data": chart_data,
                "chart_data_by_count": chart_data_by_count,
                "chart_data_by_cost": chart_data_by_cost,
                "chart_top10_by_count": chart_top10_by_count,
                "chart_top10_by_cost": chart_top10_by_cost,
                "dashboard_stats": dashboard_stats,
                "generated_at": datetime.now().isoformat(),
                "cache_version": "1.0"
            }
            
            # NOTE: Combined cache file generation disabled - file is too large and unused by application
            # Ensure directory exists
            # self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            #
            # with open(self.cache_file, 'w', encoding='utf-8') as f:
            #     json.dump(cache_data, f, indent=2, ensure_ascii=False)
            #
            # print(f"✅ Combined cache generated successfully: {self.cache_file}")
            # print(f"   Total projects: {summary['total']}")
            # print(f"   District matches: {summary['district_projects']}")
            # print(f"   Contractor matches: {summary['contractor_projects']}")
            # print(f"   Dashboard stats:")
            # print(f"     - Total cost: ₱{dashboard_stats['total_cost_all']:,.2f}")
            # print(f"     - District cost: ₱{dashboard_stats['district_cost']:,.2f}")
            # print(f"     - Contractor cost: ₱{dashboard_stats['contractor_cost']:,.2f}")

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
                if proj.get('congressman'):
                    all_congressmen_names.add(proj.get('congressman'))
            
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
                # Include projects where this congressman is in the _all_congressmen list (for projects matching multiple congressmen)
                congressman_projects = []
                for p in unique_projects:
                    # Check if this congressman matches the project
                    if p.get('congressman') == congressman_name:
                        # Create a copy with this congressman as the primary congressman
                        proj_copy = p.copy()
                        proj_copy['congressman'] = congressman_name
                        # Remove the internal _all_congressmen field before saving
                        proj_copy.pop('_all_congressmen', None)
                        congressman_projects.append(proj_copy)
                    elif congressman_name in p.get('_all_congressmen', []):
                        # This project matches multiple congressmen, create a copy for this one
                        proj_copy = p.copy()
                        proj_copy['congressman'] = congressman_name
                        # Remove the internal _all_congressmen field before saving
                        proj_copy.pop('_all_congressmen', None)
                        congressman_projects.append(proj_copy)
                
                # Calculate congressman-specific statistics
                congressman_total_cost = sum(parse_amount(p.get('amount', 0)) for p in congressman_projects)
                congressman_district_count = len([p for p in congressman_projects if p.get('match_type') == 'district'])
                congressman_contractor_count = len([p for p in congressman_projects if p.get('match_type') == 'contractor'])
                congressman_district_cost = sum(parse_amount(p.get('amount', 0)) for p in congressman_projects if p.get('match_type') == 'district')
                congressman_contractor_cost = sum(parse_amount(p.get('amount', 0)) for p in congressman_projects if p.get('match_type') == 'contractor')
                
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
            
        finally:
            await dynasty_conn.close()
            await dime_conn.close()
            await philgeps_conn.close()
            if infrawatch_conn:
                await infrawatch_conn.close()

async def main():
    generator = DynastyProjectsCacheGenerator()
    await generator.generate_cache()

if __name__ == '__main__':
    asyncio.run(main())


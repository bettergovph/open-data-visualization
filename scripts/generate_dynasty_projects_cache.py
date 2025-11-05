#!/usr/bin/env python3
"""
Generate cached JSON for dynasty-projects API.
This script fixes the matching logic and generates a cached JSON file.
"""

import asyncio
import asyncpg
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from flood_client import FloodControlClient

# Load environment variables
load_dotenv()

class DynastyProjectsCacheGenerator:
    """Generate cached JSON for dynasty-projects"""
    
    def __init__(self):
        self.cache_file = Path(__file__).parent.parent / 'static' / 'data' / 'dynasty-projects-cache.json'
        self.config_file = Path(__file__).parent.parent / 'dynasty-projects-config.json'
        self.districts_file = Path(__file__).parent.parent / 'districts.json'
        
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
    
    async def get_congressmen_data(self, dynasty_conn, config_data: Dict, districts_data: Dict) -> Dict:
        """Get congressmen data from database"""
        congressmen_data = {}
        processed_congressmen = set()
        
        target_congressmen = config_data.get('target_congressmen', [])
        
        for congressman_config in target_congressmen:
            first_name_pattern = congressman_config.get('first_name_pattern', '')
            last_name_pattern = congressman_config.get('last_name_pattern', '')
            display_name = congressman_config.get('display_name', '')
            config_province = congressman_config.get('province')
            config_district_number = congressman_config.get('district_number')
            config_is_city_district = congressman_config.get('is_city_district', False)
            congressman_id = congressman_config.get('id')
            
            # Get congressman from database
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
                f"%{first_name_pattern}%", 
                f"%{last_name_pattern}%",
                f"%{first_name_pattern}%{last_name_pattern}%",
                first_name_pattern
            )
            
            if not person:
                continue
            
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
            
            # Get contractors
            contractor_names = []
            direct_contractors = await dynasty_conn.fetch('''
                SELECT DISTINCT company_name, role
                FROM contractor_dynasty_matches
                WHERE dynasty_first_name = $1 AND dynasty_last_name = $2
            ''', person['first_name'], person['last_name'])
            
            verified_patterns = config_data.get('verified_contractors', {}).get('patterns', [])
            contractor_exclusions = {}
            for exclusion in config_data.get('verified_contractors', {}).get('exclusions', []):
                pattern = exclusion.get('pattern')
                exclude = exclusion.get('exclude')
                if pattern and exclude:
                    if pattern not in contractor_exclusions:
                        contractor_exclusions[pattern] = []
                    contractor_exclusions[pattern].append(exclude)
            
            for contractor in direct_contractors:
                company_name = contractor['company_name']
                if company_name and any(pattern.upper() in company_name.upper() for pattern in verified_patterns):
                    contractor_names.append(company_name)
            
            # Get party-list contractors
            party_lists = await dynasty_conn.fetch('''
                SELECT pl.party_list_number, pl.party_name
                FROM party_list_members plm
                JOIN party_list pl ON plm.party_list_number = pl.party_list_number
                WHERE plm.person_id = $1
            ''', person['id'])
            
            for pl in party_lists:
                pl_contractors = await dynasty_conn.fetch('''
                    SELECT DISTINCT cdm.company_name, cdm.role
                    FROM party_list_members plm2
                    JOIN political_dynasties pd ON plm2.person_id = pd.id
                    JOIN contractor_dynasty_matches cdm ON cdm.dynasty_first_name = pd.first_name 
                                                           AND cdm.dynasty_last_name = pd.last_name
                    WHERE plm2.party_list_number = $1
                ''', pl['party_list_number'])
                for contractor in pl_contractors:
                    company_name = contractor['company_name']
                    if company_name and any(pattern.upper() in company_name.upper() for pattern in verified_patterns):
                        contractor_names.append(company_name)
            
            contractor_names = list(set(contractor_names))
            
            # If we don't have district_municipalities from districts.json, skip UNLESS congressman has contractors
            # (Party-list representatives like Gardiola match via contractors, not districts)
            if not district_municipalities and not config_is_city_district:
                if not contractor_names:
                    print(f"⚠️  Skipping {display_name}: No municipalities found in districts.json for {config_district_number} and no verified contractors")
                    continue
                else:
                    print(f"ℹ️  Processing {display_name} via contractors only (no district data)")
            
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
                    if valid_barangay in combined_text:
                        valid_barangay_found = True
                        break
                
                # If barangay indicator exists but no valid barangay found, check for known invalid ones
                if not valid_barangay_found:
                    # Common non-2nd-district barangays that should be excluded
                    invalid_barangays = ['TALISAYAN', 'LABUAN', 'AYALA', 'SINUNUC', 'BALIWASAN', 'PASONANCA', 'SINUBONG', 'RECODO', 'SAN RAMON', 'MAASIN', 'MENZI', 'CULIANAN']
                    for invalid_barangay in invalid_barangays:
                        if invalid_barangay in combined_text:
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
                if barangay and barangay.upper() in combined_text:
                    return (congressman_name, "district", 100)
        
        # 2. Check contractor match EARLY (for party-list representatives like Gardiola and Co)
        # This must happen before district checks, as some congressmen have no districts
        contractors = congressman_data.get('contractors', [])
        contractor_exclusions = congressman_data.get('contractor_exclusions', {})
        
        if contractor_name:
            contractor_name_upper = contractor_name.upper()
            
            # For Gonzales: Match contractor names containing "A.D. GONZALES" (even if not in DB contractors list)
            if 'GONZALES' in congressman_name.upper():
                if 'A.D. GONZALES' in contractor_name_upper:
                    return (congressman_name, "contractor", 50)
            
            if contractors:
                # Check if this congressman has contractors that match
                for contractor in contractors:
                    contractor_upper = contractor.upper()
                    
                    # For Co: Match contractor names containing "SUNWEST"
                    if 'SUNWEST' in contractor_upper:
                        if 'SUNWEST' in contractor_name_upper:
                            return (congressman_name, "contractor", 50)
                    
                    # For JSG: Match JSG but NOT JSGCRAFT
                    if 'JSG' in contractor_upper:
                        if 'JSG' in contractor_name_upper and 'JSGCRAFT' not in contractor_name_upper:
                            return (congressman_name, "contractor", 50)
                    
                    # For A.D. GONZALES: Match contractor names containing "A.D. GONZALES" or "A.D. GONZALES JR"
                    if 'A.D. GONZALES' in contractor_upper:
                        if 'A.D. GONZALES' in contractor_name_upper:
                            return (congressman_name, "contractor", 50)
                    
                    # For other patterns, check if pattern is in contractor name
                    for pattern in ['ROVING PREMIER', 'VIRKAR', 'GARDIOLA']:
                        if pattern in contractor_upper:
                            if pattern in contractor_name_upper:
                                return (congressman_name, "contractor", 50)
        
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
            if "QUEZON CITY" in combined_text:
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
                
                # Check all municipalities in districts.json for this province
                for mun_key, mun_district in municipalities_map.items():
                    mun_key_upper = mun_key.upper()
                    # Use word boundary check to avoid partial matches (e.g., "Palompon" in "Palompon-Isabel")
                    # Check if municipality is mentioned as a whole word or with hyphen
                    if mun_key_upper in combined_text:
                        # Check if it belongs to a DIFFERENT district
                        if mun_district and mun_district.upper() != congressman_district:
                            # Municipality from different district is mentioned - exclude!
                            return (None, None, 0)
        
        # 6. Check if district identifier is in project text
        if district_identifier not in combined_text:
            return (None, None, 0)
        
        # 7. For city districts (like Zamboanga City), match all city projects
        # BUT only if no barangay indicator was found, or if a valid barangay was found
        if congressman_data.get('is_city_district') and district_identifier:
            # Check if barangay indicator exists
            has_barangay_indicator = any(indicator in combined_text for indicator in ['BARANGAY', 'BRGY', 'BRG', 'BR.', 'BRGY.'])
            
            if has_barangay_indicator:
                # If barangay indicator exists, we already checked for valid/invalid barangays above
                # If we reach here, it means no valid barangay was found and no invalid one was detected
                # In this case, we should NOT match (better to exclude uncertain matches)
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
                if mun and mun.upper() in combined_text:
                    # Found BOTH district identifier AND municipality from that district - match!
                    return (congressman_name, "district", 100)
        
        # For province districts, if we reach here without a municipality match, exclude it
        # (Only city districts allow city-wide matches)
        if not congressman_data.get('is_city_district'):
            return (None, None, 0)
        
        return (None, None, 0)
    
    async def process_projects(self, dynasty_conn, dime_conn, philgeps_conn, congressmen_data: Dict, districts_data: Dict) -> List[Dict]:
        """Process projects from all databases"""
        all_projects = []
        
        # Process SSP/MeiliSearch projects
        try:
            client = FloodControlClient()
            # Get all provinces from congressmen
            all_provinces = set()
            for cm_data in congressmen_data.values():
                if cm_data.get('provinces'):
                    all_provinces.update(cm_data['provinces'])
            
            for province in all_provinces:
                if not province:
                    continue
                
                # Query by province
                filter_str = f'Province = "{province}"'
                projects, metadata = await client.search_projects(
                    query=province,
                    filters=filter_str,
                    limit=1000,
                    offset=0
                )
                
                for proj in projects:
                    proj_desc = (proj.ProjectDescription or '').upper()
                    proj_province = (proj.Province or '').upper()
                    proj_municipality = (proj.Municipality or '').upper()
                    proj_contractor = (proj.Contractor or '').upper()
                    # Include contractor in combined text for matching
                    combined_text = f'{proj_desc} {proj_province} {proj_municipality} {proj_contractor}'
                    
                    matched_congressman = None
                    match_type = None
                    match_score = 0
                    
                    # Try to match to each congressman (includes district and contractor matching)
                    for cm_name, cm_data in congressmen_data.items():
                        cm_name_result, match_type_result, match_score_result = self.match_project(combined_text, cm_data, districts_data, proj_contractor)
                        if cm_name_result:
                            matched_congressman = cm_name_result
                            match_type = match_type_result
                            match_score = match_score_result
                            break
                    
                    if matched_congressman and match_score > 0:
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
                            "congressman": matched_congressman,
                            "source": "SSP",
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
        except Exception as e:
            print(f"Error processing SSP/MeiliSearch projects: {e}")
        
        # Process DIME projects
        try:
            dime_projects = await dime_conn.fetch('''
                SELECT project_name, contractors, cost, province, city, barangay, status, date_started, meilisearch_id
                FROM projects
                LIMIT 10000
            ''')
            
            for proj in dime_projects:
                proj_name = (proj.get('project_name') or '').upper()
                proj_province = (proj.get('province') or '').upper()
                proj_city = (proj.get('city') or '').upper()
                proj_barangay = (proj.get('barangay') or '').upper()
                combined_text = f'{proj_name} {proj_province} {proj_city} {proj_barangay}'
                
                matched_congressman = None
                match_type = None
                match_score = 0
                
                # Include contractor in combined text for matching
                contractor_str = ''
                if isinstance(proj.get('contractors'), list):
                    contractor_str = ', '.join(proj['contractors']).upper()
                elif proj.get('contractors'):
                    contractor_str = str(proj['contractors']).upper()
                combined_text = f'{combined_text} {contractor_str}'
                
                # Try to match to each congressman (includes district and contractor matching)
                for cm_name, cm_data in congressmen_data.items():
                    cm_name_result, match_type_result, match_score_result = self.match_project(combined_text, cm_data, districts_data, contractor_str)
                    if cm_name_result:
                        matched_congressman = cm_name_result
                        match_type = match_type_result
                        match_score = match_score_result
                        break  # Found match, stop checking other congressmen
                
                if matched_congressman and match_score > 0:
                    location_parts = []
                    if proj.get('province'):
                        location_parts.append(proj['province'])
                    if proj.get('city'):
                        location_parts.append(proj['city'])
                    if proj.get('barangay'):
                        location_parts.append(proj['barangay'])
                    location_str = ', '.join(location_parts).strip() or "N/A"
                    
                    all_projects.append({
                        "congressman": matched_congressman,
                        "source": "DIME",
                        "meilisearch_id": proj.get('meilisearch_id'),
                        "project_name": proj['project_name'] or "N/A",
                        "contractor": contractor_str if contractor_str else "N/A",
                        "amount": float(proj['cost']) if proj['cost'] else 0,
                        "location": location_str,
                        "year": proj['date_started'].year if proj['date_started'] else "N/A",
                        "status": proj['status'] or "N/A",
                        "match_type": match_type,
                        "match_score": match_score,
                        "is_city_wide": (match_score == 1 and match_type == "district")
                    })
        except Exception as e:
            print(f"Error processing DIME projects: {e}")
        
        # Process PhilGEPS projects (similar logic)
        try:
            philgeps_projects = await philgeps_conn.fetch('''
                SELECT award_title, awardee_name, contract_amount, area_of_delivery, award_date, award_status, meilisearch_id
                FROM contracts
                LIMIT 10000
            ''')
            
            for contract in philgeps_projects:
                award_title = (contract.get('award_title') or '').upper()
                area_of_delivery = (contract.get('area_of_delivery') or '').upper()
                awardee_name = (contract.get('awardee_name') or '').upper()
                # Include contractor in combined text for matching
                combined_text = f'{award_title} {area_of_delivery} {awardee_name}'
                
                matched_congressman = None
                match_type = None
                match_score = 0
                
                # Try to match to each congressman (includes district and contractor matching)
                awardee_name = (contract.get('awardee_name') or '').upper()
                for cm_name, cm_data in congressmen_data.items():
                    cm_name_result, match_type_result, match_score_result = self.match_project(combined_text, cm_data, districts_data, awardee_name)
                    if cm_name_result:
                        matched_congressman = cm_name_result
                        match_type = match_type_result
                        match_score = match_score_result
                        break
                
                if matched_congressman and match_score > 0:
                    all_projects.append({
                        "congressman": matched_congressman,
                        "source": "PhilGEPS",
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
        except Exception as e:
            print(f"Error processing PhilGEPS projects: {e}")
        
        return all_projects
    
    async def generate_cache(self):
        """Generate the cached JSON file"""
        print("🚀 Starting dynasty-projects cache generation...")
        
        # Load config
        config_data, districts_data = await self.load_config()
        print(f"✅ Loaded config with {len(config_data.get('target_congressmen', []))} congressmen")
        
        # Connect to databases
        dynasty_conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
        )
        
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
        
        try:
            # Get congressmen data
            congressmen_data = await self.get_congressmen_data(dynasty_conn, config_data, districts_data)
            print(f"✅ Loaded {len(congressmen_data)} congressmen")
            
            # Process projects
            all_projects = await self.process_projects(dynasty_conn, dime_conn, philgeps_conn, congressmen_data, districts_data)
            print(f"✅ Processed {len(all_projects)} projects")
            
            # Deduplicate and add cross-database bonus
            projects_by_key = {}
            for proj in all_projects:
                key = proj.get('meilisearch_id') or f"{proj.get('project_name', '')}_{proj.get('amount', 0)}_{proj.get('location', '')}"
                
                if key not in projects_by_key:
                    projects_by_key[key] = {
                        'project': proj,
                        'sources': set(),
                        'congressmen': set()
                    }
                
                projects_by_key[key]['sources'].add(proj.get('source', 'Unknown'))
                projects_by_key[key]['congressmen'].add(proj.get('congressman', 'Unknown'))
            
            # Build unique projects list
            unique_projects = []
            for key, data in projects_by_key.items():
                proj = data['project'].copy()
                sources_count = len(data['sources'])
                
                # New scoring system:
                # 1. Base score: 1 point per 2M (max 70)
                amount = proj.get('amount', 0)
                if isinstance(amount, str):
                    # Handle string amounts like "₱270,194,706"
                    amount_str = amount.replace('₱', '').replace(',', '').strip()
                    try:
                        amount = float(amount_str)
                    except (ValueError, AttributeError):
                        amount = 0
                
                amount_in_millions = amount / 1_000_000
                base_score = min(70, int(amount_in_millions / 2))  # 1 point per 2M, max 70
                
                # 2. Add +10 per database
                db_bonus = sources_count * 10
                
                # 3. Calculate total score
                current_score = base_score + db_bonus
                
                # 4. For city-type districts: penalize city-wide matches (no barangay) by -50
                # Check if this was a city-wide match using the is_city_wide flag
                is_city_wide = proj.get('is_city_wide', False)
                if is_city_wide:
                    # City-wide match - apply -50 penalty
                    current_score = max(0, current_score - 50)
                
                proj['match_score'] = current_score
                proj['sources_count'] = sources_count
                proj['sources_list'] = sorted(list(data['sources']))
                
                unique_projects.append(proj)
            
            # Sort by match_score descending, then by amount descending
            unique_projects.sort(key=lambda x: (x.get('match_score', 0), x.get('amount', 0)), reverse=True)
            
            # Calculate summary
            summary = {
                "total": len(unique_projects),
                "dime": len([p for p in unique_projects if 'DIME' in (p.get('sources_list', []))]),
                "philgeps": len([p for p in unique_projects if 'PhilGEPS' in (p.get('sources_list', []))]),
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
            
            # Save to cache file
            cache_data = {
                "success": True,
                "projects": unique_projects,
                "summary": summary,
                "chart_data": chart_data,
                "dashboard_stats": dashboard_stats,
                "generated_at": datetime.now().isoformat(),
                "cache_version": "1.0"
            }
            
            # Ensure directory exists
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            print(f"✅ Cache generated successfully: {self.cache_file}")
            print(f"   Total projects: {summary['total']}")
            print(f"   District matches: {summary['district_projects']}")
            print(f"   Contractor matches: {summary['contractor_projects']}")
            print(f"   Dashboard stats:")
            print(f"     - Total cost: ₱{dashboard_stats['total_cost_all']:,.2f}")
            print(f"     - District cost: ₱{dashboard_stats['district_cost']:,.2f}")
            print(f"     - Contractor cost: ₱{dashboard_stats['contractor_cost']:,.2f}")
            
        finally:
            await dynasty_conn.close()
            await dime_conn.close()
            await philgeps_conn.close()

async def main():
    generator = DynastyProjectsCacheGenerator()
    await generator.generate_cache()

if __name__ == '__main__':
    asyncio.run(main())


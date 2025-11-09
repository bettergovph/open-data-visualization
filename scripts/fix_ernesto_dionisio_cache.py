#!/usr/bin/env python3
"""
Fix Ernesto M. Dionisio Jr. cache file by reprocessing with corrected Manila district matching logic.

This script addresses the issue where road codes like "K0578 + 800" were incorrectly
attributing projects to Manila 1st District congressman. The fix requires barangay-level
matching for Manila districts instead of allowing city-wide matches.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

class ErnestoDionisioCacheFixer:
    """Fix cache for Ernesto M. Dionisio Jr. with corrected district matching"""

    def __init__(self):
        root_dir = Path(__file__).parent.parent
        self.cache_base_dir = root_dir / 'static' / 'data'
        self.config_file = self.cache_base_dir / 'dynasty-projects-config.json'
        self.districts_file = self.cache_base_dir / 'districts.json'
        self.target_congressman = "Ernesto M. Dionisio Jr."

    def _log(self, message: str) -> None:
        """Log message if verbose mode is enabled"""
        if self.verbose:
            print(message)

    def contains_word(self, text: str, word: str) -> bool:
        """Check if word appears as a whole word in text"""
        if not word:
            return False
        pattern = rf'(?<!\w){re.escape(word)}(?!\w)'
        return re.search(pattern, text) is not None

    def match_project(self, project_text: str, congressman_data: Dict, districts_data: Dict, contractor_name: str = '') -> Tuple[Optional[str], Optional[str], int]:
        """
        Match a project to a congressman using corrected logic.
        Returns: (congressman_name, match_type, match_score) or (None, None, 0)
        """
        combined_text = project_text.upper()
        congressman_name = congressman_data['name']

        # 1. Check barangay match (highest priority)
        if congressman_data.get('is_city_district'):
            # Get valid barangays - prioritize districts.json for Manila
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

            # For Manila, prioritize districts.json barangays over congressman config
            if not valid_barangays and congressman_data.get('barangays'):
                valid_barangays = [b.upper() for b in congressman_data.get('barangays', []) if b]

            if valid_barangays:
                # Check if any valid barangay is mentioned (with or without indicators)
                valid_barangay_found = False
                for valid_barangay in valid_barangays:
                    if self.contains_word(combined_text, valid_barangay):
                        valid_barangay_found = True
                        break

                # If a valid barangay is found, it's a strong match
                if valid_barangay_found:
                    return (congressman_name, "district", 100)

                # If barangay indicator exists but no valid barangay found, exclude
                has_barangay_indicator = any(indicator in combined_text for indicator in ['BARANGAY', 'BRGY', 'BRG', 'BR.', 'BRGY.'])
                if has_barangay_indicator and not valid_barangay_found:
                    return (None, None, 0)

        # 2. Check contractor match
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

        # Get district identifier
        district_identifier = None
        if congressman_data.get('provinces') and congressman_data['provinces']:
            district_identifier = congressman_data['provinces'][0].upper()

        if not district_identifier:
            return (None, None, 0)

        # Exclusion check for province/city name conflicts
        if district_identifier == "QUEZON":
            if self.contains_word(combined_text, "QUEZON CITY"):
                return (None, None, 0)

        # Check for municipality conflicts (different district)
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
                    if self.contains_word(combined_text, mun_key_upper):
                        if mun_district and mun_district.upper() != congressman_district:
                            return (None, None, 0)

        # Check if district identifier is in project text
        if not self.contains_word(combined_text, district_identifier):
            return (None, None, 0)

        # 7. For city districts - CORRECTED LOGIC FOR MANILA
        if congressman_data.get('is_city_district') and district_identifier:
            # SPECIAL RULE: For Manila districts, require barangay-level matching
            # This prevents road codes like "K0578 + 800" from being misinterpreted
            if district_identifier == 'MANILA':
                # For Manila, do NOT allow city-wide matches - require barangay matches
                return (None, None, 0)

            # Check if barangay indicator exists
            has_barangay_indicator = any(indicator in combined_text for indicator in ['BARANGAY', 'BRGY', 'BRG', 'BR.', 'BRGY.'])

            if has_barangay_indicator:
                return (None, None, 0)

            # STRICT RULE: If project mentions "ROAD", require "CITY"
            if re.search(r'\bROAD\b', combined_text, re.IGNORECASE):
                if 'CITY' not in combined_text:
                    return (None, None, 0)

            # City-wide match for non-Manila cities
            if district_identifier in combined_text:
                return (congressman_name, "district", 1)

        # 8. For province districts: Check municipalities
        district_municipalities = congressman_data.get('district_municipalities', [])
        if district_municipalities:
            for mun in district_municipalities:
                if mun and self.contains_word(combined_text, mun.upper()):
                    # Check for naming conflicts
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
                            continue

                    return (congressman_name, "district", 100)

        # For province districts without municipality match, exclude
        if not congressman_data.get('is_city_district'):
            return (None, None, 0)

        return (None, None, 0)

    def fix_cache(self):
        """Fix the Ernesto M. Dionisio Jr. cache file by re-filtering with corrected logic"""
        print(f"🔧 Fixing cache for {self.target_congressman}")

        # Load configuration files
        config_data = {}
        districts_data = {}

        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

        if self.districts_file.exists():
            with open(self.districts_file, 'r', encoding='utf-8') as f:
                districts_data = json.load(f)

        # Find Ernesto M. Dionisio Jr. configuration
        ernesto_config = None
        for congressman in config_data.get('target_congressmen', []):
            if congressman.get('display_name') == self.target_congressman:
                ernesto_config = congressman
                break

        if not ernesto_config:
            print(f"❌ Could not find configuration for {self.target_congressman}")
            return

        print(f"✅ Found configuration for {self.target_congressman}")

        # Load congressman data
        congressman_data = {
            "name": self.target_congressman,
            "provinces": [ernesto_config.get('province', 'Manila')],
            "district_municipalities": [],  # Manila is a city district
            "district_number": ernesto_config.get('district_number', '1st District'),
            "is_city_district": ernesto_config.get('is_city_district', True),
            "contractors": ernesto_config.get('contractors', []),
            "contractor_patterns": ernesto_config.get('contractor_patterns', []),
            "contractor_exclusions": ernesto_config.get('contractor_exclusions', {}),
            "barangays": ernesto_config.get('barangays', [])
        }

        # Load existing cache file
        congressman_slug = self.target_congressman.lower().replace(' ', '-').replace('.', '')
        cache_dir = self.cache_base_dir / f'congressman-projects-{congressman_slug}'
        cache_file = cache_dir / 'all-projects-cache.json'

        if not cache_file.exists():
            print(f"❌ Cache file not found: {cache_file}")
            return

        print(f"📂 Loading existing cache file: {cache_file}")
        with open(cache_file, 'r', encoding='utf-8') as f:
            existing_cache = json.load(f)

        original_projects = existing_cache.get('projects', [])
        print(f"📊 Original cache has {len(original_projects)} projects")

        # Re-filter projects using corrected matching logic
        filtered_projects = []

        for project in original_projects:
            # Create project text for matching
            if project['source'] == 'DIME':
                project_text = f"{project.get('project_name', '')} {project.get('province', '')} {project.get('city', '')} {project.get('barangay', '')}"
                contractor_name = project.get('contractors', [None])[0] if project.get('contractors') else None
            elif project['source'] == 'PhilGEPS':
                project_text = f"{project.get('project_name', '')} {project.get('location', '')}"
                contractor_name = project.get('contractors', [None])[0] if project.get('contractors') else None
            elif project['source'] == 'SSP':
                project_text = f"{project.get('project_name', '')} {project.get('province', '')} {project.get('city', '')} {project.get('barangay', '')}"
                contractor_name = None
            else:
                project_text = str(project)
                contractor_name = None

            # Comprehensive fix: for Manila districts, require explicit barangay matches
            # No city-wide matching allowed - must mention actual barangay names
            # Check for both full names (Tondo I, Tondo II) and base names (Tondo, Binondo)
            valid_barangays = ['TONDO I', 'TONDO II', 'BINONDO', 'QUIAPO', 'SAN NICOLAS', 'SANTA CRUZ', 'SAMPALOC',
                              'TONDO', 'QUIAPO', 'SAN NICOLAS', 'SANTA CRUZ', 'SAMPALOC']
            has_real_barangay = any(barangay in project_text.upper() for barangay in valid_barangays)

            # Also exclude road code projects that are definitely not in Manila
            has_road_code = bool(re.search(r'K\d{4}\s*\+\s*\d{3}', project_text.upper()))
            mentions_other_provinces = any(prov in project_text.upper() for prov in ['TARLAC', 'PAMPANGA', 'BULACAN', 'NUEVA ECIJA'])

            # Keep only projects that have real barangay names OR are clearly in Manila without road codes
            should_keep = False
            if has_real_barangay:
                should_keep = True  # Has actual barangay name
            elif has_road_code and mentions_other_provinces:
                should_keep = False  # Road codes in other provinces
            elif not has_road_code and not mentions_other_provinces:
                # Could be legitimate Manila project without explicit barangay
                # For now, be conservative and exclude if no barangay mentioned
                should_keep = False

            if should_keep:
                filtered_projects.append(project)

        print(f"📊 After filtering: {len(filtered_projects)} projects remain")

        # Calculate corrected statistics
        district_projects = [p for p in filtered_projects if p.get('match_type') == 'district']
        contractor_projects = [p for p in filtered_projects if p.get('match_type') == 'contractor']

        total_cost = sum(p.get('amount', 0) for p in filtered_projects)
        district_cost = sum(p.get('amount', 0) for p in district_projects)
        contractor_cost = sum(p.get('amount', 0) for p in contractor_projects)

        # Create updated summary
        summary = {
            "total_projects": len(filtered_projects),
            "district_projects": len(district_projects),
            "contractor_projects": len(contractor_projects),
            "total_cost": total_cost,
            "district_cost": district_cost,
            "contractor_cost": contractor_cost
        }

        # Create updated dashboard stats
        dashboard_stats = {
            "total_cost_all": total_cost,
            "district_cost": district_cost,
            "contractor_cost": contractor_cost,
            "total_projects_all": len(filtered_projects),
            "district_projects": len(district_projects),
            "contractor_projects": len(contractor_projects)
        }

        # Create updated cache data
        cache_data = {
            "success": True,
            "congressman": self.target_congressman,
            "projects": filtered_projects,
            "summary": summary,
            "dashboard_stats": dashboard_stats,
            "generated_at": datetime.now().isoformat(),
            "cache_version": "3.0-fixed",
            "fix_note": "Fixed Manila district matching to require barangay-level matches instead of city-wide matches. Removed projects that were incorrectly attributed due to road codes.",
            "original_project_count": len(original_projects),
            "filtered_project_count": len(filtered_projects)
        }

        # Save updated cache file
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)

        # Also update summary.json
        summary_data = {
            "congressman": self.target_congressman,
            "summary": summary,
            "total_cost": total_cost,
            "generated_at": datetime.now().isoformat()
        }

        summary_file = cache_dir / 'summary.json'
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, indent=2, ensure_ascii=False)

        print("✅ Fixed cache file successfully!")
        print(f"   Original projects: {len(original_projects)}")
        print(f"   Filtered projects: {len(filtered_projects)}")
        print(f"   Projects removed: {len(original_projects) - len(filtered_projects)}")
        print(f"   District projects: {len(district_projects)}")
        print(f"   Contractor projects: {len(contractor_projects)}")
        print(f"   Total cost: ₱{total_cost:,.2f}")
        print(f"   District cost: ₱{district_cost:,.2f}")
        print(f"   Contractor cost: ₱{contractor_cost:,.2f}")

def main():
    fixer = ErnestoDionisioCacheFixer()
    fixer.fix_cache()


if __name__ == '__main__':
    main()

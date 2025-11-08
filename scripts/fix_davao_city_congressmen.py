#!/usr/bin/env python3
"""
Fix Davao City congressmen cache files by ensuring proper district-level matching.

This script addresses the issue where Davao City congressmen (Paolo Duterte,
Mylene Garcia-Albano, Vincent Garcia) were getting identical project counts
due to city-wide matching instead of district-specific barangay matching.

Davao City districts have specific barangays assigned to each district.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

class DavaoCityCongressmenFixer:
    """Fix cache for Davao City congressmen with proper district matching"""

    def __init__(self):
        self.cache_base_dir = Path(__file__).parent.parent / 'static' / 'data'
        self.config_file = Path(__file__).parent.parent / 'dynasty-projects-config.json'
        self.districts_file = Path(__file__).parent.parent / 'districts.json'
        self.target_congressmen = [
            "Paolo Duterte",
            "Mylene Garcia-Albano",
            "Vincent Garcia",
            "Isidro Ungab"
        ]

    def _log(self, message: str) -> None:
        """Log message"""
        print(message)

    def contains_word(self, text: str, word: str) -> bool:
        """Check if word appears as a whole word in text"""
        if not word:
            return False
        pattern = rf'(?<!\w){re.escape(word)}(?!\w)'
        return re.search(pattern, text) is not None

    def match_project(self, project_text: str, congressman_data: Dict, districts_data: Dict, contractor_name: str = '', project_year: Optional[int] = None) -> Tuple[Optional[str], Optional[str], int]:
        """
        Match a project to a congressman using strict district matching for Davao City + contractor matching + term checking.
        Returns: (congressman_name, match_type, match_score) or (None, None, 0)
        """
        combined_text = project_text.upper()
        congressman_name = congressman_data['name']

        # 1. Check contractor match FIRST (for party-list representatives like Gardiola)
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

            # Check direct contractor matches
            for contractor in contractors:
                if contractor and contractor.upper() in contractor_name_upper:
                    if not _contractor_is_excluded(contractor_name_upper):
                        return (congressman_name, "contractor", 100)

            # Check pattern matches
            for pattern in contractor_patterns:
                if pattern and _normalize_for_match(pattern) in normalized_candidate:
                    if not _contractor_is_excluded(contractor_name_upper):
                        return (congressman_name, "contractor", 90)

        # 2. For Davao City districts, require barangay-level matching + term checking
        if congressman_data.get('is_city_district') and congressman_data.get('provinces') and congressman_data['provinces'][0] == 'Davao City':
            # Check if project year falls within congressman's terms
            if project_year is not None:
                terms = congressman_data.get('terms', [])
                year_in_terms = False

                for term in terms:
                    term_start = term.get('start')
                    term_end = term.get('end')
                    if term_start and term_end and term_start <= project_year <= term_end:
                        year_in_terms = True
                        break

                if not year_in_terms:
                    return (None, None, 0)  # Project year doesn't match congressman's terms

            # Get valid barangays for this specific district
            valid_barangays = []
            if districts_data:
                davao_info = districts_data.get('districts', {}).get('Davao City', {})
                barangays_map = davao_info.get('barangays', {})
                district_number = congressman_data.get('district_number')

                if district_number and district_number in barangays_map:
                    # Get both full names and base names
                    full_barangays = barangays_map[district_number]
                    base_barangays = []
                    for barangay in full_barangays:
                        # Extract base name (remove numbers/suffixes)
                        base_name = re.sub(r'\s+\d+$|.*\s+', '', barangay).strip()
                        if base_name != barangay:  # Only add if different
                            base_barangays.append(base_name)
                    valid_barangays = [b.upper() for b in full_barangays + base_barangays]


            # For Davao City, REQUIRE barangay match - no city-wide matching
            if valid_barangays:
                has_barangay_match = any(barangay in combined_text for barangay in valid_barangays)
                if has_barangay_match:
                    return (congressman_name, "district", 100)

            # If no barangay match found for Davao City, return no match
            return (None, None, 0)

        # For non-Davao City congressmen, use standard matching (this shouldn't happen in this script)
        return (None, None, 0)

    def fix_congressman_cache(self, congressman_name: str, districts_data: Dict) -> None:
        """Fix cache for a specific congressman"""
        print(f"🔧 Fixing cache for {congressman_name}")

        # Load congressman configuration
        config_data = {}
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

        congressman_config = None
        for congressman in config_data.get('target_congressmen', []):
            if congressman.get('display_name') == congressman_name:
                congressman_config = congressman
                break

        if not congressman_config:
            print(f"❌ Could not find configuration for {congressman_name}")
            return

        # Parse terms - they might be stored as JSON string or already as list
        terms_raw = congressman_config.get('terms', [])
        if isinstance(terms_raw, str):
            try:
                terms_raw = json.loads(terms_raw)
            except (json.JSONDecodeError, TypeError):
                terms_raw = []

        congressman_data = {
            "name": congressman_name,
            "provinces": [congressman_config.get('province', 'Davao City')],
            "district_municipalities": [],
            "district_number": congressman_config.get('district_number', '1st District'),
            "is_city_district": congressman_config.get('is_city_district', True),
            "contractors": congressman_config.get('contractors', []),
            "contractor_patterns": congressman_config.get('contractor_patterns', []),
            "contractor_exclusions": congressman_config.get('contractor_exclusions', {}),
            "barangays": congressman_config.get('barangays', []),
            "terms": terms_raw
        }

        # Debug: show what barangays we're using
        if congressman_data.get('is_city_district') and congressman_data.get('provinces') and congressman_data['provinces'][0] == 'Davao City':
            valid_barangays = []
            if districts_data:
                davao_info = districts_data.get('districts', {}).get('Davao City', {})
                barangays_map = davao_info.get('barangays', {})
                district_number = congressman_data.get('district_number')

                if district_number and district_number in barangays_map:
                    full_barangays = barangays_map[district_number]
                    base_barangays = []
                    for barangay in full_barangays:
                        base_name = re.sub(r'\s+\d+$|.*\s+', '', barangay).strip()
                        if base_name != barangay:
                            base_barangays.append(base_name)
                    valid_barangays = [b.upper() for b in full_barangays + base_barangays]
                    print(f"   🔍 Using districts.json barangays for {congressman_name} {district_number}: {valid_barangays[:10]}...")
                else:
                    valid_barangays = [b.upper() for b in congressman_data.get('barangays', []) if b]
                    print(f"   🔍 Using config file barangays for {congressman_name} {district_number}: {len(valid_barangays)} barangays")

        # Load existing cache file
        congressman_slug = congressman_name.lower().replace(' ', '-').replace('.', '')
        cache_dir = self.cache_base_dir / f'congressman-projects-{congressman_slug}'
        cache_file = cache_dir / 'all-projects-cache.json'

        if not cache_file.exists():
            print(f"❌ Cache file not found: {cache_file}")
            return

        print(f"📂 Loading existing cache file")
        with open(cache_file, 'r', encoding='utf-8') as f:
            existing_cache = json.load(f)

        original_projects = existing_cache.get('projects', [])
        print(f"📊 Original cache has {len(original_projects)} projects")

        # Re-filter projects using strict Davao City district matching
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

            # Get project year for term checking
            project_year = project.get('year')
            if isinstance(project_year, str):
                try:
                    project_year = int(project_year)
                except (ValueError, TypeError):
                    project_year = None

            # Test match with strict district matching + term checking
            matched_congressman, match_type, match_score = self.match_project(
                project_text, congressman_data, districts_data, contractor_name, project_year
            )

            if matched_congressman == congressman_name:
                # Update match info
                project['match_type'] = match_type
                project['match_score'] = match_score
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
            "congressman": congressman_name,
            "projects": filtered_projects,
            "summary": summary,
            "dashboard_stats": dashboard_stats,
            "generated_at": datetime.now().isoformat(),
            "cache_version": "3.0-davao-fixed",
            "fix_note": "Fixed Davao City district matching to require barangay-level matches instead of city-wide matches. Each congressman now only gets projects from their specific district's barangays.",
            "original_project_count": len(original_projects),
            "filtered_project_count": len(filtered_projects)
        }

        # Save updated cache file
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)

        # Also update summary.json
        summary_data = {
            "congressman": congressman_name,
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
        print()

    def fix_all_davao_congressmen(self):
        """Fix caches for all target Davao City congressmen"""
        print("🏛️ Fixing Davao City congressmen caches...")
        print("Target congressmen:", self.target_congressmen)
        print()

        # Load districts data
        districts_data = {}
        if self.districts_file.exists():
            with open(self.districts_file, 'r', encoding='utf-8') as f:
                districts_data = json.load(f)

        # Fix each congressman
        for congressman in self.target_congressmen:
            self.fix_congressman_cache(congressman, districts_data)

        print("🎯 All Davao City congressmen caches have been fixed!")
        print("Each congressman now only has projects from their specific district's barangays.")


def main():
    fixer = DavaoCityCongressmenFixer()
    fixer.fix_all_davao_congressmen()


if __name__ == '__main__':
    main()

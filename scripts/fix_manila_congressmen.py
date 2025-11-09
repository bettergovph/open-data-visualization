import asyncio
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import re

class ManilaCongressmenFixer:
    def __init__(self):
        root_dir = Path(__file__).resolve().parent.parent
        self.cache_dir = root_dir / "static" / "data"
        self.config_file = self.cache_dir / "dynasty-projects-config.json"
        self.districts_file = self.cache_dir / "districts.json"

        # Target Manila congressmen
        self.target_congressmen = [
            "Manny Lopez",           # 1st District
            "Rolan Valeriano",       # 2nd District
            "Rolando M. Valeriano",  # 2nd District
            "Joel R. Chua",          # 3rd District
            "John Marvin Nieto",     # 3rd District
            "Edward M. Maceda",      # 4th District
            "William Irwin C. Tieng", # 5th District
            "Amanda Christina Bagatsing", # 5th District
            "Bienvenido Abante",     # 6th District
        ]

        self.config_data = None
        self.districts_data = None

    def load_config(self):
        """Load congressman configuration"""
        with open(self.config_file, 'r') as f:
            data = json.load(f)
            self.config_data = data.get('target_congressmen', [])

    def load_districts(self):
        """Load district boundaries"""
        with open(self.districts_file, 'r') as f:
            self.districts_data = json.load(f)

    def contains_word(self, text: str, word: str) -> bool:
        """Check if word appears in text with word boundaries"""
        if not word:
            return False
        pattern = rf'(?<!\w){re.escape(word)}(?!\w)'
        return re.search(pattern, text.upper()) is not None

    def match_project(self, project_text: str, congressman_data: Dict, districts_data: Dict, contractor_name: str = '', project_year: Optional[int] = None) -> Tuple[Optional[str], Optional[str], int]:
        """
        Match a project to a congressman using strict district matching for Manila + contractor matching + term checking.
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

        # 2. For Manila districts, require barangay-level matching + term checking
        if congressman_data.get('is_city_district') and congressman_data.get('provinces') and congressman_data['provinces'][0] == 'Manila':
            # Term filtering logic:
            # - If project has a valid year: check if it falls within congressman's terms
            # - If project has no year: give to ALL congressmen (universal -50 penalty applied in scoring)
            match_score = 100  # Default high score
            should_include = False

            if project_year is not None:
                # Project has a year - check if it falls within any of the congressman's terms
                terms = congressman_data.get('terms', [])
                for term in terms:
                    term_start = term.get('start')
                    term_end = term.get('end')
                    if term_start and term_end and term_start <= project_year <= term_end:
                        should_include = True
                        break
            else:
                # Project has no year - give to ALL congressmen (universal -50 penalty will be applied in scoring)
                should_include = True
                match_score = 100  # Normal score, universal penalty applied later

            if not should_include:
                return (None, None, 0)  # Project doesn't match congressman's terms

            # Get valid barangays for this specific district
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

            # For Manila, REQUIRE barangay match - no city-wide matching
            if valid_barangays:
                has_barangay_match = any(self.contains_word(combined_text, barangay) for barangay in valid_barangays)
                if has_barangay_match:
                    return (congressman_name, "district", match_score)

            # If no barangay match found for Manila, return no match
            return (None, None, 0)

        # For non-Manila congressmen, use standard matching (this shouldn't happen in this script)
        return (None, None, 0)

    def fix_congressman_cache(self, congressman_slug: str):
        """Fix cache for a specific congressman"""
        print(f"🔧 Fixing cache for {congressman_slug}")

        # Find congressman config
        congressman_config = None
        for entry in self.config_data:
            if entry.get('display_name'):
                # Convert display name to slug format for comparison
                entry_slug = entry['display_name'].lower().replace(' ', '-').replace('.', '')
                if entry_slug == congressman_slug:
                    congressman_config = entry
                    break

        if not congressman_config:
            print(f"   ❌ Congress config not found for {congressman_slug}")
            return

        # Add 'name' field for compatibility with match_project function
        congressman_config['name'] = congressman_config['display_name']

        # Parse terms if it's a string
        if isinstance(congressman_config.get('terms'), str):
            try:
                congressman_config['terms'] = json.loads(congressman_config['terms'])
            except:
                congressman_config['terms'] = []

        # Check if cache file exists
        cache_file = self.cache_dir / f"congressman-projects-{congressman_slug}" / "all-projects-cache.json"
        if not cache_file.exists():
            print(f"   ❌ Cache file not found: {cache_file}")
            return

        # Load existing cache
        with open(cache_file, 'r') as f:
            cache_data = json.load(f)

        original_projects = cache_data.get('projects', [])
        print(f"   📂 Original cache has {len(original_projects)} projects")

        # Filter projects using the new matching logic
        filtered_projects = []

        for project in original_projects:
            project_text = project.get('description', '')
            contractor_name = project.get('contractor', '')
            project_year = project.get('year')

            # Convert project_year to int if it's a string
            if isinstance(project_year, str) and project_year.isdigit():
                project_year = int(project_year)

            match_result = self.match_project(project_text, congressman_config, self.districts_data, contractor_name, project_year)

            if match_result[0] == congressman_config['name']:
                filtered_projects.append(project)

        print(f"   📊 After filtering: {len(filtered_projects)} projects remain")

        # Recalculate totals
        total_cost = 0
        district_cost = 0
        contractor_cost = 0

        for project in filtered_projects:
            amount = project.get('amount', 0)
            if isinstance(amount, str):
                amount_str = amount.replace('₱', '').replace(',', '').replace(' ', '')
                try:
                    amount = float(amount_str)
                except (ValueError, AttributeError):
                    amount = 0

            total_cost += amount

            # Categorize by match type
            match_type = project.get('match_type', 'district')
            if match_type == 'contractor':
                contractor_cost += amount
            else:
                district_cost += amount

        # Update cache data
        cache_data['projects'] = filtered_projects
        cache_data['total_projects'] = len(filtered_projects)
        cache_data['total_cost'] = f"₱{total_cost:,.2f}"
        cache_data['district_cost'] = f"₱{district_cost:,.2f}"
        cache_data['contractor_cost'] = f"₱{contractor_cost:,.2f}"

        # Save updated cache
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)

        # Update summary.json
        summary_file = self.cache_dir / f"congressman-projects-{congressman_slug}" / "summary.json"
        if summary_file.exists():
            with open(summary_file, 'r') as f:
                summary_data = json.load(f)

            summary_data['total_projects'] = len(filtered_projects)
            summary_data['total_cost'] = f"₱{total_cost:,.2f}"

            with open(summary_file, 'w') as f:
                json.dump(summary_data, f, indent=2)

        print("   ✅ Fixed cache file successfully!")
        print(f"      Original projects: {len(original_projects)}")
        print(f"      Filtered projects: {len(filtered_projects)}")
        print(f"      Projects removed: {len(original_projects) - len(filtered_projects)}")
        print(f"      Total cost: ₱{total_cost:,.2f}")

    def fix_all_manila_congressmen(self):
        """Fix caches for all target Manila congressmen"""
        print("🏛️ Fixing Manila congressmen caches...")

        self.load_config()
        self.load_districts()

        for congressman_name in self.target_congressmen:
            # Convert name to slug
            congressman_slug = congressman_name.lower().replace(' ', '-').replace('.', '')
            self.fix_congressman_cache(congressman_slug)

        print("🎯 All Manila congressmen caches have been fixed!")
        print("Each congressman now only has projects from their specific district's barangays and terms.")

async def main():
    fixer = ManilaCongressmenFixer()
    fixer.fix_all_manila_congressmen()

if __name__ == "__main__":
    asyncio.run(main())

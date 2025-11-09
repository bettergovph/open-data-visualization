import asyncio
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import re
from datetime import datetime

class ManilaCacheGenerator:
    def __init__(self):
        root_dir = Path(__file__).resolve().parent.parent
        self.cache_dir = root_dir / "static" / "data"
        self.config_file = self.cache_dir / "dynasty-projects-config.json"
        self.districts_file = self.cache_dir / "districts.json"

        # Target Manila congressmen only
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

        # Common database connection parameters
        common_db_kwargs = {
            "host": os.getenv('POSTGRES_HOST', 'localhost'),
            "port": int(os.getenv('POSTGRES_PORT', 5432)),
            "user": os.getenv('POSTGRES_USER', 'budget_admin'),
            "password": os.getenv('POSTGRES_PASSWORD', ''),
        }

        self.dynasty_conn = None
        self.dime_conn = None
        self.philgeps_conn = None

        self.config_data = None
        self.districts_data = None
        self.projects_cache = {}  # Cache for loaded projects

    async def connect_databases(self):
        """Connect to all required databases"""
        import asyncpg
        from dotenv import load_dotenv
        load_dotenv()

        common_db_kwargs = {
            "host": os.getenv('POSTGRES_HOST', 'localhost'),
            "port": int(os.getenv('POSTGRES_PORT', 5432)),
            "user": os.getenv('POSTGRES_USER', 'budget_admin'),
            "password": os.getenv('POSTGRES_PASSWORD', ''),
        }

        self.dynasty_conn = await asyncpg.connect(**{
            **common_db_kwargs,
            "database": os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
        })

        self.dime_conn = await asyncpg.connect(**{
            **common_db_kwargs,
            "database": os.getenv('POSTGRES_DB_DIME', 'dime')
        })

        self.philgeps_conn = await asyncpg.connect(**{
            **common_db_kwargs,
            "database": os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
        })

        # Set up JSON codecs
        for conn in [self.dynasty_conn, self.dime_conn, self.philgeps_conn]:
            await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
            await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

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

        # 2. For Manila districts, prefer barangay-level matching but allow city-wide
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

            # For Manila, prefer barangay match but allow city-wide
            if valid_barangays:
                has_barangay_match = any(self.contains_word(combined_text, barangay) for barangay in valid_barangays)
                if has_barangay_match:
                    return (congressman_name, "district", 100)  # Strong match for barangay mention
                else:
                    # Allow city-wide match for Manila with lower score
                    return (congressman_name, "district", 50)

            # If no barangays defined, allow city-wide match
            return (congressman_name, "district", 50)

        # For non-Manila congressmen, use standard matching (this shouldn't happen in this script)
        return (None, None, 0)

    async def load_projects_from_db(self):
        """Load all projects from databases"""
        print("📥 Loading projects from databases...")

        # Load DIME projects
        dime_projects = await self.dime_conn.fetch("""
            SELECT
                id, description, cost as amount, contractors as contractor_name,
                EXTRACT(YEAR FROM date_started) as year, project_image_url as source_url,
                'DIME' as source, meilisearch_id
            FROM projects
            WHERE description IS NOT NULL
        """)

        # Load PhilGEPS projects
        philgeps_projects = await self.philgeps_conn.fetch("""
            SELECT
                id, description, amount, contractor_name, year, source_url,
                'PhilGEPS' as source, meilisearch_id
            FROM projects
            WHERE description IS NOT NULL
        """)

        # Load SSP/Infrawatch projects from dynasty DB
        dynasty_projects = await self.dynasty_conn.fetch("""
            SELECT
                id, description, amount, contractor_name, year, source_url,
                'SSP' as source, meilisearch_id
            FROM dynasty_projects
            WHERE description IS NOT NULL
        """)

        all_projects = []
        for project in dime_projects + philgeps_projects + dynasty_projects:
            all_projects.append({
                'id': project['id'],
                'description': project['description'] or '',
                'amount': project['amount'],
                'contractor_name': project['contractor_name'] or '',
                'year': project['year'],
                'source': project['source'],
                'source_url': project['source_url'],
                'meilisearch_id': project['meilisearch_id']
            })

        print(f"✅ Loaded {len(all_projects)} total projects")
        return all_projects

    def generate_congressman_cache(self, congressman_slug: str, all_projects: List[Dict]):
        """Generate cache for a specific congressman"""
        print(f"🔧 Generating cache for {congressman_slug}")

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

        # Filter projects using the matching logic
        matched_projects = []
        district_projects = []
        contractor_projects = []

        for project in all_projects:
            project_text = project.get('description', '')
            contractor_name = project.get('contractor_name', '')
            project_year = project.get('year')

            # Convert project_year to int if it's a string
            if isinstance(project_year, str) and project_year.isdigit():
                project_year = int(project_year)

            match_result = self.match_project(project_text, congressman_config, self.districts_data, contractor_name, project_year)

            if match_result[0] == congressman_config['name']:
                project_copy = project.copy()
                project_copy['match_type'] = match_result[1]
                project_copy['match_score'] = match_result[2]
                matched_projects.append(project_copy)

                if match_result[1] == 'contractor':
                    contractor_projects.append(project_copy)
                else:
                    district_projects.append(project_copy)

        # Calculate scores and apply penalties
        for project in matched_projects:
            match_score = project.get('match_score', 0)

            # New scoring system:
            # 1. Base score: 1 point per 2M (max 60)
            amount = project.get('amount', 0)
            if isinstance(amount, str):
                # Handle string amounts like "₱270,194,706"
                amount_str = amount.replace('₱', '').replace(',', '').replace(' ', '')
                try:
                    amount = float(amount_str)
                except (ValueError, AttributeError):
                    amount = 0

            amount_in_millions = amount / 1_000_000
            base_score = min(60, int(amount_in_millions / 2))  # 1 point per 2M, max 60

            # 2. Add +10 per database (capped per project)
            sources_count = 1  # Each project comes from one source initially
            db_bonus = min(40, sources_count * 10)

            # 3. Calculate total score
            current_score = base_score + db_bonus

            # 4. For city-type districts: penalize city-wide matches (no barangay) by -40
            # Check if this was a city-wide match (score 50 indicates city-wide for Manila)
            is_city_wide = match_score == 50
            if is_city_wide:
                # City-wide match - apply -40 penalty
                current_score = max(0, current_score - 40)

            # 5. Penalize projects with null years by -50 (uncertain timeframe)
            has_null_year = project.get('year') is None or project.get('year') == '' or project.get('year') == 'null'
            if has_null_year:
                # Null year - apply -50 penalty for uncertainty
                current_score = max(0, current_score - 50)

            project['match_score'] = current_score
            project['sources_count'] = sources_count
            project['sources_list'] = [project.get('source', 'unknown')]

        # Calculate totals
        total_cost = 0
        district_cost = 0
        contractor_cost = 0

        for project in matched_projects:
            amount = project.get('amount', 0)
            if isinstance(amount, str):
                amount_str = amount.replace('₱', '').replace(',', '').replace(' ', '')
                try:
                    amount = float(amount_str)
                except (ValueError, AttributeError):
                    amount = 0

            total_cost += amount

            if project.get('match_type') == 'contractor':
                contractor_cost += amount
            else:
                district_cost += amount

        # Create cache data
        cache_data = {
            "success": True,
            "congressman": congressman_config['display_name'],
            "projects": matched_projects,
            "summary": {
                "total": len(matched_projects),
                "dime": len([p for p in matched_projects if p.get('source') == 'DIME']),
                "philgeps": len([p for p in matched_projects if p.get('source') == 'PhilGEPS']),
                "ssp": len([p for p in matched_projects if p.get('source') == 'SSP']),
                "infrawatch": 0,
                "microsite": 0,
                "district_projects": len(district_projects),
                "contractor_projects": len(contractor_projects)
            },
            "dashboard_stats": {
                "total_cost_all": total_cost,
                "total_projects": len(matched_projects),
                "district_count": len(district_projects),
                "district_cost": district_cost,
                "contractor_count": len(contractor_projects),
                "contractor_cost": contractor_cost
            },
            "generated_at": datetime.now().isoformat(),
            "cache_version": "1.0",
            "total_projects": len(matched_projects),
            "total_cost": f"₱{total_cost:,.2f}",
            "district_cost": f"₱{district_cost:,.2f}",
            "contractor_cost": f"₱{contractor_cost:,.2f}"
        }

        # Save cache
        cache_dir = self.cache_dir / f"congressman-projects-{congressman_slug}"
        cache_dir.mkdir(exist_ok=True)

        cache_file = cache_dir / "all-projects-cache.json"
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)

        # Create summary.json
        summary_data = {
            "total_projects": len(matched_projects),
            "total_cost": f"₱{total_cost:,.2f}",
            "district_projects": len(district_projects),
            "contractor_projects": len(contractor_projects),
            "generated_at": datetime.now().isoformat()
        }

        summary_file = cache_dir / "summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary_data, f, indent=2)

        print(f"   ✅ Generated cache with {len(matched_projects)} projects, ₱{total_cost:,.2f}")

    async def generate_all_manila_caches(self):
        """Generate caches for all Manila congressmen"""
        print("🏛️ Generating Manila congressmen caches only...")

        await self.connect_databases()
        self.load_config()
        self.load_districts()

        # Load all projects once
        all_projects = await self.load_projects_from_db()

        # Generate cache for each Manila congressman
        for congressman_name in self.target_congressmen:
            congressman_slug = congressman_name.lower().replace(' ', '-').replace('.', '')
            self.generate_congressman_cache(congressman_slug, all_projects)

        await self.dynasty_conn.close()
        await self.dime_conn.close()
        await self.philgeps_conn.close()

        print("🎯 All Manila congressmen caches generated!")

async def main():
    generator = ManilaCacheGenerator()
    await generator.generate_all_manila_caches()

if __name__ == "__main__":
    asyncio.run(main())

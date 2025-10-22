#!/usr/bin/env python3
"""
Parse SEC contractor data and update the contractors table
"""

import asyncio
import asyncpg
import os
import re
import chardet
import glob
import datetime
from typing import List, Dict, Any
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher

load_dotenv()

class SECContractorParser:
    def __init__(self):
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', 5432)),
            'user': os.getenv('POSTGRES_USER', 'budget_admin'),
            'password': os.getenv('POSTGRES_PASSWORD', ''),
            'database': 'sec'
        }
        self.philgeps_db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', 5432)),
            'user': os.getenv('POSTGRES_USER', 'budget_admin'),
            'password': os.getenv('POSTGRES_PASSWORD', ''),
            'database': 'philgeps'
        }

    def detect_encoding(self, file_path: str) -> str:
        """Detect file encoding"""
        with open(file_path, 'rb') as f:
            raw_data = f.read()
            result = chardet.detect(raw_data)
            return result.get('encoding', 'utf-8')

    def parse_sec_file(self, file_path: str) -> List[Dict[str, Any]]:
        """Parse SEC data from a single file"""
        encoding = self.detect_encoding(file_path)

        with open(file_path, 'r', encoding=encoding or 'utf-8', errors='ignore') as f:
            content = f.read()

        # Pattern to match company details
        company_pattern = r'COMPANY DETAILS\nCompany Name\n(.*?)\n\nSEC Number\n(.*?)\n\nDate Registered\n(.*?)\n\nStatus\n(.*?)\n\nAddress\n(.*?)\n\nSECONDARY LICENSE DETAILS'

        companies = []
        matches = re.findall(company_pattern, content, re.DOTALL)

        for match in matches:
            company_name = match[0].strip()  # Exact name from SEC database
            sec_number = match[1].strip()
            date_registered = match[2].strip()
            status = match[3].strip()
            address = match[4].strip()

            # Parse date
            date_obj = None
            try:
                # Try different date formats
                for fmt in ['%B %d, %Y', '%b %d, %Y', '%Y-%m-%d']:
                    try:
                        date_obj = datetime.strptime(date_registered, fmt)
                        break
                    except ValueError:
                        continue
            except:
                pass

            companies.append({
                'contractor_name': company_name,  # Exact name from SEC database
                'sec_number': sec_number,
                'date_registered': date_obj,
                'status': status,
                'address': address,
                'secondary_licenses': 'No records of secondary licenses were found.'
            })

        return companies

    async def update_contractors_table(self, contractors: List[Dict[str, Any]]):
        """Update the contractors table with SEC data
        
        Finds matching contractors by fuzzy name matching and updates their SEC data.
        """
        conn = await asyncpg.connect(**self.db_config)

        try:
            for contractor in contractors:
                sec_name = contractor['contractor_name']
                sec_number = contractor['sec_number']
                
                # Try exact match first on SEC number (if contractor was already processed)
                existing = await conn.fetchrow('''
                    SELECT id, contractor_name 
                    FROM contractors 
                    WHERE sec_number = $1
                ''', sec_number)
                
                if existing:
                    # Update existing entry
                    await conn.execute('''
                        UPDATE contractors
                        SET date_registered = $1, status = $2, address = $3, 
                            updated_at = CURRENT_TIMESTAMP
                        WHERE sec_number = $4
                    ''', contractor['date_registered'], contractor['status'],
                         contractor['address'], sec_number)
                    print(f"✅ Updated: {existing['contractor_name']}")
                    continue
                
                # Find contractor by fuzzy name matching
                all_contractors = await conn.fetch('''
                    SELECT id, contractor_name 
                    FROM contractors 
                    WHERE sec_number IS NULL OR sec_number = ''
                ''')
                
                best_match = None
                best_ratio = 0.0
                
                for db_contractor in all_contractors:
                    db_name = db_contractor['contractor_name']
                    ratio = self.calculate_similarity(sec_name, db_name)
                    
                    if ratio > best_ratio and ratio >= 0.85:  # 85% similarity threshold
                        best_ratio = ratio
                        best_match = db_contractor
                
                if best_match:
                    # Update the matched contractor with SEC data
                    await conn.execute('''
                        UPDATE contractors
                        SET sec_number = $1, date_registered = $2, status = $3, 
                            address = $4, updated_at = CURRENT_TIMESTAMP
                        WHERE id = $5
                    ''', sec_number, contractor['date_registered'], contractor['status'],
                         contractor['address'], best_match['id'])
                    print(f"✅ Matched & Updated: {best_match['contractor_name']} → {sec_name} ({best_ratio:.2%})")
                else:
                    # No match found - skip (we only update existing contractors in SEC db)
                    print(f"⚠️  No match found for: {sec_name} (skipping)")

        finally:
            await conn.close()

    def calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity using SequenceMatcher (better for variations)"""
        if not str1 or not str2:
            return 0.0
        
        s1 = str1.lower()
        s2 = str2.lower()
        
        # Exact match = 1.0 (fast path)
        if s1 == s2:
            return 1.0
        
        # Use SequenceMatcher for variations (transpositions, insertions, deletions)
        return SequenceMatcher(None, s1, s2).ratio()

    def normalize_contractor_name(self, name: str) -> str:
        """Normalize contractor name for better matching"""
        if not name:
            return ""

        # Remove common suffixes and prefixes
        name = re.sub(r'\s*(corp|corporation|inc|incorporated|ltd|limited|co|company|llc|llp)\.?\s*$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'^\s*(the\s+)?', '', name, flags=re.IGNORECASE)

        # Remove extra spaces and normalize
        name = re.sub(r'\s+', ' ', name.strip())

        return name

    async def load_flood_projects_with_jv(self):
        """Load flood projects from MeiliSearch including JV data"""
        import aiohttp

        meili_url = f"http://{os.getenv('MEILI_HOST', '10.27.79.4')}:{os.getenv('MEILI_PORT', '7700')}"
        meili_key = os.getenv('MEILI_MASTER_KEY', '0jH6Q1HHOBgJ8j3ISMx415T+mOKvURP9RA9FFpjoeco=')

        async with aiohttp.ClientSession() as session:
            headers = {'Authorization': f'Bearer {meili_key}'}

            # Get all flood projects (we'll need to paginate)
            all_projects = []
            offset = 0
            limit = 1000

            while True:
                async with session.post(
                    f'{meili_url}/indexes/bettergov_flood_control/search',
                    headers=headers,
                    json={
                        'q': '',
                        'limit': limit,
                        'offset': offset,
                        'attributesToRetrieve': [
                            'GlobalID', 'ProjectDescription', 'Contractor', 'ContractID',
                            'is_joint_venture', 'jv_partner1', 'jv_partner2'
                        ]
                    }
                ) as response:
                    if response.status != 200:
                        break

                    data = await response.json()
                    projects = data.get('hits', [])

                    if not projects:
                        break

                    all_projects.extend(projects)
                    offset += limit

                    if len(projects) < limit:
                        break

            return all_projects

    async def populate_project_contractors(self, flood_projects):
        """Populate project_contractors table with JV data in philgeps database"""
        conn = await asyncpg.connect(**self.philgeps_db_config)

        try:
            print(f"📋 Processing {len(flood_projects)} flood projects for JV data...")

            inserted = 0
            for project in flood_projects:
                global_id = project['GlobalID']
                contractor = project.get('Contractor', '')
                is_jv = project.get('is_joint_venture', False)
                jv_partner1 = project.get('jv_partner1')
                jv_partner2 = project.get('jv_partner2')

                # Handle main contractor
                if contractor:
                    await conn.execute('''
                        INSERT INTO project_contractors (project_id, contractor_name, contractor_role)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (project_id, contractor_name, contractor_role) DO NOTHING
                    ''', global_id, contractor, 'main')
                    inserted += 1

                # Handle JV partners
                if is_jv and jv_partner1:
                    await conn.execute('''
                        INSERT INTO project_contractors (project_id, contractor_name, contractor_role)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (project_id, contractor_name, contractor_role) DO NOTHING
                    ''', global_id, jv_partner1, 'jv_partner1')
                    inserted += 1

                if is_jv and jv_partner2:
                    await conn.execute('''
                        INSERT INTO project_contractors (project_id, contractor_name, contractor_role)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (project_id, contractor_name, contractor_role) DO NOTHING
                    ''', global_id, jv_partner2, 'jv_partner2')
                    inserted += 1

            print(f"✅ Inserted {inserted} project-contractor relationships")

        finally:
            await conn.close()

    async def correlate_with_existing_contracts(self):
        """Correlate SEC data with existing contractors using JV-aware matching"""
        # Connect to philgeps for project_contractors table
        philgeps_conn = await asyncpg.connect(**self.philgeps_db_config)
        # Connect to sec for contractors table
        sec_conn = await asyncpg.connect(**self.db_config)

        try:
            # Load flood projects with JV data
            print("🔄 Loading flood projects with JV data...")
            flood_projects = await self.load_flood_projects_with_jv()
            print(f"📋 Loaded {len(flood_projects)} flood projects")

            # Populate project_contractors table (in philgeps database)
            await self.populate_project_contractors(flood_projects)

            # Get all contractors from project_contractors table (from philgeps database)
            project_contractors = await philgeps_conn.fetch(
                'SELECT DISTINCT contractor_name FROM project_contractors WHERE contractor_name IS NOT NULL'
            )

            print(f"📋 Found {len(project_contractors)} unique contractors in JV data")

            # Get all contractors from our SEC contractors table (from sec database)
            sec_contractors = await sec_conn.fetch(
                'SELECT contractor_name, sec_number, status FROM contractors WHERE sec_number IS NOT NULL'
            )

            print(f"📋 Found {len(sec_contractors)} contractors in SEC contractors table")

            # Build fast lookup dictionary with normalized names
            print("🔧 Building SEC contractor lookup index...")
            sec_lookup = {}  # normalized name -> list of SEC contractors
            sec_list = []    # all SEC contractors with normalized names
            
            for sec_contractor in sec_contractors:
                normalized = self.normalize_contractor_name(sec_contractor['contractor_name'])
                # Convert Record to dict and add normalized field
                sec_dict = {
                    'contractor_name': sec_contractor['contractor_name'],
                    'sec_number': sec_contractor['sec_number'],
                    'status': sec_contractor['status'],
                    'normalized': normalized
                }
                sec_list.append(sec_dict)
                
                if normalized not in sec_lookup:
                    sec_lookup[normalized] = []
                sec_lookup[normalized].append(sec_dict)
            
            print(f"📋 Indexed {len(sec_lookup)} unique normalized SEC contractor names")

            # Matching with Score >= 0.966 threshold
            # Only accept high-confidence matches (score >= 0.966)
            valid_matches = []
            MATCH_THRESHOLD = 0.966
            
            # Statistics buckets for analysis
            score_buckets = {
                1.00: [],
                0.99: [],
                0.98: [],
                0.97: [],
                0.96: [],
                0.95: [],
                0.94: []
            }

            for project_contractor in project_contractors:
                normalized = self.normalize_contractor_name(project_contractor['contractor_name'])
                
                # Try exact match first (O(1) lookup)
                if normalized in sec_lookup:
                    sec_contractor = sec_lookup[normalized][0]
                    score_buckets[1.00].append((project_contractor['contractor_name'], 
                                               sec_contractor['contractor_name'], 
                                               sec_contractor['sec_number'], 
                                               1.0))
                    continue
                
                # Calculate similarity with all SEC contractors
                best_match = None
                best_score = 0.0
                
                for sec_contractor in sec_list:
                    score = self.calculate_similarity(normalized, sec_contractor['normalized'])
                    if score > best_score:
                        best_score = score
                        best_match = sec_contractor
                
                # Categorize by score threshold for statistics
                if best_match and best_score >= 0.94:
                    # Find which bucket this belongs to
                    for threshold in sorted(score_buckets.keys(), reverse=True):
                        if best_score >= threshold:
                            score_buckets[threshold].append((project_contractor['contractor_name'],
                                                            best_match['contractor_name'],
                                                            best_match['sec_number'],
                                                            best_score))
                            break
                    
                    # Add to valid matches if >= threshold
                    if best_score >= MATCH_THRESHOLD:
                        valid_matches.append((project_contractor['contractor_name'],
                                            best_match['contractor_name'],
                                            best_match['sec_number'],
                                            best_score))

            # Print statistics to console (captured by shell redirection)
            print("\n📊 Score Distribution Statistics:")
            print("=" * 80)
            print(f"Total project contractors: {len(project_contractors):,}")
            print(f"Total SEC contractors: {len(sec_contractors):,}")
            print()
            
            cumulative = 0
            for threshold in sorted(score_buckets.keys(), reverse=True):
                count = len(score_buckets[threshold])
                cumulative += count
                pct = (cumulative / len(project_contractors)) * 100
                print(f"Score ≥ {threshold:.2f}: {count:4d} matches (Cumulative: {cumulative:4d}, {pct:5.2f}%)")
            
            print(f"\n✅ Valid matches accepted (Score ≥ {MATCH_THRESHOLD}):")
            print(f"   Total: {len(valid_matches)} matches ({len(valid_matches)/len(project_contractors)*100:.2f}%)")
            
            # Print sample matches for each threshold
            print("\n📋 Sample Matches by Threshold:")
            print("=" * 80)
            
            for threshold in sorted(score_buckets.keys(), reverse=True):
                matches = score_buckets[threshold]
                if matches:
                    print(f"\n🎯 Score ≥ {threshold:.2f} ({len(matches)} matches):")
                    for proj_name, sec_name, sec_num, score in matches[:10]:
                        print(f"   {score:.3f}: '{proj_name}' → '{sec_name}' (SEC: {sec_num})")

        finally:
            await philgeps_conn.close()
            await sec_conn.close()

    def parse_file_wrapper(self, file_path: str) -> tuple:
        """Wrapper for parse_sec_file to work with ThreadPoolExecutor"""
        filename = os.path.basename(file_path)
        companies = self.parse_sec_file(file_path)
        return (filename, companies)

    async def run(self):
        """Main execution function"""
        print("🚀 Starting JV-aware SEC contractor data processing...")

        # Find all SEC result files
        sec_files = glob.glob('sec_scraper/sec_results/*.txt')

        print(f"📁 Found {len(sec_files)} SEC result files")
        print(f"🧵 Using 20 threads for parallel parsing...")

        all_companies = []

        # Parse all SEC files in parallel using 20 threads
        with ThreadPoolExecutor(max_workers=20) as executor:
            results = list(executor.map(self.parse_file_wrapper, sec_files))
        
        # Collect results
        for filename, companies in results:
            if companies:
                print(f"📖 Processed: {filename} - Found {len(companies)} companies")
                all_companies.extend(companies)

        print(f"\n📊 Total companies parsed: {len(all_companies)}")

        # Update contractors table
        await self.update_contractors_table(all_companies)

        # JV-aware correlation with existing contracts
        print("\n🔗 JV-aware correlating with existing contract data...")
        await self.correlate_with_existing_contracts()

        print("✅ JV-aware SEC contractor processing complete!")

if __name__ == "__main__":
    parser = SECContractorParser()
    asyncio.run(parser.run())

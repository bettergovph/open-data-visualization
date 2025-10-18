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
from difflib import SequenceMatcher

load_dotenv()

class SECContractorParser:
    def __init__(self):
        self.db_config = {
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
            company_name = match[0].strip()
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
                'contractor_name': company_name,
                'sec_number': sec_number,
                'date_registered': date_obj,
                'status': status,
                'address': address,
                'secondary_licenses': 'No records of secondary licenses were found.'
            })

        return companies

    async def update_contractors_table(self, contractors: List[Dict[str, Any]]):
        """Update the contractors table with SEC data"""
        conn = await asyncpg.connect(**self.db_config)

        try:
            for contractor in contractors:
                # Check if contractor already exists
                existing = await conn.fetchrow(
                    'SELECT id FROM contractors WHERE contractor_name = $1',
                    contractor['contractor_name']
                )

                if existing:
                    # Update existing contractor
                    await conn.execute('''
                        UPDATE contractors
                        SET sec_number = $2, date_registered = $3, status = $4,
                            address = $5, updated_at = CURRENT_TIMESTAMP
                        WHERE contractor_name = $1
                    ''', contractor['contractor_name'], contractor['sec_number'],
                         contractor['date_registered'], contractor['status'],
                         contractor['address'])
                    print(f"✅ Updated: {contractor['contractor_name']}")
                else:
                    # Insert new contractor
                    await conn.execute('''
                        INSERT INTO contractors (contractor_name, sec_number, date_registered, status, address)
                        VALUES ($1, $2, $3, $4, $5)
                    ''', contractor['contractor_name'], contractor['sec_number'],
                         contractor['date_registered'], contractor['status'],
                         contractor['address'])
                    print(f"➕ Added: {contractor['contractor_name']}")

        finally:
            await conn.close()

    def calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity ratio between two strings using SequenceMatcher"""
        if not str1 or not str2:
            return 0.0
        return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

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
        """Populate project_contractors table with JV data"""
        conn = await asyncpg.connect(**self.db_config)

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
        conn = await asyncpg.connect(**self.db_config)

        try:
            # Load flood projects with JV data
            print("🔄 Loading flood projects with JV data...")
            flood_projects = await self.load_flood_projects_with_jv()
            print(f"📋 Loaded {len(flood_projects)} flood projects")

            # Populate project_contractors table
            await self.populate_project_contractors(flood_projects)

            # Get all contractors from project_contractors table (includes JV data)
            project_contractors = await conn.fetch(
                'SELECT DISTINCT contractor_name FROM project_contractors WHERE contractor_name IS NOT NULL'
            )

            print(f"📋 Found {len(project_contractors)} unique contractors in JV data")

            # Get all contractors from our SEC contractors table
            sec_contractors = await conn.fetch(
                'SELECT contractor_name, sec_number, status FROM contractors WHERE sec_number IS NOT NULL'
            )

            print(f"📋 Found {len(sec_contractors)} contractors in SEC contractors table")

            # JV-aware fuzzy matching
            matches = 0
            strict_matches = 0
            fuzzy_matches = 0

            for project_contractor in project_contractors:
                contractor_name = self.normalize_contractor_name(project_contractor['contractor_name'])
                best_match = None
                best_score = 0.0
                best_sec_contractor = None

                for sec_contractor in sec_contractors:
                    sec_name = self.normalize_contractor_name(sec_contractor['contractor_name'])

                    # Strategy 1: Exact match after normalization
                    if contractor_name == sec_name:
                        best_score = 1.0
                        best_match = "EXACT"
                        best_sec_contractor = sec_contractor
                        break

                    # Strategy 2: High similarity ratio (> 0.9)
                    similarity = self.calculate_similarity(contractor_name, sec_name)
                    if similarity > 0.9 and similarity > best_score:
                        best_score = similarity
                        best_match = f"FUZZY_{similarity:.3f}"
                        best_sec_contractor = sec_contractor

                    # Strategy 3: Substring matching with high overlap
                    elif similarity > 0.8 and len(set(contractor_name.split()) & set(sec_name.split())) >= 2:
                        if similarity > best_score:
                            best_score = similarity
                            best_match = f"SUBSTRING_{similarity:.3f}"
                            best_sec_contractor = sec_contractor

                if best_sec_contractor:
                    if best_score >= 0.9:
                        strict_matches += 1
                        match_type = "STRICT"
                    else:
                        fuzzy_matches += 1
                        match_type = "FUZZY"

                    print(f"🔗 {match_type} JV-Match: '{project_contractor['contractor_name']}' -> '{best_sec_contractor['contractor_name']}' (Score: {best_score:.3f}, SEC: {best_sec_contractor['sec_number']})")
                    matches += 1

            print("\n📊 JV-Aware Correlation Results:")
            print(f"   • Total matches: {matches}")
            print(f"   • Strict matches (≥90%): {strict_matches}")
            print(f"   • Fuzzy matches (<90%): {fuzzy_matches}")
            print(f"   • Match rate: {matches/len(project_contractors)*100:.1f}%")

        finally:
            await conn.close()

    async def run(self):
        """Main execution function"""
        print("🚀 Starting JV-aware SEC contractor data processing...")

        # Find all SEC result files
        sec_files = glob.glob('database/sec_results/*.txt')

        print(f"📁 Found {len(sec_files)} SEC result files")

        all_companies = []

        # Parse all SEC files
        for file_path in sec_files:
            print(f"📖 Processing: {os.path.basename(file_path)}")
            companies = self.parse_sec_file(file_path)
            all_companies.extend(companies)
            print(f"   Found {len(companies)} companies")

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

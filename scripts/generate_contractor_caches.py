#!/usr/bin/env python3
"""
Script to generate contractor project caches across all provinces
This aggregates all projects for each contractor regardless of province
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

class ContractorCacheGenerator:
    """Generate cached JSON for contractor-projects across all provinces"""
    
    def __init__(self):
        self.cache_dir = Path(__file__).parent.parent / 'static' / 'data' / 'contractor-projects'
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    async def collect_all_projects(self):
        """Collect all projects from all data sources (no province filter)"""
        import asyncpg
        from flood_client import FloodControlClient
        
        print("🔄 Collecting all projects from data sources...")
        all_projects = []
        
        # Initialize connections
        dime_conn = None
        philgeps_conn = None
        client = None
        
        try:
            # Connect to DIME database
            dime_conn = await asyncpg.connect(
                host=os.getenv('DIME_DB_HOST', 'localhost'),
                port=int(os.getenv('DIME_DB_PORT', 5432)),
                user=os.getenv('DIME_DB_USER', 'postgres'),
                password=os.getenv('DIME_DB_PASSWORD', ''),
                database=os.getenv('DIME_DB_NAME', 'dime')
            )
            
            # Connect to PhilGEPS database
            philgeps_conn = await asyncpg.connect(
                host=os.getenv('PHILGEPS_DB_HOST', 'localhost'),
                port=int(os.getenv('PHILGEPS_DB_PORT', 5432)),
                user=os.getenv('PHILGEPS_DB_USER', 'postgres'),
                password=os.getenv('PHILGEPS_DB_PASSWORD', ''),
                database=os.getenv('PHILGEPS_DB_NAME', 'philgeps')
            )
            
            # Initialize MeiliSearch client
            client = FloodControlClient()
            
            # Get ALL DIME projects (no province filter)
            print("   📊 Loading ALL DIME projects...")
            dime_projects = await dime_conn.fetch('''
                SELECT project_name, contractors, cost, province, city, barangay, status, date_started, meilisearch_id
                FROM projects
                LIMIT 100000
            ''')
            print(f"   ✅ Loaded {len(dime_projects)} DIME projects")
            
            for proj in dime_projects:
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
                    "sources_list": ["DIME"],
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
            
            # Get ALL PhilGEPS projects (no province filter)
            print("   📊 Loading ALL PhilGEPS projects...")
            philgeps_projects = await philgeps_conn.fetch('''
                SELECT award_title, awardee_name, contract_amount, area_of_delivery, award_date, award_status, meilisearch_id
                FROM contracts
                LIMIT 100000
            ''')
            print(f"   ✅ Loaded {len(philgeps_projects)} PhilGEPS projects")
            
            for proj in philgeps_projects:
                amount = 0
                if proj['contract_amount']:
                    if isinstance(proj['contract_amount'], str):
                        amount = float(proj['contract_amount'].replace(',', '').replace('₱', '').replace('PHP', '').strip() or 0)
                    else:
                        amount = float(proj['contract_amount'])
                
                all_projects.append({
                    "source": "PhilGEPS",
                    "sources_list": ["PhilGEPS"],
                    "meilisearch_id": proj.get('meilisearch_id'),
                    "project_name": proj['award_title'] or "N/A",
                    "contractor": proj['awardee_name'] or "N/A",
                    "amount": amount,
                    "location": proj['area_of_delivery'] or "N/A",
                    "province": "N/A",
                    "municipality": "N/A",
                    "year": proj['award_date'].year if proj['award_date'] else "N/A",
                    "status": proj['award_status'] or "N/A",
                })
            
            # Search ALL MeiliSearch projects (no province filter)
            print("   📊 Searching ALL MeiliSearch projects...")
            projects, metadata = await client.search_projects(
                query="",
                filters="",
                limit=100000,
                offset=0
            )
            print(f"   ✅ Loaded {len(projects)} MeiliSearch projects")
            
            for proj in projects:
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
                
                all_projects.append({
                    "source": "SSP",
                    "sources_list": ["SSP"],
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
            
        finally:
            if dime_conn:
                await dime_conn.close()
            if philgeps_conn:
                await philgeps_conn.close()
        
        print(f"✅ Total projects collected: {len(all_projects)}")
        return all_projects
    
    def deduplicate_projects(self, projects):
        """Deduplicate projects based on project_name, location, and amount"""
        seen = set()
        unique_projects = []
        project_map = {}  # Map key to project for merging sources
        
        for proj in projects:
            # Create a unique key
            project_name = (proj.get('project_name') or '').strip().upper()
            location = (proj.get('location') or '').strip().upper()
            amount = proj.get('amount', 0)
            
            # Normalize amount for comparison
            if isinstance(amount, str):
                try:
                    amount = float(amount.replace(',', '').replace('₱', '').strip())
                except:
                    amount = 0
            elif not isinstance(amount, (int, float)):
                amount = 0
            
            key = (project_name, location, round(amount, 2))
            
            if key not in seen:
                seen.add(key)
                # Initialize sources_list if not present
                if 'sources_list' not in proj:
                    proj['sources_list'] = [proj.get('source', 'Unknown')]
                unique_projects.append(proj)
                project_map[key] = proj
            else:
                # Merge sources if duplicate found
                existing_proj = project_map[key]
                existing_sources = set(existing_proj.get('sources_list', [existing_proj.get('source', 'Unknown')]))
                new_source = proj.get('source', 'Unknown')
                if new_source not in existing_sources:
                    existing_sources.add(new_source)
                    existing_proj['sources_list'] = list(existing_sources)
        
        return unique_projects
    
    def group_by_contractor(self, projects):
        """Group projects by contractor"""
        projects_by_contractor = defaultdict(list)
        
        for proj in projects:
            contractor = (proj.get('contractor') or '').strip()
            if not contractor or contractor == 'N/A':
                contractor = 'Unknown'
            
            projects_by_contractor[contractor].append(proj)
        
        return dict(projects_by_contractor)
    
    def calculate_contractor_stats(self, contractor_projects):
        """Calculate statistics for a contractor's projects"""
        total = len(contractor_projects)
        
        # Count by source
        ssp_count = len([p for p in contractor_projects if 'SSP' in (p.get('sources_list', []))])
        dime_count = len([p for p in contractor_projects if 'DIME' in (p.get('sources_list', []))])
        philgeps_count = len([p for p in contractor_projects if 'PhilGEPS' in (p.get('sources_list', []))])
        
        # Calculate total cost
        total_cost = sum(
            float(p.get('amount', 0)) if isinstance(p.get('amount'), (int, float)) else 0
            for p in contractor_projects
        )
        
        # Extract provinces
        provinces = defaultdict(int)
        for proj in contractor_projects:
            location = (proj.get('location') or '').strip()
            project_name = (proj.get('project_name') or '').strip()
            combined_text = f"{location} {project_name}".upper()
            
            # Try to extract province from location/project name
            # This is a simplified version - could be enhanced
            province = "Unknown"
            for prov in [
                'CEBU', 'DAVAO', 'MANILA', 'LAGUNA', 'CAVITE', 'BULACAN', 'PAMPANGA',
                'ILOILO', 'NEGROS', 'LEYTE', 'SAMAR', 'BOHOL', 'PALAWAN', 'MINDORO',
                'BATANGAS', 'QUEZON', 'RIZAL', 'NUEVA ECIJA', 'PANGASINAN', 'ILOCOS',
                'BENGUET', 'BATAAN', 'ZAMBALES', 'TARLAC', 'PAMPANGA', 'ALBAY',
                'CAMARINES', 'SORSOGON', 'MASBATE', 'CATANDUANES', 'AKLAN', 'ANTIQUE',
                'CAPIZ', 'GUIMARAS', 'SIQUIJOR', 'BILIRAN', 'SOUTHERN LEYTE', 'EASTERN SAMAR',
                'NORTHERN SAMAR', 'WESTERN SAMAR', 'OCCIDENTAL MINDORO', 'ORIENTAL MINDORO',
                'MARINDUQUE', 'ROMBLON', 'CAMIGUIN', 'MISAMIS', 'BUKIDNON', 'LANAO',
                'SULTAN KUDARAT', 'MAGUINDANAO', 'COTABATO', 'SARANGANI', 'SULU', 'TAWI-TAWI',
                'BASILAN', 'ZAMBOANGA', 'AGUSAN', 'SURIGAO', 'DINAGAT', 'DAVAO OCCIDENTAL',
                'DAVAO ORIENTAL', 'DAVAO DEL NORTE', 'DAVAO DEL SUR', 'DAVAO DE ORO',
                'COMPOSTELA VALLEY', 'CAGAYAN', 'ISABELA', 'NUEVA VIZCAYA', 'QUIRINO',
                'IFUGAO', 'KALINGA', 'MOUNTAIN PROVINCE', 'ABRA', 'APAYAO', 'BENGUET',
                'LA UNION', 'ILOCOS NORTE', 'ILOCOS SUR', 'PANGASINAN', 'AURORA',
                'BATAAN', 'BULACAN', 'NUEVA ECIJA', 'PAMPANGA', 'TARLAC', 'ZAMBALES',
                'BATANGAS', 'CAVITE', 'LAGUNA', 'QUEZON', 'RIZAL', 'METRO MANILA'
            ]:
                if prov in combined_text:
                    province = prov.title()
                    break
            
            provinces[province] += 1
        
        provinces_list = [
            {"name": name, "count": count}
            for name, count in sorted(provinces.items(), key=lambda x: x[1], reverse=True)
        ]
        
        return {
            "total": total,
            "ssp": ssp_count,
            "dime": dime_count,
            "philgeps": philgeps_count,
            "total_cost": total_cost,
            "provinces": provinces_list
        }
    
    async def generate_all_contractor_caches(self):
        """Generate cache files for all contractors"""
        print("🚀 Starting contractor cache generation...")
        print("=" * 80)
        
        # Collect all projects
        all_projects = await self.collect_all_projects()
        
        # Deduplicate
        print("\n🔄 Deduplicating projects...")
        unique_projects = self.deduplicate_projects(all_projects)
        print(f"✅ Unique projects: {len(unique_projects)}")
        
        # Group by contractor
        print("\n🔄 Grouping projects by contractor...")
        projects_by_contractor = self.group_by_contractor(unique_projects)
        print(f"✅ Found {len(projects_by_contractor)} unique contractors")
        
        # Sort contractors by project count
        contractors_sorted = sorted(
            projects_by_contractor.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )
        
        # Generate cache for each contractor
        contractor_summaries = {}
        total_contractors = len(contractors_sorted)
        
        print(f"\n🔄 Generating cache files for {total_contractors} contractors...")
        print("=" * 80)
        
        for i, (contractor, contractor_projects) in enumerate(contractors_sorted, 1):
            print(f"\n[{i}/{total_contractors}] Processing: {contractor} ({len(contractor_projects)} projects)")
            
            try:
                # Calculate stats
                stats = self.calculate_contractor_stats(contractor_projects)
                
                # Sort projects by cost descending
                contractor_projects_sorted = sorted(
                    contractor_projects,
                    key=lambda p: float(p.get('amount', 0)) if isinstance(p.get('amount'), (int, float)) else 0,
                    reverse=True
                )
                
                # Create cache file name (sanitize contractor name)
                safe_contractor_name = contractor.lower().replace(' ', '-').replace('/', '-').replace('\\', '-')
                safe_contractor_name = ''.join(c for c in safe_contractor_name if c.isalnum() or c in '-_')
                contractor_cache_file = self.cache_dir / f'{safe_contractor_name}-cache.json'
                
                # Create cache data
                contractor_cache_data = {
                    "success": True,
                    "contractor": contractor,
                    "projects": contractor_projects_sorted,
                    "summary": {
                        "total": stats["total"],
                        "ssp": stats["ssp"],
                        "dime": stats["dime"],
                        "philgeps": stats["philgeps"]
                    },
                    "total_cost": stats["total_cost"],
                    "filter_options": {
                        "provinces": stats["provinces"]
                    },
                    "generated_at": datetime.now().isoformat(),
                    "cache_version": "1.0"
                }
                
                # Write cache file
                with open(contractor_cache_file, 'w', encoding='utf-8') as f:
                    json.dump(contractor_cache_data, f, indent=2, ensure_ascii=False)
                
                contractor_summaries[contractor] = {
                    "count": stats["total"],
                    "total_cost": stats["total_cost"],
                    "cache_file": str(contractor_cache_file.relative_to(self.cache_dir.parent))
                }
                
                print(f"   ✅ Created cache: {contractor_cache_file.name}")
                
            except Exception as e:
                print(f"   ❌ Error processing {contractor}: {e}")
                import traceback
                traceback.print_exc()
        
        # Create summary file
        summary_file = self.cache_dir / 'summary.json'
        summary_data = {
            "success": True,
            "total_contractors": len(contractor_summaries),
            "total_projects": len(unique_projects),
            "contractors": contractor_summaries,
            "generated_at": datetime.now().isoformat(),
            "cache_version": "1.0"
        }
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, indent=2, ensure_ascii=False)
        
        print("\n" + "=" * 80)
        print(f"✅ Contractor cache generation complete!")
        print(f"   Total contractors: {len(contractor_summaries)}")
        print(f"   Total projects: {len(unique_projects)}")
        print(f"   Summary file: {summary_file}")
        print("=" * 80)

async def main():
    generator = ContractorCacheGenerator()
    await generator.generate_all_contractor_caches()

if __name__ == '__main__':
    asyncio.run(main())


#!/usr/bin/env python3
"""
Generate comprehensive summary report of contractor-dynasty relationships
found through Perplexity scraping and dynasty database matching.
"""

import asyncio
import asyncpg
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List
from dotenv import load_dotenv


def load_env_from_dotenv() -> None:
    """Load environment variables from .env file"""
    root = Path(__file__).resolve().parents[3]
    env_path = root / '.env'
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


async def get_dynasty_conn():
    """Get connection to Dynasty database"""
    load_env_from_dotenv()
    load_dotenv()
    return await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
    )


async def generate_report() -> str:
    """Generate comprehensive report of contractor-dynasty relationships"""
    conn = await get_dynasty_conn()
    
    try:
        # Check if tables exist
        matches_table_exists = await conn.fetchval('''
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'contractor_dynasty_matches'
            )
        ''')
        
        # Get overall statistics
        total_affiliations = await conn.fetchval('SELECT COUNT(*) FROM company_affiliations')
        unique_companies = await conn.fetchval('SELECT COUNT(DISTINCT company_name) FROM company_affiliations')
        unique_persons = await conn.fetchval('SELECT COUNT(DISTINCT person_name) FROM company_affiliations')
        
        if matches_table_exists:
            total_matches = await conn.fetchval('SELECT COUNT(*) FROM contractor_dynasty_matches')
            unique_dynasty_matches = await conn.fetchval('SELECT COUNT(DISTINCT dynasty_full_name) FROM contractor_dynasty_matches')
        else:
            total_matches = 0
            unique_dynasty_matches = 0
        
        # Get top companies by number of officers
        top_companies = await conn.fetch('''
            SELECT 
                company_name,
                COUNT(DISTINCT person_name) as officer_count,
                COUNT(*) as total_affiliations
            FROM company_affiliations
            GROUP BY company_name
            ORDER BY officer_count DESC, total_affiliations DESC
            LIMIT 20
        ''')
        
        # Get all dynasty matches with details
        if matches_table_exists:
            dynasty_matches = await conn.fetch('''
                SELECT 
                    company_name,
                    person_name,
                    role,
                    dynasty_full_name,
                    dynasty_first_name,
                    dynasty_last_name,
                    matched_at,
                    source_csv_file
                FROM contractor_dynasty_matches
                ORDER BY matched_at DESC, company_name, person_name
            ''')
            
            # Get unique dynasty names involved
            dynasty_names = await conn.fetch('''
                SELECT DISTINCT
                    dynasty_full_name,
                    dynasty_first_name,
                    dynasty_last_name,
                    COUNT(*) as match_count
                FROM contractor_dynasty_matches
                GROUP BY dynasty_full_name, dynasty_first_name, dynasty_last_name
                ORDER BY match_count DESC, dynasty_full_name
            ''')
            
            # Get companies with dynasty connections
            companies_with_dynasty = await conn.fetch('''
                SELECT DISTINCT
                    cdm.company_name,
                    COUNT(DISTINCT cdm.person_name) as matched_officers,
                    COUNT(DISTINCT cdm.dynasty_full_name) as dynasty_connections,
                    COUNT(*) as total_matches
                FROM contractor_dynasty_matches cdm
                GROUP BY cdm.company_name
                ORDER BY matched_officers DESC, dynasty_connections DESC
            ''')
        else:
            dynasty_matches = []
            dynasty_names = []
            companies_with_dynasty = []
        
        # Build report
        report = []
        report.append("=" * 80)
        report.append("CONTRACTOR-DYNASTY RELATIONSHIP REPORT")
        report.append("=" * 80)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        report.append("OVERALL STATISTICS")
        report.append("-" * 80)
        report.append(f"Total Company Affiliations: {total_affiliations:,}")
        report.append(f"Unique Companies: {unique_companies:,}")
        report.append(f"Unique Persons (Officers/Owners/Directors): {unique_persons:,}")
        report.append(f"")
        report.append(f"Dynasty Matches Found: {total_matches:,}")
        report.append(f"Unique Dynasty Members Matched: {unique_dynasty_matches:,}")
        report.append(f"Companies with Dynasty Connections: {len(companies_with_dynasty):,}")
        report.append("")
        
        if dynasty_matches:
            report.append("=" * 80)
            report.append("DYNASTY MATCHES - DETAILED LISTING")
            report.append("=" * 80)
            report.append("")
            
            for match in dynasty_matches:
                report.append(f"Company: {match['company_name']}")
                report.append(f"  Person: {match['person_name']} ({match['role']})")
                report.append(f"  Dynasty Match: {match['dynasty_full_name']}")
                report.append(f"  Matched At: {match['matched_at']}")
                report.append(f"  Source: {match['source_csv_file']}")
                report.append("")
            
            report.append("=" * 80)
            report.append("DYNASTY MEMBERS INVOLVED")
            report.append("=" * 80)
            report.append("")
            
            for dyn in dynasty_names:
                report.append(f"{dyn['dynasty_full_name']}")
                report.append(f"  Matched in {dyn['match_count']} company relationship(s)")
                report.append("")
            
            report.append("=" * 80)
            report.append("COMPANIES WITH DYNASTY CONNECTIONS")
            report.append("=" * 80)
            report.append("")
            
            for comp in companies_with_dynasty:
                report.append(f"{comp['company_name']}")
                report.append(f"  Matched Officers: {comp['matched_officers']}")
                report.append(f"  Dynasty Connections: {comp['dynasty_connections']}")
                report.append(f"  Total Matches: {comp['total_matches']}")
                report.append("")
        
        report.append("=" * 80)
        report.append("TOP COMPANIES BY NUMBER OF OFFICERS")
        report.append("=" * 80)
        report.append("")
        
        for i, comp in enumerate(top_companies, 1):
            report.append(f"{i:2d}. {comp['company_name']}")
            report.append(f"     Officers: {comp['officer_count']}, Total Affiliations: {comp['total_affiliations']}")
            report.append("")
        
        return "\n".join(report)
    
    finally:
        await conn.close()


async def main():
    print("🔍 Generating contractor-dynasty relationship report...")
    
    report = await generate_report()
    
    # Save to file
    output_file = Path(__file__).parent / 'CONTRACTOR_DYNASTY_REPORT.txt'
    output_file.write_text(report, encoding='utf-8')
    
    print(f"✅ Report saved to: {output_file}")
    print("\n" + "=" * 80)
    print("REPORT SUMMARY")
    print("=" * 80)
    
    # Print summary
    lines = report.split('\n')
    in_stats = False
    for line in lines:
        if line.startswith("OVERALL STATISTICS"):
            in_stats = True
        elif in_stats and line.startswith("-"):
            continue
        elif in_stats and line and not line.startswith("="):
            print(line)
        elif in_stats and line.startswith("="):
            break
    
    print("\n" + "=" * 80)
    if "DYNASTY MATCHES - DETAILED LISTING" in report:
        match_section = report.split("DYNASTY MATCHES - DETAILED LISTING")[1]
        if "COMPANIES WITH DYNASTY CONNECTIONS" in match_section:
            match_details = match_section.split("COMPANIES WITH DYNASTY CONNECTIONS")[0]
            match_count = match_details.count("Company:")
            print(f"📊 Found {match_count} contractor-dynasty matches")
            print(f"📄 Full report: {output_file}")


if __name__ == '__main__':
    asyncio.run(main())


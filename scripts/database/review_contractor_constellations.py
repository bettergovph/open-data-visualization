#!/usr/bin/env python3
"""
Review and verify all contractor-mediated constellations.

This script generates a comprehensive report of all contractor connections
so they can be independently reviewed for accuracy.
"""

import asyncio
import asyncpg
import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv


def load_env_from_dotenv():
    """Load environment variables from .env file"""
    root = Path(__file__).resolve().parents[2]
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


async def get_db_connection():
    load_env_from_dotenv()
    load_dotenv()
    return await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
)


async def get_contractor_constellations(conn):
    """Get all contractor-mediated constellations for review"""
    
    print("🔍 Fetching contractor-mediated constellations...")
    
    # Get all contractor connections
    contractor_connections = await conn.fetch("""
        WITH contractor_connections AS (
            SELECT DISTINCT
                cdm1.company_name as contractor_name,
                cdm1.dynasty_full_name as person1_name,
                cdm1.dynasty_first_name as person1_first,
                cdm1.dynasty_last_name as person1_last,
                cdm1.role as person1_role,
                cdm2.dynasty_full_name as person2_name,
                cdm2.dynasty_first_name as person2_first,
                cdm2.dynasty_last_name as person2_last,
                cdm2.role as person2_role,
                cdm1.person_name as person1_original_name,
                cdm2.person_name as person2_original_name,
                cdm1.source_csv_file as source_file
            FROM contractor_dynasty_matches cdm1
            JOIN contractor_dynasty_matches cdm2 
                ON cdm1.company_name = cdm2.company_name
                AND cdm1.dynasty_full_name != cdm2.dynasty_full_name
            JOIN political_dynasties p1 
                ON UPPER(TRIM(p1.first_name)) = UPPER(TRIM(cdm1.dynasty_first_name))
                AND UPPER(TRIM(p1.last_name)) = UPPER(TRIM(cdm1.dynasty_last_name))
            JOIN political_dynasties p2 
                ON UPPER(TRIM(p2.first_name)) = UPPER(TRIM(cdm2.dynasty_first_name))
                AND UPPER(TRIM(p2.last_name)) = UPPER(TRIM(cdm2.dynasty_last_name))
            WHERE p1.id != p2.id
                AND p1.last_name != p2.last_name  -- Different families
        )
        SELECT 
            cc.contractor_name,
            cc.person1_name,
            cc.person1_first,
            cc.person1_last,
            cc.person1_role,
            cc.person1_original_name,
            cc.person2_name,
            cc.person2_first,
            cc.person2_last,
            cc.person2_role,
            cc.person2_original_name,
            cc.source_file,
            p1.id as person1_id,
            p1.position as person1_position,
            p1.province as person1_province,
            p1.year as person1_year,
            p2.id as person2_id,
            p2.position as person2_position,
            p2.province as person2_province,
            p2.year as person2_year,
            p1.last_name as person1_surname,
            p2.last_name as person2_surname
        FROM contractor_connections cc
        JOIN political_dynasties p1 
            ON UPPER(TRIM(p1.first_name)) = UPPER(TRIM(cc.person1_first))
            AND UPPER(TRIM(p1.last_name)) = UPPER(TRIM(cc.person1_last))
        JOIN political_dynasties p2 
            ON UPPER(TRIM(p2.first_name)) = UPPER(TRIM(cc.person2_first))
            AND UPPER(TRIM(p2.last_name)) = UPPER(TRIM(cc.person2_last))
        WHERE p1.id != p2.id
        ORDER BY cc.contractor_name, p1.last_name, p2.last_name
    """)
    
    print(f"✅ Found {len(contractor_connections)} contractor-mediated connections")
    
    # Group by contractor
    by_contractor = defaultdict(list)
    for conn in contractor_connections:
        contractor_name = conn['contractor_name']
        by_contractor[contractor_name].append(conn)
    
    return by_contractor, contractor_connections


async def get_perplexity_source_data(conn):
    """Get the original Perplexity source data to show what was returned"""
    
    # Check if company_affiliations table exists
    table_exists = await conn.fetchval("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'company_affiliations'
        )
    """)
    
    if not table_exists:
        return {}
    
    # Get all company affiliations from Perplexity
    affiliations = await conn.fetch("""
        SELECT 
            company_name,
            person_name,
            role,
            source_url,
            confidence_level
        FROM company_affiliations
        ORDER BY company_name, role, person_name
    """)
    
    by_company = defaultdict(list)
    for aff in affiliations:
        by_company[aff['company_name']].append(dict(aff))
    
    return by_company


async def generate_review_report():
    """Generate comprehensive review report"""
    
    db_conn = await get_db_connection()
    
    try:
        print("=" * 80)
        print("CONTRACTOR-MEDIATED CONSTELLATIONS REVIEW REPORT")
        print("=" * 80)
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # Get contractor constellations
        by_contractor, all_connections = await get_contractor_constellations(db_conn)
        
        # Get Perplexity source data
        perplexity_data = await get_perplexity_source_data(db_conn)
        
        # Generate report
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("CONTRACTOR-MEDIATED CONSTELLATIONS REVIEW REPORT")
        report_lines.append("=" * 80)
        report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        report_lines.append(f"Total Contractors: {len(by_contractor)}")
        report_lines.append(f"Total Connections: {len(all_connections)}\n")
        report_lines.append("=" * 80 + "\n")
        
        # Sort contractors by number of connections
        sorted_contractors = sorted(by_contractor.items(), key=lambda x: len(x[1]), reverse=True)
        
        for contractor_name, connections in sorted_contractors:
            report_lines.append(f"\n{'=' * 80}")
            report_lines.append(f"CONTRACTOR: {contractor_name}")
            report_lines.append(f"{'=' * 80}")
            report_lines.append(f"Total Connections: {len(connections)}")
            
            # Show Perplexity source data if available
            if contractor_name in perplexity_data:
                perplexity_officers = perplexity_data[contractor_name]
                report_lines.append(f"\n📋 Perplexity API Reported Officers:")
                for officer in perplexity_officers:
                    report_lines.append(f"   • {officer['person_name']} ({officer['role']}) - Confidence: {officer.get('confidence_level', 'N/A')}")
                    if officer.get('source_url'):
                        report_lines.append(f"     Source: {officer['source_url']}")
            else:
                report_lines.append(f"\n⚠️  No Perplexity source data found for this contractor")
            
            # Show connections grouped by family pairs
            family_pairs = defaultdict(list)
            for conn in connections:
                pair_key = f"{conn['person1_surname']} ↔ {conn['person2_surname']}"
                family_pairs[pair_key].append(conn)
            
            report_lines.append(f"\n🔗 Family Connections ({len(family_pairs)} pairs):")
            
            for pair_key, pair_connections in sorted(family_pairs.items()):
                report_lines.append(f"\n   {pair_key}")
                
                # Show all connections for this pair
                for conn in pair_connections:
                    report_lines.append(f"\n      Person 1: {conn['person1_name']}")
                    report_lines.append(f"         Original Name from Perplexity: {conn.get('person1_original_name', 'N/A')}")
                    report_lines.append(f"         Role in Company: {conn['person1_role']}")
                    report_lines.append(f"         Political Position: {conn.get('person1_position', 'N/A')}")
                    report_lines.append(f"         Province: {conn.get('person1_province', 'N/A')}")
                    report_lines.append(f"         Year: {conn.get('person1_year', 'N/A')}")
                    
                    report_lines.append(f"\n      Person 2: {conn['person2_name']}")
                    report_lines.append(f"         Original Name from Perplexity: {conn.get('person2_original_name', 'N/A')}")
                    report_lines.append(f"         Role in Company: {conn['person2_role']}")
                    report_lines.append(f"         Political Position: {conn.get('person2_position', 'N/A')}")
                    report_lines.append(f"         Province: {conn.get('person2_province', 'N/A')}")
                    report_lines.append(f"         Year: {conn.get('person2_year', 'N/A')}")
                    
                    report_lines.append(f"\n      Source File: {conn.get('source_file', 'N/A')}")
                    report_lines.append(f"      {'─' * 70}")
        
        # Write report to file
        report_content = '\n'.join(report_lines)
        report_file = 'CONTRACTOR_CONSTELLATIONS_REVIEW.txt'
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        print(f"\n✅ Review report generated: {report_file}")
        print(f"   Total contractors reviewed: {len(by_contractor)}")
        print(f"   Total connections: {len(all_connections)}")
        
        # Also generate JSON for programmatic review
        json_data = {
            'generated_at': datetime.now().isoformat(),
            'total_contractors': len(by_contractor),
            'total_connections': len(all_connections),
            'contractors': {}
        }
        
        for contractor_name, connections in sorted_contractors:
            json_data['contractors'][contractor_name] = {
                'total_connections': len(connections),
                'perplexity_officers': perplexity_data.get(contractor_name, []),
                'connections': []
            }
            
            for conn in connections:
                json_data['contractors'][contractor_name]['connections'].append({
                    'person1': {
                        'name': conn['person1_name'],
                        'original_name': conn.get('person1_original_name'),
                        'role': conn['person1_role'],
                        'position': conn.get('person1_position'),
                        'province': conn.get('person1_province'),
                        'year': conn.get('person1_year'),
                        'id': conn['person1_id']
                    },
                    'person2': {
                        'name': conn['person2_name'],
                        'original_name': conn.get('person2_original_name'),
                        'role': conn['person2_role'],
                        'position': conn.get('person2_position'),
                        'province': conn.get('person2_province'),
                        'year': conn.get('person2_year'),
                        'id': conn['person2_id']
                    },
                    'source_file': conn.get('source_file')
                })
        
        json_file = 'CONTRACTOR_CONSTELLATIONS_REVIEW.json'
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ JSON report generated: {json_file}")
        
        # Print summary to console
        print(f"\n{'=' * 80}")
        print("SUMMARY")
        print(f"{'=' * 80}")
        print(f"Top 10 contractors by connection count:")
        for i, (contractor_name, connections) in enumerate(sorted_contractors[:10], 1):
            print(f"   {i}. {contractor_name}: {len(connections)} connections")
        
    finally:
        if db_conn:
            await db_conn.close()


if __name__ == '__main__':
    asyncio.run(generate_review_report())


#!/usr/bin/env python3
"""
Generate Flood-DIME Contractor Correlation Analysis

This script analyzes the correlation between flood control projects and DIME infrastructure projects
by matching contractors across both databases and generating correlation statistics.

Data Sources:
- Flood Control: DPWH Flood Control Projects Database (via MeiliSearch)
- DIME: Department of Budget and Management - Digital Information for Monitoring and Evaluation (via PostgreSQL)

Output:
- JSON files with contractor correlation data for each year and all years combined
"""

import asyncio
import asyncpg
import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path
from difflib import SequenceMatcher
import requests
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DIME_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'user': os.getenv('POSTGRES_USER', 'budget_admin'),
    'password': os.getenv('POSTGRES_PASSWORD', ''),
    'database': 'dime'
}

# MeiliSearch configuration
MEILI_HTTP_ADDR = os.getenv('MEILI_HTTP_ADDR', '127.0.0.1:7700')
MEILI_MASTER_KEY = os.getenv('MEILI_MASTER_KEY', '0jH6Q1HHOBgJ8j3ISMx415T+mOKvURP9RA9FFpjoeco=')

def normalize_contractor_name(name: str) -> str:
    """Normalize contractor name for matching"""
    if not name:
        return ""
    
    # Convert to uppercase and remove common suffixes
    name = name.upper().strip()
    
    # Remove common suffixes
    suffixes = [
        " INC", " INC.", " INCORPORATED",
        " CORP", " CORP.", " CORPORATION", 
        " CO", " CO.", " COMPANY",
        " LTD", " LTD.", " LIMITED",
        " LLC", " L.L.C.",
        " JV", " J.V.", " JOINT VENTURE",
        " & CO", " & CO.",
        " ENTERPRISES", " ENTERPRISE",
        " CONSTRUCTION", " CONSTRUCTION CO",
        " BUILDERS", " BUILDER",
        " ENGINEERING", " ENGINEERS",
        " CONSULTANTS", " CONSULTANT"
    ]
    
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)].strip()
            break
    
    return name

def fuzzy_match_contractors(flood_contractors: List[str], dime_contractors: List[str], threshold: float = 0.8) -> Dict[str, str]:
    """Match contractors between flood and DIME databases using fuzzy matching"""
    matches = {}
    
    for flood_contractor in flood_contractors:
        if not flood_contractor:
            continue
            
        flood_normalized = normalize_contractor_name(flood_contractor)
        if not flood_normalized:
            continue
            
        best_match = None
        best_score = 0
        
        for dime_contractor in dime_contractors:
            if not dime_contractor:
                continue
                
            dime_normalized = normalize_contractor_name(dime_contractor)
            if not dime_normalized:
                continue
            
            # Calculate similarity score
            score = SequenceMatcher(None, flood_normalized, dime_normalized).ratio()
            
            if score > best_score and score >= threshold:
                best_score = score
                best_match = dime_contractor
        
        if best_match:
            matches[flood_contractor] = best_match
    
    return matches

async def get_flood_contractors() -> Dict[str, Any]:
    """Get flood control contractors from MeiliSearch"""
    try:
        # Search for flood control projects
        search_url = f"http://{MEILI_HTTP_ADDR}/indexes/bettergov_flood_control/search"
        headers = {}
        if MEILI_MASTER_KEY:
            headers['Authorization'] = f'Bearer {MEILI_MASTER_KEY}'
        
        # Get all flood control projects
        search_data = {
            "q": "",
            "limit": 10000,
            "attributesToRetrieve": ["Contractor", "ProjectDescription", "ContractCost", "InfraYear"]
        }
        
        response = requests.post(search_url, json=search_data, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        projects = data.get('hits', [])
        
        # Group by contractor
        contractors = {}
        for project in projects:
            contractor = project.get('Contractor', '').strip()
            if not contractor:
                continue
                
            if contractor not in contractors:
                contractors[contractor] = {
                    'contractor': contractor,
                    'flood_projects': 0,
                    'flood_total_cost': 0,
                    'years': set()
                }
            
            contractors[contractor]['flood_projects'] += 1
            contractors[contractor]['flood_total_cost'] += float(project.get('ContractCost', 0) or 0)
            contractors[contractor]['years'].add(int(project.get('InfraYear', 0) or 0))
        
        # Convert years set to list and sort
        for contractor_data in contractors.values():
            contractor_data['years'] = sorted(list(contractor_data['years']))
        
        return contractors
        
    except Exception as e:
        print(f"❌ Error getting flood contractors: {e}")
        return {}

async def get_dime_contractors() -> Dict[str, Any]:
    """Get DIME contractors from PostgreSQL database"""
    conn = None
    try:
        conn = await asyncpg.connect(**DIME_CONFIG)
        
        # Query DIME projects (excluding flood-related projects)
        # Since contractors is an array, we need to unnest it
        query = """
        SELECT 
            unnest(contractors) as contractor,
            project_name,
            cost,
            EXTRACT(YEAR FROM contract_completion_date) as year
        FROM projects 
        WHERE contractors IS NOT NULL 
        AND array_length(contractors, 1) > 0
        AND LOWER(project_name) NOT LIKE '%flood%'
        AND LOWER(project_name) NOT LIKE '%drainage%'
        AND LOWER(project_name) NOT LIKE '%canal%'
        AND LOWER(project_name) NOT LIKE '%river%'
        AND LOWER(project_name) NOT LIKE '%water%'
        AND LOWER(project_name) NOT LIKE '%sewer%'
        ORDER BY contractor, year
        """
        
        rows = await conn.fetch(query)
        
        # Group by contractor
        contractors = {}
        for row in rows:
            contractor = row['contractor'].strip()
            if not contractor:
                continue
                
            if contractor not in contractors:
                contractors[contractor] = {
                    'contractor': contractor,
                    'dime_non_flood_projects': 0,
                    'dime_non_flood_cost': 0,
                    'years': set()
                }
            
            contractors[contractor]['dime_non_flood_projects'] += 1
            contractors[contractor]['dime_non_flood_cost'] += float(row['cost'] or 0)
            contractors[contractor]['years'].add(int(row['year'] or 0))
        
        # Convert years set to list and sort
        for contractor_data in contractors.values():
            contractor_data['years'] = sorted(list(contractor_data['years']))
        
        return contractors
        
    except Exception as e:
        print(f"❌ Error getting DIME contractors: {e}")
        return {}
    finally:
        if conn:
            await conn.close()

def generate_correlation_data(flood_contractors: Dict[str, Any], dime_contractors: Dict[str, Any], year_filter: Optional[int] = None) -> Dict[str, Any]:
    """Generate correlation data between flood and DIME contractors"""
    
    # Filter by year if specified
    if year_filter:
        flood_contractors = {
            k: v for k, v in flood_contractors.items() 
            if year_filter in v.get('years', [])
        }
        dime_contractors = {
            k: v for k, v in dime_contractors.items() 
            if year_filter in v.get('years', [])
        }
    
    # Get contractor names for matching
    flood_names = list(flood_contractors.keys())
    dime_names = list(dime_contractors.keys())
    
    # Match contractors
    contractor_matches = fuzzy_match_contractors(flood_names, dime_names)
    
    # Generate correlation data
    correlation_data = {}
    
    for flood_contractor, flood_data in flood_contractors.items():
        # Initialize contractor data
        contractor_id = f"contractor_{len(correlation_data) + 1}"
        
        correlation_data[contractor_id] = {
            'contractor': flood_contractor,
            'flood_projects': flood_data['flood_projects'],
            'flood_total_cost': flood_data['flood_total_cost'],
            'dime_non_flood_projects': 0,
            'dime_non_flood_cost': 0,
            'total_projects': flood_data['flood_projects'],
            'total_value': flood_data['flood_total_cost'],
            'diversification_ratio': 0,
            'correlation_score': 0
        }
        
        # Check if contractor has DIME projects
        if flood_contractor in contractor_matches:
            dime_contractor = contractor_matches[flood_contractor]
            if dime_contractor in dime_contractors:
                dime_data = dime_contractors[dime_contractor]
                
                correlation_data[contractor_id]['dime_non_flood_projects'] = dime_data['dime_non_flood_projects']
                correlation_data[contractor_id]['dime_non_flood_cost'] = dime_data['dime_non_flood_cost']
                correlation_data[contractor_id]['total_projects'] = flood_data['flood_projects'] + dime_data['dime_non_flood_projects']
                correlation_data[contractor_id]['total_value'] = flood_data['flood_total_cost'] + dime_data['dime_non_flood_cost']
                
                # Calculate diversification ratio (DIME projects / total projects)
                if correlation_data[contractor_id]['total_projects'] > 0:
                    correlation_data[contractor_id]['diversification_ratio'] = dime_data['dime_non_flood_projects'] / correlation_data[contractor_id]['total_projects']
                
                # Calculate correlation score (simple metric based on project overlap)
                if flood_data['flood_projects'] > 0 and dime_data['dime_non_flood_projects'] > 0:
                    correlation_data[contractor_id]['correlation_score'] = min(1.0, (dime_data['dime_non_flood_projects'] / flood_data['flood_projects']))
    
    # Generate summary statistics
    contractors_list = list(correlation_data.values())
    total_contractors = len(contractors_list)
    total_flood_projects = sum(c['flood_projects'] for c in contractors_list)
    total_dime_projects = sum(c['dime_non_flood_projects'] for c in contractors_list)
    total_flood_value = sum(c['flood_total_cost'] for c in contractors_list)
    total_dime_value = sum(c['dime_non_flood_cost'] for c in contractors_list)
    
    # Calculate averages
    avg_correlation_score = sum(c['correlation_score'] for c in contractors_list) / total_contractors if total_contractors > 0 else 0
    avg_diversification_ratio = sum(c['diversification_ratio'] for c in contractors_list) / total_contractors if total_contractors > 0 else 0
    
    summary = {
        'total_contractors': total_contractors,
        'total_flood_projects': total_flood_projects,
        'total_dime_projects': total_dime_projects,
        'total_flood_value': total_flood_value,
        'total_dime_value': total_dime_value,
        'average_correlation_score': avg_correlation_score,
        'average_diversification_ratio': avg_diversification_ratio
    }
    
    return {
        'contractors': correlation_data,
        'summary': summary,
        'generated_at': datetime.now().isoformat(),
        'cache_version': '1.0'
    }

async def generate_correlation_files():
    """Generate all correlation JSON files"""
    print("🔍 Starting Flood-DIME correlation analysis...")
    
    # Get data from both sources
    print("📊 Fetching flood control contractors...")
    flood_contractors = await get_flood_contractors()
    print(f"✅ Found {len(flood_contractors)} flood contractors")
    
    print("📊 Fetching DIME contractors...")
    dime_contractors = await get_dime_contractors()
    print(f"✅ Found {len(dime_contractors)} DIME contractors")
    
    if not flood_contractors:
        print("❌ No flood contractors found. Check MeiliSearch connection.")
        return
    
    if not dime_contractors:
        print("❌ No DIME contractors found. Check PostgreSQL connection.")
        return
    
    # Generate files for each year and all years
    years = [2020, 2021, 2022, 2023, 2024, 2025]
    output_dir = Path("static/data")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate all years data
    print("📈 Generating all years correlation data...")
    all_years_data = generate_correlation_data(flood_contractors, dime_contractors)
    
    # Save all years file
    all_years_file = output_dir / "flood_dime_contractor_correlation_all_years.json"
    with open(all_years_file, 'w', encoding='utf-8') as f:
        json.dump(all_years_data, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved all years data: {all_years_file}")
    
    # Generate yearly data
    for year in years:
        print(f"📈 Generating {year} correlation data...")
        year_data = generate_correlation_data(flood_contractors, dime_contractors, year)
        
        # Save yearly file
        year_file = output_dir / f"flood_dime_contractor_correlation_{year}.json"
        with open(year_file, 'w', encoding='utf-8') as f:
            json.dump(year_data, f, indent=2, ensure_ascii=False)
        print(f"✅ Saved {year} data: {year_file}")
    
    # Generate default file (all years)
    default_file = output_dir / "flood_dime_contractor_correlation.json"
    with open(default_file, 'w', encoding='utf-8') as f:
        json.dump(all_years_data, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved default data: {default_file}")
    
    print("🎉 Flood-DIME correlation analysis complete!")

if __name__ == "__main__":
    asyncio.run(generate_correlation_files())

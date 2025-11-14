#!/usr/bin/env python3
"""
Find missing matches for projects with no matches by using looser matching criteria.
Uses correct matches as examples to understand matching patterns.
"""

import asyncio
import asyncpg
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from flood_client import FloodControlClient
from infrawatch_postgres_client import get_infrawatch_connection
from flood_db_client import search_flood_projects

load_dotenv()


def parse_amount(amount_str: str) -> Optional[float]:
    """Parse amount string to float, handling commas and currency symbols."""
    if not amount_str:
        return None
    try:
        cleaned = re.sub(r'[₱,\s]', '', str(amount_str))
        if not cleaned:
            return None
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def normalize_title(title: str) -> str:
    """Normalize title by removing leading numbers and extra whitespace."""
    if not title:
        return ""
    normalized = re.sub(r'^\d+\s*[.-]?\s*', '', title.strip())
    return normalized


def extract_chainage_markers(title: str) -> set:
    """Extract chainage markers (K followed by digits) from title."""
    if not title:
        return set()
    patterns = re.findall(r'K\d+[+\-]?\d*', title.upper())
    return set(patterns)


def amount_matches(amount1: Optional[float], amount2: Optional[float], max_diff: float = 2000000.0) -> bool:
    """Check if two amounts match within absolute difference (default 2M for looser matching)."""
    if amount1 is None or amount2 is None:
        return False
    if amount1 == 0 or amount2 == 0:
        return False
    diff = abs(amount1 - amount2)
    return diff <= max_diff


async def find_loose_match_flood(flood_client: FloodControlClient, project_title: str, amount: Optional[float]) -> Optional[Dict[str, Any]]:
    """Find matching project in Flood DB using looser criteria."""
    try:
        normalized_title = normalize_title(project_title)
        flood_projects, _ = await flood_client.search_projects(
            query=normalized_title,
            limit=30  # Check more results
        )
        
        title_chainages = extract_chainage_markers(project_title)
        title_words = set(re.findall(r'\b\w{3,}\b', normalized_title.lower()))
        
        best_match = None
        best_score = 0
        
        for proj in flood_projects:
            proj_desc = (proj.ProjectDescription or "")
            proj_desc_normalized = normalize_title(proj_desc)
            proj_desc_lower = proj_desc_normalized.lower()
            
            proj_chainages = extract_chainage_markers(proj_desc)
            chainage_match = False
            if title_chainages and proj_chainages:
                chainage_match = len(title_chainages.intersection(proj_chainages)) > 0
            
            proj_words = set(re.findall(r'\b\w{3,}\b', proj_desc_lower))
            matching_words = title_words.intersection(proj_words)
            title_score = len(matching_words) / max(len(title_words), 1) if title_words else 0
            
            # Looser threshold: 0.4 instead of 0.6
            if not chainage_match and title_score < 0.4:
                continue
            
            db_amount = None
            try:
                contract_cost = proj.ContractCost
                if isinstance(contract_cost, str):
                    db_amount = parse_amount(contract_cost)
                elif contract_cost is not None:
                    db_amount = float(contract_cost)
            except (ValueError, TypeError):
                pass
            
            amount_match = True
            if amount is not None and db_amount is not None:
                amount_match = amount_matches(amount, db_amount, max_diff=2000000.0)  # 2M tolerance
            elif amount is not None and db_amount is None:
                # Looser: 0.5 instead of 0.7
                if not chainage_match and title_score < 0.5:
                    continue
            
            score = title_score
            if chainage_match:
                score += 0.5
            if amount_match and amount is not None:
                score += 0.2
            
            if score > best_score:
                best_score = score
                best_match = {
                    "contract_id": proj.ContractID or proj.ProjectID or "",
                    "contractor": proj.Contractor or "",
                    "db_project_title": proj_desc,
                    "db_amount": db_amount
                }
        
        # Looser final threshold: 0.25 instead of 0.3
        if best_match and best_score >= 0.25:
            return best_match
        
        return None
    except Exception as e:
        print(f"  ⚠️  Error checking Flood DB: {e}")
        return None


async def find_loose_match_infrawatch(infrawatch_conn: asyncpg.Connection, project_title: str, amount: Optional[float], gaa_page: str = "") -> Optional[Dict[str, Any]]:
    """Find matching project in Infrawatch using looser criteria."""
    try:
        normalized_title = normalize_title(project_title)
        title_chainages = extract_chainage_markers(project_title)
        title_words = set(re.findall(r'\b\w{3,}\b', normalized_title.lower()))
        
        # Wrong contract IDs to exclude
        WRONG_CONTRACT_IDS = {
            "60": ["22GL0059"],
            "394": ["22D00057"],
            "632": ["24CJ0230"],
            "635": ["24CJ0230"],
            "659": ["23BE0018"],
            "664": ["22JD0059"],
            "849": ["23EG0016"],
        }
        
        query = """
            SELECT data
            FROM infrawatch_projects_rows
            WHERE data->>'Project Name' ILIKE $1
               OR data->>'Project' ILIKE $1
               OR data->>'Project Title' ILIKE $1
               OR data->>'Project Description' ILIKE $1
               OR data->>'Contract Details' ILIKE $1
            LIMIT 30
        """
        rows = await infrawatch_conn.fetch(query, f"%{normalized_title}%")
        
        best_match = None
        best_score = 0
        
        for row in rows:
            data_raw = row.get('data')
            if not data_raw:
                continue
            
            if isinstance(data_raw, str):
                try:
                    import json
                    data = json.loads(data_raw)
                except:
                    continue
            else:
                data = data_raw
            
            db_title = (data.get('Project Name') or 
                       data.get('Project') or 
                       data.get('Project Title') or 
                       data.get('Project Description') or "")
            
            if not db_title:
                continue
            
            db_title_normalized = normalize_title(db_title)
            proj_chainages = extract_chainage_markers(db_title)
            proj_words = set(re.findall(r'\b\w{3,}\b', db_title_normalized.lower()))
            
            chainage_match = False
            if title_chainages and proj_chainages:
                chainage_match = len(title_chainages.intersection(proj_chainages)) > 0
            
            matching_words = title_words.intersection(proj_words)
            title_score = len(matching_words) / max(len(title_words), 1) if title_words else 0
            
            # Looser threshold: 0.4
            if not chainage_match and title_score < 0.4:
                continue
            
            amount_fields = ['Contract Amount', 'Amount', 'Project Cost', 'Cost', 'Value']
            db_amount = None
            for field in amount_fields:
                val = data.get(field)
                if val:
                    db_amount = parse_amount(str(val))
                    if db_amount:
                        break
            
            amount_match = True
            if amount is not None and db_amount is not None:
                amount_match = amount_matches(amount, db_amount, max_diff=2000000.0)
            elif amount is not None and db_amount is None:
                if not chainage_match and title_score < 0.5:
                    continue
            
            score = title_score
            if chainage_match:
                score += 0.5
            if amount_match and amount is not None:
                score += 0.2
            
            if score > best_score:
                contract_id = data.get('Contract ID') or data.get('Contract Number') or data.get('Contract No') or ""
                
                # Skip wrong contract IDs
                if gaa_page in WRONG_CONTRACT_IDS:
                    wrong_ids = WRONG_CONTRACT_IDS[gaa_page]
                    if contract_id in wrong_ids:
                        continue
                
                best_score = score
                contractor = data.get('Contractor') or data.get('Awardee') or ""
                
                best_match = {
                    "contract_id": contract_id,
                    "contractor": contractor,
                    "db_project_title": db_title,
                    "db_amount": db_amount
                }
        
        if best_match and best_score >= 0.25:
            return best_match
        
        return None
    except Exception as e:
        print(f"  ⚠️  Error checking Infrawatch DB: {e}")
        return None


async def main():
    print("🔍 Finding Missing Matches Using Looser Criteria")
    print("=" * 60)
    
    # Load current cache
    cache_path = Path(__file__).parent.parent / "static" / "data" / "zaldy_dpwh_projects_cache.json"
    with open(cache_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    projects = data.get('projects', [])
    
    # Find projects with no matches
    no_match_projects = []
    for project in projects:
        found_any = (project.get('found_flood') or project.get('found_dime') or 
                    project.get('found_philgeps') or project.get('found_infrawatch'))
        if not found_any:
            no_match_projects.append(project)
    
    print(f"📊 Found {len(no_match_projects)} projects with no matches")
    print(f"   Total projects: {len(projects)}\n")
    
    if not no_match_projects:
        print("✅ All projects have matches!")
        return
    
    # Connect to databases
    print("🔌 Connecting to databases...")
    infrawatch_conn = await get_infrawatch_connection()
    flood_client = FloodControlClient()
    
    print("  ✅ Connected to Infrawatch DB")
    print("  ✅ Initialized Flood DB client\n")
    
    # Try to find matches with looser criteria
    new_matches = 0
    for idx, project in enumerate(no_match_projects, 1):
        project_title = project.get('project_title', '')
        amount_str = project.get('amount', '')
        amount = parse_amount(amount_str) if amount_str else None
        gaa_page = project.get('gaa_page', '').replace('vetoed/', '').strip()
        
        print(f"[{idx}/{len(no_match_projects)}] Trying: {project_title[:60]}...")
        if amount:
            print(f"  Amount: ₱{amount:,.0f}")
        
        # Try Flood DB with looser criteria
        flood_match = await find_loose_match_flood(flood_client, project_title, amount)
        
        # Try Infrawatch with looser criteria
        infrawatch_match = await find_loose_match_infrawatch(infrawatch_conn, project_title, amount, gaa_page)
        
        # Update project if we found a match
        if flood_match or infrawatch_match:
            # Prefer Infrawatch over Flood
            match = infrawatch_match if infrawatch_match else flood_match
            
            project['contract_id'] = match.get('contract_id', '')
            project['contractor'] = match.get('contractor', '')
            project['db_project_title'] = match.get('db_project_title', '')
            project['db_amount'] = match.get('db_amount')
            
            if flood_match:
                project['found_flood'] = True
            if infrawatch_match:
                project['found_infrawatch'] = True
            
            new_matches += 1
            print(f"  ✅ Found match!")
            print(f"  📋 Contract ID: {match.get('contract_id', '')}")
            if match.get('contractor'):
                print(f"  👤 Contractor: {match.get('contractor', '')[:50]}")
        else:
            print(f"  ❌ No match found with looser criteria")
    
    # Update statistics
    total_projects = len(projects)
    found_flood_count = sum(1 for p in projects if p['found_flood'])
    found_dime_count = sum(1 for p in projects if p['found_dime'])
    found_philgeps_count = sum(1 for p in projects if p['found_philgeps'])
    found_infrawatch_count = sum(1 for p in projects if p['found_infrawatch'])
    
    data['statistics'] = {
        'total_projects': total_projects,
        'found_flood': found_flood_count,
        'found_dime': found_dime_count,
        'found_philgeps': found_philgeps_count,
        'found_infrawatch': found_infrawatch_count
    }
    
    # Save updated cache
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\n📊 Results:")
    print(f"  New matches found: {new_matches}")
    print(f"  Updated statistics:")
    print(f"    Found in Flood DB: {found_flood_count}")
    print(f"    Found in DIME: {found_dime_count}")
    print(f"    Found in PhilGEPS: {found_philgeps_count}")
    print(f"    Found in Infrawatch: {found_infrawatch_count}")
    print(f"\n✅ Cache updated: {cache_path}")


if __name__ == "__main__":
    asyncio.run(main())


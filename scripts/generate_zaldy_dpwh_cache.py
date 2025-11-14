#!/usr/bin/env python3
"""
Generate cached JSON for Zaldy DPWH projects with database tags.
This script checks each DPWH project against Flood, DIME, PhilGEPS, and Infrawatch databases
by matching both title and amount, and saves the results to a cache file for fast API responses.
"""

import asyncio
import asyncpg
import csv
import json
import os
import re
from difflib import SequenceMatcher
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from flood_client import FloodControlClient
from infrawatch_postgres_client import get_infrawatch_connection
from flood_db_client import search_flood_projects

# Load environment variables
load_dotenv()


def parse_amount(amount_str: str) -> Optional[float]:
    """Parse amount string to float, handling commas and currency symbols."""
    if not amount_str:
        return None
    try:
        # Remove commas, currency symbols, and whitespace
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
    # Remove leading numbers and following whitespace/dots
    normalized = re.sub(r'^\d+\s*[.-]?\s*', '', title.strip())
    return normalized


# Define wrong contract IDs to filter out for specific GAA pages
# All matches with these contract IDs will be dropped
WRONG_CONTRACT_IDS = {
    "60": ["22GL0059"],  # GAA 60: wrong contract ID
    "88": ["22DQ0079"],  # GAA 88: wrong match (road vs flood control)
    "394": ["22D00057"],  # GAA 394: wrong contract ID
    "632": ["24CJ0230"],  # GAA 632: wrong segment
    "634": ["24A00008"],  # GAA 634: wrong match (road vs flood control)
    "635": ["24CJ0230"],  # GAA 635: wrong segment
    "659": ["23BE0018"],  # GAA 659: wrong contract ID
    "664": ["22JD0059"],  # GAA 664: wrong contract ID
    "849": ["23EG0016"],  # GAA 849: wrong contract ID (vetoed)
}

# Define correct contract IDs for specific GAA pages
CORRECT_CONTRACT_IDS = {
    "60": ["25GK0112", "25GL0110"],
    "70": ["25OG0071"],
    "75": ["18DE0011"],  # Maybe, but retain
    "119": ["25OG0146", "25OG0147", "25OG0101"],
    "209": ["25D00200"],
    "247": ["25OH0099", "25OH0105"],
    "253": ["18OB0164"],
    "259": ["25OG0063"],
    "389": ["320102107252000", "320102107253000", "320102107254000", "320102107255000", "22CD0005"],  # All correct + maybe
    "390": ["320102107256000"],
    "394": ["24DH0040"],
    "664": ["300234100345000", "23L00042", "23JB0029"],  # Correct + maybe (phase 2 and 3)
}

# GAA pages that should have stricter matching (wrong matches - tighten)
# Note: 632, 635, 659, 849 are not here because only specific contract IDs are wrong, not all matches
STRICT_GAA_PAGES = {"133", "641", "642", "643", "658"}

# GAA pages that are correct (retain current matching)
CORRECT_GAA_PAGES = {"209", "259", "75", "70", "253", "394", "390", "247", "60", "119", "664", "389"}

# GAA pages that are "maybe" (retain, attempt to loosen a bit but retain if no more candidate)
MAYBE_GAA_PAGES = {"75", "389", "664"}



def fuzzy_title_match(title1: str, title2: str) -> float:
    """Calculate fuzzy match score between two titles using SequenceMatcher."""
    if not title1 or not title2:
        return 0.0
    norm1 = normalize_title(title1).lower()
    norm2 = normalize_title(title2).lower()
    return SequenceMatcher(None, norm1, norm2).ratio()

def extract_chainage_markers(title: str) -> set:
    """Extract chainage markers (K followed by digits, like K0015+400) from title."""
    if not title:
        return set()
    # Find all patterns like K0015+400, K0015+(-400), K0015, etc.
    patterns = re.findall(r'K\d+[+\-]?\d*', title.upper())
    return set(patterns)


def amount_matches(amount1: Optional[float], amount2: Optional[float], max_diff: float = 1000000.0) -> bool:
    """Check if two amounts match within absolute difference (default 1M)."""
    if amount1 is None or amount2 is None:
        return False
    if amount1 == 0 or amount2 == 0:
        return False
    diff = abs(amount1 - amount2)
    return diff <= max_diff


async def find_flood_match(flood_client: FloodControlClient, project_title: str, amount: Optional[float], gaa_page: str = "") -> Optional[Dict[str, Any]]:
    """Find matching project in Flood DB and return ContractID, Contractor, DB title, and amount."""
    try:
        # Normalize title (remove leading numbers)
        normalized_title = normalize_title(project_title)
        flood_projects, _ = await flood_client.search_projects(
            query=normalized_title,
            limit=20
        )
        
        # Extract chainage markers and key words from normalized title
        title_chainages = extract_chainage_markers(project_title)
        title_words = set(re.findall(r'\b\w{3,}\b', normalized_title.lower()))
        
        best_match = None
        best_score = 0
        
        for proj in flood_projects:
            proj_desc = (proj.ProjectDescription or "")
            proj_desc_normalized = normalize_title(proj_desc)
            proj_desc_lower = proj_desc_normalized.lower()
            
            # Extract chainage markers from DB title
            proj_chainages = extract_chainage_markers(proj_desc)
            
            # Check chainage match (strong indicator)
            chainage_match = False
            if title_chainages and proj_chainages:
                # If both have chainages, they should overlap
                chainage_match = len(title_chainages.intersection(proj_chainages)) > 0
            
            # Calculate title match score (how many key words match)
            proj_words = set(re.findall(r'\b\w{3,}\b', proj_desc_lower))
            matching_words = title_words.intersection(proj_words)
            title_score = len(matching_words) / max(len(title_words), 1) if title_words else 0
            # Calculate fuzzy string similarity score
            fuzzy_score = fuzzy_title_match(project_title, proj_desc)
            # Combine scores (weighted average: 60% word overlap, 40% fuzzy)
            title_score = (title_score * 0.6) + (fuzzy_score * 0.4)
            
            # Adjust threshold based on GAA page
            min_title_score = 0.5  # Default (lowered with fuzzy matching)
            if gaa_page in STRICT_GAA_PAGES:
                min_title_score = 0.7  # Stricter for wrong GAA pages (lowered with fuzzy matching)
            elif gaa_page in MAYBE_GAA_PAGES:
                min_title_score = 0.5  # Slightly looser for maybe pages
            elif gaa_page not in CORRECT_GAA_PAGES and gaa_page:
                min_title_score = 0.4  # Looser for not mentioned GAA pages (with fuzzy matching)
            
            # Require either chainage match OR strong title match
            if not chainage_match and title_score < min_title_score:
                continue
            
            # Get amount from DB
            db_amount = None
            try:
                contract_cost = proj.ContractCost
                if isinstance(contract_cost, str):
                    db_amount = parse_amount(contract_cost)
                elif contract_cost is not None:
                    db_amount = float(contract_cost)
            except (ValueError, TypeError):
                pass
            
            # Check amount match if available
            amount_match = True
            if amount is not None and db_amount is not None:
                amount_match = amount_matches(amount, db_amount, max_diff=1000000.0)
            elif amount is not None and db_amount is None:
                # If CSV has amount but DB doesn't, require strong match
                min_score_no_amount = 0.6
                if gaa_page in STRICT_GAA_PAGES:
                    min_score_no_amount = 0.6  # Stricter (with fuzzy matching)
                elif gaa_page in MAYBE_GAA_PAGES:
                    min_score_no_amount = 0.6  # Slightly looser for maybe pages
                elif gaa_page not in CORRECT_GAA_PAGES and gaa_page:
                    min_score_no_amount = 0.5  # Looser (with fuzzy matching)
                if not chainage_match and title_score < min_score_no_amount:
                    continue
            
            # Calculate overall score
            score = title_score
            if chainage_match:
                score += 0.5  # Strong bonus for chainage match
            if amount_match and amount is not None:
                score += 0.2  # Bonus for amount match
            
            if score > best_score:
                best_score = score
                best_match = {
                    "contract_id": proj.ContractID or proj.ProjectID or "",
                    "contractor": proj.Contractor or "",
                    "db_project_title": proj_desc,
                    "db_amount": db_amount
                }
        
        if best_match:
            return best_match
        
        # Fallback to PostgreSQL flood DB
        try:
            flood_projects_pg, _ = await search_flood_projects(
                query=normalized_title,
                limit=20
            )
            
            title_chainages = extract_chainage_markers(project_title)
            title_words = set(re.findall(r'\b\w{3,}\b', normalized_title.lower()))
            best_match_pg = None
            best_score_pg = 0
            
            for proj in flood_projects_pg:
                proj_desc = (proj.get("ProjectDescription") or "")
                proj_desc_normalized = normalize_title(proj_desc)
                proj_desc_lower = proj_desc_normalized.lower()
                proj_chainages = extract_chainage_markers(proj_desc)
                
                chainage_match = False
                if title_chainages and proj_chainages:
                    chainage_match = len(title_chainages.intersection(proj_chainages)) > 0
                
                proj_words = set(re.findall(r'\b\w{3,}\b', proj_desc_lower))
                matching_words = title_words.intersection(proj_words)
                title_score = len(matching_words) / max(len(title_words), 1) if title_words else 0
                # Calculate fuzzy string similarity score
                fuzzy_score = fuzzy_title_match(project_title, proj_desc)
                # Combine scores (weighted average: 60% word overlap, 40% fuzzy)
                title_score = (title_score * 0.6) + (fuzzy_score * 0.4)
                
                min_title_score = 0.6
                if gaa_page in STRICT_GAA_PAGES:
                    min_title_score = 0.75
                elif gaa_page in MAYBE_GAA_PAGES:
                    min_title_score = 0.5
                elif gaa_page not in CORRECT_GAA_PAGES and gaa_page:
                    min_title_score = 0.5
                if not chainage_match and title_score < min_title_score:
                    continue
                
                db_amount = proj.get("ContractCost", 0)
                if isinstance(db_amount, str):
                    db_amount = parse_amount(db_amount)
                elif db_amount:
                    db_amount = float(db_amount)
                else:
                    db_amount = None
                
                amount_match = True
                if amount is not None and db_amount is not None:
                    amount_match = amount_matches(amount, db_amount, max_diff=1000000.0)
                elif amount is not None and db_amount is None:
                    min_score_no_amount = 0.6
                    if gaa_page in STRICT_GAA_PAGES:
                        min_score_no_amount = 0.8
                    elif gaa_page in MAYBE_GAA_PAGES:
                        min_score_no_amount = 0.6
                    elif gaa_page not in CORRECT_GAA_PAGES and gaa_page:
                        min_score_no_amount = 0.6
                    if not chainage_match and title_score < min_score_no_amount:
                        continue
                
                score = title_score
                if chainage_match:
                    score += 0.5
                if amount_match and amount is not None:
                    score += 0.2
                
                if score > best_score_pg:
                    best_score_pg = score
                    best_match_pg = {
                        "contract_id": proj.get("ContractID") or proj.get("ProjectID") or "",
                        "contractor": proj.get("Contractor") or "",
                        "db_project_title": proj_desc,
                        "db_amount": db_amount
                    }
            
            return best_match_pg if best_score_pg >= 0.3 else None
        except Exception:
            return None
    except Exception as e:
        print(f"  ⚠️  Error checking Flood DB: {e}")
        return None


async def find_dime_match(dime_conn: asyncpg.Connection, project_title: str, amount: Optional[float], gaa_page: str = "") -> Optional[Dict[str, Any]]:
    """Find matching project in DIME DB and return contract info."""
    try:
        normalized_title = normalize_title(project_title)
        title_chainages = extract_chainage_markers(project_title)
        dime_query = """
            SELECT project_code, contractors, cost, project_name, description
            FROM projects
            WHERE (project_name ILIKE $1 OR description ILIKE $1)
            LIMIT 20
        """
        rows = await dime_conn.fetch(dime_query, f"%{normalized_title}%")
        
        # Extract key words from normalized title
        title_words = set(re.findall(r'\b\w{3,}\b', normalized_title.lower()))
        
        best_match = None
        best_score = 0
        
        for row in rows:
            # Calculate title match score
            proj_name = normalize_title(row.get('project_name') or "")
            proj_desc = normalize_title(row.get('description') or "")
            combined_text = f"{proj_name} {proj_desc}"
            proj_chainages = extract_chainage_markers(combined_text)
            
            chainage_match = False
            if title_chainages and proj_chainages:
                chainage_match = len(title_chainages.intersection(proj_chainages)) > 0
            
            combined_lower = combined_text.lower()
            proj_words = set(re.findall(r'\b\w{3,}\b', combined_lower))
            matching_words = title_words.intersection(proj_words)
            title_score = len(matching_words) / max(len(title_words), 1) if title_words else 0
            # Calculate fuzzy string similarity score
            fuzzy_score = fuzzy_title_match(project_title, combined_text)
            # Combine scores (weighted average: 60% word overlap, 40% fuzzy)
            title_score = (title_score * 0.6) + (fuzzy_score * 0.4)
            
            min_title_score = 0.6
            if gaa_page in STRICT_GAA_PAGES:
                min_title_score = 0.75
            elif gaa_page in MAYBE_GAA_PAGES:
                min_title_score = 0.5
            elif gaa_page not in CORRECT_GAA_PAGES and gaa_page:
                min_title_score = 0.5
            if not chainage_match and title_score < min_title_score:
                continue
            
            # Get amount from DB
            db_amount = float(row['cost']) if row['cost'] else None
            
            # Check amount match if available
            amount_match = True
            if amount is not None and db_amount is not None:
                amount_match = amount_matches(amount, db_amount, max_diff=1000000.0)
            elif amount is not None and db_amount is None:
                min_score_no_amount = 0.6
                if gaa_page in STRICT_GAA_PAGES:
                    min_score_no_amount = 0.8
                elif gaa_page in MAYBE_GAA_PAGES:
                    min_score_no_amount = 0.6
                elif gaa_page not in CORRECT_GAA_PAGES and gaa_page:
                    min_score_no_amount = 0.6
                if not chainage_match and title_score < min_score_no_amount:
                    continue
            
            score = title_score
            if chainage_match:
                score += 0.5
            if amount_match and amount is not None:
                score += 0.2
            
            if score > best_score:
                best_score = score
                contractors = row.get('contractors', [])
                contractor_str = ", ".join(contractors) if isinstance(contractors, list) else (contractors or "")
                
                db_title = proj_name or proj_desc or (row.get('project_name') or row.get('description') or "")
                
                best_match = {
                    "contract_id": row.get('project_code') or "",
                    "contractor": contractor_str,
                    "db_project_title": db_title,
                    "db_amount": db_amount
                }
        
        return best_match if best_score >= 0.3 else None
    except Exception as e:
        print(f"  ⚠️  Error checking DIME DB: {e}")
        return None


async def find_philgeps_match(philgeps_conn: asyncpg.Connection, project_title: str, amount: Optional[float], gaa_page: str = "") -> Optional[Dict[str, Any]]:
    """Find matching project in PhilGEPS DB and return contract info."""
    try:
        normalized_title = normalize_title(project_title)
        title_chainages = extract_chainage_markers(project_title)
        philgeps_query = """
            SELECT contract_no, awardee_name, contract_amount, award_title, notice_title
            FROM contracts
            WHERE (award_title ILIKE $1 OR notice_title ILIKE $1)
            LIMIT 20
        """
        rows = await philgeps_conn.fetch(philgeps_query, f"%{normalized_title}%")
        
        # Extract key words from normalized title
        title_words = set(re.findall(r'\b\w{3,}\b', normalized_title.lower()))
        
        best_match = None
        best_score = 0
        
        for row in rows:
            # Calculate title match score
            award_title = normalize_title(row.get('award_title') or "")
            notice_title = normalize_title(row.get('notice_title') or "")
            combined_text = f"{award_title} {notice_title}"
            proj_chainages = extract_chainage_markers(combined_text)
            
            chainage_match = False
            if title_chainages and proj_chainages:
                chainage_match = len(title_chainages.intersection(proj_chainages)) > 0
            
            combined_lower = combined_text.lower()
            proj_words = set(re.findall(r'\b\w{3,}\b', combined_lower))
            matching_words = title_words.intersection(proj_words)
            title_score = len(matching_words) / max(len(title_words), 1) if title_words else 0
            # Calculate fuzzy string similarity score
            fuzzy_score = fuzzy_title_match(project_title, combined_text)
            # Combine scores (weighted average: 60% word overlap, 40% fuzzy)
            title_score = (title_score * 0.6) + (fuzzy_score * 0.4)
            
            min_title_score = 0.6
            if gaa_page in STRICT_GAA_PAGES:
                min_title_score = 0.75
            elif gaa_page in MAYBE_GAA_PAGES:
                min_title_score = 0.5
            elif gaa_page not in CORRECT_GAA_PAGES and gaa_page:
                min_title_score = 0.5
            if not chainage_match and title_score < min_title_score:
                continue
            
            # Get amount from DB
            db_amount = float(row['contract_amount']) if row['contract_amount'] else None
            
            # Check amount match if available
            amount_match = True
            if amount is not None and db_amount is not None:
                amount_match = amount_matches(amount, db_amount, max_diff=1000000.0)
            elif amount is not None and db_amount is None:
                min_score_no_amount = 0.6
                if gaa_page in STRICT_GAA_PAGES:
                    min_score_no_amount = 0.8
                elif gaa_page in MAYBE_GAA_PAGES:
                    min_score_no_amount = 0.6
                elif gaa_page not in CORRECT_GAA_PAGES and gaa_page:
                    min_score_no_amount = 0.6
                if not chainage_match and title_score < min_score_no_amount:
                    continue
            
            score = title_score
            if chainage_match:
                score += 0.5
            if amount_match and amount is not None:
                score += 0.2
            
            if score > best_score:
                best_score = score
                db_title = award_title or notice_title or (row.get('award_title') or row.get('notice_title') or "")
                
                best_match = {
                    "contract_id": row.get('contract_no') or "",
                    "contractor": row.get('awardee_name') or "",
                    "db_project_title": db_title,
                    "db_amount": db_amount
                }
        
        min_final_score = 0.2
        if gaa_page in STRICT_GAA_PAGES:
            min_final_score = 0.4
        elif gaa_page in MAYBE_GAA_PAGES:
            min_final_score = 0.2
        elif gaa_page not in CORRECT_GAA_PAGES and gaa_page:
            min_final_score = 0.2
        return best_match if best_score >= min_final_score else None
    except Exception as e:
        print(f"  ⚠️  Error checking PhilGEPS DB: {e}")
        return None


async def find_infrawatch_match(infrawatch_conn: asyncpg.Connection, project_title: str, amount: Optional[float], gaa_page: str = "") -> Optional[Dict[str, Any]]:
    """Find matching project in Infrawatch DB and return contract info."""
    if not infrawatch_conn:
        return None
    
    try:
        normalized_title = normalize_title(project_title)
        title_chainages = extract_chainage_markers(project_title)
        title_words = set(re.findall(r'\b\w{3,}\b', normalized_title.lower()))
        
        infrawatch_query = """
            SELECT data
            FROM infrawatch_projects_rows
            WHERE data->>'Project Name' ILIKE $1
               OR data->>'Project' ILIKE $1
               OR data->>'Project Title' ILIKE $1
               OR data->>'Project Description' ILIKE $1
               OR data->>'Contract Details' ILIKE $1
            LIMIT 20
        """
        rows = await infrawatch_conn.fetch(infrawatch_query, f"%{normalized_title}%")
        
        best_match = None
        best_score = 0
        
        for row in rows:
            # Handle both dict and string data
            data_raw = row.get('data')
            if isinstance(data_raw, str):
                try:
                    data = json.loads(data_raw)
                except json.JSONDecodeError:
                    continue
            elif isinstance(data_raw, dict):
                data = data_raw
            else:
                continue
            
            # Get project title from database
            db_title = (data.get('Project Name') or 
                       data.get('Project') or 
                       data.get('Project Title') or 
                       data.get('Project Description') or 
                       data.get('Contract Details') or "")
            
            if not db_title:
                continue
            
            # Extract chainage markers and words from DB title
            db_title_normalized = normalize_title(db_title)
            proj_chainages = extract_chainage_markers(db_title)
            proj_words = set(re.findall(r'\b\w{3,}\b', db_title_normalized.lower()))
            
            # Check chainage match
            chainage_match = False
            if title_chainages and proj_chainages:
                chainage_match = len(title_chainages.intersection(proj_chainages)) > 0
            
            # Calculate title match score
            matching_words = title_words.intersection(proj_words)
            title_score = len(matching_words) / max(len(title_words), 1) if title_words else 0
            # Calculate fuzzy string similarity score
            fuzzy_score = fuzzy_title_match(project_title, db_title)
            # Combine scores (weighted average: 60% word overlap, 40% fuzzy)
            title_score = (title_score * 0.6) + (fuzzy_score * 0.4)
            
            # Adjust threshold based on GAA page
            min_title_score = 0.6
            if gaa_page in STRICT_GAA_PAGES:
                min_title_score = 0.75
            elif gaa_page in MAYBE_GAA_PAGES:
                min_title_score = 0.5
            elif gaa_page not in CORRECT_GAA_PAGES and gaa_page:
                min_title_score = 0.5
            if not chainage_match and title_score < min_title_score:
                continue
            
            # Get amount from DB
            amount_fields = ['Contract Amount', 'Amount', 'Project Cost', 'Cost', 'Value']
            db_amount = None
            for field in amount_fields:
                val = data.get(field)
                if val:
                    db_amount = parse_amount(str(val))
                    if db_amount:
                        break
            
            # Check amount match if available
            amount_match = True
            if amount is not None and db_amount is not None:
                amount_match = amount_matches(amount, db_amount, max_diff=1000000.0)
            elif amount is not None and db_amount is None:
                min_score_no_amount = 0.6
                if gaa_page in STRICT_GAA_PAGES:
                    min_score_no_amount = 0.8
                elif gaa_page in MAYBE_GAA_PAGES:
                    min_score_no_amount = 0.6
                elif gaa_page not in CORRECT_GAA_PAGES and gaa_page:
                    min_score_no_amount = 0.6
                if not chainage_match and title_score < min_score_no_amount:
                    continue
            
            # Calculate overall score
            score = title_score
            if chainage_match:
                score += 0.5
            if amount_match and amount is not None:
                score += 0.2
            
            if score > best_score:
                best_score = score
                contract_id = (data.get('Contract ID') or 
                              data.get('Contract Number') or 
                              data.get('Project ID') or 
                              data.get('ID') or "")
                
                contractor = (data.get('Contractor') or 
                             data.get('Awardee') or 
                             data.get('Awardee Name') or "")
                
                best_match = {
                    "contract_id": contract_id,
                    "contractor": contractor,
                    "db_project_title": db_title,
                    "db_amount": db_amount
                }
        
        min_final_score = 0.2
        if gaa_page in STRICT_GAA_PAGES:
            min_final_score = 0.4
        elif gaa_page in MAYBE_GAA_PAGES:
            min_final_score = 0.2
        elif gaa_page not in CORRECT_GAA_PAGES and gaa_page:
            min_final_score = 0.2
        return best_match if best_score >= min_final_score else None
    except Exception as e:
        print(f"  ⚠️  Error checking Infrawatch DB: {e}")
        return None


async def generate_cache() -> Dict[str, Any]:
    """Generate cache for DPWH projects with database tags."""
    print("🚀 Generating Zaldy DPWH Projects Cache")
    print("=" * 60)
    
    # Read the CSV file
    script_dir = Path(__file__).resolve().parent.parent
    csv_path = script_dir / "database" / "dpwh_projects_combined.csv"
    
    if not csv_path.exists():
        return {
            "success": False,
            "error": f"DPWH projects CSV file not found at {csv_path}",
            "generated_at": datetime.now().isoformat()
        }
    
    print(f"📄 Reading CSV file: {csv_path}")
    projects = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            amount_str = row.get("Amount", "").strip()
            amount = parse_amount(amount_str)
            gaa_page = row.get("GAA Page", "").strip()
            projects.append({
                "project_title": row.get("Project Title", "").strip(),
                "gaa_page": gaa_page,
                "amount": amount_str,
                "amount_parsed": amount
            })
    
    print(f"✅ Loaded {len(projects)} projects from CSV")
    print()
    
    # Connect to databases
    print("🔌 Connecting to databases...")
    dime_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_DIME', 'dime')
    )
    print("  ✅ Connected to DIME DB")
    
    philgeps_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database=os.getenv('POSTGRES_DB_PHILGEPS', 'philgeps')
    )
    print("  ✅ Connected to PhilGEPS DB")
    
    infrawatch_conn = await get_infrawatch_connection()
    if infrawatch_conn:
        print("  ✅ Connected to Infrawatch DB")
    else:
        print("  ⚠️  Could not connect to Infrawatch DB (continuing without it)")
    
    # Initialize Flood client
    try:
        flood_client = FloodControlClient()
        print("  ✅ Initialized Flood DB client")
    except Exception as e:
        print(f"  ⚠️  Could not initialize Flood client: {e}")
        flood_client = None
    
    print()
    
    # Check each project against databases
    results = []
    total = len(projects)
    
    for idx, project in enumerate(projects, 1):
        project_title = project["project_title"]
        amount = project["amount_parsed"]
        
        if not project_title:
            continue
        
        print(f"[{idx}/{total}] Checking: {project_title[:60]}...")
        if amount:
            print(f"  Amount: ₱{amount:,.0f}")
        
        # Check all databases and get match details
        flood_match = None
        dime_match = None
        philgeps_match = None
        infrawatch_match = None
        
        # Get GAA page for matching adjustments
        gaa_page = project.get("gaa_page", "")
        
        if flood_client:
            flood_match = await find_flood_match(flood_client, project_title, amount, gaa_page)
        
        dime_match = await find_dime_match(dime_conn, project_title, amount, gaa_page)
        philgeps_match = await find_philgeps_match(philgeps_conn, project_title, amount, gaa_page)
        
        if infrawatch_conn:
            infrawatch_match = await find_infrawatch_match(infrawatch_conn, project_title, amount, gaa_page)
        
        # For wrong GAA pages (133, 641, 642, 643, 658, 632, 635, 659, 849), reject all matches
        if gaa_page in STRICT_GAA_PAGES:
            flood_match = None
            dime_match = None
            philgeps_match = None
            infrawatch_match = None
        
        # Determine which databases found matches
        found_flood = flood_match is not None
        found_dime = dime_match is not None
        found_philgeps = philgeps_match is not None
        found_infrawatch = infrawatch_match is not None
        
        # Get contract ID, contractor, DB title, and DB amount from first match found (priority: Flood > DIME > PhilGEPS > Infrawatch)
        # But filter out wrong contract IDs for specific GAA pages
        contract_id = ""
        contractor = ""
        db_project_title = ""
        db_amount = None
        
        # Collect all matches
        all_matches = []
        if flood_match:
            all_matches.append(("flood", flood_match))
        if dime_match:
            all_matches.append(("dime", dime_match))
        if philgeps_match:
            all_matches.append(("philgeps", philgeps_match))
        if infrawatch_match:
            all_matches.append(("infrawatch", infrawatch_match))        # Filter matches based on GAA page rules
        # Normalize GAA page (remove "vetoed/" prefix)
        gaa_page_normalized = gaa_page.replace("vetoed/", "").strip() if gaa_page else ""
        
        filtered_matches = []
        for source, match in all_matches:
            match_contract_id = match.get("contract_id", "")
            
            # Check if this contract ID should be filtered out
            if gaa_page in WRONG_CONTRACT_IDS:
                wrong_ids = WRONG_CONTRACT_IDS[gaa_page]
                if match_contract_id in wrong_ids:
                    continue  # Skip wrong contract IDs
            
            # For GAA pages with specific correct contract IDs, only keep those
            if gaa_page in CORRECT_CONTRACT_IDS:
                correct_ids = CORRECT_CONTRACT_IDS[gaa_page]
                if correct_ids and match_contract_id not in correct_ids:
                    continue  # Skip wrong contract IDs
            
            # For GAA pages with correct contract IDs, prioritize them
            if gaa_page in CORRECT_CONTRACT_IDS:
                correct_ids = CORRECT_CONTRACT_IDS[gaa_page]
                if correct_ids and match_contract_id in correct_ids:
                    # Prioritize correct contract IDs
                    filtered_matches.insert(0, (source, match))
                    continue
            
            filtered_matches.append((source, match))
        
        # Use first filtered match (or first match if no filtering needed)
        if filtered_matches:
            source, match = filtered_matches[0]
            contract_id = match.get("contract_id", "")
            contractor = match.get("contractor", "")
            db_project_title = match.get("db_project_title", "")
            db_amount = match.get("db_amount")
        elif all_matches:
            # Fallback to first match if all were filtered (shouldn't happen)
            source, match = all_matches[0]
            contract_id = match.get("contract_id", "")
            contractor = match.get("contractor", "")
            db_project_title = match.get("db_project_title", "")
            db_amount = match.get("db_amount")
        
        # Show results
        tags = []
        if found_flood:
            tags.append("Flood")
        if found_dime:
            tags.append("DIME")
        if found_philgeps:
            tags.append("PhilGEPS")
        if found_infrawatch:
            tags.append("Infrawatch")
        
        if tags:
            print(f"  ✅ Found in: {', '.join(tags)}")
            if contract_id:
                print(f"  📋 Contract ID: {contract_id}")
            if contractor:
                print(f"  👤 Contractor: {contractor[:50]}")
        else:
            print(f"  ❌ Not found in any database")                # Extract PhilGEPS ID if PhilGEPS match exists
        philgeps_id = ""
        if philgeps_match:
            philgeps_id = philgeps_match.get("contract_id", "")
        
        # Final check: Clear wrong contract IDs completely
        gaa_page_normalized_final = gaa_page.replace("vetoed/", "").strip() if gaa_page else ""
        if gaa_page_normalized_final in WRONG_CONTRACT_IDS:
            wrong_ids = WRONG_CONTRACT_IDS[gaa_page_normalized_final]
            if contract_id in wrong_ids:
                # Clear all match data for wrong contract IDs
                contract_id = ""
                contractor = ""
                db_project_title = ""
                db_amount = None
                found_flood = False
                found_dime = False
                found_philgeps = False
                found_infrawatch = False
                philgeps_id = ""
        
        results.append({
            "project_title": project_title,
            "gaa_page": project.get("gaa_page", ""),
            "amount": project["amount"],
            "found_flood": found_flood,
            "found_dime": found_dime,
            "found_philgeps": found_philgeps,
            "found_infrawatch": found_infrawatch,
            "contract_id": contract_id,
            "philgeps_id": philgeps_id,
            "contractor": contractor,
            "db_project_title": db_project_title,
            "db_amount": db_amount
        })
    
    # Close connections
    await dime_conn.close()
    await philgeps_conn.close()
    if infrawatch_conn:
        await infrawatch_conn.close()
    
    # Sort results by GAA page ascending (lower GAA page first)
    def sort_key(project):
        gaa_page = project.get("gaa_page", "")
        # Convert to int for numeric sorting, handle non-numeric values
        try:
            return int(gaa_page) if gaa_page and gaa_page.isdigit() else 0
        except (ValueError, TypeError):
            return 0
    
    results.sort(key=sort_key, reverse=False)
    
    # Calculate statistics
    total_projects = len(results)
    found_flood_count = sum(1 for p in results if p["found_flood"])
    found_dime_count = sum(1 for p in results if p["found_dime"])
    found_philgeps_count = sum(1 for p in results if p["found_philgeps"])
    found_infrawatch_count = sum(1 for p in results if p["found_infrawatch"])
    
    print()
    print("📊 Statistics:")
    print(f"  Total projects: {total_projects}")
    print(f"  Found in Flood DB: {found_flood_count}")
    print(f"  Found in DIME: {found_dime_count}")
    print(f"  Found in PhilGEPS: {found_philgeps_count}")
    print(f"  Found in Infrawatch: {found_infrawatch_count}")
    
    return {
        "success": True,
        "projects": results,
        "total": total_projects,
        "statistics": {
            "found_flood": found_flood_count,
            "found_dime": found_dime_count,
            "found_philgeps": found_philgeps_count,
            "found_infrawatch": found_infrawatch_count
        },
        "generated_at": datetime.now().isoformat(),
        "cache_version": "2.0"
    }


def save_json_cache(data: Dict[str, Any], output_file: str) -> bool:
    """Save data to JSON cache file."""
    try:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Cache saved to: {output_path}")
        return True
    except Exception as e:
        print(f"❌ Error saving cache: {e}")
        return False


async def main():
    """Main function."""
    try:
        data = await generate_cache()
        
        if data.get("success"):
            # Save to cache file
            script_dir = Path(__file__).resolve().parent.parent
            output_file = script_dir / "static" / "data" / "zaldy_dpwh_projects_cache.json"
            success = save_json_cache(data, str(output_file))
            
            if success:
                print()
                print("🎉 Cache generation complete!")
                print(f"  • Output: {output_file}")
                return 0
            else:
                print()
                print("❌ Failed to save cache file")
                return 1
        else:
            print()
            print(f"❌ Error generating cache: {data.get('error', 'Unknown error')}")
            return 1
            
    except Exception as e:
        print()
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

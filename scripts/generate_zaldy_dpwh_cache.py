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
    "88": ["22DQ0079"],  # GAA 88: wrong contract ID
    "133": ["22CD0070"],  # GAA 133: wrong contract ID
    "209": ["23D00168"],  # GAA 209: wrong contract ID
    "394": ["22D00057"],  # GAA 394: wrong contract ID
    "528": ["21PA0235"],  # GAA 528: wrong contract ID
    "542": ["24E00052"],  # GAA 542: wrong contract ID
    "632": ["24CJ0230"],  # GAA 632: wrong segment
    "634": ["24A00008"],  # GAA 634: wrong contract ID
    "635": ["24CJ0230"],  # GAA 635: wrong segment
    "659": ["23BE0018"],  # GAA 659: wrong contract ID
    "664": ["22JD0059"],  # GAA 664: wrong contract ID (also all matches are wrong - Abutment A vs B)
    "849": ["23EG0016"],  # GAA 849: wrong contract ID (vetoed)
}

# Define correct contract IDs for specific GAA pages
CORRECT_CONTRACT_IDS = {
    "60": ["25GK0112", "25GL0110"],
    "70": ["25OG0071"],
    "75": ["18DE0011"],  # Correct
    "119": ["25OG0146", "25OG0147", "25OG0101"],
    "209": ["25D00200"],
    "247": ["25OH0099", "25OH0105"],
    "253": ["18OB0164"],
    "259": ["25OG0063"],
    "389": ["320102107252000", "320102107253000", "320102107254000", "320102107255000", "22CD0005"],  # All correct + maybe
    "390": ["320102107256000"],
    "394": ["24DH0040"],
    # 664 removed - all matches are wrong (Abutment A vs Abutment B)
}

# GAA pages that should have stricter matching (wrong matches - tighten)
# Note: 632, 635, 659, 849 are not here because only specific contract IDs are wrong, not all matches
# 641, 642: wrong municipality - reject all matches
# 643, 644: have special search terms, should allow matches
# 664: all matches are wrong (Abutment A vs Abutment B in CSV)
STRICT_GAA_PAGES = {"133", "641", "642", "658", "664"}

# GAA pages that are correct (retain current matching)
# 664 removed - all matches are wrong (Abutment A vs Abutment B)
# 75 and 389 moved from maybe to correct
CORRECT_GAA_PAGES = {"209", "259", "75", "70", "253", "394", "390", "247", "60", "119", "389"}


def extract_chainage_markers(title: str) -> set:
    """Extract chainage markers (K followed by digits, like K0015+400) from title."""
    if not title:
        return set()
    # Find all patterns like K0015+400, K0015+(-400), K0015, etc.
    patterns = re.findall(r'K\d+[+\-]?\d*', title.upper())
    
    # Also find "Chainage" patterns (e.g., "Chainage 000", "Chainage 491")
    # Convert them to K format (K000, K491)
    chainage_patterns = re.findall(r'Chainage\s+(\d+)', title, re.IGNORECASE)
    for chainage_num in chainage_patterns:
        # Pad with zeros to 3 digits if needed, or use as-is
        patterns.append(f"K{chainage_num.zfill(3)}")
    
    return set(patterns)


def extract_chainage_base_markers(title: str) -> set:
    """Extract base chainage markers (K followed by digits, like K0032) for SQL search."""
    if not title:
        return set()
    # Extract base chainages (K followed by digits, before + or -)
    patterns = re.findall(r'K\d+', title.upper())
    
    # Also find "Chainage" patterns and convert to K format
    chainage_patterns = re.findall(r'Chainage\s+(\d+)', title, re.IGNORECASE)
    for chainage_num in chainage_patterns:
        # Pad with zeros to 3 digits if needed
        patterns.append(f"K{chainage_num.zfill(3)}")
    
    return set(patterns)


def extract_chainage_with_offsets(title: str) -> set:
    """Extract chainage markers with offsets (K0032 + 057, K0032 + 885) for high-confidence matching."""
    if not title:
        return set()
    # Find patterns like K0032 + 057, K0032 + 885 (with spaces around +)
    patterns = re.findall(r'K\d+\s*\+\s*\d+', title.upper())
    # Also find patterns without spaces: K0032+057
    patterns_no_space = re.findall(r'K\d+\+\d+', title.upper())
    all_patterns = set(patterns + patterns_no_space)
    
    # Also find "Chainage" patterns and convert to K format
    # For "Chainage 000 - Chainage 491", we want K000 and K491
    chainage_patterns = re.findall(r'Chainage\s+(\d+)', title, re.IGNORECASE)
    for chainage_num in chainage_patterns:
        # Pad with zeros to 3 digits if needed
        all_patterns.add(f"K{chainage_num.zfill(3)}")
    
    return all_patterns


def amount_matches(amount1: Optional[float], amount2: Optional[float], max_diff: float = 1000000.0) -> bool:
    """Check if two amounts match within percentage-based threshold (default 20% or 1M, whichever is larger)."""
    if amount1 is None or amount2 is None:
        return False
    if amount1 == 0 or amount2 == 0:
        return False
    
    # Use percentage-based matching: 20% difference or 1M, whichever is larger
    # This prevents matching 4M vs 100M (75% difference) but allows 100M vs 120M (20% difference)
    avg_amount = (amount1 + amount2) / 2
    percentage_diff = abs(amount1 - amount2) / avg_amount if avg_amount > 0 else float('inf')
    absolute_diff = abs(amount1 - amount2)
    
    # Allow up to 20% difference, but at least 1M tolerance for small amounts
    max_percentage_diff = 0.20
    max_absolute_diff = max(max_diff, avg_amount * max_percentage_diff)
    
    return absolute_diff <= max_absolute_diff and percentage_diff <= max_percentage_diff


def extract_unique_words(text: str) -> Tuple[set, set]:
    """Extract unique location names and significant words. Returns (unique_words, location_names)."""
    if not text:
        return set(), set()
    
    # Extract all words (3+ characters)
    all_words = set(re.findall(r'\b\w{3,}\b', text.lower()))
    
    # Extract location names (proper nouns - capitalized words, place names)
    # These are the unique identifiers: Iloilo, Davao, Lagayan, Maoyon, Puerto Princesa, etc.
    # NOTE: Do NOT use generic location type words (province, city, municipality) as primary matching
    # They can add confidence but not certainty
    location_names = set()
    
    # Common non-location capitalized words to exclude
    excluded_words = {'construction', 'improvement', 'rehabilitation', 'maintenance', 
                     'package', 'phase', 'segment', 'section', 'including', 'approaches',
                     'coastal', 'road', 'rd', 'bridge', 'building', 'facilities', 'structure',
                     'province', 'city', 'municipality', 'municipal', 'barangay', 'brgy',
                     'river', 'bypass', 'government', 'center', 'multi', 'purpose', 'service',
                     'west', 'north', 'south', 'east', 'expressway', 'flood', 'mitigation',
                     'abutment', 'downstream', 'upstream'}  # Generic/common words - not unique identifiers
    
    # Province names - exclude these as they're too common and match too many projects
    province_names = {'batangas', 'cavite', 'laguna', 'rizal', 'quezon', 'bulacan', 'pampanga', 
                     'tarlac', 'nueva', 'ecija', 'zambales', 'bataan', 'aurora', 'camarines', 
                     'sur', 'norte', 'zamboanga', 'mindoro', 'palawan', 'cebu', 'leyte', 'samar',
                     'bohol', 'negros', 'ilocos', 'pangasinan', 'isabela', 'cagayan', 'albay',
                     'sorsogon', 'masbate', 'catanduanes', 'romblon', 'marinduque', 'mindanao'}
    
    # Find hyphenated compound names (e.g., "Batangas-Tabangao-Lobo")
    hyphenated_compounds = re.findall(r'\b([A-Z][a-z]+(?:-[A-Z][a-z]+)+)\b', text)
    for compound in hyphenated_compounds:
        # Split by hyphen and add each part
        parts = compound.split('-')
        for part in parts:
            part_lower = part.lower()
            if part_lower not in excluded_words and len(part_lower) > 3:
                location_names.add(part_lower)
    
    # Find multi-word phrases (e.g., "North Expressway", "West Service", "San Pablo", "Puerto Princesa")
    # Prioritize these as single units - don't add individual words from phrases
    multi_word_phrases = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b', text)
    phrase_words = set()  # Track words that are part of phrases (to avoid duplicates)
    filtered_phrase_words = set()  # Track words from phrases that were filtered out
    
    for phrase in multi_word_phrases:
        phrase_lower = phrase.lower()
        words = phrase_lower.split()
        # Filter out phrases containing province names (e.g., "camarines sur")
        if any(word in province_names for word in words):
            filtered_phrase_words.update(words)  # Mark these words as filtered
            continue  # Skip phrases with province names
        # If phrase ends with excluded word OR contains excluded words, filter out the phrase
        # BUT still allow valid location names to be extracted as single words
        if words and (words[-1] in excluded_words or any(word in excluded_words for word in words)):
            # Mark only excluded words as filtered (so they don't appear as single words)
            # Valid location names will still be extracted as single words
            excluded_in_phrase = [w for w in words if w in excluded_words]
            filtered_phrase_words.update(excluded_in_phrase)
            # Don't add the phrase itself, but valid words can still be extracted separately
            continue  # Skip the full phrase
        # Check if it's not a common phrase
        if not any(word in excluded_words for word in words):
            # Add the full phrase as a unit (e.g., "north expressway", "west service", "san pablo")
            location_names.add(phrase_lower)
            # Track words that are part of phrases (don't add them separately to avoid duplicates)
            phrase_words.update(words)
    
    # Find single capitalized words (likely place names)
    # But exclude words that are already part of multi-word phrases OR were filtered out
    capitalized_words = re.findall(r'\b([A-Z][a-z]{3,})\b', text)
    for word in capitalized_words:
        word_lower = word.lower()
        # Skip if this word is part of a phrase we already added (avoid duplicates)
        if word_lower in phrase_words:
            continue
        # Skip if this word was part of a filtered phrase (e.g., "calampinay" from "Calampinay Coastal Road")
        if word_lower in filtered_phrase_words:
            continue
        # Filter out common capitalized words that aren't locations
        if word_lower not in excluded_words:
            # Exclude province names (they're too common and match too many projects)
            if word_lower in province_names:
                continue  # Skip province names
            # Include if it's part of a hyphenated compound (e.g., "Batangas-Tabangao")
            word_pos = text.find(word)
            if word_pos > 0 and text[word_pos - 1] == '-':
                location_names.add(word_lower)  # Part of compound, include it
            elif word_pos + len(word) < len(text) and text[word_pos + len(word)] == '-':
                location_names.add(word_lower)  # Part of compound, include it
            else:
                location_names.add(word_lower)
    
    # Extract names from parentheses (e.g., "(Cabcabuban Section)" -> "Cabcabuban")
    paren_matches = re.findall(r'\(([A-Z][a-z]+)', text)
    for match in paren_matches:
        match_lower = match.lower()
        if match_lower not in excluded_words and len(match_lower) > 3:
            location_names.add(match_lower)
    
    # Also look for common location indicators followed by names
    # "Barangay Maoyon", "Puerto Princesa City", etc.
    location_patterns = [
        r'\b(barangay|brgy|municipality|city|province)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(City|Province|Municipality)',
    ]
    for pattern in location_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                # Take the location name part (usually the second element)
                for part in match:
                    if part and part[0].isupper() and part.lower() not in excluded_words:
                        location_names.add(part.lower())
                        # Also add individual words
                        for word in part.split():
                            if word[0].isupper() and word.lower() not in excluded_words:
                                location_names.add(word.lower())
            else:
                if match and match[0].isupper() and match.lower() not in excluded_words:
                    location_names.add(match.lower())
    
    # All words are kept, but location names will be weighted more heavily
    return all_words, location_names


def extract_codes(text: str) -> set:
    """Extract project codes, contract numbers, and other identifiers."""
    if not text:
        return set()
    
    codes = set()
    
    # Contract codes: patterns like 22GL0059, 25GK0112, 18DE0011
    contract_patterns = re.findall(r'\b\d{2}[A-Z]{2}\d{4}\b', text.upper())
    codes.update(contract_patterns)
    
    # Long numeric codes: patterns like 320102107252000
    long_codes = re.findall(r'\b\d{12,}\b', text)
    codes.update(long_codes)
    
    # Alphanumeric codes: 4+ characters, mostly uppercase
    alphanumeric = re.findall(r'\b[A-Z0-9]{4,}\b', text.upper())
    codes.update(alphanumeric)
    
    return codes


def extract_bridge_identifiers(text: str) -> set:
    """Extract bridge identifiers like B03318LZ, S03978LZ from project titles."""
    if not text:
        return set()
    
    # Pattern: Letter(s) followed by digits followed by letters (e.g., B03318LZ, S03978LZ)
    # Also matches patterns in parentheses: (B03318LZ)
    bridge_patterns = re.findall(r'\(?([A-Z]\d+[A-Z]+)\)?', text.upper())
    return set(bridge_patterns)


def extract_gaa644_components(text: str) -> Dict[str, Optional[str]]:
    """Extract components for GAA page 644 matching: Ilaya, Abutment (A/B), stream (down/up), package (1/2/3)."""
    if not text:
        return {"ilaya": None, "abutment": None, "stream": None, "package": None}
    
    text_lower = text.lower()
    components = {"ilaya": None, "abutment": None, "stream": None, "package": None}
    
    # Check for Ilaya
    if "ilaya" in text_lower:
        components["ilaya"] = "ilaya"
    
    # Extract Abutment A or B
    abutment_match = re.search(r'\babutment\s+([ab])', text_lower)
    if abutment_match:
        components["abutment"] = abutment_match.group(1).upper()
    elif "abutment" in text_lower:
        components["abutment"] = "any"  # Has abutment but no A/B specified
    
    # Extract downstream or upstream
    if "downstream" in text_lower:
        components["stream"] = "down"
    elif "upstream" in text_lower:
        components["stream"] = "up"
    elif "stream" in text_lower:
        components["stream"] = "any"  # Has stream but no down/up specified
    
    # Extract Package 1, 2, or 3
    package_match = re.search(r'\bpackage\s+([123])', text_lower)
    if package_match:
        components["package"] = package_match.group(1)
    elif "package" in text_lower:
        components["package"] = "any"  # Has package but no number specified
    
    return components


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
            
            # Adjust threshold based on GAA page
            min_title_score = 0.6  # Default
            if gaa_page in STRICT_GAA_PAGES:
                min_title_score = 0.75  # Stricter for wrong GAA pages
            elif gaa_page not in CORRECT_GAA_PAGES and gaa_page:
                min_title_score = 0.5  # Looser for not mentioned GAA pages
            
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
            
            # Check amount match if available - STRICT: reject if amounts don't match
            if amount is not None and db_amount is not None:
                amount_match = amount_matches(amount, db_amount, max_diff=1000000.0)
                # REJECT if amounts don't match (outrageous differences like 250M vs 4.9M)
                if not amount_match:
                    continue  # Skip this match completely
            elif amount is not None and db_amount is None:
                # If CSV has amount but DB doesn't, require strong match
                min_score_no_amount = 0.7
                if gaa_page in STRICT_GAA_PAGES:
                    min_score_no_amount = 0.8  # Stricter
                elif gaa_page not in CORRECT_GAA_PAGES and gaa_page:
                    min_score_no_amount = 0.6  # Looser
                if not chainage_match and title_score < min_score_no_amount:
                    continue
            
            # Calculate overall score
            score = title_score
            if chainage_match:
                score += 0.5  # Strong bonus for chainage match
            if amount is not None and db_amount is not None and amount_matches(amount, db_amount):
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
                
                min_title_score = 0.6
                if gaa_page in STRICT_GAA_PAGES:
                    min_title_score = 0.75
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
                    min_score_no_amount = 0.7
                    if gaa_page in STRICT_GAA_PAGES:
                        min_score_no_amount = 0.8
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
        title_chainage_bases = extract_chainage_base_markers(project_title)
        title_chainage_with_offsets = extract_chainage_with_offsets(project_title)
        
        # Initialize search_patterns list for permutations
        search_patterns = None
        filtered_locations = None
        search_pattern_for_display = None  # Store pattern for display
        
        # Check for bridge identifiers first - they're unique and should be prioritized
        title_bridge_ids = extract_bridge_identifiers(project_title)
        
        # Build SQL search pattern
        if title_bridge_ids:
            # Bridge identifiers are unique - use them as primary search pattern
            bridge_id = sorted(title_bridge_ids)[0]  # Use first bridge ID
            search_pattern = f"%{bridge_id}%"
            search_patterns = [search_pattern]
            search_pattern_for_display = search_pattern
        elif title_chainage_bases:
            # For chainages with offsets, extract all base-offset pairs
            # Format: %Kxxxx%yyy%Kxxxx%zzz% (same base chainage with 2 offsets = high confidence)
            chainage_offset_map = {}  # {base_chainage: [offsets]}
            
            if title_chainage_with_offsets:
                # Extract all chainage+offset pairs in order from the title (preserve order, don't sort)
                # Pattern: pair consecutive chainages (e.g., K0062+000 with K0063+250)
                # Extract directly from title to preserve order
                chainage_pairs = []  # List of (base, offset) tuples in order
                # Find all chainage+offset patterns in order from title
                chainage_matches = re.finditer(r'(K\d+)\s*\+\s*(\d+)', project_title.upper())
                for match in chainage_matches:
                    base, offset = match.groups()
                    chainage_pairs.append((base, offset))
                
                # Build patterns by pairing consecutive chainages
                # Format: %Kxxxx%yyy%Kzzzz%www% (consecutive chainages with their offsets)
                search_patterns_list = []
                for i in range(0, len(chainage_pairs) - 1, 2):
                    if i + 1 < len(chainage_pairs):
                        base1, offset1 = chainage_pairs[i]
                        base2, offset2 = chainage_pairs[i + 1]
                        pattern = f"%{base1}%{offset1}%{base2}%{offset2}%"
                        search_patterns_list.append(pattern)
                    elif i < len(chainage_pairs):
                        # If odd number, use the last one with its offset (duplicate for pattern)
                        base, offset = chainage_pairs[i]
                        pattern = f"%{base}%{offset}%{base}%{offset}%"
                        search_patterns_list.append(pattern)
                
                if search_patterns_list:
                    # Use the first pattern (highest confidence - 2 offsets for same base)
                    search_pattern = search_patterns_list[0]
                    search_patterns = search_patterns_list  # Store all for OR query
                    # Store pattern for display (show all patterns if multiple)
                    if len(search_patterns_list) > 1:
                        search_pattern_for_display = ", ".join(search_patterns_list)
                    else:
                        search_pattern_for_display = search_pattern
                elif len(title_chainage_bases) >= 2:
                    # Fallback: multiple bases without offsets
                    chainage_list = sorted(title_chainage_bases)
                    search_pattern = f"%{'%'.join(chainage_list)}%"
                    search_patterns = [search_pattern]
                else:
                    # Fallback: single base
                    primary_chainage = sorted(title_chainage_bases)[0]
                    search_pattern = f"%{primary_chainage}%"
                    search_patterns = [search_pattern]
            elif len(title_chainage_bases) >= 2:
                # Multiple bases without offsets
                chainage_list = sorted(title_chainage_bases)
                search_pattern = f"%{'%'.join(chainage_list)}%"
                search_patterns = [search_pattern]
            else:
                # Single base without offsets
                primary_chainage = sorted(title_chainage_bases)[0]
                search_pattern = f"%{primary_chainage}%"
                search_patterns = [search_pattern]
        else:
            # No chainages - use unique location names (filter out common words and provinces)
            title_words, title_locations = extract_unique_words(project_title)
            if title_locations:
                # Filter out common words, provinces, and duplicates
                # Exclude province names (too common)
                province_names_set = {'batangas', 'cavite', 'laguna', 'rizal', 'quezon', 'bulacan', 'pampanga', 
                                    'tarlac', 'nueva', 'ecija', 'zambales', 'bataan', 'aurora', 'camarines', 'sur', 'norte'}
                
                filtered_locations = []
                # Multi-word phrases - exclude those with provinces, common words, or ending with excluded words
                excluded_phrases = {'barangay', 'brgy', 'section', 'segment', 'phase', 'package', 'along', 'overlay',
                                   'government center', 'multi purpose', 'bypass road', 'coastal road'}
                excluded_endings = {'road', 'rd', 'section', 'segment', 'river', 'bypass', 'center', 'purpose', 'coastal'}
                multi_word_phrases = [loc for loc in title_locations 
                                     if ' ' in loc 
                                     and not any(loc.endswith(f' {excluded}') for excluded in excluded_endings)
                                     and not any(loc == excluded or excluded in loc for excluded in excluded_phrases)
                                     and not any(prov in loc for prov in province_names_set)
                                     and not any(excluded in loc.split() for excluded in {'river', 'bypass', 'government', 'multi', 'purpose', 'expressway', 'coastal', 'road'})
                                     and loc not in excluded_phrases]
                # Single words - exclude provinces and common words
                excluded_common = {'barangay', 'brgy', 'section', 'segment', 'phase', 'package', 'rd', 'road', 'along', 'overlay', 
                                  'service', 'west', 'north', 'south', 'east', 'river', 'bypass', 'government', 'center', 
                                  'multi', 'purpose', 'expressway', 'coastal', 'bridge', 'building', 'facilities', 'structure'}
                single_words = [loc for loc in title_locations 
                               if ' ' not in loc 
                               and loc not in province_names_set
                               and loc not in excluded_common
                               and len(loc) > 3]
                
                # Combine and remove duplicates (set will preserve order in Python 3.7+)
                # Remove any duplicates where a word appears both as single word and in a phrase
                filtered_locations = []
                seen_words = set()
                
                # First add multi-word phrases
                for phrase in multi_word_phrases:
                    words_in_phrase = phrase.split()
                    # Only add if none of the words are already seen as single words
                    if not any(word in seen_words for word in words_in_phrase):
                        filtered_locations.append(phrase)
                        seen_words.update(words_in_phrase)
                
                # Then add single words that aren't part of any phrase
                for word in single_words:
                    if word not in seen_words:
                        filtered_locations.append(word)
                        seen_words.add(word)
                
                # Limit to exactly 3 proper names (not more)
                if len(filtered_locations) > 3:
                    filtered_locations = filtered_locations[:3]
                
                if filtered_locations:
                    # Generate all permutations: 2 keywords = 2 permutations, 3 keywords = 6 permutations
                    # Split multi-word locations into individual words for pattern matching
                    import itertools
                    # Flatten multi-word locations: "talahib pandayan" -> ["talahib", "pandayan"], "zone iii" -> ["zone", "iii"]
                    flattened_locations = []
                    for loc in filtered_locations:
                        if ' ' in loc:
                            # Split multi-word location into individual words
                            flattened_locations.extend(loc.split())
                        else:
                            flattened_locations.append(loc)
                    
                    # Filter out common non-location words (case insensitive)
                    excluded_words = {'shore', 'protection', 'coastal', 'road', 'rd', 'construction', 'improvement', 
                                    'rehabilitation', 'maintenance', 'along', 'barangay', 'brgy', 'section', 'segment',
                                    'phase', 'package', 'structure', 'facilities', 'building', 'bridge', 'flyover'}
                    flattened_locations = [loc.lower() for loc in flattened_locations 
                                          if loc.lower() not in excluded_words and len(loc) > 2]
                    
                    # Limit to max 3 keywords after flattening (to avoid too many permutations)
                    if len(flattened_locations) > 3:
                        flattened_locations = flattened_locations[:3]
                    
                    if len(flattened_locations) >= 2:
                        # Generate all permutations (2! = 2, 3! = 6, etc.)
                        permutations = list(itertools.permutations(flattened_locations))
                        # Use first permutation as primary pattern, but store all for query building
                        search_pattern = f"%{'%'.join(permutations[0])}%"
                        search_patterns = [f"%{'%'.join(p)}%" for p in permutations]
                        # Store pattern for display (show all permutations)
                        search_pattern_for_display = ", ".join([f"%{'%'.join(p)}%" for p in permutations])
                    else:
                        # Only 1 keyword, just use one pattern
                        search_pattern = f"%{'%'.join(flattened_locations)}%"
                        search_patterns = [search_pattern]
                        search_pattern_for_display = search_pattern
                else:
                    search_pattern = f"%{normalized_title}%"
                    search_patterns = [search_pattern]
            else:
                # Fallback to normalized title
                search_pattern = f"%{normalized_title}%"
                search_patterns = [search_pattern]
        
        # Build query: try all chainage patterns (at least 1 match, more = higher confidence)
        # OR try all keyword permutations if we have 2+ keywords
        if search_patterns and (len(search_patterns) > 1 or (filtered_locations and len(filtered_locations) >= 2)):
            # Multiple patterns: chainage patterns OR keyword permutations
            if filtered_locations and len(filtered_locations) >= 2:
                # Generate all keyword permutations (already done above, but ensure we use them)
                # search_patterns already contains all permutations, so just use it
                all_patterns = search_patterns
            else:
                all_patterns = search_patterns
            
            # Use OR to try all patterns
            pattern_conditions = ' OR '.join([f"(project_name ILIKE ${i+1} OR description ILIKE ${i+1})" 
                                            for i in range(len(all_patterns))])
            dime_query = f"""
                SELECT project_code, contractors, cost, project_name, description
                FROM projects
                WHERE ({pattern_conditions})
                LIMIT 20
            """
            rows = await dime_conn.fetch(dime_query, *all_patterns)
        else:
            dime_query = """
                SELECT project_code, contractors, cost, project_name, description
                FROM projects
                WHERE (project_name ILIKE $1 OR description ILIKE $1)
                LIMIT 20
            """
            rows = await dime_conn.fetch(dime_query, search_pattern)
        
        # Simple matching: SQL pattern + amount threshold
        # BUT: For chainage patterns, verify that the exact chainage ranges match
        # AND: For bridge identifiers, verify they match exactly
        best_match = None
        
        # Extract bridge identifiers from CSV title
        csv_bridge_ids = extract_bridge_identifiers(project_title)
        
        for row in rows:
            # Get amount from DB
            db_amount = float(row['cost']) if row['cost'] else None
            
            # Get amount from DB (just show it, don't reject based on amount differences)
            # Amount differences are OK - projects can be split into multiple components
            
            proj_name = row.get('project_name') or ""
            proj_desc = row.get('description') or ""
            db_title = proj_name or proj_desc
            db_text = f"{proj_name} {proj_desc}".upper()
            
            # If CSV has bridge identifiers, verify they match in DB
            if csv_bridge_ids:
                db_bridge_ids = extract_bridge_identifiers(db_text)
                # Require at least one exact bridge ID match
                if not csv_bridge_ids.intersection(db_bridge_ids):
                    continue  # Bridge IDs don't match, skip this row
            
            # If we used chainage patterns with offsets, verify exact matches
            if title_chainage_with_offsets:
                # Extract all chainage+offset pairs from CSV (e.g., "K0032+057", "K0032+885")
                csv_chainage_pairs = set()
                for chainage_offset in title_chainage_with_offsets:
                    # Extract base and offset (e.g., "K0032 + 057" -> ("K0032", "057"))
                    match = re.search(r'(K\d+)\s*\+\s*(\d+)', chainage_offset, re.IGNORECASE)
                    if match:
                        base, offset = match.groups()
                        csv_chainage_pairs.add(f"{base}+{offset}")
                
                # Extract all chainage+offset pairs from DB text
                db_chainage_pairs = set()
                db_matches = re.findall(r'(K\d+)\s*[+\-]\s*(\d+)', db_text, re.IGNORECASE)
                for base, offset in db_matches:
                    db_chainage_pairs.add(f"{base.upper()}+{offset}")
                
                # Require at least one exact chainage+offset match
                # This prevents matching K0032+057 against K0032+867
                if not csv_chainage_pairs.intersection(db_chainage_pairs):
                    continue  # No exact chainage+offset match, skip this row
            
            # If we get here, it's a valid match
            contractors = row.get('contractors', [])
            contractor_str = ", ".join(contractors) if isinstance(contractors, list) else (contractors or "")
            
            best_match = {
                "contract_id": row.get('project_code') or "",
                "contractor": contractor_str,
                "db_project_title": db_title,
                "db_amount": db_amount
            }
            break  # Take first match that passes validation
        
        return best_match
    except Exception as e:
        print(f"  ⚠️  Error checking DIME DB: {e}")
        return None


async def find_philgeps_match(philgeps_conn: asyncpg.Connection, project_title: str, amount: Optional[float], gaa_page: str = "") -> Optional[Dict[str, Any]]:
    """Find matching project in PhilGEPS DB and return contract info."""
    try:
        normalized_title = normalize_title(project_title)
        title_chainages = extract_chainage_markers(project_title)
        title_chainage_bases = extract_chainage_base_markers(project_title)
        title_chainage_with_offsets = extract_chainage_with_offsets(project_title)
        
        # Check for bridge identifiers first - they're unique and should be prioritized
        title_bridge_ids = extract_bridge_identifiers(project_title)
        
        # Build SQL search pattern (same logic as DIME)
        if title_bridge_ids:
            # Bridge identifiers are unique - use them as primary search pattern
            bridge_id = sorted(title_bridge_ids)[0]  # Use first bridge ID
            search_pattern = f"%{bridge_id}%"
        elif title_chainage_bases:
            # If we have multiple chainage bases (e.g., K000, K491), use them all
            if len(title_chainage_bases) >= 2:
                chainage_list = sorted(title_chainage_bases)
                search_pattern = f"%{'%'.join(chainage_list)}%"
            elif title_chainage_with_offsets:
                # Extract chainage+offset pairs in order and pair consecutive ones
                chainage_pairs = []
                chainage_matches = re.finditer(r'(K\d+)\s*\+\s*(\d+)', project_title.upper())
                for match in chainage_matches:
                    base, offset = match.groups()
                    chainage_pairs.append((base, offset))
                
                # Build patterns by pairing consecutive chainages
                search_patterns_list = []
                for i in range(0, len(chainage_pairs) - 1, 2):
                    if i + 1 < len(chainage_pairs):
                        base1, offset1 = chainage_pairs[i]
                        base2, offset2 = chainage_pairs[i + 1]
                        pattern = f"%{base1}%{offset1}%{base2}%{offset2}%"
                        search_patterns_list.append(pattern)
                    elif i < len(chainage_pairs):
                        base, offset = chainage_pairs[i]
                        pattern = f"%{base}%{offset}%{base}%{offset}%"
                        search_patterns_list.append(pattern)
                
                if search_patterns_list:
                    search_pattern = search_patterns_list[0]
                else:
                    primary_chainage = sorted(title_chainage_bases)[0]
                    search_pattern = f"%{primary_chainage}%"
            else:
                primary_chainage = sorted(title_chainage_bases)[0]
                search_pattern = f"%{primary_chainage}%"
        else:
            # No chainages - use unique location names (filter out common words)
            title_words, title_locations = extract_unique_words(project_title)
            if title_locations:
                # Filter out common words and province names, keep only unique location names
                filtered_locations = [loc for loc in title_locations 
                                     if loc not in {'barangay', 'brgy', 'section', 'segment', 'phase', 'package'}
                                     and len(loc) > 3]
                if filtered_locations:
                    location_list = sorted(filtered_locations)
                    search_pattern = f"%{'%'.join(location_list)}%"
                else:
                    search_pattern = f"%{normalized_title}%"
            else:
                search_pattern = f"%{normalized_title}%"
        
        philgeps_query = """
            SELECT contract_no, awardee_name, contract_amount, award_title, notice_title, id
            FROM contracts
            WHERE (award_title ILIKE $1 OR notice_title ILIKE $1)
            LIMIT 20
        """
        rows = await philgeps_conn.fetch(philgeps_query, search_pattern)
        
        # Simple matching: SQL pattern + amount threshold
        # BUT: For chainage patterns, verify that the exact chainage ranges match
        best_match = None
        
        for row in rows:
            # Get amount from DB (just show it, don't reject based on amount differences)
            db_amount = float(row['contract_amount']) if row['contract_amount'] else None
            
            db_title = row.get('award_title') or row.get('notice_title') or ""
            db_text = db_title.upper()
            
            # If we used chainage patterns with offsets, verify exact matches
            if title_chainage_with_offsets:
                # Extract all chainage+offset pairs from CSV (e.g., "K0032+057", "K0032+885")
                csv_chainage_pairs = set()
                for chainage_offset in title_chainage_with_offsets:
                    # Extract base and offset (e.g., "K0032 + 057" -> ("K0032", "057"))
                    match = re.search(r'(K\d+)\s*\+\s*(\d+)', chainage_offset, re.IGNORECASE)
                    if match:
                        base, offset = match.groups()
                        csv_chainage_pairs.add(f"{base}+{offset}")
                
                # Extract all chainage+offset pairs from DB text
                db_chainage_pairs = set()
                db_matches = re.findall(r'(K\d+)\s*[+\-]\s*(\d+)', db_text, re.IGNORECASE)
                for base, offset in db_matches:
                    db_chainage_pairs.add(f"{base.upper()}+{offset}")
                
                # Require at least one exact chainage+offset match
                # This prevents matching K0032+057 against K0032+867
                if not csv_chainage_pairs.intersection(db_chainage_pairs):
                    continue  # No exact chainage+offset match, skip this row
            
            # If we get here, it's a valid match
            # Amount differences are OK - projects can be split into multiple components
            
            best_match = {
                "contract_id": row.get('contract_no') or "",
                "contractor": row.get('awardee_name') or "",
                "db_project_title": db_title,
                "db_amount": db_amount,
                "philgeps_id": row.get('contract_no') or ""  # Use contract_no as philgeps_id (e.g., "24FC0027")
            }
            break  # Take first match
        
        return best_match
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
        title_chainage_bases = extract_chainage_base_markers(project_title)
        title_chainage_with_offsets = extract_chainage_with_offsets(project_title)
        title_words = set(re.findall(r'\b\w{3,}\b', normalized_title.lower()))
        
        # Check for bridge identifiers first - they're unique and should be prioritized
        title_bridge_ids = extract_bridge_identifiers(project_title)
        
        # Build SQL search pattern (same logic as DIME and PhilGEPS)
        if title_bridge_ids:
            # Bridge identifiers are unique - use them as primary search pattern
            bridge_id = sorted(title_bridge_ids)[0]  # Use first bridge ID
            search_term = f"%{bridge_id}%"
        elif title_chainage_bases:
            # If we have multiple chainage bases (e.g., K000, K491), use them all
            if len(title_chainage_bases) >= 2:
                chainage_list = sorted(title_chainage_bases)
                search_term = f"%{'%'.join(chainage_list)}%"
            elif title_chainage_with_offsets:
                # Extract chainage+offset pairs in order and pair consecutive ones
                chainage_pairs = []
                chainage_matches = re.finditer(r'(K\d+)\s*\+\s*(\d+)', project_title.upper())
                for match in chainage_matches:
                    base, offset = match.groups()
                    chainage_pairs.append((base, offset))
                
                # Build patterns by pairing consecutive chainages
                search_patterns_list = []
                for i in range(0, len(chainage_pairs) - 1, 2):
                    if i + 1 < len(chainage_pairs):
                        base1, offset1 = chainage_pairs[i]
                        base2, offset2 = chainage_pairs[i + 1]
                        pattern = f"%{base1}%{offset1}%{base2}%{offset2}%"
                        search_patterns_list.append(pattern)
                    elif i < len(chainage_pairs):
                        base, offset = chainage_pairs[i]
                        pattern = f"%{base}%{offset}%{base}%{offset}%"
                        search_patterns_list.append(pattern)
                
                if search_patterns_list:
                    search_term = search_patterns_list[0]
                else:
                    primary_chainage = sorted(title_chainage_bases)[0]
                    search_term = f"%{primary_chainage}%"
            else:
                primary_chainage = sorted(title_chainage_bases)[0]
                search_term = f"%{primary_chainage}%"
        else:
            # No chainages - use unique location names (filter out common words)
            title_words, title_locations = extract_unique_words(project_title)
            if title_locations:
                # Filter out common words and province names, keep only unique location names
                filtered_locations = [loc for loc in title_locations 
                                     if loc not in {'barangay', 'brgy', 'section', 'segment', 'phase', 'package'}
                                     and len(loc) > 3]
                if filtered_locations:
                    location_list = sorted(filtered_locations)
                    search_term = f"%{'%'.join(location_list)}%"
                else:
                    search_term = f"%{normalized_title}%"
            else:
                search_term = f"%{normalized_title}%"
        
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
        rows = await infrawatch_conn.fetch(infrawatch_query, search_term)
        
        # Simple matching: SQL pattern + amount threshold
        # BUT: For chainage patterns, verify that the exact chainage ranges match
        # AND: For bridge identifiers, verify they match exactly
        best_match = None
        
        # Extract bridge identifiers from CSV title
        csv_bridge_ids = extract_bridge_identifiers(project_title)
        
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
            
            db_text = db_title.upper()
            
            # If CSV has bridge identifiers, verify they match in DB
            if csv_bridge_ids:
                db_bridge_ids = extract_bridge_identifiers(db_text)
                # Require at least one exact bridge ID match
                if not csv_bridge_ids.intersection(db_bridge_ids):
                    continue  # Bridge IDs don't match, skip this row
            
            # If we used chainage patterns with offsets, verify exact matches
            if title_chainage_with_offsets:
                # Extract all chainage+offset pairs from CSV (e.g., "K0088+596", "K0091+537")
                csv_chainage_pairs = set()
                for chainage_offset in title_chainage_with_offsets:
                    # Extract base and offset (e.g., "K0088 + 596" -> ("K0088", "596"))
                    match = re.search(r'(K\d+)\s*\+\s*(\d+)', chainage_offset, re.IGNORECASE)
                    if match:
                        base, offset = match.groups()
                        csv_chainage_pairs.add(f"{base}+{offset}")
                
                # Extract all chainage+offset pairs from DB text
                db_chainage_pairs = set()
                db_matches = re.findall(r'(K\d+)\s*[+\-]\s*(\d+)', db_text, re.IGNORECASE)
                for base, offset in db_matches:
                    db_chainage_pairs.add(f"{base.upper()}+{offset}")
                
                # Require at least one exact chainage+offset match
                # This prevents matching K0088+596 against projects without K0088+596
                if not csv_chainage_pairs.intersection(db_chainage_pairs):
                    continue  # No exact chainage+offset match, skip this row
            
            # Get amount from DB
            amount_fields = ['Contract Amount', 'Amount', 'Project Cost', 'Cost', 'Value']
            db_amount = None
            for field in amount_fields:
                val = data.get(field)
                if val:
                    db_amount = parse_amount(str(val))
                    if db_amount:
                        break
            
            # Get amount from DB (just show it, don't reject based on amount differences)
            # Amount differences are OK - projects can be split into multiple components
            
            # If we get here, it's a match (SQL pattern matched)
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
            break  # Take first match that passes amount check
        
        return best_match
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
        
        # Build search pattern for display (always show it, even if match found)
        normalized_title = normalize_title(project_title)
        title_chainage_bases = extract_chainage_base_markers(project_title)
        title_chainage_with_offsets = extract_chainage_with_offsets(project_title)
        search_pattern_for_display = None
        
        if title_chainage_bases and title_chainage_with_offsets:
            # Extract chainage+offset pairs in order and pair consecutive ones
            # Pattern: pair consecutive chainages (e.g., K0062+000 with K0063+250)
            chainage_pairs = []
            chainage_matches = re.finditer(r'(K\d+)\s*\+\s*(\d+)', project_title.upper())
            for match in chainage_matches:
                base, offset = match.groups()
                chainage_pairs.append((base, offset))
            
            # Build patterns by pairing consecutive chainages
            # Format: %Kxxxx%yyy%Kzzzz%www% (consecutive chainages with their offsets)
            search_patterns_list = []
            for i in range(0, len(chainage_pairs) - 1, 2):
                if i + 1 < len(chainage_pairs):
                    base1, offset1 = chainage_pairs[i]
                    base2, offset2 = chainage_pairs[i + 1]
                    pattern = f"%{base1}%{offset1}%{base2}%{offset2}%"
                    search_patterns_list.append(pattern)
                elif i < len(chainage_pairs):
                    # If odd number, use the last one with its offset (duplicate for pattern)
                    base, offset = chainage_pairs[i]
                    pattern = f"%{base}%{offset}%{base}%{offset}%"
                    search_patterns_list.append(pattern)
            
            if search_patterns_list:
                search_pattern_for_display = ", ".join(search_patterns_list)
        elif title_chainage_bases:
            chainage_list = sorted(title_chainage_bases)
            search_pattern_for_display = f"%{'%'.join(chainage_list)}%"
        else:
            # Use location names
            title_words, title_locations = extract_unique_words(project_title)
            if title_locations:
                province_names_set = {'batangas', 'cavite', 'laguna', 'rizal', 'quezon', 'bulacan', 'pampanga', 
                                    'tarlac', 'nueva', 'ecija', 'zambales', 'bataan', 'aurora', 'camarines', 'sur', 'norte'}
                excluded_phrases = {'barangay', 'brgy', 'section', 'segment', 'phase', 'package', 'along', 'overlay',
                                   'government center', 'multi purpose', 'bypass road', 'coastal road'}
                excluded_endings = {'road', 'rd', 'section', 'segment', 'river', 'bypass', 'center', 'purpose', 'coastal'}
                excluded_common = {'barangay', 'brgy', 'section', 'segment', 'phase', 'package', 'rd', 'road', 'along', 'overlay', 
                                  'service', 'west', 'north', 'south', 'east', 'river', 'bypass', 'government', 'center', 
                                  'multi', 'purpose', 'expressway', 'coastal', 'bridge', 'building', 'facilities', 'structure'}
                
                multi_word_phrases = [loc for loc in title_locations 
                                     if ' ' in loc 
                                     and not any(loc.endswith(f' {excluded}') for excluded in excluded_endings)
                                     and not any(loc == excluded or excluded in loc for excluded in excluded_phrases)
                                     and not any(prov in loc for prov in province_names_set)
                                     and not any(excluded in loc.split() for excluded in {'river', 'bypass', 'government', 'multi', 'purpose', 'expressway', 'coastal', 'road'})
                                     and loc not in excluded_phrases]
                single_words = [loc for loc in title_locations 
                               if ' ' not in loc 
                               and loc not in province_names_set
                               and loc not in excluded_common
                               and len(loc) > 3]
                
                filtered_locations = []
                seen_words = set()
                for phrase in multi_word_phrases:
                    words_in_phrase = phrase.split()
                    if not any(word in seen_words for word in words_in_phrase):
                        filtered_locations.append(phrase)
                        seen_words.update(words_in_phrase)
                for word in single_words:
                    if word not in seen_words:
                        filtered_locations.append(word)
                        seen_words.add(word)
                
                if len(filtered_locations) > 3:
                    filtered_locations = filtered_locations[:3]
                
                if filtered_locations:
                    import itertools
                    # Flatten multi-word locations: "talahib pandayan" -> ["talahib", "pandayan"], "zone iii" -> ["zone", "iii"]
                    flattened_locations = []
                    for loc in filtered_locations:
                        if ' ' in loc:
                            # Split multi-word location into individual words
                            flattened_locations.extend(loc.split())
                        else:
                            flattened_locations.append(loc)
                    
                    # Filter out common non-location words (case insensitive)
                    excluded_words = {'shore', 'protection', 'coastal', 'road', 'rd', 'construction', 'improvement', 
                                    'rehabilitation', 'maintenance', 'along', 'barangay', 'brgy', 'section', 'segment',
                                    'phase', 'package', 'structure', 'facilities', 'building', 'bridge', 'flyover'}
                    flattened_locations = [loc.lower() for loc in flattened_locations 
                                          if loc.lower() not in excluded_words and len(loc) > 2]
                    
                    # Limit to max 3 keywords after flattening (to avoid too many permutations)
                    if len(flattened_locations) > 3:
                        flattened_locations = flattened_locations[:3]
                    
                    if len(flattened_locations) >= 2:
                        # Generate all permutations: 2 keywords = 2 permutations, 3 keywords = 6 permutations
                        permutations = list(itertools.permutations(flattened_locations))
                        search_pattern_for_display = ", ".join([f"%{'%'.join(p)}%" for p in permutations])
                    else:
                        # Only 1 keyword
                        search_pattern_for_display = f"%{'%'.join(flattened_locations)}%"
                else:
                    search_pattern_for_display = f"%{normalized_title}%"
            else:
                search_pattern_for_display = f"%{normalized_title}%"
        
        # Check all databases and get match details
        flood_match = None
        dime_match = None
        philgeps_match = None
        infrawatch_match = None
        
        # Get GAA page for matching adjustments
        gaa_page = project.get("gaa_page", "")
        # Normalize GAA page (remove "vetoed/" prefix for filtering checks)
        gaa_page_normalized = gaa_page.replace("vetoed/", "") if gaa_page else ""
        
        if flood_client:
            flood_match = await find_flood_match(flood_client, project_title, amount, gaa_page)
        
        dime_match = await find_dime_match(dime_conn, project_title, amount, gaa_page)
        philgeps_match = await find_philgeps_match(philgeps_conn, project_title, amount, gaa_page)
        
        if infrawatch_conn:
            infrawatch_match = await find_infrawatch_match(infrawatch_conn, project_title, amount, gaa_page)
        
        # For wrong GAA pages (133, 641, 642, 658, 664), reject all matches
        # Use normalized GAA page for checking
        if gaa_page_normalized in STRICT_GAA_PAGES:
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
        philgeps_id = ""
        search_terms_used = []  # Initialize search terms list
        
        # Collect all matches
        all_matches = []
        if flood_match:
            all_matches.append(("flood", flood_match))
        if dime_match:
            all_matches.append(("dime", dime_match))
        if philgeps_match:
            all_matches.append(("philgeps", philgeps_match))
        if infrawatch_match:
            all_matches.append(("infrawatch", infrawatch_match))
        
        # Filter matches based on GAA page rules
        filtered_matches = []
        for source, match in all_matches:
            match_contract_id = match.get("contract_id", "")
            
            # Check if this contract ID should be filtered out (use normalized GAA page)
            if gaa_page_normalized in WRONG_CONTRACT_IDS:
                wrong_ids = WRONG_CONTRACT_IDS[gaa_page_normalized]
                if match_contract_id in wrong_ids:
                    continue  # Skip wrong contract IDs
            
            # For GAA pages with specific correct contract IDs, only keep those
            if gaa_page_normalized in CORRECT_CONTRACT_IDS:
                correct_ids = CORRECT_CONTRACT_IDS[gaa_page_normalized]
                if correct_ids and match_contract_id not in correct_ids:
                    continue  # Skip wrong contract IDs
            
            # For GAA pages with correct contract IDs, prioritize them
            if gaa_page_normalized in CORRECT_CONTRACT_IDS:
                correct_ids = CORRECT_CONTRACT_IDS[gaa_page_normalized]
                if correct_ids and match_contract_id in correct_ids:
                    # Prioritize correct contract IDs
                    filtered_matches.insert(0, (source, match))
                    continue
            
            filtered_matches.append((source, match))
        
        # Use first filtered match (or first match if no filtering needed)
        # Priority: Flood > DIME > PhilGEPS > Infrawatch
        if filtered_matches:
            source, match = filtered_matches[0]
            contract_id = match.get("contract_id", "")
            contractor = match.get("contractor", "")
            db_title_from_match = match.get("db_project_title", "")
            db_amount = match.get("db_amount")
            philgeps_id = match.get("philgeps_id", "")
            
            # Show all matched project titles from all databases for debugging
            all_matched_titles = []
            for src, m in filtered_matches:
                matched_title = m.get("db_project_title", "")
                if matched_title:
                    all_matched_titles.append(f"{src.upper()}: {matched_title}")
            
            # Show DB project name normally, and search pattern separately (will be styled in italics in frontend)
            if search_pattern_for_display:
                search_info = f"SQL Pattern: {search_pattern_for_display}"
                if amount:
                    search_info += f" | Amount: ₱{amount:,.0f}"
                # Show DB title first (normal), then search pattern (will be styled italic in frontend)
                # Also show all matched titles for debugging
                if db_title_from_match:
                    if all_matched_titles and len(all_matched_titles) > 1:
                        # Show all matches: "DB Title | [FLOOD: title1, DIME: title2, ...] | SQL Pattern: ..."
                        all_matches_str = " | ".join(all_matched_titles)
                        db_project_title = f"{db_title_from_match} | [{all_matches_str}] | {search_info}"
                    else:
                        db_project_title = f"{db_title_from_match} | {search_info}"
                else:
                    if all_matched_titles:
                        all_matches_str = " | ".join(all_matched_titles)
                        db_project_title = f"[{all_matches_str}] | {search_info}"
                    else:
                        db_project_title = search_info
            else:
                if all_matched_titles and len(all_matched_titles) > 1:
                    all_matches_str = " | ".join(all_matched_titles)
                    db_project_title = f"{db_title_from_match} | [{all_matches_str}]" if db_title_from_match else f"[{all_matches_str}]"
                else:
                    db_project_title = db_title_from_match if db_title_from_match else ""
        elif all_matches:
            # Check if all matches were filtered because they're wrong contract IDs
            # If so, don't use any match (treat as not found)
            all_wrong = True
            for source, match in all_matches:
                match_contract_id = match.get("contract_id", "")
                if gaa_page_normalized in WRONG_CONTRACT_IDS:
                    wrong_ids = WRONG_CONTRACT_IDS[gaa_page_normalized]
                    if match_contract_id not in wrong_ids:
                        all_wrong = False
                        break
                else:
                    all_wrong = False
                    break
            
            if not all_wrong:
                # Fallback to first match if not all were wrong (shouldn't happen normally)
                source, match = all_matches[0]
                contract_id = match.get("contract_id", "")
                contractor = match.get("contractor", "")
                db_title_from_match = match.get("db_project_title", "")
                db_amount = match.get("db_amount")
                philgeps_id = match.get("philgeps_id", "")
                
                # Show DB project name normally, and search pattern separately (will be styled in italics in frontend)
                # Don't include amount in db_project_title - it will be shown in Amount column
                if search_pattern_for_display:
                    search_info = f"SQL Pattern: {search_pattern_for_display}"
                    # Show DB title first (normal), then search pattern (will be styled italic in frontend)
                    if db_title_from_match:
                        db_project_title = f"{db_title_from_match} | {search_info}"
                    else:
                        db_project_title = search_info
                else:
                    db_project_title = db_title_from_match if db_title_from_match else ""
            else:
                # All matches were wrong contract IDs, don't use any
                contract_id = ""
                contractor = ""
                db_project_title = ""
                db_amount = None
                # Also clear the found flags since we're rejecting all matches
                found_flood = False
                found_dime = False
                found_philgeps = False
                found_infrawatch = False
        
        # Final check: if contract_id is in wrong list, reject it completely (use normalized GAA page)
        if gaa_page_normalized in WRONG_CONTRACT_IDS:
            wrong_ids = WRONG_CONTRACT_IDS[gaa_page_normalized]
            if contract_id in wrong_ids:
                # Reject this match completely
                contract_id = ""
                contractor = ""
                db_project_title = ""
                db_amount = None
                philgeps_id = ""
                found_flood = False
                found_dime = False
                found_philgeps = False
                found_infrawatch = False
        
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
        
        # Always show search pattern (even when match found)
        if not db_project_title or (not tags and not db_project_title.startswith("SQL Pattern")):
            # No match found or pattern not shown yet - display search pattern
            if search_pattern_for_display:
                search_info = f"SQL Pattern: {search_pattern_for_display}"
                if amount:
                    search_info += f" | Amount: ₱{amount:,.0f}"
                if not db_project_title:
                    db_project_title = search_info
                elif not db_project_title.startswith("SQL Pattern"):
                    db_project_title = f"{db_project_title} | {search_info}"
        
        if tags:
            print(f"  ✅ Found in: {', '.join(tags)}")
            if contract_id:
                print(f"  📋 Contract ID: {contract_id}")
            if contractor:
                print(f"  👤 Contractor: {contractor[:50]}")
        else:
            print(f"  ❌ Not found in any database")
            if search_terms_used:
                print(f"  🔍 Search terms used: {db_project_title[:100]}")
        
        results.append({
            "project_title": project_title,
            "gaa_page": project.get("gaa_page", ""),
            "amount": project["amount"],
            "found_flood": found_flood,
            "found_dime": found_dime,
            "found_philgeps": found_philgeps,
            "found_infrawatch": found_infrawatch,
            "contract_id": contract_id,
            "contractor": contractor,
            "db_project_title": db_project_title,
            "db_amount": db_amount,
            "philgeps_id": philgeps_id
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

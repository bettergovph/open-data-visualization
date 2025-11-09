#!/usr/bin/env python3
"""
Add term information to dynasty-projects-config.json and regenerate congressman caches
with term-based validation.

This script:
1. Extracts term data from districts.json representatives field
2. Updates dynasty-projects-config.json with term information
3. Regenerates all congressman project caches with strict term validation
"""

import json
import re
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import asyncio

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flood_client import FloodControlClient


def parse_term_from_representative_string(rep_string: str) -> List[Dict[str, int]]:
    """
    Parse term information from representative string.
    
    Examples:
        "Aurelio Gonzales Jr. (2016-2025)" -> [{"start": 2016, "end": 2025}]
        "Gwendolyn Garcia (2016-2019); Pablo John Garcia (2019-present)" -> 
            [{"start": 2016, "end": 2019}, {"start": 2019, "end": 2025}]
    """
    terms = []
    
    # Pattern: (YYYY-YYYY) or (YYYY-present)
    pattern = r'\((\d{4})-(\d{4}|present)\)'
    matches = re.findall(pattern, rep_string)
    
    for start_str, end_str in matches:
        start_year = int(start_str)
        end_year = 2025 if end_str == 'present' else int(end_str)
        terms.append({"start": start_year, "end": end_year})
    
    # If no explicit terms found, assume 2016-2025 (full period)
    if not terms:
        terms.append({"start": 2016, "end": 2025})
    
    return terms


def extract_name_from_representative_string(rep_string: str) -> str:
    """Extract clean name from representative string, removing term info."""
    # Remove everything in parentheses and after semicolons
    name = re.sub(r'\([^)]*\)', '', rep_string)
    name = name.split(';')[0].strip()
    return name


def load_districts_data(districts_path: Path) -> Dict:
    """Load districts.json data."""
    with open(districts_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_config_data(config_path: Path) -> Dict:
    """Load dynasty-projects-config.json data."""
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def build_representative_term_map(districts_data: Dict) -> Dict[str, List[Dict]]:
    """
    Build a map of representative names to their terms from districts.json.
    
    Returns:
        Dict mapping normalized names to list of term dicts
    """
    rep_term_map = {}
    
    districts = districts_data.get('districts', {})
    for province, province_data in districts.items():
        representatives = province_data.get('representatives', {})
        for district, rep_string in representatives.items():
            # Handle multiple representatives separated by semicolons
            rep_entries = rep_string.split(';')
            for rep_entry in rep_entries:
                rep_entry = rep_entry.strip()
                name = extract_name_from_representative_string(rep_entry)
                terms = parse_term_from_representative_string(rep_entry)
                
                # Normalize name for matching
                normalized = name.lower().strip()
                
                if normalized not in rep_term_map:
                    rep_term_map[normalized] = []
                
                # Merge terms if they overlap or are adjacent
                for term in terms:
                    rep_term_map[normalized].append(term)
    
    # Deduplicate and merge overlapping terms
    for name, terms in rep_term_map.items():
        rep_term_map[name] = merge_overlapping_terms(terms)
    
    return rep_term_map


def merge_overlapping_terms(terms: List[Dict]) -> List[Dict]:
    """Merge overlapping or adjacent terms."""
    if not terms:
        return []
    
    # Sort by start year
    sorted_terms = sorted(terms, key=lambda t: t['start'])
    merged = [sorted_terms[0].copy()]
    
    for term in sorted_terms[1:]:
        last = merged[-1]
        # If terms overlap or are adjacent, merge them
        if term['start'] <= last['end'] + 1:
            last['end'] = max(last['end'], term['end'])
        else:
            merged.append(term.copy())
    
    return merged


def update_config_with_terms(config_data: Dict, rep_term_map: Dict[str, List[Dict]]) -> Dict:
    """Add term information to config entries."""
    updated_count = 0
    
    for entry in config_data.get('target_congressmen', []):
        display_name = entry.get('display_name', '')
        normalized = display_name.lower().strip()
        
        if normalized in rep_term_map:
            entry['terms'] = rep_term_map[normalized]
            updated_count += 1
        else:
            # Default to 2016-2025 if not found
            entry['terms'] = [{"start": 2016, "end": 2025}]
    
    print(f"✅ Updated {updated_count} entries with term data from districts.json")
    print(f"⚠️  {len(config_data.get('target_congressmen', [])) - updated_count} entries using default 2016-2025")
    
    return config_data


def extract_year_from_project(project: Dict) -> Optional[int]:
    """
    Extract year from project, checking multiple date fields.
    
    Checks: year, infra_year, award_date, start_date, end_date, completion_date
    """
    # Direct year field
    year = project.get('year')
    if year and year != 'N/A':
        try:
            return int(year)
        except (ValueError, TypeError):
            pass
    
    # Infrastructure year
    infra_year = project.get('infra_year')
    if infra_year:
        try:
            return int(infra_year)
        except (ValueError, TypeError):
            pass
    
    # Date fields (extract year from ISO date strings)
    date_fields = ['award_date', 'start_date', 'end_date', 'completion_date', 'contract_date']
    for field in date_fields:
        date_val = project.get(field)
        if date_val and isinstance(date_val, str):
            # Try to extract year from date string (YYYY-MM-DD or YYYY)
            year_match = re.match(r'(\d{4})', date_val)
            if year_match:
                try:
                    return int(year_match.group(1))
                except ValueError:
                    pass
    
    return None


def project_falls_in_terms(project: Dict, terms: List[Dict]) -> bool:
    """
    Check if project year falls within any of the congressman's terms.
    
    Returns True if:
    - Project has no year data (include by default)
    - Project year falls within any term
    """
    project_year = extract_year_from_project(project)
    
    # If no year data, include the project (can't validate)
    if project_year is None:
        return True
    
    # Check if year falls in any term
    for term in terms:
        if term['start'] <= project_year <= term['end']:
            return True
    
    return False


async def regenerate_congressman_cache(
    congressman_name: str,
    terms: List[Dict],
    province: str,
    district_number: str,
    is_partylist: bool,
    output_dir: Path,
    flood_client: FloodControlClient
):
    """Regenerate cache for a single congressman with term validation."""
    print(f"\n🔄 Regenerating cache for {congressman_name}...")
    print(f"   Terms: {terms}")
    print(f"   Province: {province}, District: {district_number}")
    
    # Load existing cache to get all projects
    cache_slug = congressman_name.lower().replace(' ', '-').replace('"', '').replace("'", "")
    cache_dir = output_dir / f"congressman-projects-{cache_slug}"
    cache_file = cache_dir / "all-projects-cache.json"
    
    if not cache_file.exists():
        print(f"   ⚠️  No existing cache found at {cache_file}, skipping...")
        return
    
    with open(cache_file, 'r', encoding='utf-8') as f:
        cache_data = json.load(f)
    
    all_projects = cache_data.get('projects', [])
    
    # Filter projects by term
    filtered_projects = []
    excluded_count = 0
    
    for project in all_projects:
        if project_falls_in_terms(project, terms):
            filtered_projects.append(project)
        else:
            excluded_count += 1
    
    print(f"   ✅ Kept {len(filtered_projects)} projects, excluded {excluded_count} outside term")
    
    # Update cache
    cache_data['projects'] = filtered_projects
    cache_data['generated_at'] = datetime.utcnow().isoformat()
    cache_data['term_validated'] = True
    cache_data['terms'] = terms
    
    # Recalculate summary
    summary = {
        "total": len(filtered_projects),
        "dime": 0,
        "philgeps": 0,
        "district_projects": 0,
        "contractor_projects": 0
    }
    
    total_cost = 0.0
    
    for project in filtered_projects:
        sources = project.get('sources_list', [project.get('source', 'Unknown')])
        if 'DIME' in sources:
            summary['dime'] += 1
        if 'PhilGEPS' in sources:
            summary['philgeps'] += 1
        if 'SSP' in sources:
            summary['ssp'] = summary.get('ssp', 0) + 1
        
        match_type = project.get('match_type', 'unknown')
        if match_type == 'district':
            summary['district_projects'] += 1
        elif match_type == 'contractor':
            summary['contractor_projects'] += 1
        
        amount = project.get('amount', 0)
        if amount:
            try:
                total_cost += float(amount)
            except (ValueError, TypeError):
                pass
    
    cache_data['summary'] = summary
    cache_data['total_cost'] = total_cost
    
    # Write updated cache
    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, indent=2, ensure_ascii=False)
    
    # Update summary.json
    summary_file = cache_dir / "summary.json"
    summary_data = {
        "congressman": congressman_name,
        "summary": summary,
        "total_cost": total_cost,
        "generated_at": datetime.utcnow().isoformat(),
        "term_validated": True,
        "terms": terms
    }
    
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary_data, f, indent=2, ensure_ascii=False)
    
    print(f"   💾 Updated cache: {len(filtered_projects)} projects, ₱{total_cost:,.2f}")


async def main():
    """Main execution."""
    print("🚀 Starting term-based cache regeneration...\n")
    
    # Paths
    root_dir = Path(__file__).resolve().parent.parent
    static_data_dir = root_dir / "static" / "data"
    districts_path = static_data_dir / "districts.json"
    config_path = static_data_dir / "dynasty-projects-config.json"
    output_dir = root_dir / "static" / "data"
    
    # Load data
    print("📖 Loading districts.json...")
    districts_data = load_districts_data(districts_path)
    
    print("📖 Loading dynasty-projects-config.json...")
    config_data = load_config_data(config_path)
    
    # Build term map
    print("\n🔍 Extracting term data from districts.json...")
    rep_term_map = build_representative_term_map(districts_data)
    print(f"   Found term data for {len(rep_term_map)} representatives")
    
    # Update config
    print("\n✏️  Updating dynasty-projects-config.json with term data...")
    updated_config = update_config_with_terms(config_data, rep_term_map)
    
    # Save updated config
    config_backup = config_path.with_suffix('.json.backup')
    print(f"\n💾 Backing up config to {config_backup.name}...")
    with open(config_backup, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)
    
    print(f"💾 Saving updated config to {config_path.name}...")
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(updated_config, f, indent=2, ensure_ascii=False)
    
    # Regenerate caches
    print("\n🔄 Regenerating congressman caches with term validation...")
    
    flood_client = FloodControlClient()
    
    for entry in updated_config.get('target_congressmen', []):
        display_name = entry.get('display_name', '')
        terms = entry.get('terms', [{"start": 2016, "end": 2025}])
        province = entry.get('province', '')
        district_number = entry.get('district_number', '')
        is_partylist = entry.get('is_partylist', False)
        
        if not display_name:
            continue
        
        await regenerate_congressman_cache(
            congressman_name=display_name,
            terms=terms,
            province=province,
            district_number=district_number,
            is_partylist=is_partylist,
            output_dir=output_dir,
            flood_client=flood_client
        )
    
    print("\n✅ All caches regenerated with term validation!")
    print(f"📊 Updated {len(updated_config.get('target_congressmen', []))} congressman caches")


if __name__ == "__main__":
    asyncio.run(main())


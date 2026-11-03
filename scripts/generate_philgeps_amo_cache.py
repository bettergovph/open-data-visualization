#!/usr/bin/env python3
"""
Generate philgeps_amo_cache.json containing analysis of PCAB AMOs (Authorized Managing Officers)
who are elected politicians. This cache powers the AMO tab in the PhilGEPS page.
"""

import asyncio
import asyncpg
import csv
import json
import os
import re
from urllib.parse import urlparse
import pandas as pd
from collections import Counter
from pathlib import Path
from typing import Dict, List, Any, Tuple
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DATA_DIR = ROOT_DIR / "static" / "data"
PARQUET_DIR = ROOT_DIR / "data" / "parquet"
OUTPUT_FILE = STATIC_DATA_DIR / "philgeps_amo_cache.json"
SEC_FILE = STATIC_DATA_DIR / "sec_contractors_database.json"
PUBLIC_ROUTE_NAME_FILE = STATIC_DATA_DIR / "public_contractor_route_people.json"
SEC_OFFICER_FILES = [
    *sorted((ROOT_DIR / "database").glob("llm_sec_officers_*.csv")),
    *sorted((ROOT_DIR / "family_analysis/family_parser/contractor_officers_csvs").glob("*.csv")),
]


def normalized_company_key(value: str) -> str:
    """Normalize business names for conservative SEC company record joins."""
    if not isinstance(value, str):
        return ""
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def normalized_person_key(value: str) -> str:
    """Normalize a full person name for strict equality matching only."""
    if not isinstance(value, str):
        return ""
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def mask_person_name(value: str) -> str:
    """Keep each token's first character and mask the remaining letters."""
    if not isinstance(value, str):
        return "*"
    def mask_token(match):
        token = match.group(0)
        return token[:1] + "*" * (len(token) - 1) if len(token) > 1 else "*"
    return re.sub(r"[^\W\d_]+", mask_token, value, flags=re.UNICODE) or "*"


def load_public_route_names() -> Dict[str, set[str]]:
    """Exact name allowlist from the unlisted legacy contractor route."""
    if not PUBLIC_ROUTE_NAME_FILE.exists():
        return {}
    try:
        payload = json.loads(PUBLIC_ROUTE_NAME_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    allowed: Dict[str, set[str]] = {}
    for company in payload.get("companies", []):
        sec_number = str(company.get("sec_number") or "").strip()
        if not sec_number:
            continue
        allowed.setdefault(sec_number, set()).update(
            normalized_person_key(name) for name in company.get("names_as_published", [])
            if normalized_person_key(name)
        )
    return allowed


def load_sec_officer_records(politician_names: set[str]) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, List[Dict[str, Any]]]]:
    """Load officer extracts and publish readable names only on exact matches."""
    by_company: Dict[str, List[Dict[str, Any]]] = {}
    by_sec_number: Dict[str, List[Dict[str, Any]]] = {}
    company_sec_numbers: Dict[str, set[str]] = {}
    public_names_by_sec = load_public_route_names()
    if SEC_FILE.exists():
        try:
            sec_payload = json.loads(SEC_FILE.read_text(encoding="utf-8"))
            for company in sec_payload.get("contractors", []):
                sec_number = str(company.get("sec_number") or "").strip()
                if not sec_number:
                    continue
                for field in ("original_contractor_name", "company_name"):
                    company_key = normalized_company_key(company.get(field))
                    if company_key:
                        company_sec_numbers.setdefault(company_key, set()).add(sec_number)
        except (OSError, json.JSONDecodeError, TypeError):
            company_sec_numbers = {}
    seen = set()
    for csv_path in SEC_OFFICER_FILES:
        try:
            with csv_path.open(encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    company_key = normalized_company_key(row.get("company_name", ""))
                    raw_name = (row.get("person_name") or "").strip()
                    if not company_key or not raw_name:
                        continue
                    person_key = normalized_person_key(raw_name)
                    role = (row.get("role") or "Officer / incorporator").strip()
                    source_url = (row.get("source_url") or "").strip()
                    source_domain = urlparse(source_url).netloc.lower() if source_url else None
                    dedupe = (company_key, person_key, role.upper(), source_url)
                    if dedupe in seen:
                        continue
                    seen.add(dedupe)
                    politician_linked = bool(person_key and person_key in politician_names)
                    sec_numbers = company_sec_numbers.get(company_key, set())
                    public_route_disclosed = bool(
                        person_key and len(sec_numbers) == 1
                        and person_key in public_names_by_sec.get(next(iter(sec_numbers)), set())
                    )
                    linked = politician_linked or public_route_disclosed
                    match_basis = (
                        "exact full-name match to political records" if politician_linked
                        else "exact name listed for this SEC company on /zarah" if public_route_disclosed
                        else "uncertain; name masked"
                    )
                    public_record = {
                        "name_display": raw_name if linked else mask_person_name(raw_name),
                        "role": role,
                        "politician_linked": politician_linked,
                        "public_route_disclosed": public_route_disclosed,
                        "match_basis": match_basis,
                        "source_domain": source_domain or None,
                        "source_file": csv_path.name,
                        "confidence_level": row.get("confidence_level") or None,
                    }
                    by_company.setdefault(company_key, []).append(public_record)
                    # Only use the SEC identifier bridge when the source company
                    # name resolves to exactly one registered company.
                    if len(sec_numbers) == 1:
                        by_sec_number.setdefault(next(iter(sec_numbers)), []).append(public_record)
        except (OSError, csv.Error, UnicodeError):
            continue
    return by_company, by_sec_number


def enrich_with_sec_company_data(amo_rows: List[Dict[str, Any]], politician_names: set[str]) -> None:
    """Attach business fields and privacy-filtered officer/incorporator records."""
    if not SEC_FILE.exists():
        return
    with SEC_FILE.open(encoding="utf-8") as f:
        payload = json.load(f)
    records = payload.get("contractors", []) if isinstance(payload, dict) else []
    by_name = {}
    for record in records:
        for candidate in (record.get("original_contractor_name"), record.get("company_name")):
            key = normalized_company_key(candidate)
            if key:
                by_name.setdefault(key, record)
    officers_by_company, officers_by_sec_number = load_sec_officer_records(politician_names)
    for amo in amo_rows:
        sec_companies = []
        for contractor in amo.get("contractors", []):
            record = by_name.get(normalized_company_key(contractor))
            if not record:
                continue
            # Business registration details only. Addresses and all person fields
            # are deliberately excluded from this public cache.
            company_key = normalized_company_key(record.get("company_name"))
            sec_number = str(record.get("sec_number") or "").strip()
            officers = officers_by_company.get(company_key, []) + officers_by_sec_number.get(sec_number, [])
            # Keep a deterministic unique list when both joins identify a row.
            officers = list({
                (person.get("name_display"), person.get("role"), person.get("source_file"), person.get("source_domain")): person
                for person in officers
            }.values())
            sec_companies.append({
                "contractor_name": contractor,
                "company_name": record.get("company_name"),
                "sec_number": record.get("sec_number"),
                "status": record.get("status"),
                "date_registered": record.get("date_registered"),
                "source": record.get("source"),
                "officers": officers,
            })
        amo["sec_companies"] = sec_companies


async def match_amos_to_politicians(pcab_amos: List[str], dynasty_conn) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Match PCAB AMO names to politicians in the dynasty database.
    Returns: (direct_matches, indirect_matches)
    - direct_matches: AMOs who are themselves elected officials
    - indirect_matches: AMOs who are related to elected officials
    """
    direct_matches = []
    indirect_matches = []
    checked = set()
    
    for amo_name in pcab_amos:
        if pd.isna(amo_name) or not amo_name or not isinstance(amo_name, str):
            continue
        
        name_clean = amo_name.strip().upper()
        if name_clean in checked:
            continue
        checked.add(name_clean)
        
        name_parts = name_clean.split()
        if len(name_parts) < 2:
            continue
        
        first_name = name_parts[0]
        last_name = name_parts[-1]
        middle_initial = None
        middle_name_full = None
        
        # Handle compound names like "JOSEPH JEREMY DE GUZMAN LARA"
        # First name could be "JOSEPH JEREMY", middle could be "DE GUZMAN"
        if len(name_parts) > 2:
            middle = name_parts[1]
            if len(middle) == 1 or middle in ['JR', 'SR', 'II', 'III', 'IV']:
                last_name = name_parts[-1]
            else:
                middle_initial = middle[0] if len(middle) > 0 else None
                # If we have multiple middle parts, use the full middle name for better matching
                if len(name_parts) > 3:
                    middle_name_full = ' '.join(name_parts[1:-1])
        
        # Try matching with first name only first
        query = """
            SELECT id, first_name, last_name, middle_name, 
                   position, position_category, government_branch,
                   province, municipality_city, district, year
            FROM political_dynasties
            WHERE UPPER(first_name) = $1 
              AND UPPER(last_name) = $2
        """
        params = [first_name, last_name]
        
        if middle_name_full:
            # Use full middle name match for better accuracy
            query += " AND (UPPER(middle_name) LIKE $3 OR UPPER(middle_name) IS NULL OR UPPER(first_name || ' ' || COALESCE(middle_name, '')) LIKE $4)"
            params.append(f"%{middle_name_full.upper()}%")
            params.append(f"%{middle_name_full.upper()}%")
        elif middle_initial:
            query += " AND (UPPER(SUBSTRING(middle_name FROM 1 FOR 1)) = $3 OR middle_name IS NULL OR UPPER(SUBSTRING(first_name FROM 1 FOR LENGTH($1) + 1)) LIKE $4)"
            params.append(middle_initial)
            params.append(f"%{first_name.upper()} {middle_initial.upper()}%")
        
        rows = await dynasty_conn.fetch(query, *params)
        
        # If multiple matches, prefer non-elected ones when AMO has detailed name
        if len(rows) > 1 and len(name_parts) > 3:
            non_elected = [r for r in rows if not (
                r['position_category'] in ['Elected Officials', 'Elected Official', 'Representative'] or
                r['government_branch'] in ('Legislative', 'Executive') or
                (r['position'] and any(term in r['position'].upper() for term in ['CONGRESS', 'SENATOR', 'MAYOR', 'GOVERNOR', 'VICE', 'REPRESENTATIVE', 'COUNCILOR', 'BOARD MEMBER']))
            )]
            if non_elected:
                rows = non_elected
        
        # If still no match and we have a compound first name, try matching first_name that contains the full first part
        if len(rows) == 0 and len(name_parts) > 3:
            compound_first = ' '.join(name_parts[:2])  # "JOSEPH JEREMY"
            query2 = """
                SELECT id, first_name, last_name, middle_name, 
                       position, position_category, government_branch,
                       province, municipality_city, district, year
                FROM political_dynasties
                WHERE UPPER(first_name) LIKE $1 
                  AND UPPER(last_name) = $2
            """
            params2 = [f"%{compound_first.upper()}%", last_name]
            rows2 = await dynasty_conn.fetch(query2, *params2)
            if rows2:
                rows = rows2
        
        for row in rows:
            position = row['position'] or ''
            position_category = row['position_category']
            gov_branch = row['government_branch']
            
            is_elected = (
                position_category in ['Elected Officials', 'Elected Official'] or
                gov_branch in ['Legislative', 'Executive'] or
                (position and any(term in position.upper() for term in ['CONGRESS', 'SENATOR', 'MAYOR', 'GOVERNOR', 'VICE', 'REPRESENTATIVE', 'COUNCILOR', 'BOARD MEMBER']))
            )
            
            match_data = {
                'pcab_amo': amo_name,
                'dynasty_id': row['id'],
                'full_name': f"{row['first_name']} {row['middle_name'] or ''} {row['last_name']}".strip(),
                'position': position,
                'position_category': position_category,
                'government_branch': gov_branch,
                'province': row['province'],
                'municipality_city': row['municipality_city'],
                'district': row['district'],
                'year': row['year'],
                'is_elected': is_elected
            }
            
            if is_elected:
                direct_matches.append(match_data)
            else:
                # Check for family relationships to elected officials
                related_elected = await find_related_elected_officials(row['id'], dynasty_conn)
                if related_elected:
                    for rel in related_elected:
                        indirect_matches.append({
                            **match_data,
                            'relationship_type': rel['relationship_type'],
                            'related_person_id': rel['related_person_id'],
                            'related_person_name': rel['related_person_name'],
                            'related_person_position': rel['related_person_position'],
                            'related_person_province': rel['related_person_province'],
                            'related_person_municipality_city': rel['related_person_municipality_city'],
                            'related_person_year': rel['related_person_year']
                        })
    
    return direct_matches, indirect_matches


async def find_related_elected_officials(person_id: int, dynasty_conn) -> List[Dict[str, Any]]:
    """Find elected officials related to a person through family relationships."""
    # Family relationship type IDs: 1-13 (Father, Mother, Son, Daughter, Husband, Wife, 
    # Brother, Sister, Uncle, Aunt, Nephew, Niece, Cousin)
    family_type_ids = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]
    
    # Find relationships where this person is related to elected officials
    relationships = await dynasty_conn.fetch("""
        SELECT r.related_person_id, ct.name as relationship_type,
               p.first_name, p.last_name, p.middle_name,
               p.position, p.province, p.municipality_city, p.year
        FROM relationships r
        JOIN connection_types ct ON r.relationship_type = ct.id
        JOIN political_dynasties p ON r.related_person_id = p.id
        WHERE r.person_id = $1
          AND r.relationship_type = ANY($2::int[])
          AND (
              p.position_category IN ('Elected Officials', 'Elected Official', 'Representative')
              OR p.government_branch IN ('Legislative', 'Executive')
              OR (p.position IS NOT NULL AND (
                  p.position ILIKE '%MAYOR%' OR
                  p.position ILIKE '%GOVERNOR%' OR
                  p.position ILIKE '%CONGRESS%' OR
                  p.position ILIKE '%REPRESENTATIVE%' OR
                  p.position ILIKE '%COUNCILOR%' OR
                  p.position ILIKE '%BOARD MEMBER%' OR
                  p.position ILIKE '%SENATOR%'
              ))
          )
    """, person_id, family_type_ids)
    
    results = []
    for rel in relationships:
        results.append({
            'relationship_type': rel['relationship_type'],
            'related_person_id': rel['related_person_id'],
            'related_person_name': f"{rel['first_name']} {rel['middle_name'] or ''} {rel['last_name']}".strip(),
            'related_person_position': rel['position'],
            'related_person_province': rel['province'],
            'related_person_municipality_city': rel['municipality_city'],
            'related_person_year': rel['year']
        })
    
    return results


def categorize_position(position: str) -> str:
    """Categorize position into a standard type."""
    if not position:
        return 'Other'
    pos_upper = position.upper()
    if 'MAYOR' in pos_upper:
        return 'Mayor'
    elif 'COUNCILOR' in pos_upper:
        return 'Councilor'
    elif 'GOVERNOR' in pos_upper:
        return 'Governor'
    elif 'REPRESENTATIVE' in pos_upper or 'CONGRESS' in pos_upper:
        return 'Congressman'
    elif 'BOARD MEMBER' in pos_upper:
        return 'Provincial Board'
    elif 'SENATOR' in pos_upper:
        return 'Senator'
    else:
        return 'Other'


async def generate_amo_cache():
    """Generate the AMO analysis cache file."""
    print("🔍 Generating PhilGEPS AMO Analysis Cache...")
    
    # Load PhilGEPS parquet
    parquet_path = PARQUET_DIR / "philgeps_contracts.parquet"
    if not parquet_path.exists():
        print(f"❌ PhilGEPS parquet file not found: {parquet_path}")
        return
    
    print(f"📖 Loading PhilGEPS parquet from {parquet_path}...")
    df = pd.read_parquet(parquet_path)
    pcab_amos = df['pcab_amo'].dropna().unique()
    print(f"✅ Found {len(pcab_amos):,} unique PCAB AMO names")
    
    # Connect to dynasty database
    print("🔗 Connecting to dynasty database...")
    dynasty_conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', 5432)),
        user=os.getenv('POSTGRES_USER', 'budget_admin'),
        password=os.getenv('POSTGRES_PASSWORD', ''),
        database='dynasty'
    )
    
    try:
        # Match AMOs to politicians (direct and indirect)
        print("🔍 Matching PCAB AMOs to politicians...")
        direct_matches, indirect_matches = await match_amos_to_politicians(pcab_amos, dynasty_conn)
        print(f"✅ Found {len(direct_matches)} direct matches (AMOs who are elected)")
        print(f"✅ Found {len(indirect_matches)} indirect matches (AMOs related to elected officials)")
        
        # Count by position type for direct matches
        position_counts = Counter()
        for m in direct_matches:
            pos_type = categorize_position(m['position'])
            position_counts[pos_type] += 1
        
        # Get contract counts and amounts for direct elected AMOs
        print("📊 Computing contract statistics for direct matches...")
        direct_amo_names = {m['pcab_amo'].upper() for m in direct_matches}
        df['is_direct_elected_amo'] = df['pcab_amo'].notna() & df['pcab_amo'].str.upper().isin(direct_amo_names)
        
        # Get unique contractor names for each AMO
        direct_contractors = df[df['is_direct_elected_amo']].groupby('pcab_amo')['contractor_name'].apply(
            lambda x: sorted(x.dropna().unique().tolist())
        ).to_dict()
        
        contracts_by_direct = df[df['is_direct_elected_amo']].groupby('pcab_amo').agg({
            'contract_amount': ['count', 'sum']
        }).reset_index()
        contracts_by_direct.columns = ['pcab_amo', 'contract_count', 'total_amount']
        contracts_by_direct = contracts_by_direct.sort_values('total_amount', ascending=False)
        
        # Merge with politician info for direct matches
        top_direct = []
        for _, row in contracts_by_direct.iterrows():
            amo_name = row['pcab_amo']
            match_info = next((m for m in direct_matches if m['pcab_amo'] == amo_name), None)
            if match_info:
                top_direct.append({
                    'pcab_amo': amo_name,
                    'full_name': match_info['full_name'],
                    'position': match_info['position'],
                    'year': int(match_info['year']) if match_info['year'] else None,
                    'province': match_info['province'],
                    'municipality_city': match_info['municipality_city'],
                    'contract_count': int(row['contract_count']),
                    'total_amount': float(row['total_amount']),
                    'contractors': direct_contractors.get(amo_name, [])
                })
        
        # Get contract counts and amounts for indirect matches
        print("📊 Computing contract statistics for indirect matches...")
        indirect_amo_names = {m['pcab_amo'].upper() for m in indirect_matches}
        df['is_indirect_elected_amo'] = df['pcab_amo'].notna() & df['pcab_amo'].str.upper().isin(indirect_amo_names)
        
        # Get unique contractor names for each AMO
        indirect_contractors = df[df['is_indirect_elected_amo']].groupby('pcab_amo')['contractor_name'].apply(
            lambda x: sorted(x.dropna().unique().tolist())
        ).to_dict()
        
        contracts_by_indirect = df[df['is_indirect_elected_amo']].groupby('pcab_amo').agg({
            'contract_amount': ['count', 'sum']
        }).reset_index()
        contracts_by_indirect.columns = ['pcab_amo', 'contract_count', 'total_amount']
        contracts_by_indirect = contracts_by_indirect.sort_values('total_amount', ascending=False)
        
        # Merge with politician info for indirect matches
        top_indirect = []
        for _, row in contracts_by_indirect.iterrows():
            amo_name = row['pcab_amo']
            # Get all indirect matches for this AMO (may have multiple relationships)
            amo_indirect_matches = [m for m in indirect_matches if m['pcab_amo'] == amo_name]
            if amo_indirect_matches:
                # Use the first match (or could aggregate if multiple relationships)
                match_info = amo_indirect_matches[0]
                top_indirect.append({
                    'pcab_amo': amo_name,
                    'full_name': match_info['full_name'],
                    'relationship_type': match_info['relationship_type'],
                    'related_person_name': match_info['related_person_name'],
                    'related_person_position': match_info['related_person_position'],
                    'related_person_year': int(match_info['related_person_year']) if match_info['related_person_year'] else None,
                    'related_person_province': match_info['related_person_province'],
                    'related_person_municipality_city': match_info['related_person_municipality_city'],
                    'contract_count': int(row['contract_count']),
                    'total_amount': float(row['total_amount']),
                    'contractors': indirect_contractors.get(amo_name, [])
                })

        # SEC cache has business registration fields, but not verified officer
        # records. Keep this enrichment to business identifiers only.
        politician_names = {
            normalized_person_key(m.get("full_name", "")) for m in direct_matches
        }
        politician_names.update(
            normalized_person_key(m.get("related_person_name", "")) for m in indirect_matches
        )
        politician_names.discard("")
        enrich_with_sec_company_data(top_direct, politician_names)
        enrich_with_sec_company_data(top_indirect, politician_names)
        
        # Prepare output
        total_direct_contracts = int(df['is_direct_elected_amo'].sum())
        total_indirect_contracts = int(df['is_indirect_elected_amo'].sum())
        total_direct_value = float(df[df['is_direct_elected_amo']]['contract_amount'].sum())
        total_indirect_value = float(df[df['is_indirect_elected_amo']]['contract_amount'].sum())
        
        output_data = {
            "success": True,
            "generated_at": pd.Timestamp.now().isoformat(),
            "summary": {
                "total_unique_amos": int(len(pcab_amos)),
                "amos_matching_politicians": len(direct_matches) + len(set(m['pcab_amo'] for m in indirect_matches)),
                "amos_with_elected_positions": len(direct_matches),
                "amos_related_to_elected": len(set(m['pcab_amo'] for m in indirect_matches)),
                "match_percentage": round(len(direct_matches) / (len(direct_matches) + len(set(m['pcab_amo'] for m in indirect_matches))) * 100, 1) if (len(direct_matches) + len(set(m['pcab_amo'] for m in indirect_matches))) > 0 else 0,
                "total_contracts_direct": total_direct_contracts,
                "total_contract_value_direct": total_direct_value,
                "total_contracts_indirect": total_indirect_contracts,
                "total_contract_value_indirect": total_indirect_value,
                "total_contracts_with_elected": total_direct_contracts + total_indirect_contracts,
                "total_contract_value": total_direct_value + total_indirect_value
            },
            "breakdown": dict(position_counts),
            "top_direct": top_direct,
            "top_indirect": top_indirect
        }
        
        # Ensure output directory exists
        STATIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        # Write cache file
        print(f"💾 Writing cache to {OUTPUT_FILE}...")
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Cache generated successfully!")
        print(f"   📊 Total unique AMOs: {output_data['summary']['total_unique_amos']:,}")
        print(f"   👥 AMOs matching politicians: {output_data['summary']['amos_matching_politicians']:,}")
        print(f"   🏛️  Direct elected AMOs: {output_data['summary']['amos_with_elected_positions']:,}")
        print(f"   👨‍👩‍👧‍👦 Indirect (related) AMOs: {output_data['summary']['amos_related_to_elected']:,}")
        print(f"   💰 Direct contract value: ₱{output_data['summary']['total_contract_value_direct']:,.2f}")
        print(f"   💰 Indirect contract value: ₱{output_data['summary']['total_contract_value_indirect']:,.2f}")
        print(f"   💰 Total contract value: ₱{output_data['summary']['total_contract_value']:,.2f}")
        print(f"   📄 Top direct AMOs: {len(top_direct)}")
        print(f"   📄 Top indirect AMOs: {len(top_indirect)}")
        
    finally:
        await dynasty_conn.close()


if __name__ == "__main__":
    asyncio.run(generate_amo_cache())


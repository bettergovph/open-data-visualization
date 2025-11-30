#!/usr/bin/env python3
"""
Download DO 172 s2016 PDF, parse integrated project code rules, and test on philgeps projects.

Integrated Project Code Format: YYRDSSSS
- YY = Year (2 digits, e.g., 17 for 2017)
- R = Region letter (1 letter, A-Z, Z for Central Office)
- D = District letter (1 letter, A-Z, varies by region)
- SSSS = Sequence (4 digits, e.g., 0001)

Example: 17DB0001
- Year: 17 (2017)
- Region: D (Region IV-A)
- District: B (Batangas 1st DEO)
- Sequence: 0001

The mapping file (database/dpwh-project-code-mapping.json) contains:
- Region letters -> Region names (A=Region I, B=Region II, D=Region IV-A, etc.)
- District letters -> DEO names within each region (e.g., D.B = Batangas 1st DEO)
"""
import os
import sys
import requests
import pdfplumber
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dotenv import load_dotenv
import asyncpg
import json

load_dotenv()

def download_pdf(url: str, output_path: Path) -> bool:
    """Download PDF from URL"""
    try:
        print(f"📥 Downloading {url}...")
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        
        with open(output_path, 'wb') as f:
            f.write(response.content)
        
        print(f"✅ Downloaded {len(response.content) / 1024:.2f} KB to {output_path}")
        return True
    except Exception as e:
        print(f"❌ Error downloading PDF: {e}")
        return False

def parse_pdf(pdf_path: Path) -> str:
    """Extract text from PDF"""
    print(f"📖 Parsing PDF: {pdf_path}")
    text = ""
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
                print(f"  Processed page {i+1}/{len(pdf.pages)}")
    except Exception as e:
        print(f"❌ Error parsing PDF: {e}")
        return ""
    
    print(f"✅ Extracted {len(text)} characters")
    return text

def extract_district_rules(text: str) -> Dict:
    """Extract integrated project code classification rules from PDF text
    
    Format: YYRDSSSS
    - YY = Year (2 digits, e.g., 17)
    - R = Region (1 letter, e.g., D)
    - D = District (1 letter, e.g., B)
    - SSSS = Sequence (4 digits, e.g., 0001)
    
    Example: 17DB0001 = Year 17, Region D, District B, Sequence 0001
    """
    print("🔍 Extracting integrated project code classification rules...")
    
    rules = {
        'code_format': 'YYRDSSSS',  # Year(2) + Region(1) + District(1) + Sequence(4)
        'region_mapping': {},  # Letter -> Region name/number
        'district_mapping': {},  # Letter -> District number
        'examples': [],
        'full_text_sections': []
    }
    
    # Look for code format description
    format_patterns = [
        re.compile(r'(\d{2})([A-Z])([A-Z])(\d{4})', re.IGNORECASE),  # 17DB0001 pattern
        re.compile(r'year[:\s=]+(\d+).*?region[:\s=]+([A-Z]).*?district[:\s=]+([A-Z]).*?sequence[:\s=]+(\d+)', re.IGNORECASE),
    ]
    
    # Extract code examples
    for pattern in format_patterns:
        matches = pattern.findall(text)
        if matches:
            print(f"  Found {len(matches)} code format examples")
            for match in matches:
                if len(match) >= 4:
                    year, region, district, sequence = match[0], match[1], match[2], match[3]
                    code = f"{year}{region}{district}{sequence}"
                    rules['examples'].append({
                        'code': code,
                        'year': year,
                        'region': region.upper(),
                        'district': district.upper(),
                        'sequence': sequence
                    })
    
    # Look for region letter mappings
    # Patterns: "Region D = Region IV" or "D = Region IV" or "Region D: Region IV"
    region_patterns = [
        re.compile(r'region\s+([A-Z])\s*[=:]\s*(?:region\s+)?([IVX\d]+|[\w\s]+)', re.IGNORECASE),
        re.compile(r'([A-Z])\s*[=:]\s*region\s+([IVX\d]+|[\w\s]+)', re.IGNORECASE),
        re.compile(r'letter\s+([A-Z])\s*(?:represents?|stands? for|is)\s*(?:region\s+)?([IVX\d]+|[\w\s]+)', re.IGNORECASE),
    ]
    
    for pattern in region_patterns:
        matches = pattern.findall(text)
        if matches:
            print(f"  Found {len(matches)} region mappings")
            for match in matches:
                if len(match) >= 2:
                    letter = match[0].upper()
                    region = match[1].strip()
                    rules['region_mapping'][letter] = region
    
    # Look for district letter mappings
    # Patterns: "District B = District 1" or "B = District 1" or "District B: District 1"
    district_patterns = [
        re.compile(r'district\s+([A-Z])\s*[=:]\s*(?:district\s+)?(\d+)', re.IGNORECASE),
        re.compile(r'([A-Z])\s*[=:]\s*district\s+(\d+)', re.IGNORECASE),
        re.compile(r'letter\s+([A-Z])\s*(?:represents?|stands? for|is)\s*(?:district\s+)?(\d+)', re.IGNORECASE),
    ]
    
    for pattern in district_patterns:
        matches = pattern.findall(text)
        if matches:
            print(f"  Found {len(matches)} district mappings")
            for match in matches:
                if len(match) >= 2:
                    letter = match[0].upper()
                    district_num = match[1].strip()
                    rules['district_mapping'][letter] = district_num
    
    # Look for tables with mappings
    # Common table format: Letter | District Number | Description
    table_patterns = [
        re.compile(r'([A-Z])\s+\|\s*(\d+)\s+\|', re.IGNORECASE),  # A | 1 |
        re.compile(r'([A-Z])\s+(\d+)\s+', re.IGNORECASE),  # A 1 (space-separated)
    ]
    
    for pattern in table_patterns:
        matches = pattern.findall(text)
        if matches:
            print(f"  Found {len(matches)} potential table entries")
            for match in matches:
                if len(match) >= 2:
                    letter = match[0].upper()
                    num = match[1].strip()
                    # Try to determine if it's region or district based on context
                    # For now, assume it's district if number is 1-250, region if Roman numeral
                    if num.isdigit() and 1 <= int(num) <= 250:
                        if letter not in rules['district_mapping']:
                            rules['district_mapping'][letter] = num
                    elif re.match(r'^[IVX]+$', num, re.IGNORECASE):
                        if letter not in rules['region_mapping']:
                            rules['region_mapping'][letter] = num
    
    # Look for sections about integrated project codes
    ipc_keywords = ['integrated project code', 'project code', 'ipc', 'code format', 'classification', 'district', 'region']
    lines = text.split('\n')
    
    relevant_sections = []
    
    for i, line in enumerate(lines):
        line_lower = line.lower()
        if any(keyword in line_lower for keyword in ipc_keywords):
            # Collect context around relevant lines
            context_start = max(0, i-3)
            context_end = min(len(lines), i+4)
            context = '\n'.join(lines[context_start:context_end])
            relevant_sections.append({
                'line_number': i+1,
                'context': context,
                'line': line
            })
    
    rules['full_text_sections'] = relevant_sections[:100]  # Limit to first 100
    
    print(f"✅ Extracted:")
    print(f"    - Code format: {rules['code_format']}")
    print(f"    - Code examples: {len(rules['examples'])}")
    print(f"    - Region mappings: {len(rules['region_mapping'])}")
    print(f"    - District mappings: {len(rules['district_mapping'])}")
    print(f"    - Relevant sections: {len(rules['full_text_sections'])}")
    
    if rules['region_mapping']:
        print(f"\n  Region mappings: {rules['region_mapping']}")
    if rules['district_mapping']:
        print(f"  District mappings: {rules['district_mapping']}")
    
    return rules

def parse_project_code(project_code: str) -> Optional[Dict]:
    """Parse integrated project code into components
    
    Format: YYRDSSSS
    - YY = Year (2 digits)
    - R = Region (1 letter)
    - D = District (1 letter)
    - SSSS = Sequence (4 digits)
    
    Returns dict with year, region_letter, district_letter, sequence, or None if invalid
    """
    if not project_code:
        return None
    
    project_code = project_code.strip().upper()
    
    # Remove any dashes or spaces
    project_code = re.sub(r'[-\s]', '', project_code)
    
    # Match pattern: YYRDSSSS (8 characters total)
    # Or variations like YY-R-D-SSSS
    pattern = re.match(r'^(\d{2})([A-Z])([A-Z])(\d{4})$', project_code)
    if pattern:
        year, region_letter, district_letter, sequence = pattern.groups()
        return {
            'year': year,
            'region_letter': region_letter,
            'district_letter': district_letter,
            'sequence': sequence,
            'full_code': project_code
        }
    
    return None

def load_code_mapping(mapping_file: Path = None) -> Dict:
    """Load the DPWH project code mapping from JSON file"""
    if mapping_file is None:
        # Default location relative to script
        script_dir = Path(__file__).parent.parent
        mapping_file = script_dir / "database" / "dpwh-project-code-mapping.json"
    
    if not mapping_file.exists():
        print(f"⚠️  Mapping file not found: {mapping_file}")
        return {}
    
    try:
        with open(mapping_file, 'r', encoding='utf-8') as f:
            mapping = json.load(f)
        print(f"✅ Loaded code mapping from {mapping_file}")
        return mapping
    except Exception as e:
        print(f"❌ Error loading mapping file: {e}")
        return {}

def classify_project_by_code(project_code: str, code_mapping: Dict = None) -> Optional[Dict]:
    """Classify a project using integrated project code and mapping file
    
    Format: YYRDSSSS
    - YY = Year (2 digits)
    - R = Region letter (A-Z, Z for Central Office)
    - D = District letter (A-Z, varies by region)
    - SSSS = Sequence (4 digits)
    
    Returns dict with classification info:
    {
        'district_letter': 'B',
        'district_deo': 'Batangas 1st DEO',
        'region': 'Region IV-A',
        'region_letter': 'D',
        'year': '17',
        'sequence': '0001',
        'full_code': '17DB0001'
    }
    """
    if not project_code:
        return None
    
    # Parse the code
    parsed = parse_project_code(project_code)
    if not parsed:
        return None
    
    classification = {
        'parsed_code': parsed,
        'district_letter': parsed['district_letter'],
        'district_deo': None,
        'region': None,
        'region_letter': parsed['region_letter'],
        'year': parsed['year'],
        'sequence': parsed['sequence'],
        'full_code': parsed['full_code']
    }
    
    # Use the mapping file if provided
    if code_mapping:
        region_letter = parsed['region_letter']
        district_letter = parsed['district_letter']
        
        # Get region info
        if region_letter in code_mapping:
            region_info = code_mapping[region_letter]
            classification['region'] = region_info.get('region_name', None)
            
            # Get district/DEO info
            districts = region_info.get('districts', {})
            if district_letter in districts:
                classification['district_deo'] = districts[district_letter]
            else:
                classification['district_deo'] = f"Unknown district '{district_letter}' in region {region_letter}"
        else:
            classification['region'] = f"Unknown region '{region_letter}'"
            classification['district_deo'] = f"Unknown district '{district_letter}'"
    
    return classification

def extract_project_code(project: Dict) -> Optional[str]:
    """Extract integrated project code from project data"""
    # Common field names for project codes
    code_fields = [
        'project_code', 'code', 'ipc', 'integrated_project_code',
        'project_id', 'contract_id', 'reference_number', 'ref_number',
        'project_number', 'project_no', 'contract_number', 'contract_no'
    ]
    
    for field in code_fields:
        if field in project and project[field]:
            code = str(project[field]).strip()
            if code and len(code) >= 3:  # Reasonable minimum length
                return code
    
    # Also check if code might be embedded in other fields
    text_fields = ['name', 'title', 'description', 'project_name', 'project_description']
    for field in text_fields:
        if field in project and project[field]:
            text = str(project[field])
            # Look for code-like patterns: YYRDSSSS
            code_match = re.search(r'(\d{2}[A-Z]{2}\d{4})', text, re.IGNORECASE)
            if code_match:
                return code_match.group(1)
    
    return None

async def get_philgeps_projects(limit: int = 10) -> List[Dict]:
    """Get philgeps projects from database"""
    print(f"📊 Fetching {limit} philgeps projects from database...")
    
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'budget_admin'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DB', 'budget')
        )
        
        # Try to find philgeps projects table
        # Common table names: projects, philgeps_projects, contracts, etc.
        query = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND (table_name LIKE '%philgeps%' OR table_name LIKE '%project%' OR table_name LIKE '%contract%')
            ORDER BY table_name
            LIMIT 10
        """
        
        tables = await conn.fetch(query)
        print(f"  Found {len(tables)} potential tables: {[t['table_name'] for t in tables]}")
        
        # Try to get projects from the most likely table
        projects = []
        for table in tables:
            table_name = table['table_name']
            try:
                # Get column names
                col_query = f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = '{table_name}'
                """
                columns = await conn.fetch(col_query)
                col_names = [c['column_name'] for c in columns]
                
                # Look for location/project name columns
                location_cols = [c for c in col_names if any(x in c.lower() for x in ['location', 'address', 'place', 'site', 'municipality', 'city', 'province'])]
                name_cols = [c for c in col_names if any(x in c.lower() for x in ['name', 'title', 'project', 'description'])]
                
                if location_cols or name_cols:
                    select_cols = ['*']  # Select all for now
                    query = f"SELECT * FROM {table_name} LIMIT {limit}"
                    rows = await conn.fetch(query)
                    
                    for row in rows:
                        project = dict(row)
                        projects.append(project)
                    
                    if projects:
                        print(f"  ✅ Found {len(projects)} projects from {table_name}")
                        break
            except Exception as e:
                print(f"  ⚠️  Error querying {table_name}: {e}")
                continue
        
        await conn.close()
        return projects[:limit]
        
    except Exception as e:
        print(f"❌ Error connecting to database: {e}")
        return []

async def main():
    """Main function"""
    print("=" * 80)
    print("DO 172 s2016 Integrated Project Code Parser and Tester")
    print("=" * 80)
    print()
    
    # Setup paths
    script_dir = Path(__file__).parent
    pdf_path = script_dir / "DO_172_s2016.pdf"
    pdf_url = "https://www.dpwh.gov.ph/dpwh/sites/default/files/issuances/DO_172_s2016.pdf"
    
    # Download PDF if not exists
    if not pdf_path.exists():
        if not download_pdf(pdf_url, pdf_path):
            print("❌ Failed to download PDF")
            return
    else:
        print(f"✅ PDF already exists: {pdf_path}")
    
    # Parse PDF
    text = parse_pdf(pdf_path)
    if not text:
        print("❌ Failed to parse PDF")
        return
    
    # Extract rules from PDF
    rules = extract_district_rules(text)
    
    # Load the official code mapping
    code_mapping = load_code_mapping()
    
    # Save extracted rules
    rules_path = script_dir / "DO_172_rules.json"
    with open(rules_path, 'w', encoding='utf-8') as f:
        json.dump(rules, f, indent=2, ensure_ascii=False)
    print(f"💾 Saved rules to {rules_path}")
    
    # Get philgeps projects
    projects = await get_philgeps_projects(limit=10)
    
    if not projects:
        print("⚠️  No projects found. Trying alternative data sources...")
        # Could try reading from parquet file or other sources
        return
    
    # Test classification
    print()
    print("=" * 80)
    print("Testing Classification on PhilGEPS Projects")
    print("=" * 80)
    print()
    
    results = []
    for i, project in enumerate(projects, 1):
        print(f"[{i}/{len(projects)}] Project:")
        
        # Show project info
        project_info = {k: v for k, v in project.items() if v is not None}
        print(f"  Keys: {list(project_info.keys())[:10]}")
        
        # Extract project code
        project_code = extract_project_code(project)
        if project_code:
            print(f"  📋 Project Code: {project_code}")
        else:
            print(f"  ⚠️  No project code found")
        
        # Try to classify using project code
        classification = None
        if project_code:
            classification = classify_project_by_code(project_code, code_mapping)
        
        result = {
            'project_index': i,
            'project_code': project_code,
            'project_data': project_info,
            'classification': classification
        }
        results.append(result)
        
        if classification:
            district_deo = classification.get('district_deo', 'Unknown')
            region_info = classification.get('region', 'Unknown')
            print(f"  ✅ Classification:")
            print(f"     Region: {region_info} ({classification.get('region_letter', 'N/A')})")
            print(f"     District/DEO: {district_deo} ({classification.get('district_letter', 'N/A')})")
            print(f"     Year: {classification.get('year', 'N/A')}")
            print(f"     Sequence: {classification.get('sequence', 'N/A')}")
            print(f"     Full Code: {classification.get('full_code', 'N/A')}")
        else:
            print(f"  ⚠️  Could not parse or classify project code")
        print()
    
    # Save results
    results_path = script_dir / "DO_172_test_results.json"
    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"💾 Saved test results to {results_path}")
    
    # Summary
    classified = sum(1 for r in results if r['classification'])
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total projects tested: {len(results)}")
    print(f"Successfully classified: {classified}")
    print(f"Could not classify: {len(results) - classified}")
    if len(results) > 0:
        print(f"Success rate: {classified/len(results)*100:.1f}%")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())


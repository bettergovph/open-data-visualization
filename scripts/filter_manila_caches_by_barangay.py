import json
import re
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
STATIC_DATA_DIR = ROOT / 'static' / 'data'
CONFIG_PATH = STATIC_DATA_DIR / 'dynasty-projects-config.json'
DISTRICTS_PATH = STATIC_DATA_DIR / 'districts.json'
CACHE_ROOT = STATIC_DATA_DIR

TARGET_CONGRESSMEN = [
    'Manny Lopez',
    'Rolan Valeriano',
    'Rolando M. Valeriano',
    'Joel R. Chua',
    'John Marvin Nieto',
    'Edward M. Maceda',
    'William Irwin C. Tieng',
    'Amanda Christina Bagatsing',
    'Bienvenido Abante',
    'Ernesto M. Dionisio Jr.',
]

# Barangay number ranges per Manila district (based on COMELEC districting)
BARANGAY_RANGES: Dict[str, Tuple[int, int]] = {
    '1st District': (1, 146),
    '2nd District': (147, 267),
    '3rd District': (268, 394),
    '4th District': (395, 648),
    '5th District': (649, 900),
    '6th District': (901, 1000),
}

# Additional location keywords per district (fallback when specific barangay names appear)
DISTRICT_KEYWORDS: Dict[str, List[str]] = {
    '1st District': ['TONDO I', 'TONDO 1', 'TONDO'],
    '2nd District': ['TONDO II', 'TONDO 2', 'TONDO'],
    '3rd District': ['QUIAPO', 'BINONDO', 'SAN NICOLAS', 'STA. CRUZ', 'SANTA CRUZ'],
    '4th District': ['SAMPALOC'],
    '5th District': ['PACO', 'PANDACAN', 'SAN ANDRES', 'STA. ANA', 'SANTA ANA'],
    '6th District': ['ERMITA', 'MALATE', 'INTRAMUROS', 'SAN MIGUEL', 'PORT AREA'],
}

# Barangay tokens derived from districts.json for Manila
DISTRICT_BARANGAY_TOKENS: Dict[str, List[str]] = {}
DISTRICT_BARANGAY_NUMBERS: Dict[str, List[int]] = {}

# Precompile regex for detecting barangay numbers (covers Barangay, Brgy., etc.)
BARANGAY_PATTERNS = [
    re.compile(r'(?:BARANGAY|BRGY|BRG|BGY)\s*(?:NO\.?\s*)?(\d{1,4})', re.IGNORECASE),
    re.compile(r'(?:BARANGAY|BRGY|BRG|BGY)\s*(?:NO\.?\s*)?(\d{1,4})\s*(?:[-–]|TO)\s*(\d{1,4})', re.IGNORECASE),
]


def slugify(name: str) -> str:
    return name.lower().replace(' ', '-').replace('.', '')


def load_config() -> Dict[str, Dict]:
    with CONFIG_PATH.open() as fh:
        data = json.load(fh)['target_congressmen']
    return {entry['display_name']: entry for entry in data}


def initialize_district_tokens() -> None:
    if not DISTRICTS_PATH.exists():
        return
    with DISTRICTS_PATH.open() as fh:
        data = json.load(fh)
    manila_info = data.get('districts', {}).get('Manila', {})
    barangay_map = manila_info.get('barangays', {})

    for district, names in barangay_map.items():
        tokens = []
        numbers = set()
        for name in names:
            upper = name.upper().strip()
            if upper:
                tokens.append(upper)
            cleaned = upper.replace('NO.', '').replace('NO', '')
            parts = cleaned.split()
            digits = [p for p in parts if p.isdigit()]
            if digits:
                try:
                    num = int(digits[-1])
                except ValueError:
                    continue
                numbers.add(num)
                base = str(num)
                tokens.extend([
                    f'BARANGAY {base}',
                    f'BARANGAY NO {base}',
                    f'BARANGAY NO. {base}',
                    f'BRGY {base}',
                    f'BRGY. {base}',
                    f'BRG {base}',
                    f'BGY {base}'
                ])
        DISTRICT_BARANGAY_TOKENS[district] = sorted(set(tokens))
        DISTRICT_BARANGAY_NUMBERS[district] = sorted(numbers)


def extract_barangay_numbers(text: str) -> List[int]:
    numbers = set()
    for pattern in BARANGAY_PATTERNS:
        for match in pattern.finditer(text):
            groups = match.groups()
            if len(groups) >= 2 and groups[0] and groups[1]:
                try:
                    start = int(groups[0])
                    end = int(groups[1])
                except ValueError:
                    continue
                if start > end:
                    start, end = end, start
                for value in range(start, end + 1):
                    numbers.add(value)
                continue
            for group in groups:
                if not group:
                    continue
                try:
                    num = int(group)
                    numbers.add(num)
                except ValueError:
                    continue
    return sorted(numbers)


def map_numbers_to_district(numbers: List[int]) -> List[str]:
    districts = []
    for num in numbers:
        for district, (low, high) in BARANGAY_RANGES.items():
            if low <= num <= high:
                districts.append(district)
                break
    return districts


def project_matches_district(project: Dict, district: str) -> bool:
    text_parts = [
        project.get('project_name', ''),
        project.get('location', ''),
        project.get('description', ''),
    ]
    combined = ' '.join(filter(None, text_parts)).upper()

    barangay_numbers = extract_barangay_numbers(combined)
    if barangay_numbers:
        mapped_districts = map_numbers_to_district(barangay_numbers)
        if mapped_districts:
            if all(d == district for d in mapped_districts):
                return True
            # Numbers present but point to other districts -> reject
            return False

    # Try explicit barangay tokens (BRGY, Barangay forms)
    tokens = DISTRICT_BARANGAY_TOKENS.get(district, [])
    for token in tokens:
        if token and token in combined:
            return True

    # Fall back to broader district-level keywords (Paco, Tondo, etc.)
    keywords = DISTRICT_KEYWORDS.get(district, [])
    for keyword in keywords:
        if keyword and keyword in combined:
            return True

    return False


def filter_projects_for_congressman(congressman_name: str, congressman_config: Dict) -> None:
    district = congressman_config.get('district_number')
    slug = slugify(congressman_name)
    cache_dir = CACHE_ROOT / f'congressman-projects-{slug}'
    cache_file = cache_dir / 'all-projects-cache.json'
    summary_file = cache_dir / 'summary.json'

    if not cache_file.exists():
        print(f"⚠️  Cache not found for {congressman_name} ({cache_file})")
        return

    with cache_file.open() as fh:
        cache_data = json.load(fh)

    projects = cache_data.get('projects', [])
    filtered = [proj for proj in projects if project_matches_district(proj, district)]

    removed = len(projects) - len(filtered)
    print(f"{congressman_name}: kept {len(filtered)} / {len(projects)} projects (removed {removed})")

    # Recompute aggregates
    total_cost = 0.0
    district_cost = 0.0
    contractor_cost = 0.0

    for proj in filtered:
        amount = proj.get('amount') or 0
        try:
            amount = float(str(amount).replace('₱', '').replace(',', ''))
        except ValueError:
            amount = 0.0
        total_cost += amount
        if proj.get('match_type') == 'contractor':
            contractor_cost += amount
        else:
            district_cost += amount

    cache_data['projects'] = filtered
    cache_data['summary']['total'] = len(filtered)
    cache_data['summary']['district_projects'] = len([p for p in filtered if p.get('match_type') != 'contractor'])
    cache_data['summary']['contractor_projects'] = len([p for p in filtered if p.get('match_type') == 'contractor'])
    cache_data['summary']['total_cost'] = total_cost

    cache_data['dashboard_stats']['total_projects'] = len(filtered)
    cache_data['dashboard_stats']['total_cost_all'] = total_cost
    cache_data['dashboard_stats']['district_count'] = cache_data['summary']['district_projects']
    cache_data['dashboard_stats']['district_cost'] = district_cost
    cache_data['dashboard_stats']['contractor_count'] = cache_data['summary']['contractor_projects']
    cache_data['dashboard_stats']['contractor_cost'] = contractor_cost

    cache_data['total_projects'] = len(filtered)
    cache_data['total_cost'] = f"₱{total_cost:,.2f}"
    cache_data['district_cost'] = f"₱{district_cost:,.2f}"
    cache_data['contractor_cost'] = f"₱{contractor_cost:,.2f}"

    with cache_file.open('w') as fh:
        json.dump(cache_data, fh, indent=2)

    if summary_file.exists():
        with summary_file.open() as fh:
            summary = json.load(fh)
        summary['total_projects'] = len(filtered)
        summary['total_cost'] = f"₱{total_cost:,.2f}"
        summary['district_projects'] = cache_data['summary']['district_projects']
        summary['contractor_projects'] = cache_data['summary']['contractor_projects']
        with summary_file.open('w') as fh:
            json.dump(summary, fh, indent=2)


def main():
    config = load_config()
    initialize_district_tokens()
    for name in TARGET_CONGRESSMEN:
        if name not in config:
            print(f"⚠️  {name} not in config, skipping")
            continue
        filter_projects_for_congressman(name, config[name])

if __name__ == '__main__':
    main()

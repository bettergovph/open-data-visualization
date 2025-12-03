#!/usr/bin/env python3
"""
Regenerate Historical Roads JSON with Updated Categorization (2020-2025)
This script regenerates historical_roads_2020_2025.json with the new categorization logic:
- road_safety_subcategories for Road Safety Facilities
- is_new flag for Road Safety Facilities
- work_type for National/Secondary Roads
- Improved _is_national_road logic

Usage:
    python3 scripts/regenerate_historical_roads_with_categorization.py
"""

import json
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import errors as psycopg2_errors
from pathlib import Path
from typing import Dict, List, Any
import re
from datetime import datetime
import statistics
from collections import Counter, defaultdict

MULTI_PURPOSE_SUBCATEGORY_PATTERNS = [
    ("Barangay Facilities", ['barangay', 'brgy']),
    ("Religious / Church", ['church', 'chapel', 'parish', 'cathedral', 'shrine', 'basilica', 'convent', 'diocese', 'mission']),
    ("Schools / Education", ['school', 'college', 'university', 'campus', 'academy', 'institute']),
    ("Museums / Cultural", ['museum', 'cultural', 'heritage', 'history', 'arts center', 'art center', 'auditorium', 'library', 'theater']),
    ("Government / Civic", ['municipal', 'city', 'provincial', 'capitol', 'government', 'civic', 'administrative', 'lgu', "people's center", 'peoples center']),
    ("Health / Social Services", ['health', 'medical', 'hospital', 'clinic', 'birthing', 'wellness', 'senior citizen', 'social welfare', 'rehabilitation']),
    ("Evacuation / DRRM", ['evacuation', 'disaster', 'drrm', 'rescue', 'operations center', 'command center', 'relief']),
    ("Sports / Youth", ['sports', 'gymnasium', 'stadium', 'coliseum', 'covered court', 'youth', 'athletic']),
    ("Markets / Economic Hubs", ['market', 'bagsakan', 'trading', 'trade', 'terminal', 'commerce'])
]

def _categorize_multi_purpose_subcategory(name_lower: str) -> str:
    target = name_lower or ''
    for label, keywords in MULTI_PURPOSE_SUBCATEGORY_PATTERNS:
        for keyword in keywords:
            if keyword in target:
                return label
    return "Other Multi-Purpose Buildings"

NIA_SUBCATEGORY_PATTERNS = [
    ("Canal Lining", ['canal lining', 'lining of canal', 'lining canal']),
    ("Drainage Canal", ['drainage canal', 'canal drainage']),
    ("Diversion Intake", ['diversion intake', 'diversion dam', 'diversion weir']),
    ("Intake of Main Canal", ['intake of main canal', 'main canal intake']),
    ("Canal Excavation / Improvement", ['canal excavation', 'canal improvement', 'canal rehab', 'canal reconstruction']),
    ("Canal Protection / Riprap", ['riprap', 'revetment', 'slope protection', 'bank protection']),
    ("Irrigation Structures", ['headgate', 'sluice', 'check gate', 'turnout', 'appurtenant structure'])
]

def _categorize_nia_subcategory(name_lower: str) -> str:
    target = name_lower or ''
    for label, keywords in NIA_SUBCATEGORY_PATTERNS:
        for keyword in keywords:
            if keyword in target:
                return label
    return "Other Irrigation Works"

def _calculate_amount_statistics(costs):
    if not costs:
        return {
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "mode": None,
            "std_dev": None,
            "threshold": None,
            "count": 0
        }
    rounded_costs = [round(c / 1000000) * 1000000 for c in costs]
    mode_value = Counter(rounded_costs).most_common(1)[0][0] if rounded_costs else None
    std_dev = statistics.stdev(costs) if len(costs) > 1 else 0
    threshold = statistics.mean(costs) + (0.1 * std_dev) if costs else None
    return {
        "min": min(costs),
        "max": max(costs),
        "mean": statistics.mean(costs),
        "median": statistics.median(costs),
        "mode": mode_value,
        "std_dev": std_dev,
        "threshold": threshold,
        "count": len(costs)
    }


def _flag_projects_by_threshold(projects, stats, category_name):
    """Flag projects when cost per km exceeds the category threshold (mean + 0.1 * std_dev)"""
    if not projects or not stats:
        return

    mean = stats.get('mean')
    std_dev = stats.get('std_dev') or 0
    threshold = None
    if mean is not None:
        threshold = mean + (0.1 * std_dev)

    if not threshold or threshold <= 0:
        for project in projects:
            project['is_flagged'] = False
        return

    for project in projects:
        cost_per_km = project.get('cost_per_km', 0)
        if cost_per_km and cost_per_km > threshold:
            project['is_flagged'] = True
            project['flag_reason'] = f"Cost/km ({cost_per_km:,.2f}) exceeds {category_name} threshold ({threshold:,.2f})"
        else:
            project['is_flagged'] = False

# Import categorization functions from visualization.py
# We'll copy them here to avoid import issues
def _categorize_single_component(component_lower: str) -> list:
    """Categorize a single component string into subcategories."""
    subcategories = []
    
    # Solar LED Streetlights (most specific first)
    if 'solar led streetlight' in component_lower or 'solar led street light' in component_lower:
        subcategories.append('Solar LED Streetlights')
    # Solar Street Lights
    elif 'solar street light' in component_lower:
        subcategories.append('Solar Street Lights')
    # Roadway Lighting
    elif 'roadway lighting' in component_lower:
        subcategories.append('Roadway Lighting')
    # General lighting
    elif any(kw in component_lower for kw in ['lighting', 'streetlight', 'street light', 'led']):
        subcategories.append('Lighting')
    
    # Guardrails
    if 'guardrail' in component_lower:
        subcategories.append('Guardrails')
    # Barrier (separate from guardrails)
    if 'barrier' in component_lower and 'guardrail' not in component_lower:
        subcategories.append('Barrier')
    
    # Traffic Signals (more specific than signs)
    if 'traffic signal' in component_lower:
        subcategories.append('Traffic Signals')
    # Road Signs
    elif 'road sign' in component_lower or ('sign' in component_lower and 'road' in component_lower and 'signal' not in component_lower):
        subcategories.append('Road Signs')
    
    # Pavement Markings
    if 'pavement marking' in component_lower or ('marking' in component_lower and 'pavement' in component_lower):
        subcategories.append('Pavement Markings')
    
    # Pedestrian Overpass
    if 'pedestrian overpass' in component_lower or ('overpass' in component_lower and 'pedestrian' in component_lower):
        subcategories.append('Pedestrian Overpass')
    
    # Off-carriageway Improvement
    if 'off-carriageway improvement' in component_lower:
        subcategories.append('Off-carriageway Improvement')
    
    # If no match, use the component name as-is (capitalized)
    if not subcategories:
        if component_lower.strip():
            subcategories.append(component_lower.title())
        else:
            subcategories.append('Road Safety Facilities')
    
    # CRITICAL: Ensure we always return at least one subcategory
    if not subcategories:
        subcategories.append('Road Safety Facilities')
    
    return subcategories

def _categorize_road_safety_facilities(name: str, name_lower: str) -> list:
    """Categorize road safety facilities into subcategories."""
    subcategories = []
    
    # Check for composite projects with parentheses
    composite_pattern = r'(?:road\s+safety\s+facilities|installation/application\s+of\s+road\s+safety\s+facilities)\s*\(([^)]+)\)'
    composite_match = re.search(composite_pattern, name_lower)
    
    if composite_match:
        # Split by comma and process each component
        components = [c.strip() for c in composite_match.group(1).split(',')]
        for component in components:
            component_lower = component.lower()
            
            # Handle composite components like "Street lights and Road Signs"
            if ' and ' in component_lower:
                parts = [p.strip() for p in component_lower.split(' and ')]
                for part in parts:
                    subcategories.extend(_categorize_single_component(part))
            else:
                subcategories.extend(_categorize_single_component(component_lower))
    else:
        # Single project - check for keywords in the full name
        # Solar LED Streetlights
        if 'solar led streetlight' in name_lower or 'solar led street light' in name_lower:
            subcategories.append('Solar LED Streetlights')
        # Solar Street Lights
        elif 'solar street light' in name_lower:
            subcategories.append('Solar Street Lights')
        # Roadway Lighting
        elif 'roadway lighting' in name_lower:
            subcategories.append('Roadway Lighting')
        # General lighting
        elif any(kw in name_lower for kw in ['lighting', 'streetlight', 'street light', 'led']):
            subcategories.append('Lighting')
        
        # Guardrails
        if 'guardrail' in name_lower:
            subcategories.append('Guardrails')
        # Barrier
        if 'barrier' in name_lower and 'guardrail' not in name_lower:
            subcategories.append('Barrier')
        
        # Traffic Signals
        if 'traffic signal' in name_lower:
            subcategories.append('Traffic Signals')
        # Road Signs
        elif 'road sign' in name_lower or ('sign' in name_lower and 'road' in name_lower and 'signal' not in name_lower):
            subcategories.append('Road Signs')
        
        # Pavement Markings
        if 'pavement marking' in name_lower or ('marking' in name_lower and 'pavement' in name_lower):
            subcategories.append('Pavement Markings')
        
        # Pedestrian Overpass
        if 'pedestrian overpass' in name_lower or ('overpass' in name_lower and 'pedestrian' in name_lower):
            subcategories.append('Pedestrian Overpass')
        
        # Off-carriageway Improvement
        if 'off-carriageway improvement' in name_lower:
            subcategories.append('Off-carriageway Improvement')
        
        # If no specific subcategory found, mark as generic
        if not subcategories:
            subcategories.append('Road Safety Facilities')
    
    # Remove duplicates while preserving order
    seen = set()
    unique_subcategories = []
    for subcat in subcategories:
        if subcat and subcat not in seen:
            seen.add(subcat)
            unique_subcategories.append(subcat)
    
    # CRITICAL: Ensure we always return at least one subcategory
    if not unique_subcategories:
        unique_subcategories.append('Road Safety Facilities')
    
    return unique_subcategories

def _is_new_installation(name: str, name_lower: str) -> bool:
    """Determine if a road safety facility is a new installation or maintenance/upgrade."""
    maintenance_keywords = [
        'maintenance', 'rehabilitation', 'repair', 'upgrade', 'upgrading',
        'improvement', 'replacement', 'rehab', 'restoration', 'renovation'
    ]
    
    new_keywords = [
        'installation', 'install', 'construction', 'construct', 'new',
        'provision', 'provide', 'establishment', 'establish'
    ]
    
    has_maintenance = any(keyword in name_lower for keyword in maintenance_keywords)
    has_new = any(keyword in name_lower for keyword in new_keywords)
    
    if has_maintenance:
        return False
    
    if has_new:
        return True
    
    return True  # Default: assume new

def _categorize_road_work_type(name: str, name_lower: str) -> list:
    """Categorize road work type based on project name.
    Returns a list of work type categories (can be multiple for composite projects).
    Returns empty list if no specific category is found.
    """
    work_types = []
    work_type_patterns = [
        (r'reblocking|road\s+reblocking', 'Road Reblocking'),
        (r'asphalt\s+overlay|item\s+304(?:\s*[-a-z])?|\basphalt\s+overlay\b', 'Asphalt Overlay'),
        (r'concreting\s+of|concrete\s+pavement|pccp|portland\s+cement\s+concrete\s+pavement|item\s+311(?:\s*[-a-z])?', 'Concreting'),
        (r'preventive\s+maintenance|periodic\s+maintenance|routine\s+maintenance', 'Preventive Maintenance'),
        (r'widening\s+of|road\s+widening|widening\s+with|widening\s+and|\bwidening\b', 'Widening'),
        (r'rehabilitation\s+of|rehabilitation/|rehabilitation\s+with|\brehabilitation\b', 'Rehabilitation'),
        (r'reconstruction\s+of|reconstruction/', 'Reconstruction'),
        (r'construction\s+of', 'Construction'),
        (r'improvement\s+of|road\s+improvement', 'Improvement'),
        (r'upgrading\s+of|upgrading/', 'Upgrading'),
        (r'restoration\s+of', 'Restoration'),
        (r'resurfacing', 'Resurfacing'),
        (r'cross\s+drainage|drainage\s+structure|drainage\s+along', 'Drainage'),
        (r'slope\s+protection|retaining\s+wall|riprap', 'Slope Protection'),
        (r'bituminous\s+pavement|bituminous\s+concrete', 'Bituminous Pavement'),
        (r'paving\s+of', 'Paving'),
    ]
    
    # Check all patterns to find multiple work types (for composite projects)
    for pattern, work_type in work_type_patterns:
        if re.search(pattern, name_lower, re.IGNORECASE):
            if work_type not in work_types:  # Avoid duplicates
                work_types.append(work_type)
    
    return work_types

class HistoricalRoadsRegenerator:
    def __init__(self):
        self.db_config = {
            'host': 'localhost',
            'port': 5432,
            'database': 'budget_analysis',
            'user': 'budget_admin',
            'password': 'wuQ5gBYCKkZiOGb61chLcByMu'
        }
        self.years = [2020, 2021, 2022, 2023, 2024, 2025]
        
    def extract_all_chainage_ranges(self, name: str):
        """Extract all chainage ranges from name"""
        import re
        if not name:
            return []

        ranges = []
        seen = set()

        def parse_number(value):
            if value is None:
                return 0.0
            if isinstance(value, (int, float)):
                return float(value)
            cleaned = str(value).replace(',', '')
            try:
                return float(cleaned)
            except ValueError:
                cleaned = re.sub(r'[^\d\.\-]', '', cleaned)
                return float(cleaned) if cleaned else 0.0

        def add_range(start_km, start_m, end_km, end_m):
            key = (
                float(parse_number(start_km)),
                float(parse_number(start_m)),
                float(parse_number(end_km)),
                float(parse_number(end_m))
            )
            if key not in seen:
                seen.add(key)
                ranges.append(key)

        dash = r'[-–—]'
        number = r'\d+(?:[.,]\d+)?'

        pattern_k = rf'K({number})\s*\+\s*\(?(-?{number})\)?\s*{dash}\s*K({number})\s*\+\s*\(?(-?{number})\)?'
        for match in re.finditer(pattern_k, name, re.IGNORECASE):
            add_range(match.group(1), match.group(2), match.group(3), match.group(4))

        pattern_chainage = rf'Chainage\s+({number})\s*{dash}\s*Chainage\s+({number})'
        for match in re.finditer(pattern_chainage, name, re.IGNORECASE):
            start_total = parse_number(match.group(1))
            end_total = parse_number(match.group(2))
            add_range(start_total // 1000, start_total % 1000, end_total // 1000, end_total % 1000)

        pattern_sta = rf'Sta\.?\s*({number})\s*\+\s*({number})\s*{dash}\s*(?:Sta\.?\s*)?({number})\s*\+\s*({number})'
        for match in re.finditer(pattern_sta, name, re.IGNORECASE):
            add_range(match.group(1), match.group(2), match.group(3), match.group(4))

        pattern_plain = rf'(?<![A-Za-z0-9])({number})\s*\+\s*({number})\s*{dash}\s*({number})\s*\+\s*({number})'
        for match in re.finditer(pattern_plain, name):
            add_range(match.group(1), match.group(2), match.group(3), match.group(4))

        return ranges
    
    def calculate_distance(self, chainage_ranges):
        """Calculate total distance in kilometers"""
        if not chainage_ranges:
            return None, None, []
        total_distance_m = 0
        individual_distances_m = []
        def to_meters(km, m):
            return km * 1000 + m
        for chainage_range in chainage_ranges:
            start_km, start_m, end_km, end_m = chainage_range
            start_total = to_meters(start_km, start_m)
            end_total = to_meters(end_km, end_m)
            distance_m = abs(end_total - start_total)
            individual_distances_m.append(distance_m)
            total_distance_m += distance_m
        distance_km = total_distance_m / 1000.0
        if len(individual_distances_m) > 1:
            breakdown = ' + '.join([f'{int(d)}m' for d in individual_distances_m]) + f' = {int(total_distance_m)}m'
        else:
            breakdown = None
        return distance_km, breakdown, individual_distances_m
    
    def format_chainage_display(self, name: str, ranges):
        """Format all chainage ranges for display"""
        if not ranges:
            return None
        chainage_strings = []
        dash = r'[-–—]'
        number = r'\d+(?:[.,]\d+)?'
        pattern_k = rf'(K{number}\s*\+\s*\(?-?{number}\)?\s*{dash}\s*K{number}\s*\+\s*\(?-?{number}\)?)'
        for match in re.finditer(pattern_k, name, re.IGNORECASE):
            chainage_strings.append(match.group(1))
        pattern_chainage = rf'(Chainage\s+{number}\s*{dash}\s*Chainage\s+{number})'
        for match in re.finditer(pattern_chainage, name, re.IGNORECASE):
            chainage_strings.append(match.group(1))
        pattern_sta = rf'(Sta\.?\s*{number}\+{number}\s*{dash}\s*(?:Sta\.?\s*)?{number}\+{number})'
        for match in re.finditer(pattern_sta, name, re.IGNORECASE):
            chainage_strings.append(match.group(1))
        pattern_plain = rf'(?<![A-Za-z0-9])({number}\s*\+\s*{number}\s*{dash}\s*{number}\s*\+\s*{number})'
        for match in re.finditer(pattern_plain, name):
            chainage_strings.append(match.group(1))
        if chainage_strings:
            return ', '.join(chainage_strings)
        return None
    
    def is_major_road(self, name: str, chainage_ranges: list) -> bool:
        """Determine if a road project is a major road (formerly "national road")
        Classification rules (in order):
        1. Highways (highway, hiway, hi-way) are automatically major roads
        2. Anything with "-" (dash) indicates cross-province or cross-municipality, so major road
        3. Any province, municipality, city named roads are major roads
        4. Any region named roads are major roads
        5. Those who can't be classified as major road is a minor road
        
        NO distance or segments logic is used.
        """
        if not name:
            return False
        
        name_lower = name.lower()
        
        # Rule 1: Highways are automatically major roads
        if any(term in name_lower for term in ['highway', 'hiway', 'hi-way']):
            return True
        
        # Rule 2: Anything with "-" (dash) indicates cross-province or cross-municipality
        import re
        road_name_part = re.split(r'\s*-\s*k\d+|chainage', name_lower, maxsplit=1, flags=re.IGNORECASE)[0]
        
        # Check for dash/hyphen pattern (but exclude chainage notation)
        dash_pattern = r'([a-záéíóúñ\s]{3,})[\s]*[-–—][\s]*([a-záéíóúñ\s]{3,})'
        matches = re.finditer(dash_pattern, road_name_part)
        for match in matches:
            part1 = match.group(1).strip()
            part2 = match.group(2).strip()
            
            # Skip if either looks like a number or chainage notation
            if re.match(r'^[\d\s\+\-\(\)]+$', part1) or re.match(r'^[\d\s\+\-\(\)]+$', part2):
                continue
            
            # Remove common road terms
            part1 = re.sub(r'\s+(road|highway|national|rd|hway|hiway|jct|junction)\s*$', '', part1).strip()
            part2 = re.sub(r'\s+(road|highway|national|rd|hway|hiway|jct|junction)\s*$', '', part2).strip()
            
            # If both parts are at least 3 chars, it's likely cross-province/municipality
            if len(part1) >= 3 and len(part2) >= 3:
                return True
        
        # Rule 3 & 4: Check for province, municipality, city, or region names
        philippine_provinces = [
            'abra', 'agusan del norte', 'agusan del sur', 'aklan', 'albay', 'antique', 'apayao', 'aurora',
            'basilan', 'bataan', 'batanes', 'batangas', 'benguet', 'biliran', 'bohol', 'bukidnon',
            'bulacan', 'cagayan', 'camarines norte', 'camarines sur', 'camiguin', 'capiz', 'catanduanes',
            'cavite', 'cebu', 'compostela valley', 'cotabato', 'davao del norte', 'davao del sur',
            'davao occidental', 'davao oriental', 'dinagat islands', 'eastern samar', 'guimaras',
            'ifugao', 'ilocos norte', 'ilocos sur', 'iloilo', 'isabela', 'kalinga', 'la union',
            'laguna', 'lanao del norte', 'lanao del sur', 'leyte', 'maguindanao', 'marinduque',
            'masbate', 'misamis occidental', 'misamis oriental', 'mountain province',
            'negros occidental', 'negros oriental', 'northern samar',
            'nueva ecija', 'nueva vizcaya', 'occidental mindoro', 'oriental mindoro', 'palawan',
            'pampanga', 'pangasinan', 'quezon', 'quirino', 'rizal', 'romblon', 'samar', 'sarangani',
            'siquijor', 'sorsogon', 'south cotabato', 'southern leyte', 'sultan kudarat', 'sulu',
            'surigao del norte', 'surigao del sur', 'tarlac', 'tawi-tawi', 'zambales',
            'zamboanga del norte', 'zamboanga del sur', 'zamboanga sibugay'
        ]
        
        philippine_regions = [
            'region i', 'region ii', 'region iii', 'region iv-a', 'region iv-b', 'region v',
            'region vi', 'region vii', 'region viii', 'region ix', 'region x', 'region xi',
            'region xii', 'region xiii', 'ncr', 'national capital region', 'cordillera',
            'car', 'bicol', 'cagayan valley', 'central luzon', 'calabarzon', 'mimaropa',
            'western visayas', 'central visayas', 'eastern visayas', 'zamboanga peninsula',
            'northern mindanao', 'davao', 'soccsksargen', 'caraga', 'bangsamoro', 'armm'
        ]
        
        major_cities = [
            'manila', 'cebu', 'davao', 'iloilo', 'baguio', 'quezon city', 'caloocan',
            'las piñas', 'makati', 'malabon', 'mandaluyong', 'marikina', 'muntinlupa',
            'navotas', 'parañaque', 'pasay', 'pasig', 'san juan', 'taguig', 'valenzuela',
            'bacoor', 'dasmarinas', 'dasmariñas', 'calamba', 'san pedro', 'biñan',
            'santa rosa', 'cabuyao', 'los baños', 'tacloban', 'ormoc', 'dumaguete',
            'bacolod', 'san carlos', 'silay', 'talisay', 'victorias', 'cadiz', 'roxas'
        ]
        
        # Check if road name contains province, region, or major city name
        for province in philippine_provinces:
            if province in name_lower:
                return True
        
        for region in philippine_regions:
            if region in name_lower:
                return True
        
        for city in major_cities:
            if city in name_lower:
                return True
        
        # Rule 5: If none of the above match, it's a minor road
        return False
    
    def load_historical_data(self, year: int):
        """Load historical budget data from PostgreSQL database"""
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = %s
            """, (f'budget_{year}',))
            
            available_columns = {row['column_name'] for row in cursor.fetchall()}
            required_columns = {'id', 'amt', 'dsc', 'year', 'source_file'}
            missing_columns = required_columns - available_columns
            if missing_columns:
                print(f"   ⚠️  Table budget_{year} missing required columns: {missing_columns}")
                cursor.close()
                conn.close()
                return []
            
            cursor.execute(f"""
                SELECT data_type 
                FROM information_schema.columns 
                WHERE table_name = 'budget_{year}' AND column_name = 'year'
            """)
            year_col_result = cursor.fetchone()
            year_type = year_col_result['data_type'] if year_col_result else 'text'
            
            if year_type == 'integer':
                year_filter = f"year = {year}"
            else:
                year_filter = f"(year::text = '{year}' OR year::text LIKE '%{year}%')"
            
            dept_filter = """
                (dsc ILIKE '%road%' OR dsc ILIKE '%bridge%' OR dsc ILIKE '%highway%' 
                 OR dsc ILIKE '%viaduct%' OR dsc ILIKE '%flyover%' OR dsc ILIKE '%overpass%'
                 OR dsc ILIKE '%underpass%' OR dsc ILIKE '%chainage%' OR dsc ILIKE '%K%d+%'
                 OR dsc ILIKE '%traffic%' OR dsc ILIKE '%installation%' OR dsc ILIKE '%pavement%'
                 OR dsc ILIKE '%lighting%' OR dsc ILIKE '%sign%')
            """
            
            min_amt = 100
            
            query = f"""
                SELECT id, amt, dsc, year, source_file
                FROM budget_{year}
                WHERE {year_filter}
                AND amt >= {min_amt}
                AND {dept_filter}
                ORDER BY amt DESC, dsc
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            historical_data = []
            for row in rows:
                try:
                    amt = float(row['amt']) if row['amt'] else 0.0
                    amt = amt * 1000
                    historical_data.append({
                        'id': row['id'],
                        'amount': amt,
                        'description': row['dsc'] or '',
                        'year': row['year'],
                        'source_file': row['source_file']
                    })
                except Exception as row_e:
                    print(f"   ⚠️  Error processing row (ID: {row.get('id', 'N/A')}): {type(row_e).__name__}: {str(row_e)}")
                    continue
            
            cursor.close()
            conn.close()
            return historical_data
            
        except Exception as e:
            error_msg = str(e)
            if "does not exist" in error_msg.lower() or "relation" in error_msg.lower():
                print(f"   Table budget_{year} does not exist, skipping")
                if 'cursor' in locals():
                    cursor.close()
                if 'conn' in locals():
                    conn.close()
                return []
            else:
                print(f"   ⚠️  Error loading {year} data: {type(e).__name__}: {str(e)}")
                if 'cursor' in locals():
                    cursor.close()
                if 'conn' in locals():
                    conn.close()
                return []
    
    def extract_roads_from_year(self, year: int):
        """Extract and categorize road infrastructure projects from a specific year"""
        print(f"\n📅 Processing year {year}...")
        
        historical_data = self.load_historical_data(year)
        if not historical_data:
            print(f"   No data found for {year}")
            return {
                'roads': [],
                'national_roads': [],
                'secondary_roads': [],
                'bridges': [],
                'traffic_signs': []
            }
        
        print(f"   Loaded {len(historical_data)} records with road-related keywords")
        
        roads = []
        national_roads = []
        secondary_roads = []
        bridges = []
        traffic_signs = []
        multi_purpose_buildings = []
        rockfall_netting = []
        schools = []
        nia_projects = []
        
        for item in historical_data:
            name = item['description']
            if not name:
                continue
            
            amount = abs(item['amount'])
            if amount <= 0:
                continue
            
            name_lower = name.lower()
            
            # Check for non-road categories FIRST (they don't need chainage)
            # Multi-Purpose Building (also: bldg) - NO CHAINAGE REQUIRED
            building_keywords = ['multi-purpose building', 'multipurpose building', ' multi-purpose bldg', ' multipurpose bldg', ' bldg']
            is_multi_purpose_building = any(keyword in name_lower for keyword in building_keywords) and \
                                        ('road' not in name_lower or 'building' in name_lower or 'bldg' in name_lower)
            
            # Rockfall Netting (also: rocknetting) - NO CHAINAGE REQUIRED
            rockfall_keywords = ['rockfall netting', 'rocknetting', 'rock fall netting', 'rockfall protection', 'rockfall mitigation']
            is_rockfall_netting = any(keyword in name_lower for keyword in rockfall_keywords)
            
            # School (focus on building/classroom construction, not salaries or equipment) - NO CHAINAGE REQUIRED
            school_keywords = ['school', 'classroom', 'elementary school', 'high school', 'secondary school', 'primary school']
            school_exclude_keywords = ['salary', 'salaries', 'equipment', 'supplies', 'textbook', 'furniture', 'computer', 'laptop', 'tablet']
            is_school = any(keyword in name_lower for keyword in school_keywords) and \
                       not any(exclude in name_lower for exclude in school_exclude_keywords) and \
                       any(construct_keyword in name_lower for construct_keyword in ['construction', 'building', 'classroom', 'bldg', 'facility', 'repair', 'rehabilitation', 'renovation', 'improvement', 'completion'])
            
            # For non-road categories, process them even without chainage
            if is_multi_purpose_building or is_rockfall_netting or is_school:
                # Check if it has chainage notation - extract ALL ranges (optional for these categories)
                chainage_ranges = self.extract_all_chainage_ranges(name)
                distance_km = 0
                breakdown = None
                individual_distances = []
                chainage_display = 'N/A'
                cost_per_km = amount  # For non-road projects, use amount as cost_per_km
                
                if chainage_ranges:
                    # If chainage exists, calculate distance
                    distance_km, breakdown, individual_distances = self.calculate_distance(chainage_ranges)
                    if distance_km and distance_km > 0:
                        cost_per_km = amount / distance_km
                    chainage_display = self.format_chainage_display(name, chainage_ranges) or 'N/A'
                
                project_data = {
                    'id': item['id'],
                    'name': name,
                    'chainage_display': chainage_display,
                    'chainage_ranges': chainage_ranges or [],  # Store all ranges (empty if none)
                    'distance_km': distance_km,
                    'distance_breakdown': breakdown,
                    'amount': amount,
                    'cost_per_km': cost_per_km,
                    'year': year,
                    'source_file': item.get('source_file')
                }
                
                if is_multi_purpose_building:
                    project_data['multi_purpose_subcategory'] = _categorize_multi_purpose_subcategory(name_lower)
                    multi_purpose_buildings.append(project_data)
                    continue  # Skip further categorization
                elif is_rockfall_netting:
                    rockfall_netting.append(project_data)
                    continue  # Skip further categorization
                elif is_school:
                    # Categorize school projects into subcategories
                    school_subcategory = 'Other School Projects'
                    if any(kw in name_lower for kw in ['classroom', 'class room']):
                        school_subcategory = 'Classroom Construction'
                    elif any(kw in name_lower for kw in ['building', 'bldg', 'facility']):
                        school_subcategory = 'School Building Construction'
                    elif any(kw in name_lower for kw in ['repair', 'rehabilitation', 'renovation', 'improvement']):
                        school_subcategory = 'School Building Repair/Rehabilitation'
                    elif any(kw in name_lower for kw in ['completion']):
                        school_subcategory = 'School Building Completion'
                    
                    project_data['school_subcategory'] = school_subcategory
                    schools.append(project_data)
                    continue  # Skip further categorization
                # If none matched, continue to regular processing below
            
            # For road-related projects, require chainage notation
            chainage_ranges = self.extract_all_chainage_ranges(name)
            if not chainage_ranges:
                continue  # Skip road projects without chainage
            
            distance_km, breakdown, individual_distances = self.calculate_distance(chainage_ranges)
            if not distance_km or distance_km <= 0:
                continue
            
            cost_per_km = amount / distance_km
            chainage_display = self.format_chainage_display(name, chainage_ranges) or 'N/A'
            
            project_data = {
                'id': item['id'],
                'name': name,
                'chainage_display': chainage_display,
                'chainage_ranges': chainage_ranges,
                'distance_km': distance_km,
                'distance_breakdown': breakdown,
                'amount': amount,
                'cost_per_km': cost_per_km,
                'year': year,
                'source_file': item.get('source_file')
            }
            
            # Farm-to-Market Roads (FMR) and NIA detection
            fmr_keywords = [' fmr', 'fmr ', 'farm to market', 'farm-to-market', 'farm to market road']
            is_fmr = any(keyword in name_lower for keyword in fmr_keywords) and 'cnia' not in name_lower
            
            nia_keywords = [
                'national irrigation', 'irrigation system', 'irrigation project',
                'irrigation canal', 'communal irrigation', 'irrigation sub-program',
                'irrigation subprogram', 'irrigation facility', 'irrigation structure',
                'annex a-4', 'communal irrigation system', 'communal irrigation project',
                'communal irrigation scheme'
            ]
            nia_keyword_patterns = [
                r'\bnis\b', r'\bnia\b', r'\bcis\b', r'\bcip\b', r'\bsip\b',
                r'\bc\.i\.s\b', r'\bc\.i\.p\b', r'\bs\.i\.p\b'
            ]
            pattern_hit = any(re.search(pattern, name_lower) for pattern in nia_keyword_patterns)
            is_nia = (any(keyword in name_lower for keyword in nia_keywords) or pattern_hit) and \
                     'cnia' not in name_lower and \
                     'xdp' not in name_lower and \
                     'dystonia' not in name_lower
            
            if is_fmr:
                roads.append(project_data)  # Historical extractor doesn't maintain dedicated FMR bucket
                continue
            if is_nia:
                project_data['nia_subcategory'] = _categorize_nia_subcategory(name_lower)
                nia_projects.append(project_data)
                continue
            
            # Road Safety Facilities
            road_safety_keywords = [
                'installation', 'road safety', 'guardrail', 'traffic facilities', 'traffic facility',
                'lighting', 'streetlight', 'street light', 'led', 'solar', 'roadway lighting',
                'road sign', 'pavement marking', 'barrier', 'pedestrian overpass'
            ]
            is_road_safety = any(keyword in name_lower for keyword in road_safety_keywords)
            
            # Bridges
            bridge_keywords = ['bridge', 'viaduct', 'flyover', 'overpass', 'underpass', 'footbridge', 'pedestrian bridge']
            is_bridge = any(keyword in name_lower for keyword in bridge_keywords)
            
            # Road terms
            road_terms = [
                ' road', ' rd', ' highway', ' hiway', ' hway', ' h-way',
                'boulevard', ' blvd', ' avenue', ' ave', ' ave.',
                'junction', ' jct', ' old route', ' diversion',
                'extension', ' ext', ' street', ' st', ' st.',
                'expressway'
            ]
            is_road_term = any(term in name_lower for term in road_terms)
            
            if is_road_safety:
                # NEW: Categorize road safety facilities
                subcategories = _categorize_road_safety_facilities(name, name_lower)
                if not subcategories or len(subcategories) == 0:
                    subcategories = ['Road Safety Facilities']
                project_data['road_safety_subcategories'] = subcategories
                project_data['is_new'] = _is_new_installation(name, name_lower)
                traffic_signs.append(project_data)
            elif is_bridge:
                bridges.append(project_data)
            elif is_road_term or not is_bridge:
                # NEW: Categorize road work type
                work_types = _categorize_road_work_type(name, name_lower)
                if work_types:
                    # Store as list for composite work types
                    project_data['work_type'] = work_types[0] if len(work_types) == 1 else work_types
                    project_data['work_types'] = work_types  # Always store full list
                else:
                    project_data['work_type'] = None
                    project_data['work_types'] = []
                
                # Separate into major and minor roads (based on segment count)
                # Determine if it's a major road using classification rules
                is_major_road = self.is_major_road(name, chainage_ranges)
                if is_major_road:
                    national_roads.append(project_data)
                else:
                    secondary_roads.append(project_data)
                roads.append(project_data)
            else:
                secondary_roads.append(project_data)
                roads.append(project_data)
        
        # Calculate statistics and flag projects by subcategory
        # (statistics, Counter, and defaultdict are already imported at module level)
        
        def calculate_statistics(projects):
            """Calculate statistics for a list of projects"""
            if not projects:
                return {
                    "min": None, "max": None, "mean": None, "median": None,
                    "mode": None, "std_dev": None, "threshold": None, "count": 0
                }
            costs = [p['cost_per_km'] for p in projects if p.get('cost_per_km', 0) > 0]
            if not costs:
                return {
                    "min": None, "max": None, "mean": None, "median": None,
                    "mode": None, "std_dev": None, "threshold": None, "count": 0
                }
            costs_sorted = sorted(costs)
            mean = statistics.mean(costs)
            rounded_costs = [round(c / 1000000) * 1000000 for c in costs]
            cost_counter = Counter(rounded_costs)
            mode_value = cost_counter.most_common(1)[0][0] if cost_counter else None
            try:
                std_dev = statistics.stdev(costs) if len(costs) > 1 else 0
            except:
                std_dev = 0
            # Calculate threshold (mean + 0.1*std_dev)
            threshold = None
            if mean is not None and std_dev is not None:
                threshold = mean + (0.1 * std_dev)
            
            return {
                "min": min(costs), "max": max(costs), "mean": mean,
                "median": statistics.median(costs), "mode": mode_value,
                "std_dev": std_dev, "threshold": threshold,  # Add threshold to stats
                "count": len(costs)
            }
        
        def flag_projects_by_subcategory(projects_by_subcategory):
            """Calculate subcategory statistics and flag projects that exceed threshold
            Uses 'average of average' approach for composite projects:
            - Statistics use cost_per_km_for_stats (divided by number of components)
            - Flagging uses original_cost_per_km against threshold
            """
            subcategory_stats = {}
            for subcategory, projects in projects_by_subcategory.items():
                # Use cost_per_km_for_stats for statistics (average of average for composites)
                stats_costs = [p.get('cost_per_km_for_stats', p.get('cost_per_km', 0)) for p in projects if p.get('cost_per_km_for_stats', p.get('cost_per_km', 0)) > 0]
                
                if not stats_costs:
                    subcategory_stats[subcategory] = {
                        "min": None, "max": None, "mean": None, "median": None,
                        "mode": None, "std_dev": None, "threshold": None, "count": 0
                    }
                    continue
                
                costs_sorted = sorted(stats_costs)
                mean = statistics.mean(stats_costs)
                rounded_costs = [round(c / 1000000) * 1000000 for c in stats_costs]
                cost_counter = Counter(rounded_costs)
                mode_value = cost_counter.most_common(1)[0][0] if cost_counter else None
                try:
                    std_dev = statistics.stdev(stats_costs) if len(stats_costs) > 1 else 0
                except:
                    std_dev = 0
                
                # Calculate threshold (mean + 0.1*std_dev)
                threshold = None
                if mean is not None and std_dev is not None:
                    threshold = mean + (0.1 * std_dev)
                
                stats = {
                    "min": min(stats_costs),
                    "max": max(stats_costs),
                    "mean": mean,
                    "median": statistics.median(stats_costs),
                    "mode": mode_value,
                    "std_dev": std_dev,
                    "threshold": threshold,  # Add threshold to stats
                    "count": len(projects)
                }
                subcategory_stats[subcategory] = stats
                
                # Flag projects that exceed mean + 2*std_dev (outlier threshold)
                # Use original_cost_per_km for flagging (not the divided one)
                for project in projects:
                    project['subcategory'] = subcategory
                    project['subcategory_stats'] = stats
                    # Use original_cost_per_km for flagging comparison
                    cost_to_check = project.get('original_cost_per_km', project.get('cost_per_km', 0))
                    if threshold and cost_to_check > threshold:
                        project['is_flagged'] = True
                        project['flag_reason'] = f"Cost/km ({cost_to_check:,.2f}) exceeds {subcategory} threshold ({threshold:,.2f})"
                    else:
                        project['is_flagged'] = False
            
            return subcategory_stats
        
        # Group road safety facilities by subcategory
        # For composite projects (multiple subcategories), count in ALL subcategories
        # Use "average of average" approach: divide cost/km by number of components
        road_safety_by_subcategory = defaultdict(list)
        for project in traffic_signs:
            subcategories = project.get('road_safety_subcategories', [])
            if subcategories:
                # For composite projects, count in ALL subcategories
                num_components = len(subcategories)
                original_cost_per_km = project.get('cost_per_km', 0)
                
                # For each subcategory, add project with cost/km divided by number of components
                for subcategory in subcategories:
                    project_copy = project.copy()
                    project_copy['cost_per_km_for_stats'] = original_cost_per_km / num_components if num_components > 0 else original_cost_per_km
                    project_copy['num_components'] = num_components
                    project_copy['original_cost_per_km'] = original_cost_per_km
                    road_safety_by_subcategory[subcategory].append(project_copy)
            else:
                # No subcategory - use "Road Safety Facilities" as default
                project_copy = project.copy()
                project_copy['cost_per_km_for_stats'] = project.get('cost_per_km', 0)
                project_copy['num_components'] = 1
                project_copy['original_cost_per_km'] = project.get('cost_per_km', 0)
                road_safety_by_subcategory['Road Safety Facilities'].append(project_copy)
        
        # Group roads by work type (within national/secondary)
        # For composite work types, count in ALL work types using "average of average"
        national_roads_by_work_type = defaultdict(list)
        secondary_roads_by_work_type = defaultdict(list)
        
        for project in national_roads:
            work_types = project.get('work_types', [])
            if not work_types:
                # Fallback to single work_type for backward compatibility
                work_type = project.get('work_type')
                work_types = [work_type] if work_type else []
            
            if work_types:
                # For composite work types, count in ALL work types
                num_components = len(work_types)
                original_cost_per_km = project.get('cost_per_km', 0)
                
                for work_type in work_types:
                    project_copy = project.copy()
                    project_copy['cost_per_km_for_stats'] = original_cost_per_km / num_components if num_components > 0 else original_cost_per_km
                    project_copy['num_components'] = num_components
                    project_copy['original_cost_per_km'] = original_cost_per_km
                    national_roads_by_work_type[work_type].append(project_copy)
            else:
                # No work type - use "Major Road" as default
                project_copy = project.copy()
                project_copy['cost_per_km_for_stats'] = project.get('cost_per_km', 0)
                project_copy['num_components'] = 1
                project_copy['original_cost_per_km'] = project.get('cost_per_km', 0)
                national_roads_by_work_type['Major Road'].append(project_copy)
        
        for project in secondary_roads:
            work_types = project.get('work_types', [])
            if not work_types:
                # Fallback to single work_type for backward compatibility
                work_type = project.get('work_type')
                work_types = [work_type] if work_type else []
            
            if work_types:
                # For composite work types, count in ALL work types
                num_components = len(work_types)
                original_cost_per_km = project.get('cost_per_km', 0)
                
                for work_type in work_types:
                    project_copy = project.copy()
                    project_copy['cost_per_km_for_stats'] = original_cost_per_km / num_components if num_components > 0 else original_cost_per_km
                    project_copy['num_components'] = num_components
                    project_copy['original_cost_per_km'] = original_cost_per_km
                    secondary_roads_by_work_type[work_type].append(project_copy)
            else:
                # No work type - use "Minor Road" as default
                project_copy = project.copy()
                project_copy['cost_per_km_for_stats'] = project.get('cost_per_km', 0)
                project_copy['num_components'] = 1
                project_copy['original_cost_per_km'] = project.get('cost_per_km', 0)
                secondary_roads_by_work_type['Minor Road'].append(project_copy)
        
        # Flag projects by subcategory
        road_safety_subcategory_stats = flag_projects_by_subcategory(road_safety_by_subcategory)
        national_roads_work_type_stats = flag_projects_by_subcategory(national_roads_by_work_type)
        secondary_roads_work_type_stats = flag_projects_by_subcategory(secondary_roads_by_work_type)
        
        # Merge flagged status back to original projects
        # Create a mapping: project identifier -> (is_flagged, flag_reason, subcategory)
        def merge_flagging_back(original_projects, grouped_projects_dict):
            """Merge flagged status from grouped projects back to original projects"""
            # Create a mapping from project name+amount to flagged status
            flagging_map = {}
            for subcategory, projects in grouped_projects_dict.items():
                for project_copy in projects:
                    # Use a unique identifier: name + amount (or other unique fields)
                    project_id = (
                        project_copy.get('name', ''),
                        project_copy.get('amount', 0),
                        project_copy.get('distance_km', 0)
                    )
                    # If this project is flagged, store it (keep the most specific subcategory)
                    if project_copy.get('is_flagged', False):
                        if project_id not in flagging_map or project_copy.get('subcategory'):
                            flagging_map[project_id] = {
                                'is_flagged': True,
                                'flag_reason': project_copy.get('flag_reason', ''),
                                'subcategory': project_copy.get('subcategory', '')
                            }
            
            # Update original projects
            for project in original_projects:
                project_id = (
                    project.get('name', ''),
                    project.get('amount', 0),
                    project.get('distance_km', 0)
                )
                if project_id in flagging_map:
                    flag_info = flagging_map[project_id]
                    project['is_flagged'] = flag_info['is_flagged']
                    project['flag_reason'] = flag_info['flag_reason']
                    if flag_info['subcategory']:
                        project['subcategory'] = flag_info['subcategory']
                else:
                    # Ensure is_flagged is set to False if not flagged
                    project['is_flagged'] = False
        
        # Merge flagging back to original project lists
        merge_flagging_back(traffic_signs, road_safety_by_subcategory)
        merge_flagging_back(national_roads, national_roads_by_work_type)
        merge_flagging_back(secondary_roads, secondary_roads_by_work_type)
        
        # Flag bridges that exceed threshold
        bridges_stats = calculate_statistics(bridges) if bridges else {}
        bridges_threshold = 0
        if bridges_stats.get('mean') is not None and bridges_stats.get('std_dev') is not None:
            # Calculate threshold for bridges (mean + 0.1*std_dev)
            bridges_threshold = 0
            if bridges_stats.get('mean') is not None and bridges_stats.get('std_dev') is not None:
                bridges_threshold = bridges_stats['mean'] + (0.1 * bridges_stats['std_dev'])
        
        # Flag bridges that exceed threshold
        for bridge in bridges:
            cost_per_km = bridge.get('cost_per_km', 0)
            if bridges_threshold and cost_per_km > bridges_threshold:
                bridge['is_flagged'] = True
                bridge['flag_reason'] = f"Cost/km ({cost_per_km:,.2f}) exceeds Bridges threshold ({bridges_threshold:,.2f})"
            else:
                bridge['is_flagged'] = False
        
        # Calculate statistics for new categories
        multi_purpose_buildings_stats = calculate_statistics(multi_purpose_buildings) if multi_purpose_buildings else {}
        rockfall_netting_stats = calculate_statistics(rockfall_netting) if rockfall_netting else {}
        schools_stats = calculate_statistics(schools) if schools else {}
        nia_stats = calculate_statistics(nia_projects) if nia_projects else {}
        
        # Group schools by subcategory for statistics
        schools_by_subcategory = defaultdict(list)
        for project in schools:
            subcategory = project.get('school_subcategory', 'Other School Projects')
            schools_by_subcategory[subcategory].append(project)
        
        # Group multi-purpose buildings by derived subcategory
        multi_purpose_by_subcategory = defaultdict(list)
        for project in multi_purpose_buildings:
            subcategory = project.get('multi_purpose_subcategory', 'Other Multi-Purpose Buildings')
            multi_purpose_by_subcategory[subcategory].append(project)
        
        # Calculate subcategory statistics for schools
        schools_subcategory_stats = {}
        for subcategory, subcategory_projects in schools_by_subcategory.items():
            schools_subcategory_stats[subcategory] = calculate_statistics(subcategory_projects)
        
        nia_by_subcategory = defaultdict(list)
        for project in nia_projects:
            subcategory = project.get('nia_subcategory', 'Other Irrigation Works')
            nia_by_subcategory[subcategory].append(project)
        
        # Calculate subcategory statistics for multi-purpose buildings (amount-based) and flag
        multi_purpose_subcategory_stats = {}
        for subcategory, subcategory_projects in multi_purpose_by_subcategory.items():
            costs = [p.get('amount', 0) for p in subcategory_projects if p.get('amount', 0) > 0]
            stats = _calculate_amount_statistics(costs)
            multi_purpose_subcategory_stats[subcategory] = stats
            threshold = stats.get('threshold')
            for building in subcategory_projects:
                amount_value = building.get('amount', 0)
                if threshold and amount_value > threshold:
                    building['is_flagged'] = True
                    building['flag_reason'] = f"Amount (₱{amount_value:,.2f}) exceeds {subcategory} threshold (₱{threshold:,.2f})"
                else:
                    building['is_flagged'] = False
        
        nia_subcategory_stats = {}
        for subcategory, subcategory_projects in nia_by_subcategory.items():
            stats = calculate_statistics(subcategory_projects)
            nia_subcategory_stats[subcategory] = stats
            threshold = 0
            if stats.get('mean') is not None and stats.get('std_dev') is not None:
                threshold = stats['mean'] + (0.1 * stats['std_dev'])
            for irrigation in subcategory_projects:
                cost_per_km = irrigation.get('cost_per_km', 0)
                if threshold and cost_per_km > threshold:
                    irrigation['is_flagged'] = True
                    irrigation['flag_reason'] = f"Cost/km ({cost_per_km:,.2f}) exceeds {subcategory} threshold ({threshold:,.2f})"
                else:
                    irrigation['is_flagged'] = False
        
        if rockfall_netting_stats.get('mean') is not None and rockfall_netting_stats.get('std_dev') is not None:
            rockfall_threshold = rockfall_netting_stats['mean'] + (0.1 * rockfall_netting_stats['std_dev'])
            for rockfall in rockfall_netting:
                cost_per_km = rockfall.get('cost_per_km', 0)
                if rockfall_threshold and cost_per_km > rockfall_threshold:
                    rockfall['is_flagged'] = True
                    rockfall['flag_reason'] = f"Cost/km ({cost_per_km:,.2f}) exceeds Rockfall Netting threshold ({rockfall_threshold:,.2f})"
                else:
                    rockfall['is_flagged'] = False
        
        # Flag schools by subcategory
        for subcategory, subcategory_projects in schools_by_subcategory.items():
            subcategory_stats = schools_subcategory_stats.get(subcategory, {})
            if subcategory_stats.get('mean') is not None and subcategory_stats.get('std_dev') is not None:
                subcategory_threshold = subcategory_stats['mean'] + (0.1 * subcategory_stats['std_dev'])
                for school in subcategory_projects:
                    cost_per_km = school.get('cost_per_km', 0)
                    if subcategory_threshold and cost_per_km > subcategory_threshold:
                        school['is_flagged'] = True
                        school['flag_reason'] = f"Cost/km ({cost_per_km:,.2f}) exceeds {subcategory} threshold ({subcategory_threshold:,.2f})"
                    else:
                        school['is_flagged'] = False
        
        # Count flagged projects
        traffic_flagged = sum(1 for p in traffic_signs if p.get('is_flagged'))
        national_flagged = sum(1 for p in national_roads if p.get('is_flagged'))
        secondary_flagged = sum(1 for p in secondary_roads if p.get('is_flagged'))
        bridges_flagged = sum(1 for p in bridges if p.get('is_flagged'))
        buildings_flagged = sum(1 for p in multi_purpose_buildings if p.get('is_flagged'))
        rockfall_flagged = sum(1 for p in rockfall_netting if p.get('is_flagged'))
        schools_flagged = sum(1 for p in schools if p.get('is_flagged'))
        nia_flagged = sum(1 for p in nia_projects if p.get('is_flagged'))
        
        print(f"   ✅ Categorized: {len(national_roads)} national roads, {len(secondary_roads)} secondary roads, {len(bridges)} bridges, {len(traffic_signs)} traffic signs, {len(multi_purpose_buildings)} multi-purpose buildings, {len(rockfall_netting)} rockfall netting, {len(schools)} schools, {len(nia_projects)} irrigation works (NIA)")
        print(f"   🚩 Flagged: {traffic_flagged} traffic signs, {national_flagged} national roads, {secondary_flagged} secondary roads, {bridges_flagged} bridges, {buildings_flagged} multi-purpose buildings, {rockfall_flagged} rockfall netting, {schools_flagged} schools, {nia_flagged} irrigation works")
        
        # Count projects with subcategories
        traffic_with_subcats = sum(1 for p in traffic_signs if p.get('road_safety_subcategories') and len(p.get('road_safety_subcategories', [])) > 0)
        print(f"   📊 Traffic signs with subcategories: {traffic_with_subcats}/{len(traffic_signs)}")
        
        return {
            'roads': roads,
            'national_roads': national_roads,
            'secondary_roads': secondary_roads,
            'bridges': bridges,
            'traffic_signs': traffic_signs,
            'multi_purpose_buildings': multi_purpose_buildings,
            'rockfall_netting': rockfall_netting,
            'schools': schools,
            'nia': nia_projects,
            'traffic_signs_subcategory_statistics': road_safety_subcategory_stats,
            'national_roads_work_type_statistics': national_roads_work_type_stats,
            'secondary_roads_work_type_statistics': secondary_roads_work_type_stats,
            'bridges_statistics': bridges_stats,
            'multi_purpose_buildings_statistics': multi_purpose_buildings_stats,
            'multi_purpose_buildings_subcategory_statistics': multi_purpose_subcategory_stats,
            'rockfall_netting_statistics': rockfall_netting_stats,
            'schools_statistics': schools_stats,
            'schools_subcategory_statistics': schools_subcategory_stats,
            'nia_statistics': nia_stats,
            'nia_subcategory_statistics': nia_subcategory_stats
        }
    
    def _calculate_all_years_category_statistics(self, all_data):
        """Calculate aggregated category statistics across all years"""
        from collections import defaultdict
        import statistics
        
        def get_project_id(project):
            """Generate a unique identifier for a project"""
            return (
                project.get('name', ''),
                project.get('amount', 0),
                project.get('distance_km', 0),
                project.get('year', '')
            )
        
        category_aggregates = defaultdict(lambda: {
            'total_amount': 0.0,
            'total_distance_km': 0.0,
            'projects': [],
            'flagged_projects': [],
            'unique_projects': set()  # Track unique projects to avoid double-counting
        })
        
        # Aggregate across all years
        for year_str in ['2020', '2021', '2022', '2023', '2024', '2025']:
            year_data = all_data.get(year_str, {})
            if not year_data:
                continue
            # Bridges
            bridges = year_data.get('bridges', [])
            for project in bridges:
                project['year'] = year_str  # Add year for uniqueness
                project_id = get_project_id(project)
                key = ('Bridges', None)
                category_aggregates[key]['projects'].append(project)
                # Only add to totals if this is the first time we see this project
                if project_id not in category_aggregates[key]['unique_projects']:
                    category_aggregates[key]['unique_projects'].add(project_id)
                    category_aggregates[key]['total_amount'] += project.get('amount', 0)
                    category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
                if project.get('is_flagged', False):
                    category_aggregates[key]['flagged_projects'].append(project)
            
            # Road Safety Facilities
            traffic_signs = year_data.get('traffic_signs', [])
            subcategory_stats = year_data.get('traffic_signs_subcategory_statistics', {})
            for subcategory, stats in subcategory_stats.items():
                # Match projects by subcategory field (set during flagging) or by road_safety_subcategories list
                subcategory_projects = [
                    p for p in traffic_signs 
                    if p.get('subcategory') == subcategory or 
                       (subcategory in (p.get('road_safety_subcategories') or []))
                ]
                key = ('Road Safety Facilities', subcategory)
                for project in subcategory_projects:
                    project['year'] = year_str  # Add year for uniqueness
                    project_id = get_project_id(project)
                    category_aggregates[key]['projects'].append(project)
                    # Only add to totals if this is the first time we see this project in this subcategory
                    # But allow it to appear in multiple subcategories for threshold calculation
                    if project_id not in category_aggregates[key]['unique_projects']:
                        category_aggregates[key]['unique_projects'].add(project_id)
                        category_aggregates[key]['total_amount'] += project.get('amount', 0)
                        category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
                    if project.get('is_flagged', False):
                        category_aggregates[key]['flagged_projects'].append(project)
            
            # Major Roads
            national_roads = year_data.get('national_roads', [])
            national_work_type_stats = year_data.get('national_roads_work_type_statistics', {})
            for work_type, stats in national_work_type_stats.items():
                # Match projects by subcategory (set during flagging), work_type, or work_types list
                work_type_projects = [
                    p for p in national_roads 
                    if p.get('subcategory') == work_type or
                       p.get('work_type') == work_type or
                       (work_type in (p.get('work_types') or []))
                ]
                key = ('Major Roads', work_type)
                for project in work_type_projects:
                    project['year'] = year_str  # Add year for uniqueness
                    project_id = get_project_id(project)
                    category_aggregates[key]['projects'].append(project)
                    # Only add to totals if this is the first time we see this project in this work type
                    if project_id not in category_aggregates[key]['unique_projects']:
                        category_aggregates[key]['unique_projects'].add(project_id)
                        category_aggregates[key]['total_amount'] += project.get('amount', 0)
                        category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
                    if project.get('is_flagged', False):
                        category_aggregates[key]['flagged_projects'].append(project)
            
            # Minor Roads
            secondary_roads = year_data.get('secondary_roads', [])
            secondary_work_type_stats = year_data.get('secondary_roads_work_type_statistics', {})
            for work_type, stats in secondary_work_type_stats.items():
                # Match projects by subcategory (set during flagging), work_type, or work_types list
                work_type_projects = [
                    p for p in secondary_roads 
                    if p.get('subcategory') == work_type or
                       p.get('work_type') == work_type or
                       (work_type in (p.get('work_types') or []))
                ]
                key = ('Minor Roads', work_type)
                for project in work_type_projects:
                    project['year'] = year_str  # Add year for uniqueness
                    project_id = get_project_id(project)
                    category_aggregates[key]['projects'].append(project)
                    # Only add to totals if this is the first time we see this project in this work type
                    if project_id not in category_aggregates[key]['unique_projects']:
                        category_aggregates[key]['unique_projects'].add(project_id)
                        category_aggregates[key]['total_amount'] += project.get('amount', 0)
                        category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
                    if project.get('is_flagged', False):
                        category_aggregates[key]['flagged_projects'].append(project)
            
            # Multi-Purpose Buildings
            multi_purpose_buildings = year_data.get('multi_purpose_buildings', [])
            multi_purpose_sub_stats = year_data.get('multi_purpose_buildings_subcategory_statistics', {})
            if multi_purpose_sub_stats:
                for subcategory in multi_purpose_sub_stats.keys():
                    subcategory_projects = [
                        p for p in multi_purpose_buildings
                        if (p.get('multi_purpose_subcategory') or 'Other Multi-Purpose Buildings') == subcategory
                    ]
                    key = ('Multi-Purpose Buildings', subcategory)
                    for project in subcategory_projects:
                        project['year'] = year_str
                        project_id = get_project_id(project)
                        if project_id not in category_aggregates[key]['unique_projects']:
                            category_aggregates[key]['unique_projects'].add(project_id)
                            category_aggregates[key]['total_amount'] += project.get('amount', 0)
                            category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
                        category_aggregates[key]['projects'].append(project)
                        if project.get('is_flagged'):
                            category_aggregates[key]['flagged_projects'].append(project)
            else:
                for project in multi_purpose_buildings:
                    project['year'] = year_str
                    project_id = get_project_id(project)
                    key = ('Multi-Purpose Buildings', None)
                    if project_id not in category_aggregates[key]['unique_projects']:
                        category_aggregates[key]['unique_projects'].add(project_id)
                        category_aggregates[key]['total_amount'] += project.get('amount', 0)
                        category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
                    category_aggregates[key]['projects'].append(project)
                    if project.get('is_flagged'):
                        category_aggregates[key]['flagged_projects'].append(project)

            # Irrigation Works (NIA)
            nia_projects = year_data.get('nia', [])
            nia_subcategory_stats = year_data.get('nia_subcategory_statistics', {})
            if nia_subcategory_stats:
                for subcategory in nia_subcategory_stats.keys():
                    subcategory_projects = [
                        p for p in nia_projects
                        if (p.get('nia_subcategory') or 'Other Irrigation Works') == subcategory
                    ]
                    key = ('Irrigation Works (NIA)', subcategory)
                    for project in subcategory_projects:
                        project['year'] = year_str
                        project_id = get_project_id(project)
                        if project_id not in category_aggregates[key]['unique_projects']:
                            category_aggregates[key]['unique_projects'].add(project_id)
                            category_aggregates[key]['total_amount'] += project.get('amount', 0)
                            category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
                        category_aggregates[key]['projects'].append(project)
                        if project.get('is_flagged'):
                            category_aggregates[key]['flagged_projects'].append(project)
            elif nia_projects:
                key = ('Irrigation Works (NIA)', None)
                for project in nia_projects:
                    project['year'] = year_str
                    project_id = get_project_id(project)
                    if project_id not in category_aggregates[key]['unique_projects']:
                        category_aggregates[key]['unique_projects'].add(project_id)
                        category_aggregates[key]['total_amount'] += project.get('amount', 0)
                        category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
                    category_aggregates[key]['projects'].append(project)
                    if project.get('is_flagged'):
                        category_aggregates[key]['flagged_projects'].append(project)

            # Rockfall Netting
            rockfall_netting = year_data.get('rockfall_netting', [])
            for project in rockfall_netting:
                project['year'] = year_str
                project_id = get_project_id(project)
                key = ('Rockfall Netting', None)
                if project_id not in category_aggregates[key]['unique_projects']:
                    category_aggregates[key]['unique_projects'].add(project_id)
                    category_aggregates[key]['total_amount'] += project.get('amount', 0)
                    category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
                category_aggregates[key]['projects'].append(project)
                if project.get('is_flagged'):
                    category_aggregates[key]['flagged_projects'].append(project)
            
            # Schools (with subcategories)
            schools = year_data.get('schools', [])
            schools_subcategory_stats = year_data.get('schools_subcategory_statistics', {})
            for subcategory, stats in schools_subcategory_stats.items():
                subcategory_projects = [
                    p for p in schools
                    if p.get('school_subcategory') == subcategory
                ]
                key = ('Schools', subcategory)
                for project in subcategory_projects:
                    project['year'] = year_str
                    project_id = get_project_id(project)
                    if project_id not in category_aggregates[key]['unique_projects']:
                        category_aggregates[key]['unique_projects'].add(project_id)
                        category_aggregates[key]['total_amount'] += project.get('amount', 0)
                        category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
                        category_aggregates[key]['projects'].append(project)
                        if project.get('is_flagged'):
                            category_aggregates[key]['flagged_projects'].append(project)
        
        # Calculate aggregated statistics
        categories = []
        for (category, subcategory), data in category_aggregates.items():
            # Calculate average cost/km
            if data['total_distance_km'] > 0:
                avg_cost_km = data['total_amount'] / data['total_distance_km']
            else:
                # Fallback: calculate mean from individual project cost_per_km
                cost_per_km_values = [p.get('cost_per_km', 0) for p in data['projects'] if p.get('cost_per_km', 0) > 0]
                avg_cost_km = statistics.mean(cost_per_km_values) if cost_per_km_values else 0
            
            # Calculate threshold (mean + 2*std_dev) from all projects in this category/subcategory
            cost_per_km_values = [p.get('cost_per_km', 0) for p in data['projects'] if p.get('cost_per_km', 0) > 0]
            threshold_cost_per_km = 0
            if cost_per_km_values and len(cost_per_km_values) > 1:
                mean = statistics.mean(cost_per_km_values)
                try:
                    std_dev = statistics.stdev(cost_per_km_values)
                    threshold_cost_per_km = mean + (0.1 * std_dev) if std_dev else 0
                except:
                    threshold_cost_per_km = 0
            elif cost_per_km_values and len(cost_per_km_values) == 1:
                # Single project: threshold is the project's cost/km
                threshold_cost_per_km = cost_per_km_values[0]
            
            # For flagged_cost, only count each unique flagged project once
            unique_flagged_projects = {}
            for p in data['flagged_projects']:
                project_id = get_project_id(p)
                if project_id not in unique_flagged_projects:
                    unique_flagged_projects[project_id] = p
            flagged_cost = sum(p.get('amount', 0) for p in unique_flagged_projects.values())
            
            # For total_count, count unique projects
            total_count = len(data['unique_projects'])
            
            categories.append({
                "category": category,
                "subcategory": subcategory,
                "average_cost_per_km": avg_cost_km,
                "threshold_cost_per_km": threshold_cost_per_km,  # Add threshold for all years
                "flagged_cost": flagged_cost,
                "flagged_count": len(unique_flagged_projects),
                "total_count": total_count
            })
        
        # Sort by average_cost_per_km descending
        categories.sort(key=lambda x: x.get('average_cost_per_km', 0), reverse=True)
        
        print(f"   ✅ Calculated {len(categories)} category statistics")
        return categories
    
    def regenerate_all_years(self):
        """Regenerate road infrastructure from all years (2020-2025) with new categorization"""
        print("=" * 100)
        print(" REGENERATING HISTORICAL ROADS WITH UPDATED CATEGORIZATION (2020-2025)")
        print("=" * 100)
        
        all_data = {}
        
        for year in self.years:
            year_data = self.extract_roads_from_year(year)
            all_data[str(year)] = year_data
        
        # Calculate totals
        total_roads = sum(len(all_data[y].get('roads', [])) for y in all_data)
        total_national_roads = sum(len(all_data[y].get('national_roads', [])) for y in all_data)
        total_secondary_roads = sum(len(all_data[y].get('secondary_roads', [])) for y in all_data)
        total_bridges = sum(len(all_data[y].get('bridges', [])) for y in all_data)
        total_traffic_signs = sum(len(all_data[y].get('traffic_signs', [])) for y in all_data)
        total_multi_purpose_buildings = sum(len(all_data[y].get('multi_purpose_buildings', [])) for y in all_data)
        total_rockfall_netting = sum(len(all_data[y].get('rockfall_netting', [])) for y in all_data)
        total_schools = sum(len(all_data[y].get('schools', [])) for y in all_data)
        
        print("\n" + "=" * 100)
        print(" REGENERATION SUMMARY")
        print("=" * 100)
        print(f"Total Roads: {total_roads:,} (National: {total_national_roads:,}, Secondary: {total_secondary_roads:,})")
        print(f"Total Bridges: {total_bridges:,}")
        print(f"Total Road Safety Facilities: {total_traffic_signs:,}")
        print(f"Total Multi-Purpose Buildings: {total_multi_purpose_buildings:,}")
        print(f"Total Rockfall Netting: {total_rockfall_netting:,}")
        print(f"Total Schools: {total_schools:,}")
        print(f"Grand Total: {total_roads + total_bridges + total_traffic_signs + total_multi_purpose_buildings + total_rockfall_netting + total_schools:,}")
        
        for year in self.years:
            year_str = str(year)
            if year_str in all_data:
                year_data = all_data[year_str]
                traffic_signs = year_data.get('traffic_signs', [])
                traffic_with_subcats = sum(1 for p in traffic_signs if p.get('road_safety_subcategories') and len(p.get('road_safety_subcategories', [])) > 0)
                print(f"\n{year}:")
                print(f"  National Roads: {len(year_data.get('national_roads', [])):,}")
                print(f"  Secondary Roads: {len(year_data.get('secondary_roads', [])):,}")
                print(f"  Total Roads: {len(year_data.get('roads', [])):,}")
                print(f"  Bridges: {len(year_data.get('bridges', [])):,}")
                print(f"  Road Safety Facilities: {len(traffic_signs):,} (with subcategories: {traffic_with_subcats:,})")
        
        # Calculate "all years" category statistics
        print("\n📊 Calculating 'All Years' category statistics...")
        all_years_categories = self._calculate_all_years_category_statistics(all_data)
        
        # Save to JSON
        output_path = Path('static/data/historical_roads_2020_2025.json')
        output_data = {
            'metadata': {
                'extracted_at': datetime.now().isoformat(),
                'years': [str(y) for y in self.years],
                'total_roads': total_roads,
                'total_national_roads': total_national_roads,
                'total_secondary_roads': total_secondary_roads,
                'total_bridges': total_bridges,
                'total_traffic_signs': total_traffic_signs,
                'version': '2.2',  # Mark as version 2.2 with all_years category statistics
                'features': [
                    'road_safety_subcategories',
                    'is_new',
                    'work_type',
                    'improved_national_road_detection',
                    'subcategory_specific_flagging',
                    'all_years_category_statistics'
                ]
            },
            'data': all_data,
            'all_years_category_statistics': all_years_categories
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Saved to: {output_path}")
        print("=" * 100)
        
        return output_data


if __name__ == "__main__":
    regenerator = HistoricalRoadsRegenerator()
    regenerator.regenerate_all_years()

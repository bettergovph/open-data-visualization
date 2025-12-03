#!/usr/bin/env python3
"""
Regenerate 2026 Roads Cost Analysis Cache with Updated Categorization
This script regenerates the cache file for /api/budget/roads-cost-analysis (2026)
with the new categorization logic:
- road_safety_subcategories for Road Safety Facilities
- is_new flag for Road Safety Facilities
- work_type for National/Secondary Roads
- Improved _is_national_road logic

Usage:
    python3 scripts/regenerate_2026_roads_cache.py
"""

import json
import re
import sys
from pathlib import Path

# Add parent directory to path to import from visualization.py
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import categorization functions from visualization.py
from visualization import (
    _categorize_road_safety_facilities,
    _is_new_installation,
    _categorize_road_work_type,
    _is_major_road,
    _is_new_construction
)

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

def categorize_multi_purpose_subcategory(name_lower: str) -> str:
    """Best-effort bucket for multi-purpose building projects"""
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

def categorize_nia_subcategory(name_lower: str) -> str:
    target = name_lower or ''
    for label, keywords in NIA_SUBCATEGORY_PATTERNS:
        for keyword in keywords:
            if keyword in target:
                return label
    return "Other Irrigation Works"

def extract_all_chainage_ranges(name: str):
    """Extract all chainage ranges from name"""
    import re
    if not name:
        return []

    ranges = []
    seen = set()

    def parse_number(value) -> float:
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
            ranges.append(key)
            seen.add(key)

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

def calculate_distance(chainage_ranges):
    """Calculate total distance in kilometers"""
    if not chainage_ranges:
        return 0.0, None, []
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

def format_chainage_display(name: str, ranges):
    """Format all chainage ranges for display"""
    if not ranges:
        return None
    import re
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

def calculate_statistics(projects):
    """Calculate statistics for a list of projects"""
    if not projects:
        return {
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "mode": None,
            "std_dev": None,
            "count": 0
        }
    
    import statistics
    from collections import Counter
    
    costs = [p['cost_per_km'] for p in projects if p.get('cost_per_km', 0) > 0]
    if not costs:
        return {
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "mode": None,
            "std_dev": None,
            "count": 0
        }
    
    costs_sorted = sorted(costs)
    mean = statistics.mean(costs)
    
    # Calculate mode (rounded to nearest million)
    rounded_costs = [round(c / 1000000) * 1000000 for c in costs]
    cost_counter = Counter(rounded_costs)
    mode_value = cost_counter.most_common(1)[0][0] if cost_counter else None
    
    try:
        std_dev = statistics.stdev(costs) if len(costs) > 1 else 0
    except:
        std_dev = 0
    
    return {
        "min": min(costs),
        "max": max(costs),
        "mean": mean,
        "median": statistics.median(costs),
        "mode": mode_value,
        "std_dev": std_dev,
        "count": len(costs)
    }


def flag_projects_by_threshold(projects, category_name, stats):
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

def process_roads_data(all_items):
    """Process items and categorize into national_roads, secondary_roads, bridges, traffic_signs"""
    import re
    from collections import defaultdict
    
    national_road_projects = []
    secondary_road_projects = []
    bridge_projects = []
    traffic_signs_projects = []
    nia_projects = []
    fmr_projects = []
    multi_purpose_buildings_projects = []
    rockfall_netting_projects = []
    schools_projects = []
    
    for item in all_items:
        # Use revised_name if available, otherwise fall back to name or description
        name = item.get('revised_name') or item.get('name', '') or item.get('description', '')
        if not name:
            continue
        
        amount = abs(item.get('final_amount', 0) or item.get('original_amount', 0))
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
            chainage_ranges = extract_all_chainage_ranges(name)
            distance_km = 0
            breakdown = None
            individual_distances = []
            chainage_display = 'N/A'
            cost_per_km = amount  # For non-road projects, use amount as cost_per_km (or 0 if we want to avoid division)
            
            if chainage_ranges:
                # If chainage exists, calculate distance
                distance_km, breakdown, individual_distances = calculate_distance(chainage_ranges)
                if distance_km and distance_km > 0:
                    cost_per_km = amount / distance_km
                chainage_display = format_chainage_display(name, chainage_ranges) or 'N/A'
            
            project_data = {
                'name': name,
                'chainage_display': chainage_display,
                'chainage_ranges': chainage_ranges or [],  # Store all ranges (empty if none)
                'distance_km': distance_km,
                'distance_breakdown': breakdown,
                'amount': amount,
                'cost_per_km': cost_per_km,
                'source_sheet': item.get('source_sheet'),
                'region': item.get('location', {}).get('region') if isinstance(item.get('location'), dict) else None
            }
            
            if is_multi_purpose_building:
                project_data['multi_purpose_subcategory'] = categorize_multi_purpose_subcategory(name_lower)
                multi_purpose_buildings_projects.append(project_data)
                continue  # Skip further categorization
            elif is_rockfall_netting:
                rockfall_netting_projects.append(project_data)
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
                schools_projects.append(project_data)
                continue  # Skip further categorization
            # If none matched, continue to regular processing below
        
        # For road-related projects, require chainage notation
        chainage_ranges = extract_all_chainage_ranges(name)
        if not chainage_ranges:
            continue  # Skip road projects without chainage
        
        distance_km, breakdown, individual_distances = calculate_distance(chainage_ranges)
        if not distance_km or distance_km <= 0:
            continue
        
        cost_per_km = amount / distance_km
        chainage_display = format_chainage_display(name, chainage_ranges) or 'N/A'
        
        project_data = {
            'name': name,
            'chainage_display': chainage_display,
            'chainage_ranges': chainage_ranges,
            'distance_km': distance_km,
            'distance_breakdown': breakdown,
            'amount': amount,
            'cost_per_km': cost_per_km,
            'source_sheet': item.get('source_sheet'),
            'region': item.get('location', {}).get('region') if isinstance(item.get('location'), dict) else None
        }
        
        # Check for FMR (Farm-to-Market Road) projects first
        fmr_keywords = [' fmr', 'fmr ', 'farm to market', 'farm-to-market', 'farm to market road']
        is_fmr = any(keyword in name_lower for keyword in fmr_keywords) and 'cnia' not in name_lower
        
        # Check for NIA (National Irrigation Administration) projects
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
            fmr_projects.append(project_data)
            continue
        elif is_nia:
            project_data['nia_subcategory'] = categorize_nia_subcategory(name_lower)
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
            # Categorize road safety facilities into subcategories
            subcategories = _categorize_road_safety_facilities(name, name_lower)
            # Defensive check: ensure subcategories is never empty
            if not subcategories or len(subcategories) == 0:
                subcategories = ['Road Safety Facilities']
            project_data['road_safety_subcategories'] = subcategories
            project_data['is_new'] = _is_new_installation(name, name_lower)
            traffic_signs_projects.append(project_data)
        elif is_bridge:
            bridge_projects.append(project_data)
        elif is_road_term or not is_bridge:
            # Categorize road work type (if found)
            work_types = _categorize_road_work_type(name, name_lower)
            if work_types:
                # Store as list for composite work types
                project_data['work_type'] = work_types[0] if len(work_types) == 1 else work_types
                project_data['work_types'] = work_types  # Always store full list
            else:
                project_data['work_type'] = None
                project_data['work_types'] = []
            
            # Determine if it's new construction or maintenance
            # If no work type, it's automatically new construction
            project_data['is_new_construction'] = _is_new_construction(work_types, name, name_lower)
            
            # Determine if it's a major road (based on segment count)
            is_major_road = _is_major_road(name, chainage_ranges)
            
            if is_major_road:
                national_road_projects.append(project_data)
            else:
                secondary_road_projects.append(project_data)
        else:
            secondary_road_projects.append(project_data)
    
    # Calculate subcategory-specific statistics and flag projects
    # Group road safety facilities by subcategory
    # For composite projects (multiple subcategories), count in ALL subcategories
    # Use "average of average" approach: divide cost/km by number of components
    road_safety_by_subcategory = defaultdict(list)
    for project in traffic_signs_projects:
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
            project_copy = project.copy()
            project_copy['cost_per_km_for_stats'] = project.get('cost_per_km', 0)
            project_copy['num_components'] = 1
            project_copy['original_cost_per_km'] = project.get('cost_per_km', 0)
            road_safety_by_subcategory['Road Safety Facilities'].append(project_copy)
    
    # Group roads by work type (within national/secondary)
    # For composite work types, count in ALL work types using "average of average"
    national_roads_by_work_type = defaultdict(list)
    secondary_roads_by_work_type = defaultdict(list)
    
    for project in national_road_projects:
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
            # Preserve work_type and work_types in the copy (even if None/empty)
            project_copy['work_type'] = project.get('work_type')
            project_copy['work_types'] = project.get('work_types', [])
            national_roads_by_work_type['Major Road'].append(project_copy)
    
    for project in secondary_road_projects:
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
                # Preserve work_type and work_types in the copy
                project_copy['work_type'] = project.get('work_type')
                project_copy['work_types'] = project.get('work_types', [])
                secondary_roads_by_work_type[work_type].append(project_copy)
        else:
            # No work type - use "Minor Road" as default
            project_copy = project.copy()
            project_copy['cost_per_km_for_stats'] = project.get('cost_per_km', 0)
            project_copy['num_components'] = 1
            project_copy['original_cost_per_km'] = project.get('cost_per_km', 0)
            # Preserve work_type and work_types in the copy (even if None/empty)
            project_copy['work_type'] = project.get('work_type')
            project_copy['work_types'] = project.get('work_types', [])
            secondary_roads_by_work_type['Minor Road'].append(project_copy)
    
    # Calculate statistics per subcategory/work_type and flag projects
    def flag_projects_by_subcategory(projects_by_subcategory, category_name):
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
                    "mode": None, "std_dev": None, "count": 0
                }
                continue
            
            import statistics
            from collections import Counter
            
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
    
    def flag_projects_by_total_cost(projects_by_subcategory, category_name):
        """Calculate subcategory statistics and flag projects based on total cost
        This is used for categories that don't have distance metrics (Schools, Buildings, Rockfall)
        - Statistics use total project amount
        - Flagging uses total amount against threshold
        """
        subcategory_stats = {}
        for subcategory, projects in projects_by_subcategory.items():
            # Use total amount for statistics (not cost_per_km)
            total_costs = [p.get('amount', 0) for p in projects if p.get('amount', 0) > 0]
            
            if not total_costs:
                subcategory_stats[subcategory] = {
                    "min": None, "max": None, "mean": None, "median": None,
                    "mode": None, "std_dev": None, "count": 0
                }
                continue
            
            import statistics
            from collections import Counter
            
            costs_sorted = sorted(total_costs)
            mean = statistics.mean(total_costs)
            rounded_costs = [round(c / 1000000) * 1000000 for c in total_costs]
            cost_counter = Counter(rounded_costs)
            mode_value = cost_counter.most_common(1)[0][0] if cost_counter else None
            try:
                std_dev = statistics.stdev(total_costs) if len(total_costs) > 1 else 0
            except:
                std_dev = 0
            
            # Calculate threshold (mean + 0.1*std_dev)
            threshold = None
            if mean is not None and std_dev is not None:
                threshold = mean + (0.1 * std_dev)
            
            stats = {
                "min": min(total_costs),
                "max": max(total_costs),
                "mean": mean,
                "median": statistics.median(total_costs),
                "mode": mode_value,
                "std_dev": std_dev,
                "threshold": threshold,  # Add threshold to stats
                "count": len(projects)
            }
            subcategory_stats[subcategory] = stats
            
            # Flag projects that exceed mean + 0.1*std_dev (outlier threshold)
            # Use total amount for flagging comparison
            
            for project in projects:
                project['subcategory'] = subcategory
                project['subcategory_stats'] = stats
                # Use total amount for flagging comparison
                total_cost = project.get('amount', 0)
                if threshold and total_cost > threshold:
                    project['is_flagged'] = True
                    project['flag_reason'] = f"Total cost (₱{total_cost:,.2f}) exceeds {subcategory} threshold (₱{threshold:,.2f})"
                else:
                    project['is_flagged'] = False
        
        return subcategory_stats
    
    # Flag road safety facilities by subcategory
    road_safety_subcategory_stats = flag_projects_by_subcategory(road_safety_by_subcategory, 'Road Safety Facilities')
    
    # Flag national roads by work type
    national_roads_work_type_stats = flag_projects_by_subcategory(national_roads_by_work_type, 'National Roads')
    
    # Flag secondary roads by work type
    secondary_roads_work_type_stats = flag_projects_by_subcategory(secondary_roads_by_work_type, 'Secondary Roads')
    
    # Merge flagged information back into original projects
    # Create a lookup map: (name, distance_km) -> flagged_project_copy
    def merge_flagging_back(original_projects, projects_by_subcategory_dict):
        """Merge flagging info from copies back into original projects"""
        flagged_map = {}
        for subcategory, flagged_projects in projects_by_subcategory_dict.items():
            for flagged_project in flagged_projects:
                # Use name + distance as unique identifier
                key = (flagged_project.get('name'), flagged_project.get('distance_km'))
                # Store the subcategory for this project
                if key not in flagged_map:
                    flagged_map[key] = []
                flagged_map[key].append(flagged_project)
        
        # Update original projects with flagging info
        for project in original_projects:
            key = (project.get('name'), project.get('distance_km'))
            if key in flagged_map:
                # For projects with work types, prioritize the work type-specific subcategory
                # over the default "National Road" or "Secondary Road"
                work_type = project.get('work_type')
                work_types = project.get('work_types', [])
                
                # Find the flagged project that matches the work type
                best_match = None
                for flagged_project in flagged_map[key]:
                    flagged_subcategory = flagged_project.get('subcategory')
                    # If project has a work type, prefer the flagged project with matching subcategory
                    if work_type and flagged_subcategory == work_type:
                        best_match = flagged_project
                        break
                    # If project has work types, prefer the flagged project with matching subcategory
                    elif work_types and flagged_subcategory in work_types:
                        best_match = flagged_project
                        break
                    # Otherwise, use the first one (default for projects without work types)
                    elif not best_match:
                        best_match = flagged_project
                
                if best_match:
                    # Merge flagging info
                    project['subcategory'] = best_match.get('subcategory')
                    project['subcategory_stats'] = best_match.get('subcategory_stats')
                    project['is_flagged'] = best_match.get('is_flagged', False)
                    project['flag_reason'] = best_match.get('flag_reason')
                    # Preserve original work_type/work_types (they should already be set)
                    # The flagged_project copies might not have them, so we keep the original
                    if not project.get('work_type') and best_match.get('work_type'):
                        project['work_type'] = best_match.get('work_type')
                    if not project.get('work_types') and best_match.get('work_types'):
                        project['work_types'] = best_match.get('work_types')
            else:
                # Project not found in flagged_map - this shouldn't happen, but if it does,
                # it means the project wasn't grouped into any subcategory
                # This can happen if the project has no work type and wasn't added to the default group
                pass
    
    merge_flagging_back(traffic_signs_projects, road_safety_by_subcategory)
    merge_flagging_back(national_road_projects, national_roads_by_work_type)
    merge_flagging_back(secondary_road_projects, secondary_roads_by_work_type)
    
    # Sort each category by cost per km descending
    national_road_projects.sort(key=lambda x: x['cost_per_km'], reverse=True)
    secondary_road_projects.sort(key=lambda x: x['cost_per_km'], reverse=True)
    bridge_projects.sort(key=lambda x: x['cost_per_km'], reverse=True)
    traffic_signs_projects.sort(key=lambda x: x['cost_per_km'], reverse=True)
    nia_projects.sort(key=lambda x: x['cost_per_km'], reverse=True)
    fmr_projects.sort(key=lambda x: x['cost_per_km'], reverse=True)
    
    # Combine all roads for backward compatibility
    road_projects = national_road_projects + secondary_road_projects
    
    # Calculate overall category statistics
    national_roads_stats = calculate_statistics(national_road_projects)
    secondary_roads_stats = calculate_statistics(secondary_road_projects)
    roads_stats = calculate_statistics(road_projects)
    bridges_stats = calculate_statistics(bridge_projects)
    flag_projects_by_threshold(bridge_projects, 'Bridges', bridges_stats)
    traffic_signs_stats = calculate_statistics(traffic_signs_projects)
    nia_stats = calculate_statistics(nia_projects)
    fmr_stats = calculate_statistics(fmr_projects)
    multi_purpose_buildings_stats = calculate_statistics(multi_purpose_buildings_projects)
    rockfall_netting_stats = calculate_statistics(rockfall_netting_projects)
    schools_stats = calculate_statistics(schools_projects)
    
    # Group schools by subcategory for statistics
    schools_by_subcategory = defaultdict(list)
    for project in schools_projects:
        subcategory = project.get('school_subcategory', 'Other School Projects')
        schools_by_subcategory[subcategory].append(project)
    
    multi_purpose_by_subcategory = defaultdict(list)
    for project in multi_purpose_buildings_projects:
        subcategory = project.get('multi_purpose_subcategory', 'Other Multi-Purpose Buildings')
        multi_purpose_by_subcategory[subcategory].append(project)
    
    nia_by_subcategory = defaultdict(list)
    for project in nia_projects:
        subcategory = project.get('nia_subcategory', 'Other Irrigation Works')
        project_copy = project.copy()
        project_copy['cost_per_km_for_stats'] = project.get('cost_per_km', 0)
        project_copy['num_components'] = 1
        project_copy['original_cost_per_km'] = project.get('cost_per_km', 0)
        nia_by_subcategory[subcategory].append(project_copy)

    # Flag schools by subcategory using total cost (not cost_per_km)
    schools_subcategory_stats = flag_projects_by_total_cost(schools_by_subcategory, 'Schools')

    # Flag multi-purpose buildings per subcategory using total cost (not cost_per_km)
    multi_purpose_subcategory_stats = flag_projects_by_total_cost(multi_purpose_by_subcategory, 'Multi-Purpose Buildings')

    # Flag NIA projects per subcategory using cost per km
    nia_subcategory_stats = flag_projects_by_subcategory(nia_by_subcategory, 'Irrigation Works (NIA)')
    merge_flagging_back(nia_projects, nia_by_subcategory)

    # Flag rockfall netting using total cost (not cost_per_km)
    rockfall_grouped = {'Rockfall Netting': rockfall_netting_projects}
    rockfall_stats_dict = flag_projects_by_total_cost(rockfall_grouped, 'Rockfall Netting')
    rockfall_netting_stats_flagged = rockfall_stats_dict.get('Rockfall Netting', {})
    
    return {
        "success": True,
        "roads": {
            "projects": road_projects,
            "total": len(road_projects),
            "statistics": roads_stats
        },
        "national_roads": {
            "projects": national_road_projects,
            "total": len(national_road_projects),
            "statistics": national_roads_stats,
            "subcategory_statistics": national_roads_work_type_stats
        },
        "secondary_roads": {
            "projects": secondary_road_projects,
            "total": len(secondary_road_projects),
            "statistics": secondary_roads_stats,
            "subcategory_statistics": secondary_roads_work_type_stats
        },
        "bridges": {
            "projects": bridge_projects,
            "total": len(bridge_projects),
            "statistics": bridges_stats
        },
        "traffic_signs": {
            "projects": traffic_signs_projects,
            "total": len(traffic_signs_projects),
            "statistics": traffic_signs_stats,
            "subcategory_statistics": road_safety_subcategory_stats
        },
        "nia": {
            "projects": nia_projects,
            "total": len(nia_projects),
            "statistics": nia_stats,
            "subcategory_statistics": nia_subcategory_stats
        },
        "fmr": {
            "projects": fmr_projects,
            "total": len(fmr_projects),
            "statistics": fmr_stats
        },
        "multi_purpose_buildings": {
            "projects": multi_purpose_buildings_projects,
            "total": len(multi_purpose_buildings_projects),
            "statistics": calculate_statistics(multi_purpose_buildings_projects),
            "subcategory_statistics": multi_purpose_subcategory_stats
        },
        "rockfall_netting": {
            "projects": rockfall_netting_projects,
            "total": len(rockfall_netting_projects),
            "statistics": rockfall_netting_stats
        },
        "schools": {
            "projects": schools_projects,
            "total": len(schools_projects),
            "statistics": schools_stats,
            "subcategory_statistics": schools_subcategory_stats
        }
    }

def regenerate_2026_cache():
    """Regenerate the 2026 roads cost analysis cache file"""
    print("=" * 100)
    print(" REGENERATING 2026 ROADS COST ANALYSIS CACHE")
    print("=" * 100)
    
    # Load source data
    json_path = Path('static/data/budget_amendments_2026.json')
    if not json_path.exists():
        print(f"❌ Source file not found: {json_path}")
        return False
    
    print(f"📂 Loading source data from: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    all_items = data.get('line_items', []) + data.get('projects', [])
    print(f"   Loaded {len(data.get('line_items', []))} line items and {len(data.get('projects', []))} projects")
    print(f"   Total items: {len(all_items)}")
    
    # Process data
    print("\n🔄 Processing and categorizing projects...")
    result = process_roads_data(all_items)
    
    # Show statistics
    print("\n📊 Processing Results:")
    print(f"   National Roads: {result['national_roads']['total']:,}")
    print(f"   Secondary Roads: {result['secondary_roads']['total']:,}")
    print(f"   Bridges: {result['bridges']['total']:,}")
    print(f"   Road Safety Facilities: {result['traffic_signs']['total']:,}")
    print(f"   NIA Projects: {result['nia']['total']:,}")
    print(f"   FMR Projects: {result['fmr']['total']:,}")
    print(f"   Multi-Purpose Buildings: {result['multi_purpose_buildings']['total']:,}")
    print(f"   Rockfall Netting: {result['rockfall_netting']['total']:,}")
    print(f"   Schools: {result['schools']['total']:,}")
    
    # Check categorization
    traffic_signs = result['traffic_signs']['projects']
    traffic_with_subcats = sum(1 for p in traffic_signs if p.get('road_safety_subcategories') and len(p.get('road_safety_subcategories', [])) > 0)
    traffic_with_is_new = sum(1 for p in traffic_signs if 'is_new' in p)
    
    print(f"\n✅ Categorization Status:")
    print(f"   Road Safety Facilities with subcategories: {traffic_with_subcats}/{len(traffic_signs)}")
    print(f"   Road Safety Facilities with is_new flag: {traffic_with_is_new}/{len(traffic_signs)}")
    
    if traffic_signs:
        sample = traffic_signs[0]
        print(f"\n📋 Sample Road Safety Facility:")
        print(f"   Name: {sample['name'][:80]}...")
        print(f"   Subcategories: {sample.get('road_safety_subcategories', [])}")
        print(f"   Is New: {sample.get('is_new', 'N/A')}")
    
    # Calculate "all years" category statistics (combining historical + 2026)
    print("\n📊 Calculating 'All Years' category statistics (2020-2026)...")
    all_years_categories = calculate_all_years_category_statistics(result)
    result['all_years_category_statistics'] = all_years_categories
    print(f"   ✅ Calculated {len(all_years_categories)} category statistics")
    
    # Save to cache file
    cache_file = Path('static/data/api_cache/roads_cost_analysis_cache.json')
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"\n💾 Saving cache to: {cache_file}")
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    file_size = cache_file.stat().st_size / (1024 * 1024)  # Size in MB
    print(f"   ✅ Cache file saved ({file_size:.2f} MB)")
    print("=" * 100)
    
    return True

def calculate_all_years_category_statistics(cache_2026):
    """Calculate aggregated category statistics combining historical (2020-2025) + 2026"""
    from collections import defaultdict
    import statistics
    from pathlib import Path
    
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
    
    # Load historical data (2020-2025)
    historical_path = Path('static/data/historical_roads_2020_2025.json')
    if historical_path.exists():
        with open(historical_path, 'r', encoding='utf-8') as f:
            historical_data = json.load(f)
        
        # Use pre-computed all_years_category_statistics if available
        if 'all_years_category_statistics' in historical_data:
            # Start with historical all_years stats
            for cat_stat in historical_data['all_years_category_statistics']:
                key = (cat_stat['category'], cat_stat['subcategory'])
                # We'll aggregate with 2026 data below
                pass
        
        # Also aggregate from individual years if needed
        for year_str in ['2020', '2021', '2022', '2023', '2024', '2025']:
            year_data = historical_data.get('data', {}).get(year_str, {})
            if not year_data:
                continue
            
            # Bridges
            bridges = year_data.get('bridges', [])
            for project in bridges:
                project['year'] = year_str  # Add year for uniqueness
                project_id = get_project_id(project)
                key = ('Bridges', None)
                category_aggregates[key]['projects'].append(project)
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
                    if project_id not in category_aggregates[key]['unique_projects']:
                        category_aggregates[key]['unique_projects'].add(project_id)
                        category_aggregates[key]['total_amount'] += project.get('amount', 0)
                        category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
                    if project.get('is_flagged', False):
                        category_aggregates[key]['flagged_projects'].append(project)
    
    # Add 2026 data
    # Bridges
    bridges = cache_2026.get('bridges', {}).get('projects', [])
    for project in bridges:
        project['year'] = '2026'  # Add year for uniqueness
        project_id = get_project_id(project)
        key = ('Bridges', None)
        category_aggregates[key]['projects'].append(project)
        if project_id not in category_aggregates[key]['unique_projects']:
            category_aggregates[key]['unique_projects'].add(project_id)
            category_aggregates[key]['total_amount'] += project.get('amount', 0)
            category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
        if project.get('is_flagged', False):
            category_aggregates[key]['flagged_projects'].append(project)
    
    # Road Safety Facilities
    traffic_signs = cache_2026.get('traffic_signs', {}).get('projects', [])
    subcategory_stats = cache_2026.get('traffic_signs', {}).get('subcategory_statistics', {})
    for subcategory, stats in subcategory_stats.items():
        # Match projects by subcategory field (set during flagging) or by road_safety_subcategories list
        subcategory_projects = [
            p for p in traffic_signs 
            if p.get('subcategory') == subcategory or 
               (subcategory in (p.get('road_safety_subcategories') or []))
        ]
        key = ('Road Safety Facilities', subcategory)
        for project in subcategory_projects:
            project['year'] = '2026'  # Add year for uniqueness
            project_id = get_project_id(project)
            category_aggregates[key]['projects'].append(project)
            if project_id not in category_aggregates[key]['unique_projects']:
                category_aggregates[key]['unique_projects'].add(project_id)
                category_aggregates[key]['total_amount'] += project.get('amount', 0)
                category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
            if project.get('is_flagged', False):
                category_aggregates[key]['flagged_projects'].append(project)
    
    # Major Roads
    national_roads = cache_2026.get('national_roads', {}).get('projects', [])
    national_work_type_stats = cache_2026.get('national_roads', {}).get('subcategory_statistics', {})
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
            project['year'] = '2026'  # Add year for uniqueness
            project_id = get_project_id(project)
            category_aggregates[key]['projects'].append(project)
            if project_id not in category_aggregates[key]['unique_projects']:
                category_aggregates[key]['unique_projects'].add(project_id)
                category_aggregates[key]['total_amount'] += project.get('amount', 0)
                category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
            if project.get('is_flagged', False):
                category_aggregates[key]['flagged_projects'].append(project)
    
    # Minor Roads
    secondary_roads = cache_2026.get('secondary_roads', {}).get('projects', [])
    secondary_work_type_stats = cache_2026.get('secondary_roads', {}).get('subcategory_statistics', {})
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
            project['year'] = '2026'  # Add year for uniqueness
            project_id = get_project_id(project)
            category_aggregates[key]['projects'].append(project)
            if project_id not in category_aggregates[key]['unique_projects']:
                category_aggregates[key]['unique_projects'].add(project_id)
                category_aggregates[key]['total_amount'] += project.get('amount', 0)
                category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
            if project.get('is_flagged', False):
                category_aggregates[key]['flagged_projects'].append(project)
    
    # Multi-Purpose Buildings (from 2026, grouped by derived subcategory)
    multi_purpose_data = cache_2026.get('multi_purpose_buildings', {})
    multi_purpose_buildings = multi_purpose_data.get('projects', [])
    multi_purpose_sub_stats = multi_purpose_data.get('subcategory_statistics', {})
    if multi_purpose_sub_stats:
        for subcategory in multi_purpose_sub_stats.keys():
            subcategory_projects = [
                p for p in multi_purpose_buildings
                if (p.get('multi_purpose_subcategory') or 'Other Multi-Purpose Buildings') == subcategory
            ]
            key = ('Multi-Purpose Buildings', subcategory)
            for project in subcategory_projects:
                project['year'] = '2026'
                project_id = get_project_id(project)
                category_aggregates[key]['projects'].append(project)
                if project_id not in category_aggregates[key]['unique_projects']:
                    category_aggregates[key]['unique_projects'].add(project_id)
                    category_aggregates[key]['total_amount'] += project.get('amount', 0)
                    category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
                if project.get('is_flagged', False):
                    category_aggregates[key]['flagged_projects'].append(project)
            
            # Irrigation Works (NIA)
            nia_projects = year_data.get('nia', [])
            nia_sub_stats = year_data.get('nia_subcategory_statistics', {})
            if nia_sub_stats:
                for subcategory in nia_sub_stats.keys():
                    subcategory_projects = [
                        p for p in nia_projects
                        if (p.get('nia_subcategory') or 'Other Irrigation Works') == subcategory
                    ]
                    key = ('Irrigation Works (NIA)', subcategory)
                    for project in subcategory_projects:
                        project['year'] = year_str
                        project_id = get_project_id(project)
                        category_aggregates[key]['projects'].append(project)
                        if project_id not in category_aggregates[key]['unique_projects']:
                            category_aggregates[key]['unique_projects'].add(project_id)
                            category_aggregates[key]['total_amount'] += project.get('amount', 0)
                            category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
                        if project.get('is_flagged', False):
                            category_aggregates[key]['flagged_projects'].append(project)
            elif nia_projects:
                key = ('Irrigation Works (NIA)', None)
                for project in nia_projects:
                    project['year'] = year_str
                    project_id = get_project_id(project)
                    category_aggregates[key]['projects'].append(project)
                    if project_id not in category_aggregates[key]['unique_projects']:
                        category_aggregates[key]['unique_projects'].add(project_id)
                        category_aggregates[key]['total_amount'] += project.get('amount', 0)
                        category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
                    if project.get('is_flagged', False):
                        category_aggregates[key]['flagged_projects'].append(project)
    else:
        for project in multi_purpose_buildings:
            project['year'] = '2026'
            project_id = get_project_id(project)
            key = ('Multi-Purpose Buildings', None)
            category_aggregates[key]['projects'].append(project)
            if project_id not in category_aggregates[key]['unique_projects']:
                category_aggregates[key]['unique_projects'].add(project_id)
                category_aggregates[key]['total_amount'] += project.get('amount', 0)
                category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
            if project.get('is_flagged', False):
                category_aggregates[key]['flagged_projects'].append(project)
    
    # Irrigation Works (NIA) from 2026
    nia_data = cache_2026.get('nia', {})
    nia_projects = nia_data.get('projects', [])
    nia_sub_stats = nia_data.get('subcategory_statistics', {})
    if nia_sub_stats:
        for subcategory in nia_sub_stats.keys():
            subcategory_projects = [
                p for p in nia_projects
                if (p.get('nia_subcategory') or 'Other Irrigation Works') == subcategory
            ]
            key = ('Irrigation Works (NIA)', subcategory)
            for project in subcategory_projects:
                project['year'] = '2026'
                project_id = get_project_id(project)
                category_aggregates[key]['projects'].append(project)
                if project_id not in category_aggregates[key]['unique_projects']:
                    category_aggregates[key]['unique_projects'].add(project_id)
                    category_aggregates[key]['total_amount'] += project.get('amount', 0)
                    category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
                if project.get('is_flagged', False):
                    category_aggregates[key]['flagged_projects'].append(project)
    elif nia_projects:
        key = ('Irrigation Works (NIA)', None)
        for project in nia_projects:
            project['year'] = '2026'
            project_id = get_project_id(project)
            category_aggregates[key]['projects'].append(project)
            if project_id not in category_aggregates[key]['unique_projects']:
                category_aggregates[key]['unique_projects'].add(project_id)
                category_aggregates[key]['total_amount'] += project.get('amount', 0)
                category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
            if project.get('is_flagged', False):
                category_aggregates[key]['flagged_projects'].append(project)
    
    # Rockfall Netting (from 2026)
    rockfall_netting = cache_2026.get('rockfall_netting', {}).get('projects', [])
    for project in rockfall_netting:
        project['year'] = '2026'
        project_id = get_project_id(project)
        key = ('Rockfall Netting', None)
        category_aggregates[key]['projects'].append(project)
        if project_id not in category_aggregates[key]['unique_projects']:
            category_aggregates[key]['unique_projects'].add(project_id)
            category_aggregates[key]['total_amount'] += project.get('amount', 0)
            category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
        if project.get('is_flagged', False):
            category_aggregates[key]['flagged_projects'].append(project)
    
    # Schools (from 2026, with subcategories)
    schools = cache_2026.get('schools', {}).get('projects', [])
    schools_subcategory_stats = cache_2026.get('schools', {}).get('subcategory_statistics', {})
    for subcategory, stats in schools_subcategory_stats.items():
        subcategory_projects = [
            p for p in schools
            if p.get('school_subcategory') == subcategory
        ]
        key = ('Schools', subcategory)
        for project in subcategory_projects:
            project['year'] = '2026'
            project_id = get_project_id(project)
            category_aggregates[key]['projects'].append(project)
            if project_id not in category_aggregates[key]['unique_projects']:
                category_aggregates[key]['unique_projects'].add(project_id)
                category_aggregates[key]['total_amount'] += project.get('amount', 0)
                category_aggregates[key]['total_distance_km'] += project.get('distance_km', 0)
            if project.get('is_flagged', False):
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
        
        # Calculate threshold (mean + 1*std_dev)
        cost_per_km_values = [p.get('cost_per_km', 0) for p in data['projects'] if p.get('cost_per_km', 0) > 0]
        threshold_cost_per_km = 0
        if cost_per_km_values and len(cost_per_km_values) > 1:
            mean = statistics.mean(cost_per_km_values)
            try:
                std_dev = statistics.stdev(cost_per_km_values)
                threshold_cost_per_km = mean + (0.1 * std_dev)
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
    
    return categories

if __name__ == "__main__":
    success = regenerate_2026_cache()
    if success:
        print("\n✅ Cache regeneration completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Cache regeneration failed!")
        sys.exit(1)

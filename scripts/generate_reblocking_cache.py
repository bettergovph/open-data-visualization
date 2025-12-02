#!/usr/bin/env python3
"""
Generate Reblocking Analysis Cache
Pre-calculates highway reblocking analysis data and saves to JSON cache file.

This script processes budget amendments 2026 data to:
- Identify major highways using keywords
- Extract chainage data
- Classify projects (new construction, repair, rehabilitation, maintenance)
- Calculate highway lengths from chainage
- Compute cost per kilometer
- Flag anomalies (expensive repairs/rehab/maintenance)

Usage:
    python3 scripts/generate_reblocking_cache.py
    
Output:
    static/data/reblocking_analysis.json
"""

import json
import re
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import errors as psycopg2_errors
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional
import os
from dotenv import load_dotenv

load_dotenv()


class ReblockingAnalysisGenerator:
    def __init__(self, year: int = 2026):
        self.year = year
        if year == 2026:
            self.input_path = Path("static/data/budget_amendments_2026.json")
        else:
            self.input_path = None  # Will load from database
        self.output_path = Path(f"static/data/reblocking_analysis_{year}.json")
        
        # Database configuration
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'port': int(os.getenv('POSTGRES_PORT', 5432)),
            'user': os.getenv('POSTGRES_USER', 'budget_admin'),
            'password': os.getenv('POSTGRES_PASSWORD', ''),
            'database': os.getenv('POSTGRES_DB_BUDGET', 'budget_analysis')
        }
        
        # Highway keywords for identification
        self.highway_keywords = {
            'maharlika': ['maharlika', 'maharlika highway', 'ah26', 'ah 26'],
            'andaya': ['andaya', 'andaya highway'],
            'pan-philippine': ['pan-philippine', 'pan philippine', 'pan-phil', 'pan phil'],
            'south luzon': ['south luzon', 'slex', 'south luzon expressway'],
            'north luzon': ['north luzon', 'nlex', 'north luzon expressway'],
            'tagaytay': ['tagaytay', 'tagaytay road'],
            'ortigas': ['ortigas', 'ortigas avenue', 'ortigas extension'],
            'edsa': ['edsa', 'epifanio delos santos', 'epifanio de los santos'],
            'commonwealth': ['commonwealth', 'commonwealth avenue'],
            'roxas': ['roxas', 'roxas boulevard', 'roxas avenue'],
            'quezon': ['quezon avenue', 'quezon boulevard'],
            'rizal': ['rizal avenue', 'rizal boulevard'],
            'marcos': ['marcos highway', 'marcos road'],
            'sumulong': ['sumulong', 'sumulong highway'],
            'batangas': ['batangas', 'batangas road'],
            'laguna': ['laguna', 'laguna boulevard'],
            'cavite': ['cavite', 'cavite road'],
            'bulacan': ['bulacan', 'bulacan road'],
            'pampanga': ['pampanga', 'pampanga road'],
            'tarlac': ['tarlac', 'tarlac road'],
            'pangasinan': ['pangasinan', 'pangasinan road'],
            'la union': ['la union', 'la union road'],
            'ilocos': ['ilocos', 'ilocos road'],
            'cagayan': ['cagayan', 'cagayan road'],
            'isabela': ['isabela', 'isabela road'],
            'nueva ecija': ['nueva ecija', 'nueva ecija road'],
            'bataan': ['bataan', 'bataan road'],
            'zambales': ['zambales', 'zambales road'],
            'quezon province': ['quezon province', 'quezon prov'],
            'camarines': ['camarines', 'camarines sur', 'camarines norte'],
            'albay': ['albay', 'albay road'],
            'sorsogon': ['sorsogon', 'sorsogon road'],
            'samar': ['samar', 'samar road'],
            'leyte': ['leyte', 'leyte road'],
            'cebu': ['cebu', 'cebu road'],
            'bohol': ['bohol', 'bohol road'],
            'mindanao': ['mindanao', 'mindanao road'],
            'davao': ['davao', 'davao road'],
            'cotabato': ['cotabato', 'cotabato road'],
            'zamboanga': ['zamboanga', 'zamboanga road'],
            'surigao': ['surigao', 'surigao road'],
            'agusan': ['agusan', 'agusan road'],
            'bukidnon': ['bukidnon', 'bukidnon road'],
            'misamis': ['misamis', 'misamis road'],
            'lanao': ['lanao', 'lanao road'],
            'maguindanao': ['maguindanao', 'maguindanao road'],
            'sulu': ['sulu', 'sulu road'],
            'tawi-tawi': ['tawi-tawi', 'tawi tawi'],
            'basilan': ['basilan', 'basilan road'],
            'palawan': ['palawan', 'palawan road'],
            'romblon': ['romblon', 'romblon road'],
            'masbate': ['masbate', 'masbate road'],
            'marinduque': ['marinduque', 'marinduque road'],
            'mindoro': ['mindoro', 'mindoro road'],
            'catanduanes': ['catanduanes', 'catanduanes road'],
            'siquijor': ['siquijor', 'siquijor road'],
            'dinagat': ['dinagat', 'dinagat road'],
            'apayao': ['apayao', 'apayao road'],
            'abra': ['abra', 'abra road'],
            'benguet': ['benguet', 'benguet road'],
            'ifugao': ['ifugao', 'ifugao road'],
            'kalinga': ['kalinga', 'kalinga road'],
            'mountain province': ['mountain province', 'mt. province'],
            'quirino': ['quirino', 'quirino road'],
            'nueva vizcaya': ['nueva vizcaya', 'nueva vizcaya road'],
            'aurora': ['aurora', 'aurora road'],
            'batanes': ['batanes', 'batanes road'],
        }
        
        # Generic highway keywords
        self.generic_highway_keywords = ['highway', 'hiway', 'hi-way', 'hway', 'expressway', 'avenue', 'boulevard', 'road', 'rd', 'ave', 'blvd']
        
        # Invalid/generic highway names to filter out
        self.invalid_highway_names = {
            'application', 'application of', 'national', 'other highway', 'other', 
            'highway', 'road', 'avenue', 'boulevard', 'expressway', 'the', 'a', 'an',
            'construction', 'improvement', 'rehabilitation', 'repair', 'maintenance'
        }
    
    def extract_all_chainage_ranges(self, name: str) -> List[Tuple[int, int, int, int]]:
        """Extract all chainage ranges from name"""
        ranges = []
        pattern_k = r'K(\d+)\s*\+\s*\(?(-?\d+)\)?\s*-\s*K(\d+)\s*\+\s*\(?(-?\d+)\)?'
        for match in re.finditer(pattern_k, name, re.IGNORECASE):
            ranges.append((int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))))
        pattern_chainage = r'Chainage\s+(\d+)\s*-\s*Chainage\s+(\d+)'
        for match in re.finditer(pattern_chainage, name, re.IGNORECASE):
            start_total = int(match.group(1))
            end_total = int(match.group(2))
            start_km = start_total // 1000
            start_m = start_total % 1000
            end_km = end_total // 1000
            end_m = end_total % 1000
            ranges.append((start_km, start_m, end_km, end_m))
        return ranges
    
    def calculate_distance(self, chainage_ranges: List[Tuple[int, int, int, int]]) -> float:
        """Calculate total distance in kilometers"""
        if not chainage_ranges:
            return 0.0
        total_distance_m = 0
        def to_meters(km, m):
            return km * 1000 + m
        for chainage_range in chainage_ranges:
            start_km, start_m, end_km, end_m = chainage_range
            start_total = to_meters(start_km, start_m)
            end_total = to_meters(end_km, end_m)
            distance_m = abs(end_total - start_total)
            total_distance_m += distance_m
        return total_distance_m / 1000.0
    
    def identify_highway(self, name: str) -> Optional[str]:
        """Identify which highway a project belongs to"""
        name_lower = name.lower()
        original_name = name
        
        # Exclude flood control projects (not roads/highways)
        # Check for flood control patterns first
        flood_control_patterns = [
            r'^flood\s+control\s+structures?\s+(?:protecting|along)',
            r'^flood\s+control\s+structure\s+(?:protecting|along)',
            r'flood\s+control\s+structures?\s+along',
            r'flood\s+control\s+structure\s+along',
            r'^flood\s+relief\s+along',  # "Flood Relief Along ..."
        ]
        for pattern in flood_control_patterns:
            if re.match(pattern, name, re.IGNORECASE):
                return None  # Not a highway project
        
        flood_control_keywords = [
            'flood control', 'floodcontrol', 'flood-control',
            'flood relief', 'floodrelief', 'flood-relief',
            'flood mitigation', 'flood management',
            'drainage system', 'drainage canal', 'drainage channel',
            'seawall', 'sea wall', 'dike', 'levee',
            'flood protection', 'flood barrier',
            'protecting national'  # Common pattern: "Flood Control Structures Protecting National"
        ]
        if any(keyword in name_lower for keyword in flood_control_keywords):
            return None  # Not a highway project
        
        # Remove codes in parentheses like (S00025Gr), (S00028Gr), etc.
        name = re.sub(r'\s*\([A-Z]\d+[A-Za-z]+\)', '', name, flags=re.IGNORECASE).strip()
        
        # Remove work type indicators in parentheses first (e.g., "Road (Asphalt Overlay)" -> "Road")
        # Common patterns: (Asphalt Overlay), (Repair), (Rehabilitation), (Maintenance), etc.
        work_type_parentheses_patterns = [
            r'\s*\(asphalt\s+overlay\)',
            r'\s*\(repair\)',
            r'\s*\(rehabilitation\)',
            r'\s*\(maintenance\)',
            r'\s*\(reconstruction\)',
            r'\s*\(improvement\)',
            r'\s*\(upgrading\)',
            r'\s*\(widening\)',
            r'\s*\(construction\)',
            r'\s*\(installation\)',
            r'\s*\(concreting\)',
            r'\s*\(paving\)',
        ]
        for pattern in work_type_parentheses_patterns:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE).strip()
        
        # Also remove generic work descriptions in parentheses
        name = re.sub(r'\s*\([^)]*(?:overlay|repair|rehab|maintenance|construction|improvement|upgrading|widening|installation|concreting|paving)[^)]*\)', '', name, flags=re.IGNORECASE).strip()
        
        # Update name_lower after cleaning
        name_lower = name.lower()
        
        # Pattern 0: Handle "Road: <work_type> At Specific Locations Along <highway_name>"
        # Example: "Road: Asphalt Overlay At Specific Locations Along Central Rd, San Miguel- Constancia- Cabano- Igcawayan"
        #          -> extract "Central Rd, San Miguel- Constancia- Cabano- Igcawayan"
        # Example: "Road: Asphalt Overlay At Specific Locations Along Guimaras Circumferential Rd (S00028Gr)"
        #          -> extract "Guimaras Circumferential Rd"
        # This is a maintenance indicator, so we drop the prefix and extract the highway name
        # Make the pattern more flexible to handle variations
        road_work_along_pattern = r'^road:\s*(?:asphalt\s+overlay|repair|rehabilitation|improvement|maintenance|construction|reconstruction|upgrading|widening)\s+at\s+specific\s+locations\s+along\s+(.+?)(?:\s*$|\s*\[|\s*\([A-Z]\d+[A-Za-z]+\)|\s*\([^)]*\)\s*$)'
        road_work_along_match = re.match(road_work_along_pattern, name, re.IGNORECASE)
        if road_work_along_match:
            potential_highway = road_work_along_match.group(1).strip()
            # Remove any trailing brackets, codes, or parentheses
            potential_highway = re.sub(r'\s*\[.*$', '', potential_highway).strip()
            # Remove codes like (S00025Gr), (S00028Gr) at the end
            potential_highway = re.sub(r'\s*\([A-Z]\d+[A-Za-z]+\)\s*$', '', potential_highway, flags=re.IGNORECASE).strip()
            # Remove other trailing parentheses content
            potential_highway = re.sub(r'\s*\([^)]*\)\s*$', '', potential_highway).strip()
            potential_lower = potential_highway.lower()
            
            # Validate it's a valid highway name
            if potential_lower not in self.invalid_highway_names and len(potential_highway) > 3:
                work_words = ['slope', 'protection', 'retaining', 'wall', 'street', 'lights', 'traffic', 'signs', 'drainage', 'damaged', 'paved', 'specific', 'locations']
                if not any(word in potential_lower for word in work_words):
                    # Check if it starts with a capital letter or contains road/highway keywords
                    if re.match(r'^[A-Z]', potential_highway) or any(kw in potential_lower for kw in ['road', 'rd', 'highway', 'hiway', 'avenue', 'boulevard', 'blvd', 'ave']):
                        # Preserve the original capitalization but title case if needed
                        return potential_highway if potential_highway[0].isupper() else potential_highway.title()
        
        # Pattern 0.5: Handle "Road: <work_type> Of <highway_name>"
        # Example: "Road: Asphalt Overlay Of Quezon" -> extract "Quezon"
        road_work_of_pattern = r'^road:\s*(?:asphalt\s+overlay|repair|rehabilitation|improvement|maintenance|construction|reconstruction|upgrading|widening)\s+of\s+(.+?)(?:\s*$|\s*\[|\s*\(|\s+-|\s+with)'
        road_work_of_match = re.match(road_work_of_pattern, name, re.IGNORECASE)
        if road_work_of_match:
            potential_highway = road_work_of_match.group(1).strip()
            # Remove any trailing brackets, codes, or project details
            potential_highway = re.sub(r'\s*\[.*$', '', potential_highway).strip()
            potential_highway = re.sub(r'\s*\([^)]*\)\s*$', '', potential_highway).strip()
            potential_highway = re.sub(r'\s+-\s+.*$', '', potential_highway).strip()
            potential_highway = re.sub(r'\s+with\s+.*$', '', potential_highway, flags=re.IGNORECASE).strip()
            potential_lower = potential_highway.lower()
            
            if potential_lower not in self.invalid_highway_names and len(potential_highway) > 3:
                work_words = ['slope', 'protection', 'retaining', 'wall', 'street', 'lights', 'traffic', 'signs', 'drainage', 'damaged', 'paved']
                if not any(word in potential_lower for word in work_words):
                    if re.match(r'^[A-Z]', potential_highway):
                        return potential_highway.title()
        
        # Pattern 0.6: Handle "Road:Asphalt Overlay/..." (no space after colon)
        # Example: "Road:Asphalt Overlay/Item 304-A (Slurry Surface Treatment 12Mm) With Correction"
        # This is maintenance work but may not have a clear highway name - skip if no highway name found
        road_work_slash_pattern = r'^road:\s*(?:asphalt\s+overlay|repair|rehabilitation|improvement|maintenance|construction|reconstruction|upgrading|widening)\s*/'
        if re.match(road_work_slash_pattern, name, re.IGNORECASE):
            # Try to extract highway name after the work type, but if it's just technical details, skip
            # For now, we'll let it fall through to other patterns or return None
            pass
        
        # Pattern 1: Extract highway name from "<work_type> Of <highway_name>" pattern
        # Examples: "Improvement Of Manila South" -> "Manila South"
        #           "Rehabilitation Of Manila East" -> "Manila East"
        #           "Reconstruction Of <name>" -> extract name after "Of"
        work_type_of_pattern = r'^(?:preventive\s+maintenance|construction|reconstruction|improvement|rehabilitation|repair|maintenance|upgrading|road\s+widening|repair\s+and\s+rehabilitation|rehabilitation\s+and\s+improvement|improvement\s+and\s+upgrading)\s+of\s+(.+?)(?:\s+-\s+|\s+K\d+|\s*$)'
        work_type_of_match = re.match(work_type_of_pattern, name, re.IGNORECASE)
        if work_type_of_match:
            potential_highway = work_type_of_match.group(1).strip()
            # Remove any trailing work-related words, chainage notation, or other project details
            potential_highway = re.sub(r'\s+(?:road|highway|avenue|boulevard|expressway).*$', '', potential_highway, flags=re.IGNORECASE)
            potential_highway = re.sub(r'\s+-\s+.*$', '', potential_highway)  # Remove anything after " - "
            potential_highway = re.sub(r'\s+K\d+.*$', '', potential_highway, flags=re.IGNORECASE)  # Remove chainage
            potential_highway = re.sub(r'\s+Chainage.*$', '', potential_highway, flags=re.IGNORECASE)  # Remove chainage text
            potential_highway = potential_highway.strip()
            potential_lower = potential_highway.lower()
            
            # Validate it's not a work-related word
            if potential_lower not in self.invalid_highway_names and len(potential_highway) > 3:
                work_words = ['slope', 'protection', 'retaining', 'wall', 'street', 'lights', 'traffic', 'signs', 'drainage', 'damaged', 'paved', 'improvement', 'repair', 'rehabilitation', 'maintenance', 'construction', 'reconstruction']
                if not any(word in potential_lower for word in work_words):
                    # Additional check: make sure it looks like a highway name (has at least one capitalized word)
                    if re.match(r'^[A-Z]', potential_highway):
                        return potential_highway.title()
        
        # Pattern 2: Handle "Along" in the middle: "Some Text Along Highway Name"
        # Extract what comes after "Along"
        along_pattern = r'\balong\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+(?:North|South|East|West|National|Provincial|Vicinal|Road|Highway|Avenue|Boulevard))?)'
        along_match = re.search(along_pattern, name, re.IGNORECASE)
        if along_match:
            potential_highway = along_match.group(1).strip()
            potential_lower = potential_highway.lower()
            # Validate it's not a work-related word
            if potential_lower not in self.invalid_highway_names and len(potential_highway) > 3:
                work_words = ['slope', 'protection', 'retaining', 'wall', 'street', 'lights', 'traffic', 'signs', 'drainage']
                if not any(word in potential_lower for word in work_words):
                    return potential_highway.title()
        
        # Pattern 3: Remove work type prefixes that are not highway names
        # Handle patterns like "Construction Of Slope Protection Along Old Zigzag" -> extract "Old Zigzag"
        work_type_patterns = [
            r'^preventive\s+maintenance\s+of\s+',
            r'^construction\s+of\s+(?:slope\s+protection|retaining\s+wall|drainage|bridge|culvert)\s+along\s+',
            r'^construction\s+of\s+',
            r'^reconstruction\s+of\s+',
            r'^installation\s+of\s+(?:street\s+lights|traffic\s+lights|signs|signals)\s+along\s+',
            r'^installation\s+of\s+',
            r'^upgrading\s+of\s+damaged\s+paved\s+',
            r'^improvement\s+of\s+',
            r'^asphalt\s+overlay\s+along\s+',
            r'^rehabilitation\s+of\s+',
            r'^road\s+widening\s+of\s+',
            r'^repair\s+of\s+',
            r'^repair\s+and\s+rehabilitation\s+of\s+',
            r'^rehabilitation\s+and\s+improvement\s+of\s+',
            r'^maintenance\s+of\s+',
            r'^upgrading\s+of\s+',
            r'^improvement\s+and\s+upgrading\s+of\s+',
            r'^along\s+',  # Remove "Along" at the start
        ]
        
        # Clean the name by removing work type prefixes
        cleaned_name = name
        for pattern in work_type_patterns:
            cleaned_name = re.sub(pattern, '', cleaned_name, flags=re.IGNORECASE).strip()
        
        # If cleaning removed something, use the cleaned name
        if cleaned_name != name and len(cleaned_name) > 3:
            name = cleaned_name
            name_lower = name.lower()
        
        # Check specific highways first (using cleaned name)
        for highway_name, keywords in self.highway_keywords.items():
            for keyword in keywords:
                if keyword in name_lower:
                    return highway_name.title()
        
        # Check for generic highway keywords combined with location/name
        has_highway_keyword = any(kw in name_lower for kw in self.generic_highway_keywords)
        if has_highway_keyword:
            # Try to extract a meaningful highway name
            patterns = [
                r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:highway|hiway|hi-way|hway|expressway)',
                r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:avenue|boulevard|road|rd|ave|blvd)',
            ]
            for pattern in patterns:
                match = re.search(pattern, name, re.IGNORECASE)
                if match:
                    extracted_name = match.group(1).strip()
                    extracted_lower = extracted_name.lower()
                    
                    # Filter out invalid/generic names
                    if extracted_lower in self.invalid_highway_names:
                        continue
                    
                    # Check if it's just a single generic word
                    if len(extracted_name.split()) == 1 and extracted_lower in ['national', 'application', 'other']:
                        continue
                    
                    return extracted_name.title()
        
        # If no highway keyword found, try to extract name after work type prefixes
        # Look for patterns like "Name Road", "Name Highway", or just capitalized names
        if not has_highway_keyword and cleaned_name != original_name:
            # Try to find a meaningful name (capitalized words, possibly with location indicators)
            # Pattern 1: Highway name with direction/location suffix (North, South, East, West, National, etc.)
            name_patterns = [
                r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+(?:North|South|East|West|National|Provincial|Vicinal))?)\s*',
                r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+(?:Road|Highway|Avenue|Boulevard|Expressway))?)\s*',
                r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s*',  # Multiple capitalized words
            ]
            
            for name_pattern in name_patterns:
                match = re.match(name_pattern, name)
                if match:
                    extracted_name = match.group(1).strip()
                    extracted_lower = extracted_name.lower()
                    
                    # Filter out invalid/generic names
                    if extracted_lower not in self.invalid_highway_names and len(extracted_name) > 3:
                        # Check if it's just a single generic word
                        if len(extracted_name.split()) == 1 and extracted_lower in ['national', 'application', 'other', 'the', 'a', 'an']:
                            continue
                        
                        # Additional filtering: skip if it's just work-related words
                        work_words = ['slope', 'protection', 'retaining', 'wall', 'street', 'lights', 'traffic', 'signs']
                        if extracted_lower in work_words or any(word in extracted_lower for word in work_words if len(word) > 4):
                            continue
                        
                        return extracted_name.title()
        
        return None  # Don't return "Other Highway" - filter it out
    
    def classify_project_type(self, name: str) -> str:
        """Classify project as new construction, repair, rehabilitation, or maintenance"""
        name_lower = name.lower()
        
        # Repair keywords
        repair_keywords = ['repair', 'repaired', 'repairing', 'repairs']
        # Rehabilitation keywords
        rehab_keywords = ['rehabilitation', 'rehabilitate', 'rehabilitated', 'rehabilitating', 'rehab']
        # Maintenance keywords (including improvement, upgrading, asphalt overlay, road widening)
        maintenance_keywords = [
            'maintenance', 'maintain', 'maintained', 'maintaining', 'maintainance',
            'improvement', 'improve', 'improved', 'improving',
            'upgrading', 'upgrade', 'upgraded',
            'asphalt overlay', 'overlay',
            'road widening', 'widening',
            'preventive maintenance'
        ]
        # New construction keywords
        construction_keywords = ['construction', 'construct', 'constructed', 'constructing', 'concreting', 'concrete', 'paving', 'paved', 'new']
        
        # Check in order of specificity
        if any(kw in name_lower for kw in repair_keywords):
            return 'repair'
        elif any(kw in name_lower for kw in rehab_keywords):
            return 'rehabilitation'
        elif any(kw in name_lower for kw in maintenance_keywords):
            return 'maintenance'
        elif any(kw in name_lower for kw in construction_keywords):
            return 'new_construction'
        else:
            # Default to new construction if unclear
            return 'new_construction'
    
    def format_chainage_display(self, name: str, ranges: List[Tuple[int, int, int, int]]) -> Optional[str]:
        """Format chainage ranges for display"""
        if not ranges:
            return None
        chainage_strings = []
        pattern_k = r'(K\d+\s*\+\s*\(?-?\d+\)?\s*-\s*K\d+\s*\+\s*\(?-?\d+\)?)'
        for match in re.finditer(pattern_k, name, re.IGNORECASE):
            chainage_strings.append(match.group(1))
        pattern_chainage = r'(Chainage\s+\d+\s*-\s*Chainage\s+\d+)'
        for match in re.finditer(pattern_chainage, name, re.IGNORECASE):
            chainage_strings.append(match.group(1))
        if chainage_strings:
            return ', '.join(chainage_strings)
        return None
    
    def load_historical_data(self) -> List[Dict[str, Any]]:
        """Load historical budget data from PostgreSQL database"""
        if self.year == 2026:
            return []  # 2026 uses JSON file
        
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Check if table exists
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = %s
            """, (f'budget_{self.year}',))
            
            available_columns = {row['column_name'] for row in cursor.fetchall()}
            
            required_columns = {'id', 'amt', 'dsc', 'year', 'source_file'}
            missing_columns = required_columns - available_columns
            if missing_columns:
                print(f"   ⚠️  Table budget_{self.year} missing required columns: {missing_columns}")
                cursor.close()
                conn.close()
                return []
            
            # Handle different year formats
            cursor.execute(f"""
                SELECT data_type 
                FROM information_schema.columns 
                WHERE table_name = 'budget_{self.year}' AND column_name = 'year'
            """)
            year_col_result = cursor.fetchone()
            year_type = year_col_result['data_type'] if year_col_result else 'text'
            
            if year_type == 'integer':
                year_filter = f"year = {self.year}"
            else:
                year_filter = f"(year::text = '{self.year}' OR year::text LIKE '%{self.year}%')"
            
            # Filter for road/highway projects with chainage notation
            query = f"""
                SELECT
                    id,
                    amt,
                    dsc,
                    year,
                    source_file
                FROM budget_{self.year}
                WHERE {year_filter}
                AND amt >= 100
                AND (dsc ILIKE '%chainage%' OR dsc ILIKE '%K%d+%' OR dsc ILIKE '%road%' OR dsc ILIKE '%highway%')
                ORDER BY amt DESC, dsc
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            historical_data = []
            for row in rows:
                try:
                    amt = float(row['amt']) if row['amt'] else 0.0
                    amt = amt * 1000  # Convert from thousands to actual amount
                    
                    historical_data.append({
                        'name': row['dsc'] or '',
                        'final_amount': amt,
                        'original_amount': amt,
                        'source_sheet': row.get('source_file', ''),
                        'location': {'region': None}  # Can be enhanced later
                    })
                except Exception as row_e:
                    print(f"   ⚠️  Error processing row (ID: {row.get('id', 'N/A')}): {type(row_e).__name__}: {str(row_e)}")
                    continue
            
            cursor.close()
            conn.close()
            
            return historical_data
            
        except psycopg2_errors.UndefinedTable:
            print(f"   Table budget_{self.year} does not exist, skipping")
            cursor.close()
            conn.close()
            return []
        except Exception as e:
            error_msg = str(e)
            if "does not exist" in error_msg.lower() or "relation" in error_msg.lower():
                print(f"   Table budget_{self.year} does not exist, skipping")
                cursor.close()
                conn.close()
                return []
            else:
                print(f"   ⚠️  Error loading {self.year} data: {type(e).__name__}: {str(e)}")
                cursor.close()
                conn.close()
                return []
    
    def generate(self):
        """Generate the reblocking analysis cache"""
        if self.year == 2026:
            print(f"Loading data from {self.input_path}...")
            
            if not self.input_path.exists():
                raise FileNotFoundError(f"Input file not found: {self.input_path}")
            
            with open(self.input_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            all_items = data.get('line_items', []) + data.get('projects', [])
        else:
            print(f"Loading data from database for year {self.year}...")
            all_items = self.load_historical_data()
        
        print(f"Processing {len(all_items)} items for year {self.year}...")
        
        # Process all items
        highway_projects = defaultdict(list)
        processed_count = 0
        
        for item in all_items:
            name = item.get('name', '') or item.get('description', '')
            if not name:
                continue
            
            # Exclude flood control projects (not roads/highways)
            name_lower = name.lower()
            # Check for flood control patterns first
            flood_control_patterns = [
                r'^flood\s+control\s+structures?\s+(?:protecting|along)',
                r'^flood\s+control\s+structure\s+(?:protecting|along)',
                r'flood\s+control\s+structures?\s+along',
                r'flood\s+control\s+structure\s+along',
                r'^flood\s+relief\s+along',  # "Flood Relief Along ..."
            ]
            is_flood_control = False
            for pattern in flood_control_patterns:
                if re.match(pattern, name, re.IGNORECASE):
                    is_flood_control = True
                    break
            
            if not is_flood_control:
                flood_control_keywords = [
                    'flood control', 'floodcontrol', 'flood-control',
                    'flood relief', 'floodrelief', 'flood-relief',
                    'flood mitigation', 'flood management',
                    'drainage system', 'drainage canal', 'drainage channel',
                    'seawall', 'sea wall', 'dike', 'levee',
                    'flood protection', 'flood barrier',
                ]
                if any(keyword in name_lower for keyword in flood_control_keywords):
                    is_flood_control = True
            
            if is_flood_control:
                continue  # Skip flood control projects
            
            # Check if it has chainage notation
            chainage_ranges = self.extract_all_chainage_ranges(name)
            if not chainage_ranges:
                continue
            
            # Identify highway
            highway = self.identify_highway(name)
            if not highway:
                continue
            
            amount = abs(item.get('final_amount', 0) or item.get('original_amount', 0))
            if amount <= 0:
                continue
            
            # Calculate distance
            distance_km = self.calculate_distance(chainage_ranges)
            if distance_km <= 0:
                continue
            
            # Calculate cost per km
            cost_per_km = amount / distance_km
            
            # Classify project type
            project_type = self.classify_project_type(name)
            
            # Get chainage start position for sorting
            start_km = chainage_ranges[0][0]
            start_m = chainage_ranges[0][1]
            chainage_start_m = start_km * 1000 + start_m
            
            chainage_display = self.format_chainage_display(name, chainage_ranges) or 'N/A'
            
            project_data = {
                'name': name,
                'highway': highway,
                'chainage_display': chainage_display,
                'chainage_ranges': chainage_ranges,
                'chainage_start_m': chainage_start_m,
                'distance_km': distance_km,
                'amount': amount,
                'cost_per_km': cost_per_km,
                'project_type': project_type,
                'source_sheet': item.get('source_sheet'),
                'region': item.get('location', {}).get('region') if isinstance(item.get('location'), dict) else None
            }
            
            highway_projects[highway].append(project_data)
            processed_count += 1
        
        print(f"Found {processed_count} highway projects across {len(highway_projects)} highways")
        
        # Process each highway to find main project and flag anomalies
        highways_data = []
        all_segments = []
        total_anomalies = 0
        
        for highway, projects in highway_projects.items():
            if not projects:
                continue
            
            # Sort by distance (longest first) to find main project
            projects_sorted_by_length = sorted(projects, key=lambda x: x['distance_km'], reverse=True)
            main_project = projects_sorted_by_length[0] if projects_sorted_by_length else None
            
            if not main_project:
                continue
            
            main_cost_per_km = main_project['cost_per_km']
            
            # Calculate total highway length (from min to max chainage)
            all_chainage_starts = []
            all_chainage_ends = []
            for p in projects:
                for cr in p['chainage_ranges']:
                    start_km, start_m, end_km, end_m = cr
                    all_chainage_starts.append(start_km * 1000 + start_m)
                    all_chainage_ends.append(end_km * 1000 + end_m)
            
            if all_chainage_starts and all_chainage_ends:
                min_chainage = min(all_chainage_starts)
                max_chainage = max(all_chainage_ends)
                estimated_highway_length_km = (max_chainage - min_chainage) / 1000.0
            else:
                estimated_highway_length_km = sum(p['distance_km'] for p in projects)
            
            # Flag anomalies (repairs/rehab/maintenance more expensive than main project)
            for project in projects:
                is_anomaly = False
                flag_reason = None
                
                if project['project_type'] in ['repair', 'rehabilitation', 'maintenance']:
                    if project['cost_per_km'] > main_cost_per_km:
                        is_anomaly = True
                        flag_reason = f"{project['project_type'].replace('_', ' ').title()} more expensive than main project"
                        total_anomalies += 1
                elif project['cost_per_km'] > main_cost_per_km * 2:
                    # Flag if cost is more than 2x the main project
                    is_anomaly = True
                    flag_reason = "Cost per km significantly higher than main project"
                    total_anomalies += 1
                
                project['is_anomaly'] = is_anomaly
                project['flag_reason'] = flag_reason
                all_segments.append(project)
            
            # Sort projects by chainage start position for visualization
            projects_sorted_by_chainage = sorted(projects, key=lambda x: x['chainage_start_m'])
            
            highways_data.append({
                'highway': highway,
                'estimated_length_km': estimated_highway_length_km,
                'main_project': main_project,
                'total_segments': len(projects),
                'total_distance_km': sum(p['distance_km'] for p in projects),
                'total_amount': sum(p['amount'] for p in projects),
                'segments': projects_sorted_by_chainage
            })
        
        # Sort highways by name
        highways_data.sort(key=lambda x: x['highway'])
        
        # Calculate total distance across all highways (sum of all segment distances, not estimated lengths)
        total_distance_km = sum(h['total_distance_km'] for h in highways_data)
        
        # Prepare output data (don't include all_segments to reduce file size - segments are in each highway)
        output_data = {
            'success': True,
            'highways': highways_data,
            'total_highways': len(highways_data),
            'total_segments': len(all_segments),
            'total_anomalies': total_anomalies,
            'total_distance_km': total_distance_km,
            # Note: all_segments removed to reduce JSON size - use highways[].segments instead
            'year': self.year,
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'source_file': str(self.input_path) if self.input_path else f'database: budget_{self.year}',
                'processed_items': processed_count,
                'year': self.year
            }
        }
        
        # Write to output file
        print(f"Writing cache to {self.output_path}...")
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Cache generated successfully!")
        print(f"  - Highways: {len(highways_data)}")
        print(f"  - Total segments: {len(all_segments)}")
        print(f"  - Total distance: {total_distance_km:.2f} km")
        print(f"  - Anomalies flagged: {total_anomalies}")
        print(f"  - Output: {self.output_path}")


if __name__ == '__main__':
    import sys
    
    # Generate for all years (2020-2026) or specific year if provided
    if len(sys.argv) > 1:
        years = [int(sys.argv[1])]
    else:
        years = [2020, 2021, 2022, 2023, 2024, 2025, 2026]
    
    for year in years:
        print(f"\n{'='*80}")
        print(f"GENERATING REBLOCKING CACHE FOR YEAR {year}")
        print(f"{'='*80}")
        generator = ReblockingAnalysisGenerator(year=year)
        try:
            generator.generate()
        except Exception as e:
            print(f"Error generating cache for {year}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"\n{'='*80}")
    print("✓ All reblocking caches generated successfully!")
    print(f"{'='*80}")

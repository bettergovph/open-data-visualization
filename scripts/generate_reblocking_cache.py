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
        
        # Check specific highways first
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
            return None  # Don't return "Other Highway" - filter it out
        
        return None
    
    def classify_project_type(self, name: str) -> str:
        """Classify project as new construction, repair, rehabilitation, or maintenance"""
        name_lower = name.lower()
        
        # Repair keywords
        repair_keywords = ['repair', 'repaired', 'repairing', 'repairs']
        # Rehabilitation keywords
        rehab_keywords = ['rehabilitation', 'rehabilitate', 'rehabilitated', 'rehabilitating', 'rehab']
        # Maintenance keywords
        maintenance_keywords = ['maintenance', 'maintain', 'maintained', 'maintaining', 'maintainance']
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
        
        # Calculate total distance across all highways
        total_distance_km = sum(h['estimated_length_km'] for h in highways_data)
        
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

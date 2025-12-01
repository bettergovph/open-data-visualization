#!/usr/bin/env python3
"""
Extract Historical Roads, Bridges, and Traffic Signs/Lights (2020-2025)
Extracts road infrastructure projects from historical budget data and categorizes them
for comparison with 2026 data.

Usage:
    python3 scripts/extract_historical_roads.py
"""

import json
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import errors as psycopg2_errors
from pathlib import Path
from typing import Dict, List, Any
import re
from datetime import datetime


class HistoricalRoadsExtractor:
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
        """Extract all chainage ranges from name and return list of (start_km, start_m, end_km, end_m)"""
        ranges = []
        
        # Pattern 1: K format - find all occurrences
        pattern_k = r'K(\d+)\s*\+\s*\(?(-?\d+)\)?\s*-\s*K(\d+)\s*\+\s*\(?(-?\d+)\)?'
        for match in re.finditer(pattern_k, name, re.IGNORECASE):
            ranges.append((int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))))
        
        # Pattern 2: Chainage format - find all occurrences
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
    
    def calculate_distance(self, chainage_ranges):
        """Calculate total distance in kilometers from list of chainage ranges"""
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
        
        # K format
        pattern_k = r'(K\d+\s*\+\s*\(?-?\d+\)?\s*-\s*K\d+\s*\+\s*\(?-?\d+\)?)'
        for match in re.finditer(pattern_k, name, re.IGNORECASE):
            chainage_strings.append(match.group(1))
        
        # Chainage format
        pattern_chainage = r'(Chainage\s+\d+\s*-\s*Chainage\s+\d+)'
        for match in re.finditer(pattern_chainage, name, re.IGNORECASE):
            chainage_strings.append(match.group(1))
        
        if chainage_strings:
            return ', '.join(chainage_strings)
        
        return None
    
    def is_national_road(self, name: str, distance_km: float) -> bool:
        """Determine if a road project is a national road
        National roads are typically:
        - Named after regions, provinces, cities, or municipalities
        - Have "national" in the name
        - Are longer highways (typically > 1km, often > 5km)
        - Connect major locations (cross-municipality/city roads)
        """
        name_lower = name.lower()
        
        # Check for explicit "national" keyword
        if 'national' in name_lower:
            return True
        
        # Common Philippine provinces, cities, and regions (partial list - can be expanded)
        # These are common in national road names
        major_locations = [
            'manila', 'cebu', 'davao', 'iloilo', 'baguio', 'quezon', 'laguna', 'cavite',
            'bulacan', 'pampanga', 'bataan', 'nueva ecija', 'tarlac', 'pangasinan',
            'batangas', 'rizal', 'antipolo', 'caloocan', 'las piñas', 'makati', 'malabon',
            'mandaluyong', 'marikina', 'muntinlupa', 'navotas', 'parañaque', 'pasay',
            'pasig', 'pateros', 'san juan', 'taguig', 'valenzuela', 'bacoor', 'dasmarinas', 'dasmariñas',
            'calamba', 'san pedro', 'biñan', 'santa rosa', 'cabuyao', 'los baños',
            'bay', 'calauan', 'liliw', 'magdalena', 'pagsanjan', 'paete', 'pila',
            'riizal', 'victoria', 'nagcarlan', 'lumban', 'kalayaan', 'cavinti',
            'pila', 'siniloan', 'famy', 'mabitac', 'pangil', 'pakil', 'paete',
            'kalayaan', 'lumban', 'cavinti', 'luisiana', 'majayjay', 'liliw',
            'magdalena', 'pagsanjan', 'pila', 'riizal', 'victoria', 'nagcarlan',
            'zamboanga', 'cagayan', 'isabela', 'nueva vizcaya', 'quirino', 'aurora',
            'bataan', 'bataan', 'pampanga', 'tarlac', 'pangasinan', 'la union',
            'ilocos sur', 'ilocos norte', 'ilocos', 'abra', 'apayao', 'benguet', 'ifugao',
            'kalinga', 'mountain province', 'albay', 'camarines norte', 'camarines sur',
            'catanduanes', 'masbate', 'sorsogon', 'aklan', 'antique', 'capiz', 'guimaras',
            'negros occidental', 'negros oriental', 'bohol', 'cebu', 'leyte', 'southern leyte',
            'eastern samar', 'northern samar', 'samar', 'biliran', 'zamboanga del norte',
            'zamboanga del sur', 'zamboanga sibugay', 'bukidnon', 'malaybalay', 'camiguin', 'lanao del norte',
            'misamis occidental', 'misamis oriental', 'davao del norte', 'davao del sur',
            'davao oriental', 'davao de oro', 'davao occidental', 'compostela valley',
            'south cotabato', 'north cotabato', 'sultan kudarat', 'sarangani', 'cotabato',
            'agusan del norte', 'agusan del sur', 'agusan', 'surigao del norte', 'surigao del sur',
            'dinagat islands', 'basilan', 'lanao del sur', 'maguindanao', 'sulu', 'tawi-tawi',
            'roxas', 'toledo', 'infanta', 'dumaguete', 'north'
        ]
        
        # Check for cross-municipality/city roads (e.g., "Bacoor-Dasmariñas", "City1 to City2", "City1–City2")
        # These are almost always national roads
        cross_municipality_patterns = [
            r'([a-záéíóúñ\s]+)[\s]*[-–—][\s]*([a-záéíóúñ\s]+)',  # hyphen, en dash, em dash
            r'([a-záéíóúñ\s]+)[\s]+to[\s]+([a-záéíóúñ\s]+)',  # "to" separator
            r'([a-záéíóúñ\s]+)[\s]*/[\s]*([a-záéíóúñ\s]+)',  # slash separator
        ]
        
        for pattern in cross_municipality_patterns:
            matches = re.finditer(pattern, name_lower)
            for match in matches:
                city1 = match.group(1).strip()
                city2 = match.group(2).strip()
                # Remove common road terms that might be in the name
                city1 = re.sub(r'\s+(road|highway|national|rd|hway|hiway)\s*$', '', city1).strip()
                city2 = re.sub(r'\s+(road|highway|national|rd|hway|hiway)\s*$', '', city2).strip()
                
                # Check if both cities are in major locations
                city1_match = any(loc in city1 or city1 in loc for loc in major_locations)
                city2_match = any(loc in city2 or city2 in loc for loc in major_locations)
                
                if city1_match and city2_match:
                    return True  # Cross-municipality road = national road
        
        # Check if name contains major location names (indicating inter-city/province roads)
        contains_major_location = any(loc in name_lower for loc in major_locations)
        
        # Check for highway designations that typically indicate national roads
        highway_indicators = ['maharlika', 'andaya', 'pan-philippine', 'philippine-japan', 'jica']
        is_highway = any(indicator in name_lower for indicator in highway_indicators)
        
        # National roads are typically longer (but not always - some segments are short)
        # If it's a longer road (> 1km) with location names, it's likely national
        # If it's explicitly a highway, it's national
        # If it has "national" in name, it's national
        if is_highway:
            return True
        
        # If it contains major location names, it's likely a national road (regardless of length)
        # Roads named after major provinces/cities are national roads
        if contains_major_location:
            return True
        
        # Very long roads (> 5km) are likely national roads
        if distance_km > 5.0:
            return True
        
        # Secondary roads are typically very short (< 1km) and don't contain major location names
        # If it's short and doesn't have major locations, it's secondary (return False)
        return False
    
    def categorize_project(self, name: str, distance_km: float):
        """Categorize project into roads, bridges, or traffic_signs"""
        name_lower = name.lower()
        
        # Traffic signs/lights: road safety facilities, installations, guardrails
        # Includes: installation, road safety, guardrail, traffic facilities
        traffic_keywords = ['installation', 'road safety', 'guardrail', 'traffic facilities', 'traffic facility']
        is_traffic = any(keyword in name_lower for keyword in traffic_keywords)
        
        # Bridges: projects with bridge-related keywords OR very short distances (< 1 km)
        # Include: bridge, viaduct, flyover, overpass, underpass, footbridge, pedestrian bridge
        bridge_keywords = ['bridge', 'viaduct', 'flyover', 'overpass', 'underpass', 'footbridge', 'pedestrian bridge']
        is_bridge_keyword = any(keyword in name_lower for keyword in bridge_keywords)
        
        # Road-related terms (these indicate roads, not bridges)
        # Includes: road, rd, highway, hiway, hway, h-way, boulevard, blvd, avenue, ave, junction, jct, 
        #           old route, diversion, extension, ext, street, st, expressway
        road_terms = [
            ' road', ' rd', ' highway', ' hiway', ' hway', ' h-way',
            'boulevard', ' blvd', ' avenue', ' ave', ' ave.',
            'junction', ' jct', ' old route', ' diversion',
            'extension', ' ext', ' street', ' st', ' st.',
            'expressway'
        ]
        is_road_term = any(term in name_lower for term in road_terms)
        
        # Also consider very short projects (< 1 km) as potential bridges
        # But exclude if it's clearly a road segment or traffic facility
        # Also exclude very tiny segments (< 0.01 km = 10m) which are likely just road repairs
        is_short_distance = distance_km < 1.0 if distance_km else False
        is_very_short = distance_km < 0.01 if distance_km else False
        
        is_bridge = is_bridge_keyword or (is_short_distance and not is_very_short and not is_traffic and not is_road_term)
        
        if is_traffic:
            return 'traffic_signs'
        elif is_bridge:
            return 'bridges'
        # Roads: everything else (including "national" roads, chainage-only projects, etc.)
        else:
            return 'roads'
    
    def load_historical_data(self, year: int):
        """Load historical budget data from PostgreSQL database"""
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Check if table exists and has required columns
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
            
            # Handle different year formats: integer (2020) or string ('GAA-2024')
            # Try to detect year column type first
            cursor.execute(f"""
                SELECT data_type 
                FROM information_schema.columns 
                WHERE table_name = 'budget_{year}' AND column_name = 'year'
            """)
            year_col_result = cursor.fetchone()
            year_type = year_col_result['data_type'] if year_col_result else 'text'
            
            # Build year filter based on column type
            if year_type == 'integer':
                # Integer column: use direct comparison
                year_filter = f"year = {year}"
            else:
                # Text column: use LIKE pattern (handles 'GAA-2024', '2024', etc.)
                year_filter = f"(year::text = '{year}' OR year::text LIKE '%{year}%')"
            
            # Filter for DPWH/road-related projects
            # Look for road, bridge, highway, infrastructure keywords in description
            dept_filter = """
                (dsc ILIKE '%road%' OR dsc ILIKE '%bridge%' OR dsc ILIKE '%highway%' 
                 OR dsc ILIKE '%viaduct%' OR dsc ILIKE '%flyover%' OR dsc ILIKE '%overpass%'
                 OR dsc ILIKE '%underpass%' OR dsc ILIKE '%chainage%' OR dsc ILIKE '%K%d+%'
                 OR dsc ILIKE '%traffic%' OR dsc ILIKE '%installation%' OR dsc ILIKE '%pavement%'
                 OR dsc ILIKE '%lighting%' OR dsc ILIKE '%sign%')
            """
            
            min_amt = 100  # Amounts are in thousands
            
            query = f"""
                SELECT
                    id,
                    amt,
                    dsc,
                    year,
                    source_file
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
                    amt = amt * 1000  # Convert from thousands to actual amount
                    
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
            
        except psycopg2_errors.UndefinedTable as e:
            print(f"   Table budget_{year} does not exist, skipping")
            cursor.close()
            conn.close()
            return []
        except Exception as e:
            error_msg = str(e)
            if "does not exist" in error_msg.lower() or "relation" in error_msg.lower():
                print(f"   Table budget_{year} does not exist, skipping")
                cursor.close()
                conn.close()
                return []
            else:
                print(f"   ⚠️  Error loading {year} data: {type(e).__name__}: {str(e)}")
                cursor.close()
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
                'bridges': [],
                'traffic_signs': []
            }
        
        print(f"   Loaded {len(historical_data)} records with road-related keywords")
        
        roads = []
        national_roads = []
        secondary_roads = []
        bridges = []
        traffic_signs = []
        
        for item in historical_data:
            name = item['description']
            if not name:
                continue
            
            # Check if it has chainage notation
            chainage_ranges = self.extract_all_chainage_ranges(name)
            if not chainage_ranges:
                continue  # Skip items without chainage
            
            amount = abs(item['amount'])
            if amount <= 0:
                continue
            
            # Calculate distance
            distance_km, breakdown, individual_distances = self.calculate_distance(chainage_ranges)
            if not distance_km or distance_km <= 0:
                continue
            
            # Calculate cost per km
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
            
            # Categorize
            category = self.categorize_project(name, distance_km)
            
            if category == 'bridges':
                bridges.append(project_data)
            elif category == 'traffic_signs':
                traffic_signs.append(project_data)
            else:
                # Separate into national and secondary roads
                if self.is_national_road(name, distance_km):
                    national_roads.append(project_data)
                else:
                    secondary_roads.append(project_data)
                roads.append(project_data)  # Keep combined list for backward compatibility
        
        print(f"   ✅ Categorized: {len(national_roads)} national roads, {len(secondary_roads)} secondary roads, {len(bridges)} bridges, {len(traffic_signs)} traffic signs")
        
        return {
            'roads': roads,  # Combined for backward compatibility
            'national_roads': national_roads,
            'secondary_roads': secondary_roads,
            'bridges': bridges,
            'traffic_signs': traffic_signs
        }
    
    def extract_all_years(self):
        """Extract road infrastructure from all years (2020-2025)"""
        print("=" * 100)
        print(" EXTRACTING HISTORICAL ROADS, BRIDGES, AND TRAFFIC SIGNS (2020-2025)")
        print("=" * 100)
        
        all_data = {}
        
        for year in self.years:
            year_data = self.extract_roads_from_year(year)
            all_data[year] = year_data
        
        # Calculate totals
        total_roads = sum(len(all_data[y].get('roads', [])) for y in all_data)
        total_national_roads = sum(len(all_data[y].get('national_roads', [])) for y in all_data)
        total_secondary_roads = sum(len(all_data[y].get('secondary_roads', [])) for y in all_data)
        total_bridges = sum(len(all_data[y].get('bridges', [])) for y in all_data)
        total_traffic_signs = sum(len(all_data[y].get('traffic_signs', [])) for y in all_data)
        
        print("\n" + "=" * 100)
        print(" EXTRACTION SUMMARY")
        print("=" * 100)
        print(f"Total Roads: {total_roads:,} (National: {total_national_roads:,}, Secondary: {total_secondary_roads:,})")
        print(f"Total Bridges: {total_bridges:,}")
        print(f"Total Traffic Signs/Lights: {total_traffic_signs:,}")
        print(f"Grand Total: {total_roads + total_bridges + total_traffic_signs:,}")
        
        for year in self.years:
            if year in all_data:
                year_data = all_data[year]
                print(f"\n{year}:")
                print(f"  National Roads: {len(year_data.get('national_roads', [])):,}")
                print(f"  Secondary Roads: {len(year_data.get('secondary_roads', [])):,}")
                print(f"  Total Roads: {len(year_data.get('roads', [])):,}")
                print(f"  Bridges: {len(year_data.get('bridges', [])):,}")
                print(f"  Traffic Signs: {len(year_data.get('traffic_signs', [])):,}")
        
        # Save to JSON
        output_path = Path('static/data/historical_roads_2020_2025.json')
        output_data = {
            'metadata': {
                'extracted_at': datetime.now().isoformat(),
                'years': self.years,
                'total_roads': total_roads,
                'total_national_roads': total_national_roads,
                'total_secondary_roads': total_secondary_roads,
                'total_bridges': total_bridges,
                'total_traffic_signs': total_traffic_signs
            },
            'data': all_data
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Saved to: {output_path}")
        print("=" * 100)
        
        return output_data


if __name__ == "__main__":
    extractor = HistoricalRoadsExtractor()
    extractor.extract_all_years()


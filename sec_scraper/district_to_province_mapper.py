#!/usr/bin/env python3
"""
District to Province Mapping Utility
Maps DPWH District Engineering Office names to provinces for heat map visualization
"""

import re
import json
from typing import Dict, List, Tuple

class DistrictToProvinceMapper:
    """Maps district engineering office names to provinces"""
    
    def __init__(self):
        # Special mappings for districts that don't follow standard patterns
        self.special_mappings = {
            "Metro Manila": "Metropolitan Manila",
            "NCR": "Metropolitan Manila",
            "North Manila": "Metropolitan Manila",
            "South Manila": "Metropolitan Manila",
            "East Manila": "Metropolitan Manila",
            "West Manila": "Metropolitan Manila",
            "Malabon-Navotas": "Metropolitan Manila",
            "Mandaluyong-San Juan": "Metropolitan Manila",
            "Marikina": "Metropolitan Manila",
            "Muntinlupa": "Metropolitan Manila",
            "Parañaque": "Metropolitan Manila",
            "Pasay": "Metropolitan Manila",
            "Pasig": "Metropolitan Manila",
            "Pateros-Taguig": "Metropolitan Manila",
            "Quezon City": "Metropolitan Manila",
            "Valenzuela": "Metropolitan Manila",
            "Las Piñas": "Metropolitan Manila",
            "Makati": "Metropolitan Manila",
            "Caloocan": "Metropolitan Manila",
            "Manila": "Metropolitan Manila",
        }
        
        # Province name mappings to GeoJSON format
        self.province_geojson_mappings = {
            "Metropolitan Manila": "metropolitan-manila",
            "Bulacan": "bulacan",
            "Pampanga": "pampanga",
            "Tarlac": "tarlac",
            "Cebu": "cebu",
            "Davao City": "davao-del-sur",  # Davao City is in Davao del Sur
            "Davao del Sur": "davao-del-sur",
            "Davao del Norte": "davao-del-norte",
            "Davao Oriental": "davao-oriental",
            "La Union": "la-union",
            "Ilocos Norte": "ilocos-norte",
            "Ilocos Sur": "ilocos-sur",
            "Isabela": "isabela",
            "Pangasinan": "pangasinan",
            "Laguna": "laguna",
            "Mindoro Occidental": "occidental-mindoro",
            "Albay": "albay",
            "Abra": "abra",
            "Agusan del Norte": "agusan-del-norte",
            "Agusan del Sur": "agusan-del-sur",
            "Aklan": "aklan",
            "Antique": "antique",
            "Apayao": "apayao",
            "Aurora": "aurora",
            "Bacolod City": "negros-occidental",  # Bacolod City is in Negros Occidental
            "Baguio City": "benguet",  # Baguio City is in Benguet
            "Bataan": "bataan",
            "Batanes": "batanes",
            "Batangas": "batangas",
            "Benguet": "benguet",
            "Biliran": "biliran",
            "Bohol": "bohol",
            "Bukidnon": "bukidnon",
            "Cagayan": "cagayan",
            "Camarines Norte": "camarines-norte",
            "Camarines Sur": "camarines-sur",
            "Camiguin": "camiguin",
            "Capiz": "capiz",
            "Catanduanes": "catanduanes",
            "Cavite": "cavite",
            "Cebu": "cebu",
            "Cotabato": "cotabato",
            "Davao": "davao-del-sur",
            "Eastern Samar": "eastern-samar",
            "Guimaras": "guimaras",
            "Ifugao": "ifugao",
            "Iloilo": "iloilo",
            "Kalinga": "kalinga",
            "Lanao del Norte": "lanao-del-norte",
            "Lanao del Sur": "lanao-del-sur",
            "Maguindanao": "maguindanao",
            "Marinduque": "marinduque",
            "Masbate": "masbate",
            "Misamis Occidental": "misamis-occidental",
            "Misamis Oriental": "misamis-oriental",
            "Mountain Province": "mountain-province",
            "Negros Occidental": "negros-occidental",
            "Negros Oriental": "negros-oriental",
            "Northern Samar": "northern-samar",
            "Nueva Ecija": "nueva-ecija",
            "Nueva Vizcaya": "nueva-vizcaya",
            "Palawan": "palawan",
            "Quezon": "quezon",
            "Rizal": "rizal",
            "Romblon": "romblon",
            "Samar": "samar",
            "Sarangani": "sarangani",
            "Siquijor": "siquijor",
            "Sorsogon": "sorsogon",
            "South Cotabato": "south-cotabato",
            "Southern Leyte": "southern-leyte",
            "Sultan Kudarat": "sultan-kudarat",
            "Sulu": "sulu",
            "Surigao del Norte": "surigao-del-norte",
            "Surigao del Sur": "surigao-del-sur",
            "Tawi-Tawi": "tawi-tawi",
            "Zambales": "zambales",
            "Zamboanga del Norte": "zamboanga-del-norte",
            "Zamboanga del Sur": "zamboanga-del-sur",
            "Zamboanga Sibugay": "zamboanga-sibugay",
        }
    
    def map_district_to_province(self, district_name: str) -> str:
        """
        Maps a district engineering office name to a province name
        
        Args:
            district_name: District Engineering Office name (e.g., "Bulacan 1st District Engineering Office")
            
        Returns:
            Province name (e.g., "Bulacan")
        """
        if not district_name:
            return "Unknown"
        
        # Check special mappings first
        for key, value in self.special_mappings.items():
            if key.lower() in district_name.lower():
                return value
        
        # Remove "District Engineering Office" suffix
        province = district_name.replace(" District Engineering Office", "")
        
        # Remove ordinal numbers (1st, 2nd, 3rd, 4th, etc.)
        province = re.sub(r'\s+\d+(st|nd|rd|th)', '', province)
        
        # Remove any remaining numbers
        province = re.sub(r'\s+\d+', '', province)
        
        # Clean up extra spaces
        province = province.strip()
        
        return province
    
    def map_province_to_geojson(self, province_name: str) -> str:
        """
        Maps a province name to its GeoJSON filename format
        
        Args:
            province_name: Province name (e.g., "Bulacan")
            
        Returns:
            GeoJSON filename format (e.g., "bulacan")
        """
        return self.province_geojson_mappings.get(province_name, province_name.lower().replace(" ", "-"))
    
    def process_districts_data(self, districts_data: List[Dict]) -> Dict[str, Dict]:
        """
        Processes district data and aggregates by province
        
        Args:
            districts_data: List of district data from flood_districts_cache.json
            
        Returns:
            Dictionary with province as key and aggregated data as value
        """
        province_aggregates = {}
        
        for district in districts_data:
            district_name = district.get('district', '')
            project_count = district.get('count', 0)
            
            province = self.map_district_to_province(district_name)
            geojson_name = self.map_province_to_geojson(province)
            
            if province not in province_aggregates:
                province_aggregates[province] = {
                    'province': province,
                    'geojson_name': geojson_name,
                    'total_projects': 0,
                    'districts': [],
                    'total_cost': 0  # Will be populated later if cost data is available
                }
            
            province_aggregates[province]['total_projects'] += project_count
            province_aggregates[province]['districts'].append({
                'district': district_name,
                'projects': project_count
            })
        
        return province_aggregates

def main():
    """Test the mapping functionality"""
    mapper = DistrictToProvinceMapper()
    
    # Test cases
    test_districts = [
        "Bulacan 1st District Engineering Office",
        "Metro Manila 1st District Engineering Office", 
        "Cebu 7th District Engineering Office",
        "Tarlac District Engineering Office",
        "North Manila District Engineering Office",
        "Davao City District Engineering Office",
        "Malabon-Navotas District Engineering Office"
    ]
    
    print("District to Province Mapping Test:")
    print("=" * 50)
    
    for district in test_districts:
        province = mapper.map_district_to_province(district)
        geojson_name = mapper.map_province_to_geojson(province)
        print(f"District: {district}")
        print(f"Province: {province}")
        print(f"GeoJSON: {geojson_name}")
        print("-" * 30)

if __name__ == "__main__":
    main()

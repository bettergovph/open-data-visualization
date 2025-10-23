#!/usr/bin/env python3
"""
Improved Province Mapping: Dynasty Database vs GeoJSON Files
Handles multiple provinces with same base names (Samar, Leyte, Cotabato, etc.)
"""

import os
import re
from typing import Dict, List, Tuple, Set

def normalize_province_name(name: str) -> str:
    """Normalize province names for comparison"""
    return name.lower().strip()

def extract_geojson_province(filename: str) -> str:
    """Extract province name from GeoJSON filename"""
    basename = os.path.basename(filename)
    name = basename.replace('.geo.json', '')
    parts = name.split('.')
    if len(parts) >= 3:
        return parts[2].replace('-', ' ')
    return name

def create_improved_province_mapping():
    """Create improved province mapping with proper handling of multiple provinces"""
    
    # Dynasty database provinces
    dynasty_provinces = [
        'ABRA', 'AGUSAN DEL NORTE', 'AGUSAN DEL SUR', 'AKLAN', 'ALBAY', 'ANTIQUE', 'APAYAO', 'AURORA',
        'BASILAN', 'BATAAN', 'BATANES', 'BATANGAS', 'BENGUET', 'BILIRAN', 'BOHOL', 'BUKIDNON',
        'BULACAN', 'CAGAYAN', 'CAMARINES NORTE', 'CAMARINES SUR', 'CAMIGUIN', 'CAPIZ', 'CATANDUANES',
        'CAVITE', 'CEBU', 'COMPOSTELA VALLEY', 'COTABATO', 'DAVAO DEL NORTE', 'DAVAO DEL SUR',
        'DAVAO OCCIDENTAL', 'DAVAO ORIENTAL', 'DINAGAT ISLANDS', 'EASTERN SAMAR', 'GUIMARAS',
        'IFUGAO', 'ILOCOS NORTE', 'ILOCOS SUR', 'ILOILO', 'ISABELA', 'KALINGA', 'LA UNION',
        'LAGUNA', 'LANAO DEL NORTE', 'LANAO DEL SUR', 'LEYTE', 'MAGUINDANAO', 'MARINDUQUE',
        'MASBATE', 'MISAMIS OCCIDENTAL', 'MISAMIS ORIENTAL', 'MOUNTAIN PROVINCE',
        'NCR, CITY OF MANILA, FIRST DISTRICT', 'NCR, FOURTH DISTRICT', 'NCR, SECOND DISTRICT',
        'NCR, THIRD DISTRICT', 'NEGROS OCCIDENTAL', 'NEGROS ORIENTAL', 'NORTHERN SAMAR',
        'NUEVA ECIJA', 'NUEVA VIZCAYA', 'OCCIDENTAL MINDORO', 'ORIENTAL MINDORO', 'PALAWAN',
        'PAMPANGA', 'PANGASINAN', 'QUEZON', 'QUIRINO', 'RIZAL', 'ROMBLON', 'SAMAR', 'SARANGANI',
        'SIQUIJOR', 'SORSOGON', 'SOUTH COTABATO', 'SOUTHERN LEYTE', 'SULTAN KUDARAT', 'SULU',
        'SURIGAO DEL NORTE', 'SURIGAO DEL SUR', 'TARLAC', 'TAWI-TAWI', 'ZAMBALES',
        'ZAMBOANGA DEL NORTE', 'ZAMBOANGA DEL SUR', 'ZAMBOANGA SIBUGAY'
    ]
    
    # GeoJSON province files
    geojson_files = [
        'ph.autonomous-region-of-muslim-mindanao-armm.basilan.any.any.geo.json',
        'ph.autonomous-region-of-muslim-mindanao-armm.lanao-del-sur.any.any.geo.json',
        'ph.autonomous-region-of-muslim-mindanao-armm.maguindanao.any.any.geo.json',
        'ph.autonomous-region-of-muslim-mindanao-armm.shariff-kabunsuan.any.any.geo.json',
        'ph.autonomous-region-of-muslim-mindanao-armm.sulu.any.any.geo.json',
        'ph.autonomous-region-of-muslim-mindanao-armm.tawi-tawi.any.any.geo.json',
        'ph.bicol-region-region-v.albay.any.any.geo.json',
        'ph.bicol-region-region-v.camarines-norte.any.any.geo.json',
        'ph.bicol-region-region-v.camarines-sur.any.any.geo.json',
        'ph.bicol-region-region-v.catanduanes.any.any.geo.json',
        'ph.bicol-region-region-v.masbate.any.any.geo.json',
        'ph.bicol-region-region-v.sorsogon.any.any.geo.json',
        'ph.cagayan-valley-region-ii.batanes.any.any.geo.json',
        'ph.cagayan-valley-region-ii.cagayan.any.any.geo.json',
        'ph.cagayan-valley-region-ii.isabela.any.any.geo.json',
        'ph.cagayan-valley-region-ii.nueva-vizcaya.any.any.geo.json',
        'ph.cagayan-valley-region-ii.quirino.any.any.geo.json',
        'ph.calabarzon-region-iv-a.batangas.any.any.geo.json',
        'ph.calabarzon-region-iv-a.cavite.any.any.geo.json',
        'ph.calabarzon-region-iv-a.laguna.any.any.geo.json',
        'ph.calabarzon-region-iv-a.quezon.any.any.geo.json',
        'ph.calabarzon-region-iv-a.rizal.any.any.geo.json',
        'ph.caraga-region-xiii.agusan-del-norte.any.any.geo.json',
        'ph.caraga-region-xiii.agusan-del-sur.any.any.geo.json',
        'ph.caraga-region-xiii.dinagat-islands.any.any.geo.json',
        'ph.caraga-region-xiii.surigao-del-norte.any.any.geo.json',
        'ph.caraga-region-xiii.surigao-del-sur.any.any.geo.json',
        'ph.central-luzon-region-iii.aurora.any.any.geo.json',
        'ph.central-luzon-region-iii.bataan.any.any.geo.json',
        'ph.central-luzon-region-iii.bulacan.any.any.geo.json',
        'ph.central-luzon-region-iii.nueva-ecija.any.any.geo.json',
        'ph.central-luzon-region-iii.pampanga.any.any.geo.json',
        'ph.central-luzon-region-iii.tarlac.any.any.geo.json',
        'ph.central-luzon-region-iii.zambales.any.any.geo.json',
        'ph.central-visayas-region-vii.bohol.any.any.geo.json',
        'ph.central-visayas-region-vii.cebu.any.any.geo.json',
        'ph.central-visayas-region-vii.negros-oriental.any.any.geo.json',
        'ph.central-visayas-region-vii.siquijor.any.any.geo.json',
        'ph.cordillera-administrative-region-car.abra.any.any.geo.json',
        'ph.cordillera-administrative-region-car.apayao.any.any.geo.json',
        'ph.cordillera-administrative-region-car.benguet.any.any.geo.json',
        'ph.cordillera-administrative-region-car.ifugao.any.any.geo.json',
        'ph.cordillera-administrative-region-car.kalinga.any.any.geo.json',
        'ph.cordillera-administrative-region-car.mountain-province.any.any.geo.json',
        'ph.davao-region-region-xi.compostela-valley.any.any.geo.json',
        'ph.davao-region-region-xi.davao-del-norte.any.any.geo.json',
        'ph.davao-region-region-xi.davao-del-sur.any.any.geo.json',
        'ph.davao-region-region-xi.davao-oriental.any.any.geo.json',
        'ph.eastern-visayas-region-viii.biliran.any.any.geo.json',
        'ph.eastern-visayas-region-viii.eastern-samar.any.any.geo.json',
        'ph.eastern-visayas-region-viii.leyte.any.any.geo.json',
        'ph.eastern-visayas-region-viii.northern-samar.any.any.geo.json',
        'ph.eastern-visayas-region-viii.samar.any.any.geo.json',
        'ph.eastern-visayas-region-viii.southern-leyte.any.any.geo.json',
        'ph.ilocos-region-region-i.ilocos-norte.any.any.geo.json',
        'ph.ilocos-region-region-i.ilocos-sur.any.any.geo.json',
        'ph.ilocos-region-region-i.la-union.any.any.geo.json',
        'ph.ilocos-region-region-i.pangasinan.any.any.geo.json',
        'ph.mimaropa-region-iv-b.marinduque.any.any.geo.json',
        'ph.mimaropa-region-iv-b.occidental-mindoro.any.any.geo.json',
        'ph.mimaropa-region-iv-b.oriental-mindoro.any.any.geo.json',
        'ph.mimaropa-region-iv-b.palawan.any.any.geo.json',
        'ph.mimaropa-region-iv-b.romblon.any.any.geo.json',
        'ph.national-capital-region.metropolitan-manila.any.any.geo.json',
        'ph.northern-mindanao-region-x.bukidnon.any.any.geo.json',
        'ph.northern-mindanao-region-x.camiguin.any.any.geo.json',
        'ph.northern-mindanao-region-x.lanao-del-norte.any.any.geo.json',
        'ph.northern-mindanao-region-x.misamis-occidental.any.any.geo.json',
        'ph.northern-mindanao-region-x.misamis-oriental.any.any.geo.json',
        'ph.soccsksargen-region-xii.north-cotabato.any.any.geo.json',
        'ph.soccsksargen-region-xii.sarangani.any.any.geo.json',
        'ph.soccsksargen-region-xii.south-cotabato.any.any.geo.json',
        'ph.soccsksargen-region-xii.sultan-kudarat.any.any.geo.json',
        'ph.western-visayas-region-vi.aklan.any.any.geo.json',
        'ph.western-visayas-region-vi.antique.any.any.geo.json',
        'ph.western-visayas-region-vi.capiz.any.any.geo.json',
        'ph.western-visayas-region-vi.guimaras.any.any.geo.json',
        'ph.western-visayas-region-vi.iloilo.any.any.geo.json',
        'ph.western-visayas-region-vi.negros-occidental.any.any.geo.json',
        'ph.zamboanga-peninsula-region-ix.zamboanga-del-norte.any.any.geo.json',
        'ph.zamboanga-peninsula-region-ix.zamboanga-del-sur.any.any.geo.json',
        'ph.zamboanga-peninsula-region-ix.zamboanga-sibugay.any.any.geo.json'
    ]
    
    # Extract province names from GeoJSON files
    geojson_provinces = []
    for filename in geojson_files:
        province = extract_geojson_province(filename)
        geojson_provinces.append((province, filename))
    
    # Manual mapping for complex cases
    manual_mappings = {
        # NCR districts all map to Metropolitan Manila
        'NCR, CITY OF MANILA, FIRST DISTRICT': 'metropolitan manila',
        'NCR, FOURTH DISTRICT': 'metropolitan manila',
        'NCR, SECOND DISTRICT': 'metropolitan manila',
        'NCR, THIRD DISTRICT': 'metropolitan manila',
        
        # Samar provinces - exact matches
        'NORTHERN SAMAR': 'northern samar',
        'EASTERN SAMAR': 'eastern samar',
        'SAMAR': 'samar',  # This is Western Samar
        
        # Leyte provinces - exact matches
        'LEYTE': 'leyte',
        'SOUTHERN LEYTE': 'southern leyte',
        
        # Cotabato provinces - exact matches
        'COTABATO': 'north cotabato',  # Dynasty "COTABATO" = GeoJSON "north cotabato"
        'SOUTH COTABATO': 'south cotabato',
        
        # Davao provinces - exact matches
        'DAVAO DEL NORTE': 'davao del norte',
        'DAVAO DEL SUR': 'davao del sur',
        'DAVAO ORIENTAL': 'davao oriental',
        'DAVAO OCCIDENTAL': 'davao occidental',  # Missing from GeoJSON
        
        # Tawi-Tawi case sensitivity
        'TAWI-TAWI': 'tawi tawi',
    }
    
    # Create mapping
    mapping = {}
    matched = []
    unmatched_dynasty = []
    unmatched_geojson = []
    
    # Try to match each dynasty province
    for dynasty_province in dynasty_provinces:
        normalized_dynasty = normalize_province_name(dynasty_province)
        found_match = False
        
        # Check manual mappings first
        if dynasty_province in manual_mappings:
            target_geojson = manual_mappings[dynasty_province]
            for geojson_province, filename in geojson_provinces:
                if normalize_province_name(geojson_province) == normalize_province_name(target_geojson):
                    mapping[dynasty_province] = {
                        'geojson_file': filename,
                        'geojson_province': geojson_province,
                        'match_type': 'manual'
                    }
                    matched.append((dynasty_province, geojson_province, filename))
                    found_match = True
                    break
        else:
            # Try automatic matching
            for geojson_province, filename in geojson_provinces:
                normalized_geojson = normalize_province_name(geojson_province)
                
                if (normalized_dynasty == normalized_geojson or 
                    normalized_dynasty in normalized_geojson or 
                    normalized_geojson in normalized_dynasty):
                    mapping[dynasty_province] = {
                        'geojson_file': filename,
                        'geojson_province': geojson_province,
                        'match_type': 'exact' if normalized_dynasty == normalized_geojson else 'partial'
                    }
                    matched.append((dynasty_province, geojson_province, filename))
                    found_match = True
                    break
        
        if not found_match:
            unmatched_dynasty.append(dynasty_province)
    
    # Find unmatched GeoJSON files
    matched_geojson_files = {match[2] for match in matched}
    for geojson_province, filename in geojson_provinces:
        if filename not in matched_geojson_files:
            unmatched_geojson.append((geojson_province, filename))
    
    return {
        'mapping': mapping,
        'matched': matched,
        'unmatched_dynasty': unmatched_dynasty,
        'unmatched_geojson': unmatched_geojson,
        'stats': {
            'total_dynasty': len(dynasty_provinces),
            'total_geojson': len(geojson_files),
            'matched_count': len(matched),
            'unmatched_dynasty_count': len(unmatched_dynasty),
            'unmatched_geojson_count': len(unmatched_geojson)
        }
    }

def generate_improved_report():
    """Generate improved mapping report"""
    result = create_improved_province_mapping()
    
    print("=" * 80)
    print("🏛️ IMPROVED PROVINCE MAPPING REPORT: Dynasty Database vs GeoJSON Files")
    print("=" * 80)
    print()
    
    # Statistics
    stats = result['stats']
    print("📊 SUMMARY STATISTICS:")
    print(f"   • Dynasty Database Provinces: {stats['total_dynasty']}")
    print(f"   • GeoJSON Files Available: {stats['total_geojson']}")
    print(f"   • Successfully Mapped: {stats['matched_count']}")
    print(f"   • Dynasty Provinces Unmapped: {stats['unmatched_dynasty_count']}")
    print(f"   • GeoJSON Files Unused: {stats['unmatched_geojson_count']}")
    print(f"   • Mapping Success Rate: {(stats['matched_count']/stats['total_dynasty']*100):.1f}%")
    print()
    
    # Successfully matched provinces
    print("✅ SUCCESSFULLY MAPPED PROVINCES:")
    print("-" * 50)
    for i, (dynasty, geojson, filename) in enumerate(result['matched'], 1):
        match_type = result['mapping'][dynasty]['match_type']
        print(f"{i:2d}. {dynasty}")
        print(f"    → {geojson} ({match_type} match)")
        print(f"    → {filename}")
        print()
    
    # Unmatched dynasty provinces
    if result['unmatched_dynasty']:
        print("❌ DYNASTY PROVINCES WITHOUT GEOJSON:")
        print("-" * 50)
        for i, province in enumerate(result['unmatched_dynasty'], 1):
            print(f"{i:2d}. {province}")
        print()
    
    # Unmatched GeoJSON files
    if result['unmatched_geojson']:
        print("🗺️ GEOJSON FILES WITHOUT DYNASTY DATA:")
        print("-" * 50)
        for i, (province, filename) in enumerate(result['unmatched_geojson'], 1):
            print(f"{i:2d}. {province} → {filename}")
        print()
    
    # Special cases analysis
    print("🔍 SPECIAL CASES ANALYSIS:")
    print("-" * 50)
    
    # Check Samar provinces
    samar_mappings = [m for m in result['matched'] if 'SAMAR' in m[0]]
    print(f"Samar Provinces: {len(samar_mappings)} mapped")
    for dynasty, geojson, filename in samar_mappings:
        print(f"  • {dynasty} → {geojson}")
    
    # Check Leyte provinces  
    leyte_mappings = [m for m in result['matched'] if 'LEYTE' in m[0]]
    print(f"Leyte Provinces: {len(leyte_mappings)} mapped")
    for dynasty, geojson, filename in leyte_mappings:
        print(f"  • {dynasty} → {geojson}")
    
    # Check Cotabato provinces
    cotabato_mappings = [m for m in result['matched'] if 'COTABATO' in m[0]]
    print(f"Cotabato Provinces: {len(cotabato_mappings)} mapped")
    for dynasty, geojson, filename in cotabato_mappings:
        print(f"  • {dynasty} → {geojson}")
    
    print()
    
    # Recommendations
    print("💡 RECOMMENDATIONS:")
    print("-" * 50)
    if stats['matched_count'] >= 80:
        print("✅ EXCELLENT: Most provinces can be mapped successfully!")
        print("   The mapping system should work well for the dynasty visualization.")
    elif stats['matched_count'] >= 60:
        print("⚠️  GOOD: Most provinces can be mapped, but some manual fixes needed.")
        print("   Consider adding manual mappings for unmatched provinces.")
    else:
        print("❌ POOR: Many provinces cannot be mapped automatically.")
        print("   Significant manual work required to create proper mappings.")
    
    print()
    print("🔧 NEXT STEPS:")
    print("   1. Review unmatched provinces and create manual mappings if needed")
    print("   2. Test the mapping with actual dynasty data")
    print("   3. Implement fallback handling for unmapped provinces")
    print("   4. Consider using fuzzy matching for better coverage")
    
    return result

if __name__ == "__main__":
    generate_improved_report()

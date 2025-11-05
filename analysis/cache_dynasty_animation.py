#!/usr/bin/env python3
"""
Cache Dynasty Animation Data Script

This script pre-generates all the data needed for the dynasty animation tab
and saves it as JSON files for fast loading.

Data cached:
- Province-specific top families for each election year (2004-2025)
- Family member counts per province per year
- Flag data mapping
- Province centroids for map positioning
"""

import asyncio
import asyncpg
import json
import os
from datetime import datetime
import sys
from pathlib import Path

def load_env_from_dotenv():
    """Load environment variables from .env file"""
    root = Path(__file__).resolve().parent
    env_path = root / '.env'
    if env_path.exists():
        for line in env_path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v

# Load environment variables
load_env_from_dotenv()

# Database connection settings
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'user': os.getenv('POSTGRES_USER', 'budget_admin'),
    'password': os.getenv('POSTGRES_PASSWORD', ''),
    'database': os.getenv('POSTGRES_DB_DYNASTY', 'dynasty')
}

# Election years (3-year gaps)
ELECTION_YEARS = [2004, 2007, 2010, 2013, 2016, 2019, 2022, 2025]

# Output directory
OUTPUT_DIR = 'static/data/dynasty_animation_cache'

async def get_db_connection():
    """Get database connection"""
    return await asyncpg.connect(**DB_CONFIG)

async def get_provinces():
    """Get all provinces from the dynasty database"""
    conn = await get_db_connection()
    try:
        query = """
        SELECT DISTINCT province 
        FROM political_dynasties 
        WHERE province IS NOT NULL AND province != ''
        ORDER BY province
        """
        rows = await conn.fetch(query)
        return [row['province'] for row in rows]
    finally:
        await conn.close()

async def get_top_families_by_province_year(province, year):
    """Get top families for a specific province and year"""
    conn = await get_db_connection()
    try:
        query = """
        SELECT 
            last_name,
            COUNT(*) as member_count,
            province
        FROM political_dynasties 
        WHERE province = $1 
        AND year = $2 
        AND fat = 1
        AND last_name IS NOT NULL 
        AND last_name != ''
        GROUP BY last_name, province
        ORDER BY member_count DESC
        LIMIT 10
        """
        rows = await conn.fetch(query, province, year)
        return [
            {
                'surname': row['last_name'],
                'province': row['province'],
                'dynasty_count': row['member_count']
            }
            for row in rows
        ]
    finally:
        await conn.close()

async def get_province_centroids():
    """Get province centroids from GeoJSON data"""
    try:
        with open('static/data/philippines-provinces.json', 'r') as f:
            geojson = json.load(f)
        
        centroids = {}
        for feature in geojson.get('features', []):
            province_name = (feature.get('properties', {}).get('name') or 
                           feature.get('properties', {}).get('NAME_1') or 
                           feature.get('properties', {}).get('PROVINCE', ''))
            
            if not province_name:
                continue
                
            # Calculate centroid
            coords = []
            if feature.get('geometry', {}).get('type') == 'MultiPolygon':
                for poly in feature['geometry']['coordinates']:
                    for ring in poly:
                        for coord in ring:
                            coords.append([coord[1], coord[0]])  # lat, lng
            elif feature.get('geometry', {}).get('type') == 'Polygon':
                for ring in feature['geometry']['coordinates']:
                    for coord in ring:
                        coords.append([coord[1], coord[0]])  # lat, lng
            
            if coords:
                lat = sum(c[0] for c in coords) / len(coords)
                lng = sum(c[1] for c in coords) / len(coords)
                centroids[province_name.upper()] = [lat, lng]
        
        return centroids
    except FileNotFoundError:
        print("⚠️ GeoJSON file not found, using default centroids")
        return {}

async def load_flag_data():
    """Load existing flag data if available"""
    try:
        with open('static/data/dynasty_flags_cache.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("⚠️ Flag data not found, using empty flags")
        return {'dynasties': {}}

async def cache_dynasty_animation_data():
    """Main function to cache all dynasty animation data"""
    print("🚀 Starting dynasty animation data caching...")
    
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Get provinces
    print("📋 Loading provinces...")
    provinces = await get_provinces()
    print(f"✅ Found {len(provinces)} provinces")
    
    # Get province centroids
    print("🗺️ Loading province centroids...")
    centroids = await get_province_centroids()
    print(f"✅ Loaded {len(centroids)} province centroids")
    
    # Load flag data
    print("🏴 Loading flag data...")
    flag_data = await load_flag_data()
    print(f"✅ Loaded flag data for {len(flag_data.get('dynasties', {}))} dynasties")
    
    # Cache data for each year
    all_years_data = {}
    
    for year in ELECTION_YEARS:
        print(f"📅 Processing year {year}...")
        year_data = {
            'year': year,
            'provinces': {},
            'top_families': [],
            'total_families': 0
        }
        
        all_families = []
        
        for province in provinces:
            print(f"  📍 Processing {province}...")
            families = await get_top_families_by_province_year(province, year)
            
            if families:
                year_data['provinces'][province] = {
                    'families': families,
                    'top_family': families[0] if families else None,
                    'centroid': centroids.get(province.upper(), [12.8797, 121.7740])
                }
                all_families.extend(families)
        
        # Sort all families by dynasty count
        all_families.sort(key=lambda x: x['dynasty_count'], reverse=True)
        year_data['top_families'] = all_families[:100]  # Top 100
        year_data['total_families'] = len(all_families)
        
        all_years_data[year] = year_data
        print(f"✅ Year {year}: {len(all_families)} families across {len(year_data['provinces'])} provinces")
    
    # Save year-specific data
    for year, data in all_years_data.items():
        filename = f"{OUTPUT_DIR}/dynasty_animation_{year}.json"
        with open(filename, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"💾 Saved {filename}")
    
    # Save master index
    master_data = {
        'cache_info': {
            'generated_at': datetime.now().isoformat(),
            'election_years': ELECTION_YEARS,
            'total_provinces': len(provinces),
            'total_years': len(ELECTION_YEARS)
        },
        'years': list(ELECTION_YEARS),
        'provinces': provinces,
        'centroids': centroids,
        'flag_data': flag_data
    }
    
    master_filename = f"{OUTPUT_DIR}/dynasty_animation_master.json"
    with open(master_filename, 'w') as f:
        json.dump(master_data, f, indent=2)
    print(f"💾 Saved master index: {master_filename}")
    
    # Summary
    total_families = sum(data['total_families'] for data in all_years_data.values())
    print(f"\n🎉 Dynasty animation caching complete!")
    print(f"📊 Total families processed: {total_families}")
    print(f"📁 Files created: {len(ELECTION_YEARS) + 1}")
    print(f"📂 Output directory: {OUTPUT_DIR}")

async def main():
    """Main entry point"""
    try:
        await cache_dynasty_animation_data()
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())

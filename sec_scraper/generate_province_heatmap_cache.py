#!/usr/bin/env python3
"""
Generate Province Heat Map Cache
Creates cached JSON data for the province-based heat map visualization
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Any

# Add the parent directory to the path to import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flood_client import FloodControlClient
from sec_scraper.district_to_province_mapper import DistrictToProvinceMapper

class ProvinceHeatMapCacheGenerator:
    """Generates cached province heat map data"""
    
    def __init__(self):
        self.client = FloodControlClient()
        self.mapper = DistrictToProvinceMapper()
    
    async def generate_cache_data(self) -> Dict[str, Any]:
        """Generate province heat map cache data"""
        print("🗺️ Generating province heat map cache...")
        
        try:
            # Fetch all flood control projects
            print("📊 Fetching flood control projects from MeiliSearch...")
            projects, metadata = await self.client.search_projects(limit=10000)  # Get all projects
            print(f"📊 Found {len(projects)} projects")
            
            # Count projects by district
            district_counts = {}
            for project in projects:
                district = project.DistrictEngineeringOffice or "Unknown District"
                district_counts[district] = district_counts.get(district, 0) + 1
            
            print(f"📊 Found {len(district_counts)} districts")
            
            # Convert to list format for processing
            districts_data = [
                {"district": district, "count": count}
                for district, count in district_counts.items()
            ]
            
            # Process districts data to get province aggregates
            province_aggregates = self.mapper.process_districts_data(districts_data)
            
            # Convert to list format for API response
            provinces_list = []
            for province_name, province_data in province_aggregates.items():
                provinces_list.append({
                    "province": province_name,
                    "geojson_name": province_data["geojson_name"],
                    "total_projects": province_data["total_projects"],
                    "districts_count": len(province_data["districts"]),
                    "districts": province_data["districts"]
                })
            
            # Sort by total projects descending
            provinces_list.sort(key=lambda x: x["total_projects"], reverse=True)
            
            # Create cache data
            cache_data = {
                "success": True,
                "provinces": provinces_list,
                "total_provinces": len(provinces_list),
                "total_projects": sum(p["total_projects"] for p in provinces_list),
                "generated_at": datetime.now().isoformat(),
                "description": "Province-level aggregation of flood control projects for heat map visualization",
                "cache_version": "1.0"
            }
            
            print(f"✅ Generated province heat map cache:")
            print(f"   📊 Total provinces: {cache_data['total_provinces']}")
            print(f"   📊 Total projects: {cache_data['total_projects']}")
            print(f"   🏆 Top province: {provinces_list[0]['province']} ({provinces_list[0]['total_projects']} projects)")
            
            return cache_data
            
        except Exception as e:
            print(f"❌ Error generating province heat map cache: {e}")
            return {
                "success": False,
                "error": str(e),
                "generated_at": datetime.now().isoformat()
            }
    
    async def save_cache(self, cache_data: Dict[str, Any], output_file: str):
        """Save cache data to JSON file"""
        try:
            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            
            # Write cache data
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            print(f"💾 Province heat map cache saved to: {output_file}")
            
        except Exception as e:
            print(f"❌ Error saving province heat map cache: {e}")

async def main():
    """Main function to generate province heat map cache"""
    generator = ProvinceHeatMapCacheGenerator()
    
    # Generate cache data
    cache_data = await generator.generate_cache_data()
    
    if cache_data.get("success"):
        # Save to static data directory
        output_file = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "static", "data", "province_heatmap_cache.json"
        )
        
        await generator.save_cache(cache_data, output_file)
        print("✅ Province heat map cache generation completed successfully!")
    else:
        print(f"❌ Failed to generate province heat map cache: {cache_data.get('error')}")
        sys.exit(1)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

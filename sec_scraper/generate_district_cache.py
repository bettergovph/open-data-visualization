#!/usr/bin/env python3
"""
Generate cached JSON file for flood control district statistics.
This script fetches district data from MeiliSearch and creates a cached JSON file
for improved performance of the district ranking chart.
"""

import os
import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from flood_client import FloodControlClient
except ImportError:
    print("❌ Error: Could not import flood_client. Make sure you're running from the project root.")
    sys.exit(1)

class DistrictCacheGenerator:
    """Generate cached district statistics for flood control projects."""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.static_data_dir = self.project_root / "static" / "data"
        self.output_file = self.static_data_dir / "flood_districts_cache.json"
        
        # Ensure static/data directory exists
        self.static_data_dir.mkdir(parents=True, exist_ok=True)
    
    async def fetch_district_data(self) -> Dict[str, Any]:
        """Fetch district data from MeiliSearch."""
        try:
            print("🔍 Fetching district data from MeiliSearch...")
            client = FloodControlClient()
            
            # Get all projects to count by district
            projects, metadata = await client.search_projects(query="", limit=10000, offset=0)
            
            print(f"📊 Found {len(projects)} projects")
            
            # Count projects by DistrictEngineeringOffice
            districts_data = {}
            for project in projects:
                district = project.DistrictEngineeringOffice or "Unknown District"
                districts_data[district] = districts_data.get(district, 0) + 1
            
            # Convert to array format for consistency
            districts_array = [
                {"district": district, "count": count}
                for district, count in districts_data.items()
            ]
            
            # Sort by count descending
            districts_array.sort(key=lambda x: x["count"], reverse=True)
            
            # Create the final data structure
            result = {
                "success": True,
                "generated_at": datetime.now().isoformat(),
                "total_districts": len(districts_array),
                "total_projects": sum(count for _, count in districts_data.items()),
                "districts": districts_array,
                "metadata": {
                    "source": "MeiliSearch flood control data",
                    "field": "DistrictEngineeringOffice",
                    "description": "District Engineering Office project counts for flood control projects",
                    "last_updated": datetime.now().isoformat()
                }
            }
            
            print(f"✅ Processed {len(districts_array)} districts")
            print(f"🏆 Top 5 districts:")
            for i, district in enumerate(districts_array[:5], 1):
                print(f"   {i}. {district['district']}: {district['count']} projects")
            
            return result
            
        except Exception as e:
            print(f"❌ Error fetching district data: {e}")
            return {
                "success": False,
                "error": str(e),
                "generated_at": datetime.now().isoformat()
            }
    
    async def generate_cache(self) -> bool:
        """Generate the district cache JSON file."""
        print("🏆 Generating Flood Control District Cache")
        print("=" * 50)
        
        # Fetch district data
        district_data = await self.fetch_district_data()
        
        if not district_data.get("success"):
            print(f"❌ Failed to fetch district data: {district_data.get('error', 'Unknown error')}")
            return False
        
        # Write to JSON file
        try:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(district_data, f, indent=2, ensure_ascii=False)
            
            print(f"✅ District cache generated successfully!")
            print(f"📁 Output file: {self.output_file}")
            print(f"📊 Total districts: {district_data['total_districts']}")
            print(f"📊 Total projects: {district_data['total_projects']}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error writing cache file: {e}")
            return False
    
    def print_cache_info(self):
        """Print information about the generated cache."""
        if self.output_file.exists():
            try:
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                print(f"\n📋 Cache Information:")
                print(f"   File: {self.output_file}")
                print(f"   Generated: {data.get('generated_at', 'Unknown')}")
                print(f"   Total Districts: {data.get('total_districts', 0)}")
                print(f"   Total Projects: {data.get('total_projects', 0)}")
                
                if 'districts' in data and data['districts']:
                    print(f"   Top District: {data['districts'][0]['district']} ({data['districts'][0]['count']} projects)")
                
            except Exception as e:
                print(f"❌ Error reading cache info: {e}")

async def main():
    """Main function to generate district cache."""
    generator = DistrictCacheGenerator()
    
    success = await generator.generate_cache()
    
    if success:
        generator.print_cache_info()
        print("\n🎉 District cache generation completed successfully!")
        return 0
    else:
        print("\n❌ District cache generation failed!")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

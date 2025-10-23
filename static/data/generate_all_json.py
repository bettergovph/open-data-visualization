#!/usr/bin/env python3
"""
Master script to generate all JSON files in static/data/ directory.
This is the single entry point for updating all cached JSON data.

CACHING STRATEGY:
- Complex tables and visuals are candidates for JSON caching
- Heavy database queries, aggregations, and transformations should be preprocessed
- See JSON_CACHING_STRATEGY.md for detailed guidelines
"""

import os
import sys
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime

# Future MongoDB integration
try:
    from analysis.mongodb_cache_manager import MongoDBCacheManager
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    print("⚠️ MongoDB cache manager not available (optional dependency)")
from typing import Dict, List, Any, Tuple

class JSONGenerator:
    """Master class to coordinate all JSON file generation."""
    
    def __init__(self, mongodb_connection_string: str = None):
        """
        Initialize the JSON generator with project paths.
        
        Args:
            mongodb_connection_string: Optional MongoDB connection for cache storage
        """
        self.project_root = Path(__file__).parent.parent.parent
        self.static_data_dir = self.project_root / "static" / "data"
        self.scripts_dir = self.project_root / "sec_scraper"
        self.utils_dir = self.project_root / "utils"
        self.analysis_dir = self.project_root / "analysis"
        
        # Ensure static/data directory exists
        self.static_data_dir.mkdir(parents=True, exist_ok=True)
        
        # MongoDB cache manager (future implementation)
        self.mongodb_cache = None
        if MONGODB_AVAILABLE and mongodb_connection_string:
            try:
                self.mongodb_cache = MongoDBCacheManager(mongodb_connection_string)
                print("✅ MongoDB cache manager initialized")
            except Exception as e:
                print(f"⚠️ MongoDB cache not available: {e}")
                self.mongodb_cache = None
        
        # JSON file inventory with their generators
        # Categorized by complexity for caching strategy
        self.json_generators = {
            # Existing Scripts (Created Before Today)
            'contractor_sec_mapping.json': {
                'script': 'sec_scraper/sec_complete_automation.py',
                'description': 'Contractor SEC mapping data',
                'category': 'sec_data',
                'dependencies': ['SEC database', 'Flood data']
            },
            
            # New Scripts (Created Today) - For New JSON Files
            'sec_contractors_database.json': {
                'script': 'sec_scraper/generate_sec_json.py',
                'description': 'SEC contractors database from PostgreSQL',
                'category': 'sec_data',
                'dependencies': ['PostgreSQL SEC database']
            },
            'excluded_flood_contractors_cache.json': {
                'script': 'sec_scraper/generate_contractors_cache.py',
                'description': 'Cached excluded flood contractors for performance',
                'category': 'cache_data',
                'dependencies': ['PhilGEPS database']
            },
            'top_contractors_cache.json': {
                'script': 'sec_scraper/generate_contractors_dashboard_cache.py',
                'description': 'Top contractors cache',
                'category': 'cache_data',
                'dependencies': ['Database queries']
            },
            'contractors_venn_cache.json': {
                'script': 'sec_scraper/generate_contractors_dashboard_cache.py',
                'description': 'Contractors Venn diagram cache',
                'category': 'cache_data',
                'dependencies': ['Database queries']
            },
            
            # Summary Statistics
            'flood_summary.json': {
                'script': 'utils/generate_summary_stats.py',
                'description': 'Flood control projects summary statistics',
                'category': 'summary_data',
                'dependencies': ['Flood API endpoint']
            },
            'dime_summary.json': {
                'script': 'utils/generate_summary_stats.py',
                'description': 'DIME projects summary statistics',
                'category': 'summary_data',
                'dependencies': ['DIME API endpoint']
            },
            'budget_summary.json': {
                'script': 'utils/generate_summary_stats.py',
                'description': 'Budget analysis summary statistics',
                'category': 'summary_data',
                'dependencies': ['Budget API endpoint']
            },
            'nep_summary.json': {
                'script': 'utils/generate_summary_stats.py',
                'description': 'NEP summary statistics',
                'category': 'summary_data',
                'dependencies': ['NEP API endpoint']
            },
            
            # Analysis Results
            'flood_same_amount_proximity_results.json': {
                'script': 'analysis/flood_same_amount_proximity_analysis.py',
                'description': 'Flood projects proximity analysis results',
                'category': 'analysis_data',
                'dependencies': ['Flood control data']
            },
            
            # Geographic Data (usually static, but may need updates)
            'philippines-regions.json': {
                'script': 'Static file (GeoJSON)',
                'description': 'Philippines regions GeoJSON data',
                'category': 'geographic_data',
                'dependencies': ['External GeoJSON source']
            },
            'region-mapping.json': {
                'script': 'Static file (manual update)',
                'description': 'Region mapping data',
                'category': 'geographic_data',
                'dependencies': ['Manual updates']
            },
            
            # Main Data Files (generated by API endpoints)
            'flood_control_data.json': {
                'script': 'API endpoint (generated on-demand)',
                'description': 'Main flood control projects data',
                'category': 'flood_data',
                'dependencies': ['Database queries']
            },
            'flood_baseline_pattern.json': {
                'script': 'API endpoint (generated on-demand)',
                'description': 'Flood baseline patterns',
                'category': 'flood_data',
                'dependencies': ['Database queries']
            },
            
            # Correlation Data
            'flood_dime_contractor_correlation.json': {
                'script': 'analysis/generate_flood_dime_correlation.py',
                'description': 'Flood-DIME contractor correlation',
                'category': 'correlation_data',
                'dependencies': ['Flood data', 'DIME data']
            },
            'flood_dime_contractor_correlation_2020.json': {
                'script': 'analysis/generate_flood_dime_correlation.py',
                'description': '2020 Flood-DIME correlation',
                'category': 'correlation_data',
                'dependencies': ['Flood data', 'DIME data']
            },
            'flood_dime_contractor_correlation_2021.json': {
                'script': 'analysis/generate_flood_dime_correlation.py',
                'description': '2021 Flood-DIME correlation',
                'category': 'correlation_data',
                'dependencies': ['Flood data', 'DIME data']
            },
            'flood_dime_contractor_correlation_2022.json': {
                'script': 'analysis/generate_flood_dime_correlation.py',
                'description': '2022 Flood-DIME correlation',
                'category': 'correlation_data',
                'dependencies': ['Flood data', 'DIME data']
            },
            'flood_dime_contractor_correlation_2023.json': {
                'script': 'analysis/generate_flood_dime_correlation.py',
                'description': '2023 Flood-DIME correlation',
                'category': 'correlation_data',
                'dependencies': ['Flood data', 'DIME data']
            },
            'flood_dime_contractor_correlation_2024.json': {
                'script': 'analysis/generate_flood_dime_correlation.py',
                'description': '2024 Flood-DIME correlation',
                'category': 'correlation_data',
                'dependencies': ['Flood data', 'DIME data']
            },
            'flood_dime_contractor_correlation_2025.json': {
                'script': 'analysis/generate_flood_dime_correlation.py',
                'description': '2025 Flood-DIME correlation',
                'category': 'correlation_data',
                'dependencies': ['Flood data', 'DIME data']
            },
            'flood_dime_contractor_correlation_all_years.json': {
                'script': 'analysis/generate_flood_dime_correlation.py',
                'description': 'All years Flood-DIME correlation',
                'category': 'correlation_data',
                'dependencies': ['Flood data', 'DIME data']
            },
            'barangay_contractors.json': {
                'script': 'analysis/generate_barangay_contractors.py',
                'description': 'Preprocessed barangay contractors with MeiliSearch connections',
                'category': 'processed_data',
                'dependencies': ['DIME data', 'MeiliSearch', 'Fastest projects data']
            },
            
            # NEP Data
            'nep_2026_red_flag.json': {
                'script': 'analysis/generate_nep_2026_red_flag.py',
                'description': 'NEP 2026 red flag analysis for road infrastructure',
                'category': 'nep_data',
                'dependencies': ['NEP database']
            },
            'nep_2026_infrastructure_categories.json': {
                'script': 'analysis/generate_nep_2026_infrastructure_categories.py',
                'description': 'NEP 2026 infrastructure categories analysis',
                'category': 'nep_data',
                'dependencies': ['NEP database']
            },
            'nep_2026_overall_analysis.json': {
                'script': 'analysis/generate_nep_2026_overall_analysis.py',
                'description': 'NEP 2026 overall analysis and statistics',
                'category': 'nep_data',
                'dependencies': ['NEP database']
            },
            
            # DIME Data
            'dime_stats.json': {
                'script': 'API endpoint (generated on-demand)',
                'description': 'DIME database statistics',
                'category': 'dime_data',
                'dependencies': ['DIME database']
            },
            'fastest_dime_projects.json': {
                'script': 'sec_scraper/generate_fastest_dime_projects.py',
                'description': 'Fastest DIME projects analysis',
                'category': 'dime_data',
                'dependencies': ['DIME database']
            },
            'contractor_stats.json': {
                'script': 'sec_scraper/generate_contractor_stats.py',
                'description': 'Contractor statistics for /contractors page',
                'category': 'sec_data',
                'dependencies': ['PostgreSQL SEC database']
            },
            'contractor_standard_deviation.json': {
                'script': 'analysis/generate_contractor_standard_deviation.py',
                'description': 'Contractor project count standard deviation analysis',
                'category': 'analysis_data',
                'dependencies': ['Contractor project data']
            }
        }
    
    def print_inventory(self):
        """Print comprehensive inventory of all JSON files and their generators."""
        print("📊 JSON Files Inventory for static/data/")
        print("=" * 60)
        
        categories = {}
        for filename, info in self.json_generators.items():
            category = info['category']
            if category not in categories:
                categories[category] = []
            categories[category].append((filename, info))
        
        for category, files in categories.items():
            print(f"\n📁 {category.replace('_', ' ').title()}")
            print("-" * 40)
            for filename, info in files:
                print(f"  📄 {filename}")
                print(f"     Script: {info['script']}")
                print(f"     Description: {info['description']}")
                print(f"     Dependencies: {', '.join(info['dependencies'])}")
                print()
    
    async def run_script(self, script_path: str, description: str) -> Tuple[bool, str]:
        """Run a Python script and return success status and output."""
        try:
            print(f"🔄 Running {description}...")
            print(f"   Script: {script_path}")
            
            # Change to project root directory
            original_cwd = os.getcwd()
            os.chdir(self.project_root)
            
            try:
                # Run the script
                result = subprocess.run(
                    [sys.executable, script_path],
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )
                
                if result.returncode == 0:
                    print(f"✅ {description} completed successfully")
                    return True, result.stdout
                else:
                    print(f"❌ {description} failed with return code {result.returncode}")
                    print(f"   Error: {result.stderr}")
                    return False, result.stderr
                    
            finally:
                os.chdir(original_cwd)
                
        except subprocess.TimeoutExpired:
            print(f"⏰ {description} timed out after 5 minutes")
            return False, "Timeout"
        except Exception as e:
            print(f"❌ Error running {description}: {e}")
            return False, str(e)
    
    async def generate_sec_data(self):
        """Generate SEC-related JSON files."""
        print("\n🏛️ Generating SEC Data...")
        print("=" * 40)
        
        # Generate contractor SEC mapping (existing script)
        success1, output1 = await self.run_script(
            'sec_scraper/sec_complete_automation.py',
            'Contractor SEC Mapping'
        )
        
        # Generate SEC contractors database (new script for new JSON)
        success2, output2 = await self.run_script(
            'sec_scraper/generate_sec_json.py',
            'SEC Contractors Database'
        )
        
        # Generate contractor statistics (new script for new JSON)
        success3, output3 = await self.run_script(
            'sec_scraper/generate_contractor_stats.py',
            'Contractor Statistics'
        )
        
        return success1 and success2 and success3
    
    async def generate_summary_stats(self):
        """Generate summary statistics JSON files."""
        print("\n📊 Generating Summary Statistics...")
        print("=" * 40)
        
        success, output = await self.run_script(
            'utils/generate_summary_stats.py',
            'Summary Statistics (Flood, DIME, Budget, NEP)'
        )
        
        return success
    
    async def generate_analysis_data(self):
        """Generate analysis results JSON files."""
        print("\n🔍 Generating Analysis Data...")
        print("=" * 40)
        
        # Generate proximity analysis
        success, output = await self.run_script(
            'analysis/flood_same_amount_proximity_analysis.py',
            'Flood Proximity Analysis'
        )
        
        return success
    
    async def generate_nep_data(self):
        """Generate NEP 2026 analysis JSON files."""
        print("\n🏛️ Generating NEP 2026 Analysis...")
        print("=" * 40)
        
        # Generate NEP 2026 red flag analysis
        success1, output1 = await self.run_script(
            'analysis/generate_nep_2026_red_flag.py',
            'NEP 2026 Red Flag Analysis'
        )
        
        # Generate NEP 2026 infrastructure categories
        success2, output2 = await self.run_script(
            'analysis/generate_nep_2026_infrastructure_categories.py',
            'NEP 2026 Infrastructure Categories'
        )
        
        # Generate NEP 2026 overall analysis
        success3, output3 = await self.run_script(
            'analysis/generate_nep_2026_overall_analysis.py',
            'NEP 2026 Overall Analysis'
        )
        
        return success1 and success2 and success3
    
    async def generate_dime_data(self):
        """Generate DIME analysis JSON files."""
        print("\n🏗️ Generating DIME Data...")
        print("=" * 40)
        
        # Generate fastest DIME projects
        success, output = await self.run_script(
            'sec_scraper/generate_fastest_dime_projects.py',
            'Fastest DIME Projects'
        )
        
        return success
    
    async def generate_cache_data(self):
        """Generate cache JSON files."""
        print("\n💾 Generating Cache Data...")
        print("=" * 40)
        
        # Generate excluded flood contractors cache (new script for new JSON)
        success1, output1 = await self.run_script(
            'sec_scraper/generate_contractors_cache.py',
            'Excluded Flood Contractors Cache'
        )
        
        # Generate contractors dashboard cache (new script for new JSON)
        success2, output2 = await self.run_script(
            'sec_scraper/generate_contractors_dashboard_cache.py',
            'Contractors Dashboard Cache'
        )
        
        return success1 and success2
    
    async def generate_api_cache(self):
        """Generate API cache files by calling all endpoints."""
        print("\n🌐 Generating API Cache...")
        print("=" * 40)
        
        # Generate API cache (new script for new JSON files)
        success, output = await self.run_script(
            'sec_scraper/generate_api_cache.py',
            'API Cache Generation (33 endpoints)'
        )
        
        return success
    
    async def generate_all(self, categories: List[str] = None):
        """Generate all JSON files or specific categories."""
        print("🚀 Starting JSON Generation Process")
        print("=" * 50)
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Target directory: {self.static_data_dir}")
        
        if categories is None:
            categories = ['sec_data', 'summary_data', 'analysis_data', 'nep_data', 'dime_data', 'cache_data', 'api_cache']
        
        results = {}
        
        # Generate SEC data
        if 'sec_data' in categories:
            results['sec_data'] = await self.generate_sec_data()
        
        # Generate summary statistics
        if 'summary_data' in categories:
            results['summary_data'] = await self.generate_summary_stats()
        
        # Generate analysis data
        if 'analysis_data' in categories:
            results['analysis_data'] = await self.generate_analysis_data()
        
        # Generate NEP data
        if 'nep_data' in categories:
            results['nep_data'] = await self.generate_nep_data()
        
        # Generate DIME data
        if 'dime_data' in categories:
            results['dime_data'] = await self.generate_dime_data()
        
        # Generate cache data
        if 'cache_data' in categories:
            results['cache_data'] = await self.generate_cache_data()
        
        # Generate API cache
        if 'api_cache' in categories:
            results['api_cache'] = await self.generate_api_cache()
        
        # Print results summary
        print("\n📋 Generation Results Summary")
        print("=" * 40)
        for category, success in results.items():
            status = "✅ Success" if success else "❌ Failed"
            print(f"{category.replace('_', ' ').title()}: {status}")
        
        total_success = sum(results.values())
        total_categories = len(results)
        print(f"\nOverall: {total_success}/{total_categories} categories successful")
        
        return results
    
    def store_cache_to_mongodb(self, cache_name: str, data: Dict, metadata: Dict = None) -> str:
        """
        Store JSON cache in MongoDB (future implementation)
        
        Args:
            cache_name: Name of the cache
            data: JSON data to store
            metadata: Additional metadata
            
        Returns:
            Version ID of stored cache
        """
        if not self.mongodb_cache:
            print(f"⚠️ MongoDB cache not available for '{cache_name}'")
            return None
        
        try:
            version_id = self.mongodb_cache.store_cache(cache_name, data, metadata)
            print(f"✅ Stored '{cache_name}' in MongoDB cache")
            return version_id
        except Exception as e:
            print(f"❌ Failed to store '{cache_name}' in MongoDB: {e}")
            return None
    
    def get_cache_from_mongodb(self, cache_name: str, version_id: str = None) -> Dict:
        """
        Retrieve JSON cache from MongoDB (future implementation)
        
        Args:
            cache_name: Name of the cache
            version_id: Specific version (latest if None)
            
        Returns:
            Cache data or None
        """
        if not self.mongodb_cache:
            print(f"⚠️ MongoDB cache not available for '{cache_name}'")
            return None
        
        try:
            data = self.mongodb_cache.get_cache(cache_name, version_id)
            if data:
                print(f"✅ Retrieved '{cache_name}' from MongoDB cache")
            else:
                print(f"⚠️ Cache '{cache_name}' not found in MongoDB")
            return data
        except Exception as e:
            print(f"❌ Failed to retrieve '{cache_name}' from MongoDB: {e}")
            return None
    
    def get_cache_analytics(self) -> Dict:
        """Get MongoDB cache analytics (future implementation)"""
        if not self.mongodb_cache:
            return {}
        
        try:
            return self.mongodb_cache.get_cache_analytics()
        except Exception as e:
            print(f"❌ Failed to get cache analytics: {e}")
            return {}
    
    def get_cache_status(self) -> Dict:
        """Get MongoDB cache system status (future implementation)"""
        if not self.mongodb_cache:
            return {"mongodb_available": False}
        
        try:
            status = self.mongodb_cache.get_cache_status()
            status["mongodb_available"] = True
            return status
        except Exception as e:
            print(f"❌ Failed to get cache status: {e}")
            return {"mongodb_available": False, "error": str(e)}

async def main():
    """Main function to run JSON generation."""
    generator = JSONGenerator()
    
    # Print inventory
    generator.print_inventory()
    
    # Generate all JSON files
    results = await generator.generate_all()
    
    # Check if any failed
    failed_categories = [cat for cat, success in results.items() if not success]
    if failed_categories:
        print(f"\n⚠️  Failed categories: {', '.join(failed_categories)}")
        print("Please check the error messages above and fix any issues.")
        return 1
    else:
        print("\n🎉 All JSON files generated successfully!")
        return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

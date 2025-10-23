#!/usr/bin/env python3
"""
Generate API cache JSON files by calling all API endpoints.

This script calls all API endpoints that generate JSON on-demand and caches their responses
to static/data/ for faster loading and offline access.
"""

import asyncio
import aiohttp
import json
import os
from datetime import datetime
from typing import Dict, Any, List
from pathlib import Path

# Base URL for the API
BASE_URL = "http://172.30.147.217:8001"

# API endpoints that generate JSON on-demand
API_ENDPOINTS = {
    # Contractor Statistics Cache
    'contractor_stats_cache.json': '/api/contractors/stats',
    
    # Flood Data
    'flood_control_data.json': '/api/flood/projects',
    'flood_baseline_pattern.json': '/api/flood/statistics',
    
    # Correlation Data
    'flood_dime_contractor_correlation.json': '/api/flood/dime/correlation',
    'flood_dime_contractor_correlation_2020.json': '/api/flood/dime/correlation/2020',
    'flood_dime_contractor_correlation_2021.json': '/api/flood/dime/correlation/2021',
    'flood_dime_contractor_correlation_2022.json': '/api/flood/dime/correlation/2022',
    'flood_dime_contractor_correlation_2023.json': '/api/flood/dime/correlation/2023',
    'flood_dime_contractor_correlation_2024.json': '/api/flood/dime/correlation/2024',
    'flood_dime_contractor_correlation_2025.json': '/api/flood/dime/correlation/2025',
    'flood_dime_contractor_correlation_all_years.json': '/api/flood/dime/correlation/all',
    
    # NEP Data
    'nep_2026_infrastructure_categories.json': '/api/budget/nep/categories',
    'nep_2026_overall_analysis.json': '/api/budget/nep/analysis',
    'nep_2026_red_flag.json': '/api/budget/nep/red-flags',
    
    # DIME Data
    'dime_stats.json': '/api/dime/statistics',
    'fastest_dime_projects.json': '/api/dime/fastest-projects',
    
    # Budget Data
    'budget_overview.json': '/api/budget/overview/stats',
    'budget_departments.json': '/api/budget/departments',
    'budget_categories.json': '/api/budget/expense-categories',
    'budget_regions.json': '/api/budget/regions',
    'budget_agencies.json': '/api/budget/agencies',
    
    # Flood Lookup Data
    'flood_regions.json': '/api/flood/lookup/regions',
    'flood_provinces.json': '/api/flood/lookup/provinces',
    'flood_years.json': '/api/flood/lookup/years',
    'flood_work_types.json': '/api/flood/lookup/types-of-work',
    'flood_contractors.json': '/api/flood/lookup/contractors',
    
    # DIME Lookup Data
    'dime_filter_options.json': '/api/dime/filter-options',
    'dime_barangay_aggregates.json': '/api/dime/barangay-aggregates',
    'dime_projects_dime_only.json': '/api/dime/projects/dime-only'
}

async def call_api_endpoint(session: aiohttp.ClientSession, endpoint: str, filename: str) -> Dict[str, Any]:
    """Call a single API endpoint and return the response data."""
    url = f"{BASE_URL}{endpoint}"
    
    try:
        print(f"🔄 Calling {endpoint}...")
        
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                
                # Add cache metadata
                cache_data = {
                    'data': data,
                    'generated_at': datetime.now().isoformat(),
                    'cache_version': '1.0',
                    'endpoint': endpoint,
                    'status': 'success'
                }
                
                print(f"✅ {endpoint} - Success")
                return cache_data
            else:
                print(f"❌ {endpoint} - HTTP {response.status}")
                return {
                    'data': None,
                    'generated_at': datetime.now().isoformat(),
                    'cache_version': '1.0',
                    'endpoint': endpoint,
                    'status': 'error',
                    'error': f"HTTP {response.status}"
                }
                
    except Exception as e:
        print(f"❌ {endpoint} - Error: {str(e)}")
        return {
            'data': None,
            'generated_at': datetime.now().isoformat(),
            'cache_version': '1.0',
            'endpoint': endpoint,
            'status': 'error',
            'error': str(e)
        }

async def save_json_cache(data: Dict[str, Any], output_file: str) -> bool:
    """Save API response data to JSON cache file."""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Generated {output_file}")
        return True
    except Exception as e:
        print(f"❌ Error saving {output_file}: {e}")
        return False

async def generate_api_cache():
    """Generate all API cache files by calling endpoints."""
    print("🌐 Generating API Cache...")
    print("=" * 50)
    print(f"Base URL: {BASE_URL}")
    print(f"Total endpoints: {len(API_ENDPOINTS)}")
    print()
    
    # Create aiohttp session
    timeout = aiohttp.ClientTimeout(total=30)  # 30 second timeout per request
    async with aiohttp.ClientSession(timeout=timeout) as session:
        
        # Call all endpoints concurrently
        tasks = []
        for filename, endpoint in API_ENDPOINTS.items():
            task = call_api_endpoint(session, endpoint, filename)
            tasks.append((task, filename))
        
        # Execute all tasks
        results = []
        for task, filename in tasks:
            try:
                result = await task
                results.append((result, filename))
            except Exception as e:
                print(f"❌ Task failed for {filename}: {e}")
                results.append(({
                    'data': None,
                    'generated_at': datetime.now().isoformat(),
                    'cache_version': '1.0',
                    'endpoint': API_ENDPOINTS[filename],
                    'status': 'error',
                    'error': str(e)
                }, filename))
        
        # Save all results
        success_count = 0
        error_count = 0
        
        for result, filename in results:
            output_file = f"static/data/{filename}"
            success = await save_json_cache(result, output_file)
            
            if success and result.get('status') == 'success':
                success_count += 1
            else:
                error_count += 1
        
        print("\n📋 API Cache Generation Results")
        print("=" * 50)
        print(f"✅ Successful: {success_count}")
        print(f"❌ Failed: {error_count}")
        print(f"📊 Total: {len(API_ENDPOINTS)}")
        
        if error_count > 0:
            print("\n⚠️ Some endpoints failed. Check the server is running and endpoints are accessible.")
        
        return success_count, error_count

async def main():
    """Main function to generate all API cache files."""
    print("🚀 Starting API Cache Generation")
    print("=" * 50)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Check if server is running
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BASE_URL}/api/flood/health", timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status != 200:
                    print("⚠️ Server is running but health check failed")
                    print("   Proceeding with API cache generation...")
    except Exception:
        print("⚠️ FastAPI server is not running!")
        print("   Please start the server with: python visualization.py")
        print("   Then run this script again.")
        print()
        print("   For now, creating placeholder cache files...")
        
        # Create placeholder files
        for filename in API_ENDPOINTS.keys():
            placeholder_data = {
                'data': None,
                'generated_at': datetime.now().isoformat(),
                'cache_version': '1.0',
                'endpoint': API_ENDPOINTS[filename],
                'status': 'server_not_running',
                'error': 'FastAPI server not running - please start server and regenerate'
            }
            await save_json_cache(placeholder_data, f"static/data/{filename}")
        
        print("✅ Placeholder cache files created")
        return True
    
    try:
        success_count, error_count = await generate_api_cache()
        
        if error_count == 0:
            print("\n🎉 All API endpoints cached successfully!")
        else:
            print(f"\n⚠️ API cache generation completed with {error_count} errors.")
            
    except Exception as e:
        print(f"\n❌ API cache generation failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    asyncio.run(main())

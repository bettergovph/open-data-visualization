#!/usr/bin/env python3
"""
Generate Contractor Project Counts JSON
========================================
Creates a JSON file with project counts per contractor for scatter plot analysis.
This script analyzes flood control projects and counts how many projects each contractor has.
"""

import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from flood_client import FloodControlClient

async def generate_contractor_project_counts():
    """Generate contractor project counts for scatter plot analysis"""
    print("🔍 Generating contractor project counts...")
    
    try:
        # Initialize flood client
        client = FloodControlClient()
        
        # Check if MeiliSearch is accessible
        is_healthy = await client.health_check()
        if not is_healthy:
            print("❌ MeiliSearch is not accessible")
            return False
        
        print("✅ MeiliSearch connection established")
        
        # Get all projects
        projects, metadata = await client.search_projects("", limit=10000)
        print(f"📊 Found {len(projects)} projects")
        
        # Count projects per contractor
        contractor_counts = defaultdict(int)
        total_projects = 0
        
        for project in projects:
            contractor = project.Contractor
            if contractor and contractor.strip():
                contractor_counts[contractor] += 1
                total_projects += 1
        
        print(f"📈 Analyzed {total_projects} projects from {len(contractor_counts)} contractors")
        
        # Convert to list of project counts (sorted for better visualization)
        project_counts = sorted([count for count in contractor_counts.values()], reverse=True)
        
        # Calculate basic statistics
        mean = sum(project_counts) / len(project_counts) if project_counts else 0
        variance = sum((count - mean) ** 2 for count in project_counts) / len(project_counts) if project_counts else 0
        standard_deviation = variance ** 0.5
        
        # Count outliers (beyond 3 standard deviations)
        outliers = [count for count in project_counts if abs(count - mean) > 3 * standard_deviation]
        
        # Prepare output data
        output_data = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "total_contractors": len(contractor_counts),
                "total_projects": total_projects,
                "mean_projects_per_contractor": round(mean, 2),
                "standard_deviation": round(standard_deviation, 2),
                "outliers_count": len(outliers),
                "outliers_threshold": round(mean + 3 * standard_deviation, 2)
            },
            "project_counts": project_counts,
            "contractor_details": [
                {
                    "contractor": contractor,
                    "project_count": count,
                    "z_score": round(abs(count - mean) / standard_deviation, 2) if standard_deviation > 0 else 0
                }
                for contractor, count in sorted(contractor_counts.items(), key=lambda x: x[1], reverse=True)
            ]
        }
        
        # Write to JSON file
        output_file = project_root / "static" / "data" / "contractor_project_counts.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Contractor project counts saved to: {output_file}")
        print(f"📊 Statistics:")
        print(f"   Mean projects per contractor: {mean:.2f}")
        print(f"   Standard deviation: {standard_deviation:.2f}")
        print(f"   Outliers (>3SD): {len(outliers)} contractors")
        print(f"   Max projects: {max(project_counts) if project_counts else 0}")
        print(f"   Min projects: {min(project_counts) if project_counts else 0}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error generating contractor project counts: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(generate_contractor_project_counts())
    sys.exit(0 if success else 1)

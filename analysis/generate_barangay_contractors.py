#!/usr/bin/env python3
"""
Generate preprocessed barangay contractors JSON with MeiliSearch connections.
This creates a lookup table for barangay contractor modals.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

def load_fastest_projects_data() -> List[Dict[str, Any]]:
    """Load the fastest projects data which has preprocessed contractor information."""
    try:
        fastest_file = Path(__file__).parent.parent / "static" / "data" / "fastest_dime_projects.json"
        if fastest_file.exists():
            with open(fastest_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('projects', [])
        else:
            print("⚠️ Fastest projects data not found")
            return []
    except Exception as e:
        print(f"❌ Error loading fastest projects data: {e}")
        return []

def process_barangay_contractors(projects: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Process projects to create barangay contractor lookup."""
    barangay_contractors = {}
    
    for project in projects:
        barangay = project.get('barangay', '').strip()
        city = project.get('city', '').strip()
        
        if not barangay or not city:
            continue
            
        # Create unique key for barangay
        key = f"{barangay},{city}".lower()
        
        if key not in barangay_contractors:
            barangay_contractors[key] = {
                'barangay': barangay,
                'city': city,
                'province': project.get('province', ''),
                'region': project.get('region', ''),
                'contractors': set(),
                'projects': [],
                'total_projects': 0,
                'total_cost': 0
            }
        
        # Add contractor information
        contractor_name = None
        contractor_source = None
        
        # Use same logic as fastest projects table
        if project.get('contractor_source') in ['flood_connected', 'dime_fallback']:
            if project.get('contractors') and len(project.get('contractors', [])) > 0:
                contractor_name = project['contractors'][0]
                contractor_source = 'SSP'
        elif project.get('contractors') and len(project.get('contractors', [])) > 0:
            contractor_name = project['contractors'][0]
            contractor_source = 'DIME'
        elif project.get('implementing_offices') and len(project.get('implementing_offices', [])) > 0:
            try:
                office = project['implementing_offices'][0]
                if isinstance(office, str):
                    office_obj = json.loads(office)
                else:
                    office_obj = office
                contractor_name = office_obj.get('name') or office_obj.get('nameAbbreviation')
                contractor_source = 'DIME Office'
            except:
                contractor_name = None
        
        if contractor_name:
            barangay_contractors[key]['contractors'].add(contractor_name)
        
        # Add project info
        barangay_contractors[key]['projects'].append({
            'project_name': project.get('project_name', ''),
            'contractor': contractor_name,
            'contractor_source': contractor_source,
            'cost': project.get('cost', 0),
            'status': project.get('status', ''),
            'completion_days': project.get('completion_days', 0)
        })
        
        barangay_contractors[key]['total_projects'] += 1
        barangay_contractors[key]['total_cost'] += project.get('cost', 0)
    
    # Convert sets to lists for JSON serialization
    for key, data in barangay_contractors.items():
        data['contractors'] = list(data['contractors'])
        data['unique_contractors'] = len(data['contractors'])
    
    return barangay_contractors

def main():
    """Generate barangay contractors JSON file."""
    print("🏘️ Generating barangay contractors JSON...")
    
    # Load fastest projects data
    projects = load_fastest_projects_data()
    if not projects:
        print("❌ No projects data available")
        return False
    
    print(f"📊 Processing {len(projects)} projects...")
    
    # Process barangay contractors
    barangay_contractors = process_barangay_contractors(projects)
    
    # Create output data
    output_data = {
        'success': True,
        'generated_at': datetime.now().isoformat(),
        'cache_version': '1.0',
        'total_barangays': len(barangay_contractors),
        'total_projects': len(projects),
        'barangay_contractors': barangay_contractors
    }
    
    # Save to file
    output_file = Path(__file__).parent.parent / "static" / "data" / "barangay_contractors.json"
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Generated barangay contractors JSON: {output_file}")
        print(f"📊 Processed {len(barangay_contractors)} barangays")
        
        # Show sample data
        if barangay_contractors:
            sample_key = list(barangay_contractors.keys())[0]
            sample_data = barangay_contractors[sample_key]
            print(f"🔍 Sample: {sample_data['barangay']}, {sample_data['city']} - {sample_data['unique_contractors']} contractors")
        
        return True
        
    except Exception as e:
        print(f"❌ Error saving barangay contractors JSON: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

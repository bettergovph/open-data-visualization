#!/usr/bin/env python3
"""
Organize JSON files for MongoDB migration.
Groups files by category and creates a migration plan.
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Any

def categorize_json_files() -> Dict[str, List[str]]:
    """
    Categorize JSON files by their purpose and content.
    
    Returns:
        Dictionary with categories and their associated files
    """
    categories = {
        'flood_data': [],
        'budget_data': [],
        'nep_data': [],
        'sec_data': [],
        'geographic_data': [],
        'correlation_data': [],
        'cache_data': [],
        'summary_data': []
    }
    
    # Scan static directory for JSON files
    static_dir = Path('.')
    data_dir = Path('data')
    
    # Files in root static directory
    for file_path in static_dir.glob('*.json'):
        filename = file_path.name
        if 'sec' in filename.lower() or 'contractor' in filename.lower():
            categories['sec_data'].append(str(file_path))
        elif 'excluded' in filename.lower() or 'cache' in filename.lower():
            categories['cache_data'].append(str(file_path))
        else:
            categories['summary_data'].append(str(file_path))
    
    # Files in static/data directory
    if data_dir.exists():
        for file_path in data_dir.glob('*.json'):
            filename = file_path.name
            relative_path = str(file_path)
            
            if 'flood' in filename.lower():
                categories['flood_data'].append(relative_path)
            elif 'budget' in filename.lower():
                categories['budget_data'].append(relative_path)
            elif 'nep' in filename.lower():
                categories['nep_data'].append(relative_path)
            elif 'correlation' in filename.lower():
                categories['correlation_data'].append(relative_path)
            elif 'philippines' in filename.lower() or 'region' in filename.lower():
                categories['geographic_data'].append(relative_path)
            elif 'cache' in filename.lower() or 'stats' in filename.lower():
                categories['cache_data'].append(relative_path)
            elif 'summary' in filename.lower():
                categories['summary_data'].append(relative_path)
            else:
                categories['flood_data'].append(relative_path)  # Default to flood data
    
    return categories

def create_mongodb_migration_plan(categories: Dict[str, List[str]]) -> Dict[str, Any]:
    """
    Create a MongoDB migration plan based on categorized files.
    
    Args:
        categories: Dictionary of categorized JSON files
        
    Returns:
        Migration plan dictionary
    """
    migration_plan = {
        'collections': {},
        'file_mappings': {},
        'api_endpoints_to_update': [],
        'migration_steps': []
    }
    
    # Define MongoDB collections
    collections = {
        'flood_data': {
            'description': 'Flood control projects and related data',
            'files': categories['flood_data'],
            'primary_key': 'project_id',
            'indexes': ['region', 'year', 'contractor', 'amount']
        },
        'budget_data': {
            'description': 'Budget analysis and financial data',
            'files': categories['budget_data'],
            'primary_key': 'budget_id',
            'indexes': ['year', 'department', 'region', 'category']
        },
        'nep_data': {
            'description': 'National Expenditure Program data',
            'files': categories['nep_data'],
            'primary_key': 'nep_id',
            'indexes': ['year', 'category', 'department', 'region']
        },
        'sec_data': {
            'description': 'SEC contractor and company data',
            'files': categories['sec_data'],
            'primary_key': 'sec_number',
            'indexes': ['contractor_name', 'status', 'registration_date']
        },
        'geographic_data': {
            'description': 'Geographic and regional data',
            'files': categories['geographic_data'],
            'primary_key': 'region_id',
            'indexes': ['region_name', 'province', 'coordinates']
        },
        'correlation_data': {
            'description': 'Data correlation and analysis results',
            'files': categories['correlation_data'],
            'primary_key': 'correlation_id',
            'indexes': ['year', 'contractor', 'correlation_type']
        },
        'cache_data': {
            'description': 'Cached data for performance optimization',
            'files': categories['cache_data'],
            'primary_key': 'cache_key',
            'indexes': ['cache_type', 'generated_at', 'expires_at']
        },
        'summary_data': {
            'description': 'Summary and aggregated data',
            'files': categories['summary_data'],
            'primary_key': 'summary_id',
            'indexes': ['data_type', 'year', 'region']
        }
    }
    
    migration_plan['collections'] = collections
    
    # Create file mappings
    for collection_name, collection_info in collections.items():
        for file_path in collection_info['files']:
            migration_plan['file_mappings'][file_path] = {
                'collection': collection_name,
                'description': collection_info['description']
            }
    
    # API endpoints that need updating
    migration_plan['api_endpoints_to_update'] = [
        '/static/data/flood_control_data.json',
        '/static/data/region-mapping.json',
        '/static/data/philippines-regions.json',
        '/static/data/contractor_stats_cache.json',
        '/static/data/flood_summary.json',
        '/static/sec_contractors_database.json',
        '/static/contractor_sec_mapping.json',
        '/static/excluded_flood_contractors_cache.json'
    ]
    
    # Migration steps
    migration_plan['migration_steps'] = [
        '1. Create MongoDB collections with proper schemas',
        '2. Import JSON files into respective collections',
        '3. Create indexes for performance optimization',
        '4. Update API endpoints to read from MongoDB',
        '5. Implement caching layer for frequently accessed data',
        '6. Test all endpoints and visualizations',
        '7. Deploy and monitor performance',
        '8. Keep JSON files as backup during transition'
    ]
    
    return migration_plan

def generate_migration_report(categories: Dict[str, List[str]], migration_plan: Dict[str, Any]) -> str:
    """
    Generate a comprehensive migration report.
    
    Args:
        categories: Categorized JSON files
        migration_plan: MongoDB migration plan
        
    Returns:
        Migration report as string
    """
    report = f"""
# JSON Files to MongoDB Migration Report

## Summary
Total JSON files found: {sum(len(files) for files in categories.values())}

## File Categories

"""
    
    for category, files in categories.items():
        report += f"### {category.replace('_', ' ').title()}\n"
        report += f"Files: {len(files)}\n"
        for file in files:
            report += f"- {file}\n"
        report += "\n"
    
    report += f"""
## MongoDB Collections Plan

"""
    
    for collection_name, collection_info in migration_plan['collections'].items():
        report += f"### {collection_name}\n"
        report += f"Description: {collection_info['description']}\n"
        report += f"Primary Key: {collection_info['primary_key']}\n"
        report += f"Indexes: {', '.join(collection_info['indexes'])}\n"
        report += f"Files: {len(collection_info['files'])}\n\n"
    
    report += f"""
## Migration Steps

"""
    for step in migration_plan['migration_steps']:
        report += f"{step}\n"
    
    return report

def main():
    """Main function to organize JSON files for MongoDB migration."""
    print("Organizing JSON files for MongoDB migration...")
    
    # Categorize files
    print("Categorizing JSON files...")
    categories = categorize_json_files()
    
    # Create migration plan
    print("Creating MongoDB migration plan...")
    migration_plan = create_mongodb_migration_plan(categories)
    
    # Generate report
    print("Generating migration report...")
    report = generate_migration_report(categories, migration_plan)
    
    # Save migration plan
    with open('mongodb_migration_plan.json', 'w', encoding='utf-8') as f:
        json.dump(migration_plan, f, indent=2, ensure_ascii=False)
    
    # Save report
    with open('mongodb_migration_report.md', 'w', encoding='utf-8') as f:
        f.write(report)
    
    print("Migration files created:")
    print("- mongodb_migration_plan.json")
    print("- mongodb_migration_report.md")
    
    # Print summary
    print(f"\nSummary:")
    for category, files in categories.items():
        print(f"- {category}: {len(files)} files")

if __name__ == "__main__":
    main()

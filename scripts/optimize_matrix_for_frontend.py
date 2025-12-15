#!/usr/bin/env python3
"""
Generate a slim version of integrated_matrix.json for faster initial page load.
Moves detailed project lists to separate per-district files loaded on demand.
"""
import json
from pathlib import Path

INPUT_FILE = Path("static/data/integrated_matrix.json")
OUTPUT_SLIM = Path("static/data/integrated_matrix_slim.json")
OUTPUT_PROJECTS_DIR = Path("static/data/district_projects")

def optimize_matrix():
    print("🔄 Loading full matrix...")
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Create output directory for per-district project files
    OUTPUT_PROJECTS_DIR.mkdir(exist_ok=True)
    
    # Create slim version
    slim_ranking = []
    
    for i, entry in enumerate(data.get('ranking', [])):
        # Create a slim entry without full project details
        slim_entry = {
            'congressman': entry.get('congressman', 'Unknown'),
            'district': entry.get('district', 'Unknown'),
            'province': entry.get('province', 'Unknown'),
            'project_count': entry.get('project_count', 0),
            'total_amount': entry.get('total_amount', 0),
            # Add only top 3 project previews for the table
            'project_previews': [
                {'name': p.get('name', '')[:100], 'amount': p.get('amount', 0)}
                for p in entry.get('projects', [])[:3]
            ],
            # Index for loading full projects on demand
            'index': i
        }
        slim_ranking.append(slim_entry)
        
        # Save full project details to separate file
        projects_file = OUTPUT_PROJECTS_DIR / f"district_{i}.json"
        with open(projects_file, 'w', encoding='utf-8') as f:
            json.dump(entry.get('projects', []), f, ensure_ascii=False)
    
    # Create slim output
    slim_data = {
        'metadata': data.get('metadata', {}),
        'ranking': slim_ranking
    }
    
    with open(OUTPUT_SLIM, 'w', encoding='utf-8') as f:
        json.dump(slim_data, f, ensure_ascii=False)
    
    # Check sizes
    full_size = INPUT_FILE.stat().st_size / 1024 / 1024
    slim_size = OUTPUT_SLIM.stat().st_size / 1024 / 1024
    
    print(f"✅ Original: {full_size:.2f} MB")
    print(f"✅ Slim: {slim_size:.2f} MB ({(1 - slim_size/full_size)*100:.1f}% reduction)")
    print(f"✅ Created {len(slim_ranking)} district project files in {OUTPUT_PROJECTS_DIR}")

if __name__ == '__main__':
    optimize_matrix()

import json
from pathlib import Path

def update_resurrected_names():
    print("🔄 Updating resurrected projects with revised_name...")
    
    # Load 2026 source data
    source_path = Path("static/data/budget_amendments_2026.json")
    if not source_path.exists():
        print(f"❌ Source file not found: {source_path}")
        return
    
    with open(source_path, 'r', encoding='utf-8') as f:
        source_data = json.load(f)
    
    # Create lookup map (id -> item)
    all_items = source_data.get('line_items', []) + source_data.get('projects', [])
    items_map = {item.get('id'): item for item in all_items if item.get('id')}
    print(f"   Loaded {len(items_map)} source items")
    
    # Load resurrected projects cache
    cache_path = Path("static/data/resurrected_projects_dpwh.json")
    if not cache_path.exists():
        print(f"❌ Cache file not found: {cache_path}")
        return
    
    with open(cache_path, 'r', encoding='utf-8') as f:
        cache_data = json.load(f)
    
    matches = cache_data.get('matches', [])
    updated_count = 0
    
    for match in matches:
        year_2026 = match.get('year_2026', {})
        project_id = year_2026.get('id')
        
        if project_id and project_id in items_map:
            source_item = items_map[project_id]
            revised_name = source_item.get('revised_name')
            
            if revised_name:
                year_2026['revised_name'] = revised_name
                updated_count += 1
    
    # Save updated cache
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Updated {updated_count} matches with revised_name")
    print(f"💾 Saved to {cache_path}")

if __name__ == "__main__":
    update_resurrected_names()

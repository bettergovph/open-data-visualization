#!/usr/bin/env python3
"""Fix Microsite count in existing congressman JSON cache files by directly editing them"""
import json
import glob
from pathlib import Path

def count_microsite_projects(projects):
    """Count projects that have Microsite in their sources_list"""
    if not projects:
        return 0
    
    count = 0
    for p in projects:
        sources_list = p.get('sources_list', [])
        if not sources_list:
            # Fallback: check source field
            source = p.get('source', '').upper()
            if 'MICROSITE' in source or 'INFRAWATCH' in source:
                count += 1
        else:
            # Check sources_list for Microsite/Infrawatch
            if any('Microsite' in str(s) or 'MICROSITE' in str(s) or 
                   'Infrawatch' in str(s) or 'INFRAWATCH' in str(s) 
                   for s in sources_list):
                count += 1
    
    return count

def fix_json_file(json_path):
    """Fix Microsite count in a single JSON file"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not data.get('success', True):
            return False, 0
        
        projects = data.get('projects', [])
        microsite_count = count_microsite_projects(projects)
        
        # Update summary if it exists
        updated = False
        if 'summary' in data:
            summary = data['summary']
            old_microsite = summary.get('microsite', 0)
            old_infrawatch = summary.get('infrawatch', 0)
            
            if microsite_count != old_microsite or microsite_count != old_infrawatch:
                summary['microsite'] = microsite_count
                summary['infrawatch'] = microsite_count
                updated = True
        
        if updated:
            # Write back the fixed data
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True, microsite_count
        
        return False, microsite_count
    except Exception as e:
        print(f"  ❌ Error fixing {json_path}: {e}")
        return False, 0

def main():
    data_root = Path(__file__).parent.parent / "static" / "data"
    
    # Fix summary.json files
    pattern1 = str(data_root / "congressman-projects-*" / "summary.json")
    summary_files = glob.glob(pattern1)
    
    print(f"🔧 Fixing Microsite count in {len(summary_files)} summary.json files...")
    
    fixed_summaries = 0
    total_microsite = 0
    for json_path in sorted(summary_files):
        updated, count = fix_json_file(json_path)
        if updated:
            fixed_summaries += 1
            total_microsite += count
            print(f"  ✅ {Path(json_path).parent.name}: {count} Microsite projects")
    
    # Fix all-projects-cache.json files
    pattern2 = str(data_root / "congressman-projects-*" / "all-projects-cache.json")
    cache_files = glob.glob(pattern2)
    
    print(f"\n🔧 Fixing Microsite count in {len(cache_files)} all-projects-cache.json files...")
    
    fixed_caches = 0
    for cache_path in sorted(cache_files):
        updated, count = fix_json_file(cache_path)
        if updated:
            fixed_caches += 1
            if count > 0:
                print(f"  ✅ {Path(cache_path).parent.name}: {count} Microsite projects")
    
    print(f"\n✅ Summary:")
    print(f"   Fixed {fixed_summaries} summary.json files")
    print(f"   Fixed {fixed_caches} all-projects-cache.json files")
    print(f"   Total Microsite projects found: {total_microsite}")

if __name__ == "__main__":
    main()










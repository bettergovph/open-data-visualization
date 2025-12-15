#!/usr/bin/env python3
"""
Merge Wikipedia 20th Congress representatives into districts.json.
Uses the same approach as update_districts_with_2025_results.py.

Data flow:
- Wikipedia 20th Congress (2022-2025) scraped data in 20th_congress_representatives.json
- Updates districts.json representatives field with "(2022-present)" format
- Only updates if current rep is missing, TBA, or blank
"""
import json
import shutil
from pathlib import Path

DISTRICTS_FILE = Path("static/data/districts.json")
WIKI_FILE = Path("static/data/20th_congress_representatives.json")

def normalize_district_key(dist_part):
    """Match the format used in districts.json"""
    d = dist_part.upper()
    if "LONE" in d: return "Lone District"
    if "1ST" in d or "FIRST" in d: return "1st District"
    if "2ND" in d or "SECOND" in d: return "2nd District"
    if "3RD" in d or "THIRD" in d: return "3rd District"
    if "4TH" in d or "FOURTH" in d: return "4th District"
    if "5TH" in d or "FIFTH" in d: return "5th District"
    if "6TH" in d or "SIXTH" in d: return "6th District"
    if "7TH" in d or "SEVENTH" in d: return "7th District"
    if "8TH" in d or "EIGHTH" in d: return "8th District"
    return dist_part.title()

def merge_wikipedia_congress():
    print("🔄 Loading data...")
    
    if not DISTRICTS_FILE.exists():
        print(f"❌ districts.json not found: {DISTRICTS_FILE}")
        return
    if not WIKI_FILE.exists():
        print(f"❌ Wikipedia data not found: {WIKI_FILE}")
        return
    
    with open(DISTRICTS_FILE, 'r', encoding='utf-8') as f:
        d_data = json.load(f)
    with open(WIKI_FILE, 'r', encoding='utf-8') as f:
        wiki_list = json.load(f)
    
    # Backup
    shutil.copy(DISTRICTS_FILE, str(DISTRICTS_FILE) + ".wiki-backup")
    print(f"📦 Backup created: {DISTRICTS_FILE}.wiki-backup")
    
    updates_count = 0
    misses = []
    
    for entry in wiki_list:
        prov_part = entry['province']
        dist_part = entry['district']
        rep_name = entry['representative']
        
        target_dist_key = normalize_district_key(dist_part)
        new_rep_str = f"{rep_name} (2022-present)"
        
        # Find matching key in districts.json
        target_key = None
        for k in d_data['districts'].keys():
            if k.upper() == prov_part.upper():
                target_key = k
                break
            # Try with variations
            if k.upper() == f"{prov_part} CITY".upper():
                target_key = k
                break
            if k.upper().replace(" CITY", "") == prov_part.upper().replace(" CITY", ""):
                target_key = k
                break
        
        if target_key:
            if 'representatives' not in d_data['districts'][target_key]:
                d_data['districts'][target_key]['representatives'] = {}
            
            reps = d_data['districts'][target_key]['representatives']
            all_dists = d_data['districts'][target_key].get('all_districts', [])
            
            # Check if district exists and current rep is missing/TBA
            current_rep = reps.get(target_dist_key, "")
            should_update = (
                not current_rep or 
                "TBA" in current_rep.upper() or
                "UNKNOWN" in current_rep.upper() or
                current_rep.strip() == ""
            )
            
            if should_update:
                if target_dist_key in reps or target_dist_key in all_dists or "District" in target_dist_key:
                    print(f"  UPDATE: {target_key} {target_dist_key}: {new_rep_str}")
                    d_data['districts'][target_key]['representatives'][target_dist_key] = new_rep_str
                    updates_count += 1
                else:
                    misses.append(f"{prov_part} {dist_part} -> District key '{target_dist_key}' not in {all_dists}")
        else:
            misses.append(f"{prov_part} -> No key match in districts.json")
    
    print(f"\n✅ Updated {updates_count} representatives from Wikipedia.")
    if misses:
        print(f"\n⚠️ Missed {len(misses)} entries (First 20):")
        for m in misses[:20]:
            print(f"   {m}")
    
    # Save
    with open(DISTRICTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(d_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Saved updated districts.json")

if __name__ == '__main__':
    merge_wikipedia_congress()

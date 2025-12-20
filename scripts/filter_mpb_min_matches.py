#!/usr/bin/env python3
"""
Filter MPB targets by minimum number of transparency matches.
Regenerate static/data/mpb_top_buildings.json with configurable minimum match count.
"""

import json
from pathlib import Path

def filter_mpb(min_matches=0):
    """Filter MPB targets and save to static/data/mpb_top_buildings.json"""
    
    # Load the raw MPB targets
    mpb_file = Path(__file__).parent.parent / "top_100_mpb_targets.json"
    if not mpb_file.exists():
        print(f"❌ MPB targets file not found: {mpb_file}")
        return False
    
    with open(mpb_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"📊 Total buildings in top_100_mpb_targets.json: {len(data)}")
    
    # Filter to only include buildings with at least min_matches matches
    filtered = [item for item in data if len(item.get('matches', [])) >= min_matches]
    
    # Sort by amount (descending)
    filtered = sorted(filtered, key=lambda x: x.get('amount', 0), reverse=True)
    
    print(f"✓ Buildings with at least {min_matches} match(es): {len(filtered)}")
    
    # Save filtered data to static/data directory
    output_file = Path(__file__).parent.parent / "static" / "data" / "mpb_top_buildings.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(filtered, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Saved {len(filtered)} buildings to {output_file}")
    
    # Print summary
    print(f"\n📈 Summary:")
    print(f"  - Total budget (₱): {sum(b.get('amount', 0) for b in filtered):,.2f}")
    print(f"  - Average budget (₱): {sum(b.get('amount', 0) for b in filtered) / len(filtered):,.2f}" if filtered else "  - Average: N/A")
    print(f"  - Total matches: {sum(len(b.get('matches', [])) for b in filtered)}")
    
    return True

if __name__ == "__main__":
    import sys
    min_matches = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    filter_mpb(min_matches)

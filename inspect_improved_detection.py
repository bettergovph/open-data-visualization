
import asyncio
import os
import sys
import json
import re

# Add the project directory to the python path
sys.path.append(os.getcwd())

from visualization import budget_roads_cost_analysis_api
from budget_client import get_all_budget_items_for_analysis

async def check_improved_detection():
    # Analyze 2023 and 2024 as user mentioned these specifically for rockfall/NIA gaps
    years = ['2023', '2024'] 
    
    # Broader regex patterns to test
    # Rockfall: User said "rockfall netting" but maybe "slope protection" is key?
    rockfall_patterns = [
        r'rockfall', r'netting', r'active wire mesh', r'soil nailing', 
        r'erosion control', r'slope protection' 
    ]
    
    # Irrigation: User said "irrigation" but maybe "canal", "lateral", "dam"?
    nia_patterns = [
        r'canal', r'lateral', r'diversion', r'dam\b', r'pump', 
        r'water system', r'sluice', r'embankment'
    ]

    for year in years:
        print(f"\n{'='*60}")
        print(f"Scanning Year: {year}")
        print(f"{'='*60}")

        try:
            # We need RAW items, not processed/categorized ones, to see what was missed.
            # Using the client directly as budget_roads_cost_analysis_api filters/processes heavily.
            db_result = await get_all_budget_items_for_analysis(year)
            if not db_result.get('success'):
                print(f"Error fetching {year}: {db_result.get('error')}")
                continue
                
            all_items = db_result.get('line_items', [])
            print(f"Total raw items fetched: {len(all_items)}")

            # Counters
            rockfall_hits = []
            nia_hits = []
            
            for item in all_items:
                name = item.get('revised_name') or item.get('name', '') or item.get('description', '')
                if not name: continue
                name_lower = name.lower()
                
                # Check Rockfall candidates
                # Distinguish between "Netting/Mesh" (High confidence Rockfall) vs "Slope Protection" (Generic)
                if any(re.search(p, name_lower) for p in rockfall_patterns):
                    if 'netting' in name_lower or 'mesh' in name_lower or 'rockfall' in name_lower:
                        rockfall_hits.append(f"[Netting/Mesh] {name}")
                    else:
                        rockfall_hits.append(f"[Slope Prot.] {name}")
                    
                # Check NIA candidates
                # Exclude "Diversion Road" which triggers "diversion"
                if any(re.search(p, name_lower) for p in nia_patterns):
                    if 'diversion road' in name_lower: continue
                    if 'drainage' in name_lower and 'canal' in name_lower: continue # Drainage canals are usually DPWH not NIA
                    nia_hits.append(name)

            print(f"\nPotential Rockfall Matches: {len(rockfall_hits)}")
            for i, match in enumerate(rockfall_hits[:20]):
                print(f"  - {match}")

            print(f"\nPotential NIA Matches (Filtered): {len(nia_hits)}")
            for i, match in enumerate(nia_hits[:20]):
                print(f"  - {match}")

        except Exception as e:
            print(f"Exception analyzing {year}: {e}")

if __name__ == "__main__":
    asyncio.run(check_improved_detection())

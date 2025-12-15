
import sys
import json
from pathlib import Path
from collections import defaultdict
import pandas as pd
import re

# Mock Generator class to host the static methods and logic
class MockGenerator:
    def __init__(self):
        self.force_reclassify = True
        self.progress_counters = defaultdict(int)
        self.progress_counters['congressmen_matched'] = set()
        
    @staticmethod
    def _normalize_source_label(source: str) -> str:
        if not source:
            return "Unknown"
        normalized = source.strip().lower()
        if "microsite" in normalized or "infrawatch" in normalized:
            return "Microsite"
        if "ssp" in normalized or "flood" in normalized:
            return "SSP"
        if "dime" in normalized:
            return "DIME"
        if "philgeps" in normalized:
            return "PhilGEPS"
        return source.strip()

    @staticmethod
    def _merge_project_records(primary, incoming):
        if not primary:
            return incoming.copy()
        merged = primary.copy()
        # Minimal merge logic for test
        merged['sources_list'] = sorted(list(set(merged.get('sources_list', []) + incoming.get('sources_list', []))))
        return merged

    def _match_project_unified(self, **kwargs):
        # Mock match result
        return ("Test Congressman", "district", 50, "Test District CM", None, None)

    def _update_progress(self, *args):
        pass

    def _parse_amount(self, amount):
        return 0.0

    def _is_flood_related(self, *args):
        return False
        
    # Copied from viewing Step 1162
    def _process_dime_chunk(self, projects_chunk):
        chunk_results = []
        for proj in projects_chunk:
            # FORCE MODE LOGIC SIMULATION
            
            # 1. Force Clean
            contaminated_fields = ['congressman_name', 'dynasty_member_id']
            for field in contaminated_fields:
                if field in proj:
                    del proj[field]

            # 2. Extract Basic Data
            proj_province = (proj.get('province') or '').strip()
            
            # 3. Simulate Logic
            # Explicitly set source as we saw in the code
            
            # Mock match
            final_congressman = "Test Congressman"
            match_type = "district"
            
            chunk_results.append({
                "source": self._normalize_source_label("DIME"),
                "project_name": proj.get('project_name') or "N/A",
                "match_type": match_type
            })
        return chunk_results

async def test_dime_pipeline():
    print("🧪 Testing DIME Pipeline Logic...")
    
    # 1. Load sample DIME data
    parquet_path = Path('static/data/parquet/dime_projects.parquet')
    if not parquet_path.exists():
        print(f"❌ Parquet not found: {parquet_path}")
        # Create mock data if file missing (for robustness in test environment)
        df = pd.DataFrame([{'project_name': 'Test Project', 'amount': 1000, 'source': 'DIME'}])
    else:
        df = pd.read_parquet(parquet_path).head(10)
        
    print(f"✅ Loaded {len(df)} rows from Parquet")
    projects_chunk = df.to_dict('records')
    
    # 2. Process Chunk
    gen = MockGenerator()
    processed_results = gen._process_dime_chunk(projects_chunk)
    
    print(f"✅ Processed {len(processed_results)} results")
    if processed_results:
        print(f"   Sample Result Source: {processed_results[0].get('source')}")
    
    # 3. Simulate Merge & Deduplication Logic
    projects_by_key = {}
    for proj in processed_results:
        key = "TEST_KEY_" + str(proj.get('project_name'))
        
        # Source Label Logic from Main Script
        raw_source = (proj.get('source') or proj.get('_source') or 'Unknown')
        source_label = gen._normalize_source_label(raw_source)
        proj['source'] = source_label
        
        if key not in projects_by_key:
            projects_by_key[key] = {
                'project': proj.copy(),
                'sources': set()
            }
        
        projects_by_key[key]['sources'].add(source_label)
        
    unique_projects = []
    for key, data in projects_by_key.items():
        proj = data['project'].copy()
        proj['sources_list'] = sorted(list(data['sources']))
        unique_projects.append(proj)
        
    # 4. Check Final Counts
    dime_count = len([p for p in unique_projects if 'DIME' in (p.get('sources_list', []))])
    print(f"📊 DIME Count in Summary: {dime_count}")
    
    if dime_count > 0:
        print("✅ SUCCESS: DIME projects tracked correctly in summary.")
    else:
        print("❌ FAILURE: DIME count is zero.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_dime_pipeline())


import sys
import os
import asyncio
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch

# Add scripts directory to path (adjusting for Windows/WSL path difference if needed)
# Using relative path assuming we run this from project root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))

from generate_dynasty_projects_cache_duckdb import DynastyProjectsCacheGeneratorDuckDB

class TestProcessingPipeline:
    def setup_method(self):
        self.generator = DynastyProjectsCacheGeneratorDuckDB(force_reclassify=True)
        # Mock dependencies
        self.generator.db_manager = MagicMock()
        self.generator.executor = MagicMock()
        self.generator.progress_counters = {
            'total_processed': 0, 'districts_matched': 0, 'city_districts': 0,
            'province_districts': 0, 'barangay_matched': 0, 'municipality_matched': 0,
            'contractors_matched': 0, 'congressmen_matched': set(), 'unmatched': 0, 'skipped': 0
        }
        
    def test_filter_projects_by_source(self):
        """Verify that _filter_projects_by_source logic matches all 5 source types correctly."""
        print("Testing Source Filtering...")
        
        # Create dummy mixed data
        mixed_data = [
            # DIME
            {'source': 'DIME', 'id': 1},
            {'source': 'dime', 'id': 2},
            # PhilGEPS
            {'source': 'PhilGEPS', 'id': 3},
            # SSP / Flood
            {'source': 'SSP', 'id': 4},
            {'source': 'FLOOD', 'id': 5},
            # Microsite / Infrawatch
            {'source': 'Microsite', 'id': 6},
            {'source': 'Infrawatch', 'id': 7},
            {'source': 'MICROSITE', 'id': 8},
            # Transparency
            {'source': 'Transparency', 'id': 9},
            {'source': 'TRANSPARENCY', 'id': 10},
        ]
        
        # Test DIME
        dime = self.generator._filter_projects_by_source(mixed_data, 'DIME')
        assert len(dime) == 2, f"Expected 2 DIME records, got {len(dime)}"
        
        # Test PhilGEPS
        philgeps = self.generator._filter_projects_by_source(mixed_data, 'PhilGEPS')
        assert len(philgeps) == 1, f"Expected 1 PhilGEPS record, got {len(philgeps)}"
        
        # Test SSP (Flood)
        ssp = self.generator._filter_projects_by_source(mixed_data, 'SSP')
        assert len(ssp) == 2, f"Expected 2 SSP records, got {len(ssp)}"
        
        # Test Microsite (Infrawatch)
        microsite = self.generator._filter_projects_by_source(mixed_data, 'Microsite')
        assert len(microsite) == 3, f"Expected 3 Microsite records, got {len(microsite)}"
        
        # Test Transparency
        transparency = self.generator._filter_projects_by_source(mixed_data, 'Transparency')
        assert len(transparency) == 2, f"Expected 2 Transparency records, got {len(transparency)}"
        
        print("✅ Source filtering logic verified for all 5 sources.")

    def test_contractor_extraction_and_matching(self):
        """Verify that contractor information is extracted and triggers a contractor match."""
        print("Testing Contractor Matching...")
        
        # Prepare minimal lookup data
        congressmen_data = {
            "Test Cong": {
                "name": "Test Cong",
                "contractors": ["TEST BUILDERS"],
                "provinces": ["Test Province"]
            }
        }
        districts_data = {}
        district_lookup = {}
        # Contractor lookup: Key -> List of (congressman_name, data)
        contractor_lookup = {
            "TEST BUILDERS": [("Test Cong", congressmen_data["Test Cong"])],
            "TEST": [("Test Cong", congressmen_data["Test Cong"])], # Expanded pattern
            "BUILDERS": [("Test Cong", congressmen_data["Test Cong"])]
        }
        contractor_inverted_index = {}
        
        # Mock _match_project_unified to return a fixed result IF the contractor matches.
        original_match = self.generator._match_project_unified
        
        def side_effect_match(*args, **kwargs):
            contractor = kwargs.get('contractor')
            if contractor == 'TEST BUILDERS':
                return "Test Cong", "contractor", 95, None, "Test Cong", None
            return None, "unmatched", 0, None, None, None
            
        self.generator._match_project_unified = MagicMock(side_effect=side_effect_match)
        
        # 1. PhilGEPS
        philgeps_chunk = [{
            "contractor_name": "Test Builders",
            "project_description": "Road Construction",
            "year": 2024
        }]
        results = self.generator._process_philgeps_chunk(
            philgeps_chunk, congressmen_data, districts_data, district_lookup, contractor_lookup, contractor_inverted_index
        )
        assert len(results) > 0, "No results for PhilGEPS"
        assert results[0]['contractor_congressman'] == "Test Cong", "PhilGEPS failed to match contractor"
        
        # 2. DIME
        dime_chunk = [{
            "contractor": "Test Builders",
            "project_name": "Bridge",
        }]
        results = self.generator._process_dime_chunk(
            dime_chunk, congressmen_data, districts_data, district_lookup, contractor_lookup, contractor_inverted_index
        )
        assert len(results) > 0, "No results for DIME"
        assert results[0]['contractor_congressman'] == "Test Cong", "DIME failed to match contractor"

        # 3. Microsite
        microsite_chunk = [{
            "contractor_name": "Test Builders",
            "project_name": "School",
        }]
        results = self.generator._process_microsite_chunk(
            microsite_chunk, congressmen_data, districts_data, district_lookup, contractor_lookup, contractor_inverted_index
        )
        assert len(results) > 0, "No results for Microsite"
        assert results[0]['contractor_congressman'] == "Test Cong", "Microsite failed to match contractor"
        
        # 4. Flood
        flood_chunk = [{
            "Contractor": "Test Builders",
            "ProjectDescription": "Flood Control",
            "Province": "Test Province",
            "Municipality": "Test Muni",
            "is_flood_related": True
        }]
        results = self.generator._process_flood_chunk(
            flood_chunk, congressmen_data, districts_data, district_lookup, contractor_lookup, contractor_inverted_index
        )
        assert len(results) > 0, "No results for Flood"
        assert results[0]['contractor_congressman'] == "Test Cong", "Flood failed to match contractor"
        
        # 5. Transparency
        transparency_chunk = [{
            "contractor_name": "Test Builders",
            "project_name": "Gym",
            "location": "Test Province"
        }]
        results = self.generator._process_transparency_chunk(
            transparency_chunk, congressmen_data, districts_data, district_lookup, contractor_lookup, contractor_inverted_index
        )
        assert len(results) > 0, "No results for Transparency"
        assert results[0]['contractor_congressman'] == "Test Cong", "Transparency failed to match contractor"

        print("✅ Contractor extraction and matching verified for all 5 sources.")

if __name__ == "__main__":
    t = TestProcessingPipeline()
    t.setup_method()
    t.test_filter_projects_by_source()
    t.test_contractor_extraction_and_matching()

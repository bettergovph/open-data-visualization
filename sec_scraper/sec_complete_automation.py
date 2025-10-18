#!/usr/bin/env python3
"""
Complete SEC Database Automation Script
Processes all unmapped contractors using SEC automation tools
"""

import json
import os
import time
import re
import subprocess
import sys
from datetime import datetime
from difflib import SequenceMatcher
from typing import List, Dict, Optional, Tuple

class SECAutomationProcessor:
    """Main class for processing all contractors through SEC database"""

    def __init__(self):
        self.project_root = "/home/joebert/open-data-visualization"
        self.mapping_file = f"{self.project_root}/static/contractor_sec_mapping.json"
        self.flood_data_file = f"{self.project_root}/static/data/flood_control_data.json"
        self.sec_database_file = f"{self.project_root}/static/sec_contractors_database.json"
        self.contractors_list = f"{self.project_root}/contractors_next25.txt"

        # Load existing data
        self.mapping_data = self.load_json(self.mapping_file)
        self.flood_data = self.load_json(self.flood_data_file)
        self.sec_database = self.load_json(self.sec_database_file)

        # Processing stats
        self.stats = {
            "total_contractors": 0,
            "already_mapped": 0,
            "processed": 0,
            "exact_matches": 0,
            "fuzzy_matches": 0,
            "jv_handled": 0,
            "not_found": 0,
            "errors": 0
        }

    def load_json(self, filepath: str) -> Dict:
        """Load JSON file with error handling"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Error loading {filepath}: {e}")
            return {}

    def save_json(self, filepath: str, data: Dict) -> bool:
        """Save JSON file with error handling"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"❌ Error saving {filepath}: {e}")
            return False

    def normalize_contractor_name(self, name: str) -> str:
        """Normalize contractor name for better matching"""
        if not name:
            return ""

        # Remove common suffixes and prefixes
        name = re.sub(r'\s*(INC|CORP|CORPORATION|LTD|LLC|JV|JOINT VENTURE)\s*$', '', name, flags=re.IGNORECASE)
        name = re.sub(r'^\s*(THE)\s+', '', name, flags=re.IGNORECASE)

        # Normalize spaces and case
        name = re.sub(r'\s+', ' ', name.strip().upper())

        # Remove special characters but keep letters, numbers, and spaces
        name = re.sub(r'[^A-Z0-9\s]', '', name)

        return name

    def extract_contractor_names(self) -> List[str]:
        """Extract all unique contractor names from various sources"""
        contractors = set()

        # From mapping file (unmapped ones)
        if 'mapping' in self.mapping_data:
            for contractor in self.mapping_data['mapping']:
                if self.mapping_data['mapping'][contractor] in [None, "", "NOT_FOUND_IN_SEC"]:
                    contractors.add(contractor)

        # From flood control data
        if 'projects' in self.flood_data:
            for project in self.flood_data['projects']:
                contractor = project.get('Contractor', '').strip()
                if contractor:
                    contractors.add(contractor)

        # From contractors list file
        if os.path.exists(self.contractors_list):
            with open(self.contractors_list, 'r', encoding='utf-8') as f:
                for line in f:
                    contractor = line.strip()
                    if contractor and not contractor.startswith('#'):
                        contractors.add(contractor)

        return sorted(list(contractors))

    def find_exact_match(self, contractor_name: str) -> Optional[Dict]:
        """Find exact match in SEC database"""
        normalized_input = self.normalize_contractor_name(contractor_name)

        for entry in self.sec_database.get('contractors', []):
            sec_name = entry.get('company_name', '').strip()
            original_name = entry.get('original_contractor_name', '').strip()

            # Check both normalized forms
            if (self.normalize_contractor_name(sec_name) == normalized_input or
                self.normalize_contractor_name(original_name) == normalized_input):
                return entry

        return None

    def find_fuzzy_match(self, contractor_name: str, threshold: float = 0.8) -> List[Dict]:
        """Find fuzzy matches in SEC database"""
        normalized_input = self.normalize_contractor_name(contractor_name)
        matches = []

        for entry in self.sec_database.get('contractors', []):
            sec_name = entry.get('company_name', '').strip()
            original_name = entry.get('original_contractor_name', '').strip()

            # Calculate similarity for both names
            for name in [sec_name, original_name]:
                if name:
                    normalized_sec = self.normalize_contractor_name(name)
                    similarity = SequenceMatcher(None, normalized_input, normalized_sec).ratio()

                    if similarity >= threshold:
                        matches.append({
                            'entry': entry,
                            'matched_name': name,
                            'similarity': similarity
                        })

        # Sort by similarity (highest first)
        matches.sort(key=lambda x: x['similarity'], reverse=True)
        return matches

    def handle_jv_contractors(self, contractor_name: str) -> List[str]:
        """Handle Joint Venture contractors - split into individual companies"""
        # Look for JV patterns like " / ", " JV ", "JOINT VENTURE", etc.
        jv_patterns = [
            r'\s*/\s*',  # "COMPANY A / COMPANY B"
            r'\s*&\s*',  # "COMPANY A & COMPANY B"
            r'\s*JV\s*',  # "COMPANY A JV COMPANY B"
            r'\s*JOINT VENTURE\s*',  # "COMPANY A JOINT VENTURE COMPANY B"
        ]

        individual_contractors = [contractor_name]

        for pattern in jv_patterns:
            if re.search(pattern, contractor_name, re.IGNORECASE):
                parts = re.split(pattern, contractor_name, flags=re.IGNORECASE)
                individual_contractors = [part.strip() for part in parts if part.strip()]
                break

        return individual_contractors

    def run_sec_search(self, contractor_name: str) -> Optional[Dict]:
        """Run SEC search automation for a contractor"""
        print(f"🔍 Searching SEC database for: {contractor_name}")

        # Try exact match first
        exact_match = self.find_exact_match(contractor_name)
        if exact_match:
            print(f"✅ Exact match found: {exact_match.get('company_name', 'Unknown')}")
            self.stats["exact_matches"] += 1
            return exact_match

        # Try fuzzy matching
        fuzzy_matches = self.find_fuzzy_match(contractor_name)
        if fuzzy_matches:
            best_match = fuzzy_matches[0]
            print(f"🎯 Fuzzy match found: {best_match['matched_name']} (similarity: {best_match['similarity']:.2f})")
            self.stats["fuzzy_matches"] += 1
            return best_match['entry']

        print("❌ No match found in SEC database")
        self.stats["not_found"] += 1
        return None

    def update_mapping(self, contractor_name: str, sec_match: Optional[Dict]) -> bool:
        """Update the mapping file with new contractor data"""
        if not self.mapping_data.get('mapping'):
            self.mapping_data['mapping'] = {}

        if sec_match:
            # Use the company_name from SEC database as the mapping target
            sec_company_name = sec_match.get('company_name', '').strip()
            if not sec_company_name:
                sec_company_name = sec_match.get('original_contractor_name', '').strip()

            self.mapping_data['mapping'][contractor_name] = sec_company_name
            print(f"📝 Updated mapping: {contractor_name} -> {sec_company_name}")
        else:
            self.mapping_data['mapping'][contractor_name] = "NOT_FOUND_IN_SEC"
            print(f"📝 Marked as not found: {contractor_name}")

        # Update metadata
        self.mapping_data['last_updated'] = datetime.now().isoformat()
        self.mapping_data['notes'] = f"Automated processing - {self.stats['processed']} contractors processed"

        return self.save_json(self.mapping_file, self.mapping_data)

    def process_single_contractor(self, contractor_name: str) -> bool:
        """Process a single contractor through the SEC automation"""
        print(f"\n{'='*60}")
        print(f"🔄 Processing contractor: {contractor_name}")
        print(f"{'='*60}")

        # Skip if already mapped
        if contractor_name in self.mapping_data.get('mapping', {}):
            current_mapping = self.mapping_data['mapping'][contractor_name]
            if current_mapping not in [None, "", "NOT_FOUND_IN_SEC"]:
                print(f"⏭️ Already mapped: {contractor_name} -> {current_mapping}")
                self.stats["already_mapped"] += 1
                return True

        # Handle JV cases
        if '/' in contractor_name or '&' in contractor_name or 'JV' in contractor_name.upper():
            jv_contractors = self.handle_jv_contractors(contractor_name)
            if len(jv_contractors) > 1:
                print(f"🔄 JV detected, processing {len(jv_contractors)} individual contractors")
                self.stats["jv_handled"] += 1

                # Process each JV partner separately
                all_successful = True
                for jv_contractor in jv_contractors:
                    sec_match = self.run_sec_search(jv_contractor)
                    if not self.update_mapping(jv_contractor, sec_match):
                        all_successful = False

                return all_successful

        # Process single contractor
        sec_match = self.run_sec_search(contractor_name)
        success = self.update_mapping(contractor_name, sec_match)

        if success:
            self.stats["processed"] += 1

        return success

    def run_complete_automation(self) -> bool:
        """Run the complete automation for all unmapped contractors"""
        print("🚀 Starting Complete SEC Database Automation")
        print("=" * 60)

        # Get all contractors to process
        all_contractors = self.extract_contractor_names()
        self.stats["total_contractors"] = len(all_contractors)

        print(f"📊 Found {len(all_contractors)} contractors to process")

        # Filter to unmapped contractors only
        unmapped_contractors = []
        for contractor in all_contractors:
            current_mapping = self.mapping_data.get('mapping', {}).get(contractor, "")
            if current_mapping in [None, "", "NOT_FOUND_IN_SEC"]:
                unmapped_contractors.append(contractor)

        print(f"📋 {len(unmapped_contractors)} contractors need SEC mapping")

        # Process each contractor
        success_count = 0
        for i, contractor in enumerate(unmapped_contractors, 1):
            print(f"\n🔢 Processing {i}/{len(unmapped_contractors)}: {contractor}")

            try:
                if self.process_single_contractor(contractor):
                    success_count += 1
                else:
                    self.stats["errors"] += 1
            except Exception as e:
                print(f"❌ Error processing {contractor}: {e}")
                self.stats["errors"] += 1

            # Brief pause between contractors
            time.sleep(1)

        # Final statistics
        print(f"\n{'='*60}")
        print("📊 FINAL STATISTICS")
        print(f"{'='*60}")
        print(f"Total contractors: {self.stats['total_contractors']}")
        print(f"Already mapped: {self.stats['already_mapped']}")
        print(f"Successfully processed: {self.stats['processed']}")
        print(f"Exact matches: {self.stats['exact_matches']}")
        print(f"Fuzzy matches: {self.stats['fuzzy_matches']}")
        print(f"JV cases handled: {self.stats['jv_handled']}")
        print(f"Not found: {self.stats['not_found']}")
        print(f"Errors: {self.stats['errors']}")

        success_rate = (success_count / len(unmapped_contractors)) * 100 if unmapped_contractors else 0
        print(f"Success rate: {success_rate:.1f}%")

        return self.stats["errors"] == 0

def main():
    """Main function"""
    processor = SECAutomationProcessor()

    print("🎯 SEC Complete Automation Script")
    print("Processes all unmapped contractors using SEC database")
    print("=" * 60)

    success = processor.run_complete_automation()

    if success:
        print("\n✅ Automation completed successfully!")
        print("📁 Check updated contractor_sec_mapping.json")
    else:
        print("\n⚠️ Automation completed with some errors")
        print("🔍 Review the error logs above")

    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())

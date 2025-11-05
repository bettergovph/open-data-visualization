#!/usr/bin/env python3
"""
Process raw NEP JSON files to extract program data with actual amounts.
This script reads the original NEP ZIP files and extracts program-level data.
"""

import json
import zipfile
import os
from pathlib import Path
from typing import Dict, List, Any
import re

class RawNEPProgramProcessor:
    """Process raw NEP data to extract program information"""
    
    def __init__(self, data_dir: str = "~/open-budget-data/scripts/nep-gaa/backup"):
        self.data_dir = Path(data_dir).expanduser()
        self.programs = [
            "Convergence and Special Support Program",
            "Local Program", 
            "Asset Preservation Program",
            "Flood Management Program",
            "General Administration and Support",
            "Bridge Program",
            "Network Development Program",
            "Support to Operations"
        ]
    
    def extract_nep_data(self, year: int) -> List[Dict]:
        """Extract data from NEP ZIP file for a given year"""
        zip_path = self.data_dir / f"NEP-{year}.zip"
        
        if not zip_path.exists():
            print(f"⚠️ NEP-{year}.zip not found")
            return []
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_file:
                # Extract the JSON file
                json_filename = f"NEP-{year}.json"
                with zip_file.open(json_filename) as json_file:
                    data = json.load(json_file)
                    print(f"✅ Loaded {len(data)} records from NEP-{year}.json")
                    return data
        except Exception as e:
            print(f"❌ Error extracting NEP-{year}: {e}")
            return []
    
    def find_program_entries(self, data: List[Dict], program_name: str) -> List[Dict]:
        """Find all entries related to a program"""
        entries = []
        program_lower = program_name.lower()
        
        # Create flexible search patterns for each program
        search_patterns = self.get_search_patterns(program_name)
        
        for record in data:
            dsc = record.get('DSC', '').lower()
            amt_str = record.get('AMT', '')
            
            # Skip empty amounts
            if not amt_str or amt_str.strip() == '':
                continue
            
            # Try to convert amount to float
            try:
                amount = float(amt_str)
                if amount <= 0:
                    continue
            except (ValueError, TypeError):
                continue
            
            # Check if this entry matches any of the search patterns
            for pattern in search_patterns:
                if pattern in dsc:
                    entries.append({
                        'description': record.get('DSC', ''),
                        'amount': amount,
                        'department': record.get('UACS_DPT_DSC', ''),
                        'agency': record.get('UACS_AGY_DSC', ''),
                        'expense_category': record.get('UACS_EXP_DSC', ''),
                        'object_code': record.get('UACS_SOBJ_DSC', ''),
                        'prexc_id': record.get('PREXC_FPAP_ID', ''),
                        'prexc_level': record.get('PREXC_LEVEL', '')
                    })
                    break  # Avoid duplicate entries
        
        return entries
    
    def get_search_patterns(self, program_name: str) -> List[str]:
        """Get flexible search patterns for program matching"""
        patterns = []
        program_lower = program_name.lower()
        
        # Add the exact program name
        patterns.append(program_lower)
        
        # Add variations based on program type
        if "convergence" in program_lower:
            patterns.extend(["convergence", "special support", "cssp"])
        
        elif "local program" in program_lower:
            patterns.extend(["local program", "local development"])
        
        elif "asset preservation" in program_lower:
            patterns.extend(["asset preservation", "preservation", "maintenance"])
        
        elif "flood management" in program_lower:
            patterns.extend(["flood management", "flood control", "flood mitigation"])
        
        elif "general administration" in program_lower:
            patterns.extend(["general administration", "administration", "management", "supervision"])
        
        elif "bridge program" in program_lower:
            patterns.extend(["bridge program", "bridge", "bridges"])
        
        elif "network development" in program_lower:
            patterns.extend(["network development", "road network", "infrastructure"])
        
        elif "support to operations" in program_lower:
            patterns.extend(["support to operations", "operations support", "operational support"])
        
        return patterns
    
    def process_year(self, year: int) -> Dict[str, Any]:
        """Process a single year of NEP data"""
        print(f"📊 Processing NEP-{year}...")
        
        data = self.extract_nep_data(year)
        if not data:
            return {}
        
        year_results = {}
        
        for program in self.programs:
            entries = self.find_program_entries(data, program)
            
            if entries:
                total_amount = sum(entry['amount'] for entry in entries)
                year_results[program] = {
                    'total_amount': total_amount,
                    'entry_count': len(entries),
                    'entries': entries[:10]  # Keep first 10 entries for details
                }
                print(f"  ✅ {program}: ₱{total_amount:,.0f} ({len(entries)} entries)")
            else:
                year_results[program] = {
                    'total_amount': 0,
                    'entry_count': 0,
                    'entries': []
                }
                print(f"  ⚠️ {program}: No entries found")
        
        return year_results
    
    def process_all_years(self, years: List[int] = None) -> Dict[str, Any]:
        """Process all available years"""
        if years is None:
            years = [2020, 2021, 2022, 2023, 2024, 2025, 2026]
        
        all_results = {}
        
        for year in years:
            year_data = self.process_year(year)
            if year_data:
                all_results[str(year)] = year_data
        
        return all_results

def main():
    """Main function to test the processor"""
    processor = RawNEPProgramProcessor()
    
    # Test with 2025 data
    print("🧪 Testing with NEP-2025...")
    results = processor.process_year(2025)
    
    # Print summary
    print("\n📋 Summary for 2025:")
    for program, data in results.items():
        if data['total_amount'] > 0:
            print(f"  {program}: ₱{data['total_amount']:,.0f} ({data['entry_count']} entries)")
    
    # Save results to JSON
    output_file = "nep_programs_raw_2025.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Results saved to {output_file}")

if __name__ == "__main__":
    main()

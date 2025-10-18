#!/usr/bin/env python3
"""
Find empty SEC result files that need to be re-scraped
"""

import os
import glob

def find_empty_files():
    """Find all empty txt files in sec_results"""
    sec_results_dir = 'sec_scraper/sec_results'
    
    if not os.path.exists(sec_results_dir):
        print(f"❌ Directory not found: {sec_results_dir}")
        return []
    
    # Find all txt files
    all_files = glob.glob(f'{sec_results_dir}/*.txt')
    
    print(f"📊 Found {len(all_files)} total SEC result files")
    
    # Find empty files (size <= 1 byte)
    empty_files = []
    for file_path in all_files:
        if os.path.getsize(file_path) <= 1:
            contractor_name = os.path.basename(file_path).replace('.txt', '').replace('_', ' ')
            empty_files.append(contractor_name)
    
    return empty_files


def main():
    print("🔍 Finding empty SEC result files...")
    print()
    
    empty_files = find_empty_files()
    
    if empty_files:
        print(f"\n⚠️  Found {len(empty_files)} empty SEC result files that need re-scraping:\n")
        for contractor in sorted(empty_files):
            print(f"   - {contractor}")
        
        print(f"\n📝 Generating contractor list for AHK...")
        
        # Write to file for AHK
        with open('sec_scraper/contractors_to_rescrape.txt', 'w') as f:
            f.write('contractors := [\n')
            for i, contractor in enumerate(sorted(empty_files)):
                f.write(f'    "{contractor}"')
                if i < len(empty_files) - 1:
                    f.write(',\n')
                else:
                    f.write('\n')
            f.write(']\n')
        
        print(f"✅ Written to sec_scraper/contractors_to_rescrape.txt")
        print(f"   You can use this list with the AHK script")
    else:
        print("✅ No empty SEC result files found - all scraped successfully!")
    
    print()


if __name__ == "__main__":
    main()


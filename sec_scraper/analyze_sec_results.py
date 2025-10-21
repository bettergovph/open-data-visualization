#!/usr/bin/env python3
"""
Analyze SEC result files to distinguish between:
1. Empty files (AHK script failure)
2. No results found (valid search, no companies)
3. Successful searches with results
"""

import os
import re
import glob

def analyze_sec_results():
    results_dir = 'sec_scraper/sec_results'
    all_files = glob.glob(f'{results_dir}/*.txt')
    
    empty_files = []
    no_results = []
    successful = []
    malformed = []
    
    for file_path in all_files:
        filename = os.path.basename(file_path)
        
        # Check if file is empty
        if os.path.getsize(file_path) == 0:
            empty_files.append(filename)
            continue
        
        # Read file content
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            malformed.append((filename, str(e)))
            continue
        
        # Check for results count
        match = re.search(r'Result/s Found:\s*(\d+|--)', content)
        
        if not match:
            # File doesn't have SEC results format
            malformed.append((filename, "No 'Result/s Found' marker"))
            continue
        
        result_count = match.group(1)
        
        if result_count == '--':
            no_results.append(filename)
        else:
            successful.append((filename, int(result_count)))
    
    # Print summary
    print("📊 SEC Results Analysis")
    print("=" * 60)
    print(f"\n📁 Total files: {len(all_files):,}")
    print(f"\n✅ Successful searches: {len(successful):,} ({len(successful)/len(all_files)*100:.1f}%)")
    print(f"❌ No results found: {len(no_results):,} ({len(no_results)/len(all_files)*100:.1f}%)")
    print(f"🚫 Empty files (AHK failure): {len(empty_files):,} ({len(empty_files)/len(all_files)*100:.1f}%)")
    print(f"⚠️  Malformed files: {len(malformed):,} ({len(malformed)/len(all_files)*100:.1f}%)")
    
    # Show sample empty files
    if empty_files:
        print(f"\n🚫 Sample empty files (first 10):")
        for f in empty_files[:10]:
            contractor_name = f.replace('.txt', '').replace('_', ' ')
            print(f"   • {contractor_name}")
    
    # Show sample no results
    if no_results:
        print(f"\n❌ Sample 'no results found' (first 10):")
        for f in no_results[:10]:
            contractor_name = f.replace('.txt', '').replace('_', ' ')
            print(f"   • {contractor_name}")
    
    # Show malformed files
    if malformed:
        print(f"\n⚠️  Malformed files (first 10):")
        for f, reason in malformed[:10]:
            contractor_name = f.replace('.txt', '').replace('_', ' ')
            print(f"   • {contractor_name}: {reason}")
    
    # Statistics on successful searches
    if successful:
        total_companies = sum(count for _, count in successful)
        avg_results = total_companies / len(successful)
        print(f"\n📈 Successful search statistics:")
        print(f"   • Total companies found: {total_companies:,}")
        print(f"   • Average results per search: {avg_results:.1f}")
        
        # Show searches with max results (10 = hit limit)
        max_results = [f for f, count in successful if count == 10]
        print(f"   • Searches that hit 10-result limit: {len(max_results)} ({len(max_results)/len(successful)*100:.1f}%)")
    
    # Create lists for potential retry
    if empty_files or malformed:
        print(f"\n📝 Contractors needing retry:")
        print(f"   Total to retry: {len(empty_files) + len(malformed)}")
        
        # Save to file
        with open('sec_scraper/contractors_to_retry.txt', 'w') as f:
            for filename in empty_files:
                contractor_name = filename.replace('.txt', '').replace('_', ' ')
                f.write(f"{contractor_name}\n")
            for filename, _ in malformed:
                contractor_name = filename.replace('.txt', '').replace('_', ' ')
                f.write(f"{contractor_name}\n")
        
        print(f"   ✅ Saved to: sec_scraper/contractors_to_retry.txt")

if __name__ == "__main__":
    analyze_sec_results()


